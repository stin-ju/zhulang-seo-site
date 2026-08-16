#!/usr/bin/env python3
"""
ct_auto_settle.py - CT彩（传统足彩）自动结算脚本 v2

功能:
  1. 从 traditional_predictions 表查询未结算的预测记录
  2. 优先从 matches 表读取竞彩已有的比分数据（通过球队名匹配）
  3. 不足时再从 titan007 补抓比分
  4. 根据比分判断实际结果，对比 AI 预测，计算命中情况
  5. 更新结算状态

v2 改动:
  - 优先从 matches 表读竞彩已有比分，减少外部请求
  - 修复 scores_map key 冲突（按 ct_id 而非 match_num 索引）
  - 每条记录独立查找比分，避免不同期号互相覆盖

用法:
  python3 ct_auto_settle.py              # 结算所有未结算记录
  python3 ct_auto_settle.py --issue 26098  # 结算指定期号
  python3 ct_auto_settle.py --dry-run     # 试运行，不更新数据库
"""

import os
import sys
import re
import json
import argparse
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta

# ============ 配置 ============
DB_URL = os.environ.get('DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 竞彩简称 ↔ CT彩全名 别名映射
ALIASES = {
    '飞马': ['飞翼', '达拉斯飞翼'],
    '康太阳': ['康涅狄克太阳', '康乃狄克太阳'],
    '迈国际': ['国际迈阿密', '迈阿密国际'],
    '圣路易城': ['圣路易斯城'],
    '洛城银河': ['洛杉矶银河'],
    '坦山猫': ['坦佩雷山猫'],
    '赫尔火花': ['赫尔辛基火花'],
    '布鲁马波': ['布鲁马波卡纳'],
    '腓特烈': ['腓特烈斯塔'],
    '瓦萨': ['VPS瓦萨'],
    '国际图尔': ['英特土尔库', '国际图尔库'],
    '巴竞技': ['巴拉纳竞技'],
    '斯达': ['斯塔贝克', 'Start'],
    '维京': ['Viking', '维京FK'],
    '库奥皮奥': ['KuPS', '库普斯'],
    '弗鲁米嫩塞': ['Fluminense', '富明尼斯'],
    '桑托斯': ['Santos', '桑托斯FC'],
    '辛辛那提': ['FC Cincinnati', '辛辛那提'],
    '圣何塞地震': ['San Jose Earthquakes', '圣何塞'],
    '华盛顿联': ['DC United', '华盛顿联队', '华盛顿'],
    '纳什维尔': ['Nashville SC', '纳什维尔SC'],
    '迈阿密国际': ['Inter Miami', '国际迈阿密'],
    '哥伦布机员': ['Columbus Crew', '哥伦布'],
    '蒙特利尔': ['Montreal Impact', '蒙特利尔冲击'],
    '新英格兰革命': ['New England Revolution', '新英格兰'],
    '温哥华白帽': ['Vancouver Whitecaps', '温哥华'],
    '洛杉矶FC': ['LAFC', '洛杉矶FC'],
    '芝加哥火焰': ['Chicago Fire', '芝加哥'],
    '夏洛特FC': ['Charlotte FC', '夏洛特'],
    '圣路易斯城': ['St. Louis City', '圣路易斯城SC'],
    '皇家盐湖城': ['Real Salt Lake', '皇家盐湖城'],
    '布兰': ['Brann', '布兰足球俱乐部'],
    '罗森博格': ['Rosenborg', '罗森博格BK'],
    '塞伊奈约基': ['SJK', '塞伊奈约基PK'],
    '赫尔辛基': ['HJK Helsinki', 'HJK', '赫尔辛基HJK'],
    '米拉索尔': ['Mirassol', '米拉索尔FC'],
    '格雷米奥': ['Gremio', '格雷米奥FBPA'],
    '索尔纳': ['AIK索尔纳'],
    '哥德堡': ['IFK哥德堡'],
    '奥斯KFUM': ['奥斯陆KFUM'],
    '萨普斯堡': ['萨尔普斯堡'],
}

# ============ 工具函数 ============

def _safe_int(val, default=0):
    if val is None or val == "" or val == "null":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _name_match(name_a, name_b):
    """判断两个球队名是否匹配（模糊匹配）。name_b 可以是字符串或列表。"""
    if not name_a:
        return False
    if isinstance(name_b, (list, tuple)):
        return any(_name_match(name_a, nb) for nb in name_b if nb)
    if not name_b:
        return False
    a = name_a.strip()
    b = name_b.strip()
    if a == b:
        return True
    if a in b or b in a:
        return True
    for alias_key, alias_list in ALIASES.items():
        if a == alias_key or a in alias_list:
            if b == alias_key or b in alias_list:
                return True
    shorter = a if len(a) <= len(b) else b
    longer = b if len(a) <= len(b) else a
    if len(shorter) >= 3:
        for i in range(len(shorter) - 2):
            if shorter[i:i+3] in longer:
                return True
    return False

def get_db():
    return psycopg2.connect(DB_URL)

# ============ 比分查找（三级查找） ============

def load_jc_scores(conn):
    """预加载所有竞彩已完赛有比分的比赛到内存"""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, home_team, away_team,
               (metadata->>'home_score')::int as home_score,
               (metadata->>'away_score')::int as away_score,
               metadata->>'half_home_score' as half_home,
               metadata->>'half_away_score' as half_away,
               metadata->>'match_date' as match_date
        FROM matches
        WHERE id NOT LIKE 'CT%%'
          AND status = '已完赛'
          AND metadata->>'home_score' IS NOT NULL
          AND metadata->>'away_score' IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"[预加载] 竞彩已有比分比赛: {len(rows)} 场", file=sys.stderr)
    return rows

