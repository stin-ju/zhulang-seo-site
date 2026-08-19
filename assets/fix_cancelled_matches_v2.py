#!/usr/bin/env python3
"""
修复已取消比赛 v2：从titan007抓真实比分，支持时区日期偏移

核心修复：体彩日期和titan007日期可能差1天（时区差异），查前后各1天
规则：不管体彩是否取消，只要赛程抓回来就必须做预测及结算

用法:
  python3 fix_cancelled_matches_v2.py              # 执行修复
  python3 fix_cancelled_matches_v2.py --dry-run    # 仅查看不执行
"""

import os
import sys
import json
import re
import psycopg2
from datetime import datetime, timedelta

try:
    from titan007_client import fetch_scores, find_match_in_titan_data
    HAS_TITAN007 = True
except ImportError:
    HAS_TITAN007 = False
    print("⚠️ titan007_client 不可用，无法获取比分数据")

DB_URL = os.environ.get('DB_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

def get_db():
    return psycopg2.connect(DB_URL)

def _derive_date_from_id(match_id):
    """从 match ID 推导日期"""
    m = re.match(r'(\d{4})(\d{2})(\d{2})_', match_id)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None

def get_cancelled_matches(conn):
    """获取所有已取消的比赛"""
    sql = """
    SELECT m.id, m.sport_type, m.home_team, m.away_team, m.status, m.metadata
    FROM matches m
    WHERE m.status = '已取消'
    ORDER BY m.id
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()

def reset_predictions_for_match(conn, match_id):
    """重置一场比赛的所有预测记录，让auto_settle重新结算"""
    sql = """
    UPDATE predictions 
    SET is_settled = false, 
        hit_status = NULL,
        spf_hit = NULL,
        handicap_spf_hit = NULL,
        goals_hit = NULL,
        score_hit = NULL,
        half_full_hit = NULL
    WHERE match_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (match_id,))
        return cur.rowcount

def fetch_scores_with_offset(sport, date_str, offset_days=0):
    """带日期偏移的titan007查询"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    target = dt + timedelta(days=offset_days)
    titan_date = f"{target.year}-{target.month}-{target.day}"
    return fetch_scores(sport, titan_date)

def find_match_across_dates(db_home, db_away, sport, date_str):
    """
    在前后各1天的范围内查找比赛（解决时区日期错位问题）
    返回 (match_data, offset_used) 或 (None, 0)
    """
    for offset in [0, -1, 1, -2, 2]:
        try:
            matches = fetch_scores_with_offset(sport, date_str, offset)
            if not matches:
                continue
            result = find_match_in_titan_data(db_home, db_away, matches)
            if result:
                return result, offset
        except Exception as e:
            print(f"  ⚠️ 查询偏移{offset:+d}天失败: {e}")
            continue
    return None, 0

def main():
    dry_run = '--dry-run' in sys.argv
    
    if not HAS_TITAN007:
        print("❌ 需要 titan007_client 才能执行")
        return 1
    
    conn = get_db()
    matches = get_cancelled_matches(conn)
    
    print(f"🔍 找到 {len(matches)} 场已取消的比赛")
    if dry_run:
        print("📋 DRY RUN 模式，不会实际修改\n")
    
    # 按日期和运动类型分组
    by_date_sport = {}
    no_date = []
    
    for row in matches:
        match_id, sport_type, home_team, away_team, status, metadata = row
        md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
        
        mt = md.get("match_time", "")
        date_str = None
        if mt and " " in mt:
            date_str = mt.split(" ")[0]
        if not date_str:
            date_str = _derive_date_from_id(match_id)
        
        if date_str:
            key = (date_str, sport_type)
            if key not in by_date_sport:
                by_date_sport[key] = []
            by_date_sport[key].append({
                "id": match_id,
                "sport_type": sport_type,
                "home_team": home_team,
                "away_team": away_team,
                "metadata": md,
                "date": date_str
            })
        else:
            no_date.append({
                "id": match_id,
                "sport_type": sport_type,
                "home_team": home_team,
                "away_team": away_team,
                "metadata": md
            })
    
    total_matches = sum(len(v) for v in by_date_sport.values())
    print(f"📅 有日期的: {total_matches} 场, {len(by_date_sport)} 个日期+运动组合")
    if no_date:
        print(f"⚠️ 无日期的: {len(no_date)} 场")
    
    recovered = 0
    not_found = 0
    total_predictions_reset = 0
    offset_stats = {}
    
    for (date_str, sport), date_matches in sorted(by_date_sport.items()):
        print(f"\n📡 查询 {sport} {date_str} ({len(date_matches)}场)...")
        
        for m in date_matches:
            result, offset = find_match_across_dates(
                m["home_team"], m["away_team"], sport, date_str
            )
            
            if result and result["home_score"] is not None and result["away_score"] is not None:
                offset_key = f"{offset:+d}天"
                offset_stats[offset_key] = offset_stats.get(offset_key, 0) + 1
                
                offset_tag = f" [偏移{offset:+d}天]" if offset != 0 else ""
                print(f"  ✅ {m['id']}: {m['home_team']} {result['home_score']}-{result['away_score']} {m['away_team']}{offset_tag}")
                
                if not dry_run:
                    md = m["metadata"]
                    md["home_score"] = result["home_score"]
                    md["away_score"] = result["away_score"]
                    md["status"] = "已完赛"
                    if result.get("home_half") is not None:
                        md["half_home_score"] = result["home_half"]
                    if result.get("away_half") is not None:
                        md["half_away_score"] = result["away_half"]
                    md.pop("cancel_reason", None)
                    md.pop("stopped_at", None)
                    
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE matches 
                            SET status = '已完赛', 
                                metadata = %s::jsonb
                            WHERE id = %s
                        """, [json.dumps(md, ensure_ascii=False), m["id"]])
                    
                    pred_count = reset_predictions_for_match(conn, m["id"])
                    total_predictions_reset += pred_count
                    conn.commit()
                
                recovered += 1
            else:
                print(f"  ❌ {m['id']}: {m['home_team']} vs {m['away_team']} - 所有日期偏移均未匹配")
                not_found += 1
    
    if no_date:
        print(f"\n⚠️ {len(no_date)} 场无日期的比赛无法处理:")
        for m in no_date:
            print(f"  - {m['id']}: {m['home_team']} vs {m['away_team']}")
    
    print(f"\n{'='*50}")
    print(f"📊 修复结果:")
    print(f"  ✅ 恢复已完赛: {recovered} 场")
    print(f"  ❌ 无法恢复: {not_found} 场")
    if offset_stats:
        print(f"  📅 日期偏移统计: {offset_stats}")
    if not dry_run:
        print(f"  🔄 重置预测结算: {total_predictions_reset} 条")
        print(f"\n💡 现在运行 auto_settle.py 即可重新结算恢复的比赛")
    else:
        print(f"  (DRY RUN 模式，未实际修改)")
    
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
