#!/usr/bin/env python3
"""
修复已取消比赛：从titan007抓真实比分，有比分的改回已完赛并重新结算

规则：不管体彩是否取消，只要赛程抓回来就必须做预测及结算

用法:
  python3 fix_cancelled_matches.py              # 执行修复
  python3 fix_cancelled_matches.py --dry-run    # 仅查看不执行
"""

import os
import sys
import json
import re
import psycopg2
from datetime import datetime

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
        half_full_hit = NULL,
        win_loss = NULL,
        handicap_result = NULL
    WHERE match_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (match_id,))
        return cur.rowcount

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
    
    # 按日期分组，减少titan007查询次数
    by_date = {}
    no_date = []
    
    for row in matches:
        match_id, sport_type, home_team, away_team, status, metadata = row
        md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
        
        # 从metadata或ID推导日期
        mt = md.get("match_time", "")
        date_str = None
        if mt and " " in mt:
            date_str = mt.split(" ")[0]
        if not date_str:
            date_str = _derive_date_from_id(match_id)
        
        if date_str:
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append({
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
    
    print(f"📅 有日期的: {sum(len(v) for v in by_date.values())} 场, {len(by_date)} 个日期")
    if no_date:
        print(f"⚠️ 无日期的: {len(no_date)} 场")
    
    # 按日期查询titan007
    recovered = 0
    not_found = 0
    total_predictions_reset = 0
    
    for date_str, date_matches in sorted(by_date.items()):
        sport_types = set(m["sport_type"] for m in date_matches)
        
        for sport in sport_types:
            matches_of_sport = [m for m in date_matches if m["sport_type"] == sport]
            if not matches_of_sport:
                continue
            
            # 查询titan007
            parts = date_str.split("-")
            titan_date = f"{parts[0]}-{int(parts[1])}-{int(parts[2])}"
            
            print(f"\n📡 查询 titan007 {sport} {titan_date} ({len(matches_of_sport)}场)...")
            titan_matches = fetch_scores(sport, titan_date)
            
            if not titan_matches:
                print(f"  ⚠️ titan007 无数据")
                not_found += len(matches_of_sport)
                continue
            
            print(f"  titan007 返回 {len(titan_matches)} 场")
            
            for m in matches_of_sport:
                found = find_match_in_titan_data(m["home_team"], m["away_team"], titan_matches)
                
                if found and found["home_score"] is not None and found["away_score"] is not None:
                    print(f"  ✅ {m['id']}: {m['home_team']} {found['home_score']}-{found['away_score']} {m['away_team']}")
                    
                    if not dry_run:
                        # 更新比赛状态为已完赛
                        md = m["metadata"]
                        md["home_score"] = found["home_score"]
                        md["away_score"] = found["away_score"]
                        md["status"] = "已完赛"
                        if found.get("home_half") is not None:
                            md["half_home_score"] = found["home_half"]
                        if found.get("away_half") is not None:
                            md["half_away_score"] = found["away_half"]
                        # 清除取消标记
                        md.pop("cancel_reason", None)
                        md.pop("stopped_at", None)
                        
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE matches 
                                SET status = '已完赛', 
                                    metadata = %s::jsonb
                                WHERE id = %s
                            """, [json.dumps(md, ensure_ascii=False), m["id"]])
                        
                        # 重置预测记录的结算状态
                        pred_count = reset_predictions_for_match(conn, m["id"])
                        total_predictions_reset += pred_count
                        conn.commit()
                    
                    recovered += 1
                else:
                    print(f"  ❌ {m['id']}: {m['home_team']} vs {m['away_team']} - titan007未匹配")
                    not_found += 1
    
    # 处理无日期的比赛
    if no_date:
        print(f"\n⚠️ {len(no_date)} 场无日期的比赛无法处理:")
        for m in no_date:
            print(f"  - {m['id']}: {m['home_team']} vs {m['away_team']}")
    
    print(f"\n{'='*50}")
    print(f"📊 修复结果:")
    print(f"  ✅ 恢复已完赛: {recovered} 场")
    print(f"  ❌ 无法恢复: {not_found} 场")
    if not dry_run:
        print(f"  🔄 重置预测结算: {total_predictions_reset} 条")
        print(f"\n💡 现在运行 auto_settle.py 即可重新结算恢复的比赛")
    else:
        print(f"  (DRY RUN 模式，未实际修改)")
    
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