def load_ct_scores(conn):
    """预加载CT彩已完赛有比分的比赛到内存，按 ct_id 索引"""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, home_team, away_team,
               (metadata->>'home_score')::int as home_score,
               (metadata->>'away_score')::int as away_score,
               metadata->>'half_home_score' as half_home,
               metadata->>'half_away_score' as half_away,
               metadata->>'match_date' as match_date
        FROM matches
        WHERE id LIKE 'CT%%'
          AND status = '已完赛'
          AND metadata->>'home_score' IS NOT NULL
          AND metadata->>'away_score' IS NOT NULL
    """)
    rows = cur.fetchall()
    ct_by_id = {}
    for r in rows:
        ct_by_id[r['id']] = r
    print(f"[预加载] CT彩已有比分比赛: {len(rows)} 场", file=sys.stderr)
    return ct_by_id

def find_score_in_rows(home, away, date_str, rows):
    """在预加载的比赛数据中查找比分。返回 score dict 或 None。"""
    if not home or not away:
        return None
    
    # 生成候选日期（±1天，处理凌晨比赛偏移）
    candidate_dates = set()
    if date_str and re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        candidate_dates.add(date_str)
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            candidate_dates.add((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
            candidate_dates.add((dt + timedelta(days=1)).strftime("%Y-%m-%d"))
        except ValueError:
            pass
    
    # 先严格匹配（日期+两队精确/包含匹配）
    for row in rows:
        md = row['match_date'] or ''
        if md not in candidate_dates and candidate_dates:
            continue
        h = row['home_team'] or ''
        a = row['away_team'] or ''
        if _name_match(home, h) and _name_match(away, a):
            return _row_to_score(row, "db")
    
    return None

def _row_to_score(row, source):
    """将数据库行转为比分 dict"""
    half_h = _safe_int(row['half_home']) if row['half_home'] is not None else None
    half_a = _safe_int(row['half_away']) if row['half_away'] is not None else None
    return {
        "home": row['home_score'],
        "away": row['away_score'],
        "half_home": half_h,
        "half_away": half_a,
        "source": f"{source}:{row['id']}"
    }

# ============ titan007 补抓 ============

def _parse_m_array(html):
    matches = {}
    for m in re.finditer(r"M\[(\d+)\]\[(\d+)\]\s*=\s*(.+?)\s*;", html, re.DOTALL):
        row, col = int(m.group(1)), int(m.group(2))
        raw = m.group(3).strip()
        if row not in matches:
            matches[row] = {}
        if raw.startswith(('"', "'")):
            val = raw.strip("\"'")
        elif raw in ("true", "false"):
            val = raw == "true"
        elif raw.startswith("new Date"):
            val = raw
        else:
            try:
                val = int(raw)
            except ValueError:
                try:
                    val = float(raw)
                except ValueError:
                    val = raw
        matches[row][col] = val
    
    results = []
    for idx in sorted(matches):
        if idx == 0:
            continue
        d = matches[idx]
        home = d.get(17, "")
        away = d.get(20, "")
        if not home or not away:
            continue
        results.append({
            "status_code": d.get(4, 0),
            "home_team": home, "away_team": away,
            "home_team_trad": d.get(18, ""), "away_team_trad": d.get(21, ""),
            "home_team_official": d.get(19, ""), "away_team_official": d.get(22, ""),
            "home_score": _safe_int(d.get(7)), "away_score": _safe_int(d.get(8)),
            "home_half": _safe_int(d.get(11)), "away_half": _safe_int(d.get(12)),
            "match_time": d.get(1, "").strip(),
        })
    return results

def fetch_scores(date_str=None):
    if date_str is None:
        now = datetime.utcnow() + timedelta(hours=8)
        date_str = f"{now.year}-{now.month}-{now.day}"
    url = f"https://cp.titan007.com/buy/JingCai.aspx?typeID=101&oddstype=2&date={date_str}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        print(f"[titan007] 请求失败 {date_str}: {e}", file=sys.stderr)
        return []
    all_matches = _parse_m_array(resp.text)
    completed = [m for m in all_matches if m["status_code"] != 0]
    print(f"[titan007] {date_str}: {len(all_matches)}场, 完场{len(completed)}场", file=sys.stderr)
    return completed

def find_in_titan(home, away, date_str, titan_cache):
    """在titan007数据中查找比分。titan_cache 缓存已抓取日期的数据。"""
    if not home or not away:
        return None
    
    candidate_dates = set()
    if date_str:
        candidate_dates.add(date_str)
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            candidate_dates.add((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
        except ValueError:
            pass
    
    for cd in sorted(candidate_dates):
        if cd not in titan_cache:
            titan_cache[cd] = fetch_scores(cd)
        for tm in titan_cache[cd]:
            h = _name_match(home, [tm["home_team"], tm["home_team_trad"], tm.get("home_team_official", "")])
            a = _name_match(away, [tm["away_team"], tm["away_team_trad"], tm.get("away_team_official", "")])
            if h and a and tm["home_score"] is not None:
                return {
                    "home": tm["home_score"],
                    "away": tm["away_score"],
                    "half_home": tm.get("home_half"),
                    "half_away": tm.get("away_half"),
                    "source": f"titan007:{cd}"
                }
    return None

# ============ 数据库操作 ============

def ensure_settle_columns(conn):
    columns_to_add = [
        ("is_settled", "BOOLEAN DEFAULT FALSE"),
        ("settled_at", "TIMESTAMP"),
        ("hit_count", "INTEGER"),
        ("total_count", "INTEGER"),
        ("hit_details", "JSONB"),
    ]
    with conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'traditional_predictions'")
        existing = set(row[0] for row in cur.fetchall())
        for col_name, col_type in columns_to_add:
            if col_name not in existing:
                print(f"[DDL] 添加列: {col_name} {col_type}")
                cur.execute(f"ALTER TABLE traditional_predictions ADD COLUMN {col_name} {col_type}")
    conn.commit()

def get_unsettled_predictions(conn, issue=None):
    sql = """
        SELECT id, game_type, ai_name, issue, predictions, matches_info, ren9
        FROM traditional_predictions
        WHERE (is_settled = FALSE OR is_settled IS NULL)
          AND game_type IN ('胜负彩', '任9', '半全场', '进球彩')
    """
    params = []
    if issue:
        sql += " AND issue = %s"
        params.append(issue)
    sql += " ORDER BY issue DESC, game_type, ai_name"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()

# ============ 结算逻辑 ============

def get_score_result(home_score, away_score):
    if home_score > away_score: return "3"
    elif home_score == away_score: return "1"
    else: return "0"

def get_result_code(home_score, away_score):
    if home_score > away_score: return "3"
    elif home_score == away_score: return "1"
    else: return "0"

def get_total_goals(home_score, away_score):
    total = home_score + away_score
    return "7" if total >= 7 else str(total)

def _find_match_info(matches_info, match_num):
    """在 matches_info 中查找指定场次"""
    mn = str(match_num).lstrip("0") or "0"
    for m in matches_info:
        if not isinstance(m, dict):
            continue
        m_num = str(m.get("num", m.get("match_num", ""))).lstrip("0") or "0"
        if m_num == mn:
            return m
    return None

def settle_sfc(predictions, matches_info, scores_map):
    hit_count = total_count = 0
    hit_details = []
    for pred in predictions:
        match_num = str(pred.get("match", "")).lstrip("0") or "0"
        pred_value = pred.get("spf")
        if pred_value is None or pred_value == "-" or pred_value == "":
            continue
        mi = _find_match_info(matches_info, match_num)
        if not mi:
            continue
        match_id = mi.get("id", f"{mi.get('issue', '')}_{str(match_num).zfill(2)}")
        score = scores_map.get(match_id)
        if not score:
            hit_details.append({"match_num": match_num, "match_id": match_id,
                "home_team": mi.get("home", ""), "away_team": mi.get("away", ""),
                "prediction": pred_value, "actual": None, "hit": None, "reason": "no_score"})
            total_count += 1
            continue
        actual = get_score_result(score["home"], score["away"])
        is_hit = str(pred_value) == actual
        if is_hit: hit_count += 1
        total_count += 1
        hit_details.append({"match_num": match_num, "match_id": match_id,
            "home_team": mi.get("home", ""), "away_team": mi.get("away", ""),
            "prediction": pred_value, "actual": actual,
            "score": f"{score['home']}-{score['away']}", "hit": is_hit})
    return hit_count, total_count, hit_details

def settle_jqc(predictions, matches_info, scores_map):
    hit_count = total_count = 0
    hit_details = []
    for pred in predictions:
        match_num = str(pred.get("match", "")).lstrip("0") or "0"
        pred_value = pred.get("zjq")
        if pred_value is None or pred_value == "-" or pred_value == "":
            continue
        mi = _find_match_info(matches_info, match_num)
        if not mi:
            continue
        match_id = mi.get("id", f"{mi.get('issue', '')}_{str(match_num).zfill(2)}")
        score = scores_map.get(match_id)
        if not score:
            hit_details.append({"match_num": match_num, "match_id": match_id,
                "home_team": mi.get("home", ""), "away_team": mi.get("away", ""),
                "prediction": pred_value, "actual": None, "hit": None, "reason": "no_score"})
            total_count += 1
            continue
        actual = get_total_goals(score["home"], score["away"])
        is_hit = str(pred_value) == actual
        if is_hit: hit_count += 1
        total_count += 1
        hit_details.append({"match_num": match_num, "match_id": match_id,
            "home_team": mi.get("home", ""), "away_team": mi.get("away", ""),
            "prediction": pred_value, "actual": actual,
            "score": f"{score['home']}-{score['away']}", "hit": is_hit})
    return hit_count, total_count, hit_details

def settle_htf(predictions, matches_info, scores_map):
    hit_count = total_count = 0
    hit_details = []
    for pred in predictions:
        match_num = str(pred.get("match", "")).lstrip("0") or "0"
        pred_value = pred.get("bqc")
        if pred_value is None or pred_value == "-" or pred_value == "":
            continue
        mi = _find_match_info(matches_info, match_num)
        if not mi:
            continue
        match_id = mi.get("id", f"{mi.get('issue', '')}_{str(match_num).zfill(2)}")
        score = scores_map.get(match_id)
        if not score:
            hit_details.append({"match_num": match_num, "match_id": match_id,
                "home_team": mi.get("home", ""), "away_team": mi.get("away", ""),
                "prediction": pred_value, "actual": None, "hit": None, "reason": "no_score"})
            total_count += 1
            continue
        half_home = score.get("half_home")
        half_away = score.get("half_away")
        if half_home is None or half_away is None:
            hit_details.append({"match_num": match_num, "match_id": match_id,
                "home_team": mi.get("home", ""), "away_team": mi.get("away", ""),
                "prediction": pred_value, "actual": None, "hit": None, "reason": "no_half_score"})
            total_count += 1
            continue
        half_result = get_result_code(half_home, half_away)
        full_result = get_result_code(score["home"], score["away"])
        actual = half_result + full_result
        is_hit = str(pred_value) == actual
        if is_hit: hit_count += 1
        total_count += 1
        hit_details.append({"match_num": match_num, "match_id": match_id,
            "home_team": mi.get("home", ""), "away_team": mi.get("away", ""),
            "prediction": pred_value, "actual": actual,
            "score": f"{half_home}-{half_away}/{score['home']}-{score['away']}", "hit": is_hit})
    return hit_count, total_count, hit_details

def update_settlement(conn, pred_id, hit_count, total_count, hit_details):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE traditional_predictions
            SET is_settled = TRUE, settled_at = NOW(),
                hit_count = %s, total_count = %s,
                hit_details = %s::jsonb
            WHERE id = %s
        """, (hit_count, total_count, json.dumps(hit_details, ensure_ascii=False), pred_id))
    conn.commit()

# ============ 主流程 ============

def main():
    parser = argparse.ArgumentParser(description="CT彩自动结算 v2")
    parser.add_argument("--issue", help="指定期号")
    parser.add_argument("--dry-run", action="store_true", help="试运行")
    args = parser.parse_args()
    
    print("=" * 60)
    print("CT彩自动结算 v2 (优先复用竞彩比分)")
    print("=" * 60)
    
    conn = get_db()
    ensure_settle_columns(conn)
    
    records = get_unsettled_predictions(conn, args.issue)
    if not records:
        print("没有未结算的记录")
        conn.close()
        return
    print(f"发现 {len(records)} 条未结算记录")
    
    # 预加载比分数据
    jc_scores = load_jc_scores(conn)
    ct_scores = load_ct_scores(conn)
    
    # titan007 缓存（按日期）
    titan_cache = {}
    
    # 统计
    db_jc_found = 0
    db_ct_found = 0
    titan_found = 0
    not_found = 0
    
    settled_count = 0
    skipped_count = 0
    
    # 按 issue+game_type 分组，同组共用比分（避免重复查找）
    groups = {}
    for row in records:
        pred_id, game_type, ai_name, issue, predictions, matches_info, ren9 = row
        if isinstance(matches_info, str):
            matches_info = json.loads(matches_info)
        if isinstance(predictions, str):
            predictions = json.loads(predictions)
        key = f"{issue}_{game_type}"
        if key not in groups:
            groups[key] = {
                "game_type": game_type,
                "issue": issue,
                "matches_info": matches_info,
                "records": []
            }
        groups[key]["records"].append({
            "pred_id": pred_id,
            "ai_name": ai_name,
            "predictions": predictions
        })
    
    print(f"共 {len(groups)} 个期号+玩法组合")
    
    # 逐组处理
    for group_key, group in sorted(groups.items(), reverse=True):
        game_type = group["game_type"]
        issue = group["issue"]
        matches_info = group["matches_info"]
        
        if not matches_info:
            for rec in group["records"]:
                skipped_count += 1
            continue
        
        # 为这个组查找所有比赛的比分
        scores_map = {}  # key = ct_id (如 "CT26099_01")
        
        for m in matches_info:
            if not isinstance(m, dict):
                continue
            ct_id = m.get("id", "")
            home = m.get("home", m.get("home_team", ""))
            away = m.get("away", m.get("away_team", ""))
            match_time = m.get("time", m.get("match_time", ""))
            match_num = str(m.get("num", "")).zfill(2)
            parts = match_time.split()
            date_str = parts[0] if parts and re.match(r'\d{4}-\d{2}-\d{2}', parts[0]) else ""
            
            # 三级查找
            score = None
            
            # Level 1: 竞彩已有比分
            score = find_score_in_rows(home, away, date_str, jc_scores)
            if score:
                db_jc_found += 1
                scores_map[ct_id] = score
                continue
            
            # Level 2: CT彩本身已有比分（按 ct_id 直接查）
            if ct_id in ct_scores:
                score = _row_to_score(ct_scores[ct_id], "ct_direct")
                db_ct_found += 1
                scores_map[ct_id] = score
                continue
            
            # Level 3: titan007 补抓
            score = find_in_titan(home, away, date_str, titan_cache)
            if score:
                titan_found += 1
                scores_map[ct_id] = score
                continue
            
            not_found += 1
        
        found_count = len(scores_map)
        total_count = len([m for m in matches_info if isinstance(m, dict)])
        print(f"\n{issue} {game_type}: {found_count}/{total_count} 场有比分")
        
        # 逐条预测记录结算
        for rec in group["records"]:
            pred_id = rec["pred_id"]
            ai_name = rec["ai_name"]
            predictions = rec["predictions"]
            
            if not predictions:
                skipped_count += 1
                continue
            
            try:
                if game_type in ("胜负彩", "任9"):
                    hc, tc, hd = settle_sfc(predictions, matches_info, scores_map)
                elif game_type == "进球彩":
                    hc, tc, hd = settle_jqc(predictions, matches_info, scores_map)
                elif game_type == "半全场":
                    hc, tc, hd = settle_htf(predictions, matches_info, scores_map)
                else:
                    skipped_count += 1
                    continue
            except Exception as e:
                print(f"  {ai_name}: 结算出错: {e}")
                skipped_count += 1
                continue
            
            print(f"  {ai_name}: 命中 {hc}/{tc}")
            settled_count += 1
            
            if not args.dry_run:
                try:
                    update_settlement(conn, pred_id, hc, tc, hd)
                except Exception as e:
                    print(f"  更新DB失败: {e}")
                    settled_count -= 1
    
    conn.close()
    
    print("\n" + "=" * 60)
    print(f"结算完成!")
    print(f"  成功结算: {settled_count} 条记录")
    print(f"  跳过: {skipped_count} 条")
    print(f"  比分来源: 竞彩DB={db_jc_found}, CT本身DB={db_ct_found}, titan007={titan_found}, 未找到={not_found}")
    if args.dry_run:
        print(f"  [DRY-RUN] 未实际更新数据库")
    print("=" * 60)
    
    result = {
        "status": "OK",
        "settled": settled_count,
        "skipped": skipped_count,
        "scores_from_jc_db": db_jc_found,
        "scores_from_ct_db": db_ct_found,
        "scores_from_titan": titan_found,
        "scores_not_found": not_found
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
