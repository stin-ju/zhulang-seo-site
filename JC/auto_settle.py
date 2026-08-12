#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""
自动结算脚本 v2 - 扫描已完赛但未结算的比赛，对比AI预测与实际结果
支持足球和篮球，适配当前数据库schema

predictions表关键列：
  足球: spf(胜/平/负), handicap_spf(让胜/让平/让负), goals(int), score(1-0), half_full(胜胜)
  篮球: win_loss(胜/负), handicap_win_loss(让胜/让负), total_points(大/小), score_diff_range(主6-10胜), half_win_loss(胜/负)
  命中列: spf_hit, goals_hit, score_hit, half_full_hit, handicap_spf_hit (bool)
  汇总: hit_status(jsonb), is_settled(bool)
"""

import psycopg2
import json
import sys
import re
import requests
from datetime import datetime, timedelta

DEFAULT_DB_URL = "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres"

# ==================== titan007 比分抓取（原 titan007_client.py）====================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 竞彩简称 → titan007全名 别名映射
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
}

def _safe_int(val, default=0):
    if val is None or val == "" or val == "null":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _parse_m_array(html):
    """解析足球竞彩页面的M数组数据"""
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

def _parse_basketball_xml(xml_text):
    """解析篮球 bf.titan007.com 的XML数据"""
    results = []
    for m in re.finditer(r'<!\[CDATA\[(.+?)\]\]>', xml_text, re.DOTALL):
        raw = m.group(1).strip()
        parts = raw.split('^')
        if len(parts) < 13:
            continue
        league_raw = parts[1]
        league = league_raw.split(',')[0] if ',' in league_raw else league_raw
        status_code = parts[2]
        home_parts = parts[8].split(',')
        home_name = re.sub(r'\[\d+\]', '', home_parts[0]).strip() if home_parts else ''
        home_trad = re.sub(r'\[\d+\]', '', home_parts[1]).strip() if len(home_parts) > 1 else ''
        home_en = re.sub(r'\[\d+\]', '', home_parts[2]).strip() if len(home_parts) > 2 else ''
        away_parts = parts[10].split(',')
        away_name = re.sub(r'\[\d+\]', '', away_parts[0]).strip() if away_parts else ''
        away_trad = re.sub(r'\[\d+\]', '', away_parts[1]).strip() if len(away_parts) > 1 else ''
        away_en = re.sub(r'\[\d+\]', '', away_parts[2]).strip() if len(away_parts) > 2 else ''
        try:
            home_score = int(parts[11])
            away_score = int(parts[12])
        except (ValueError, IndexError):
            continue
        half_home = None
        half_away = None
        if len(parts) >= 17:
            try:
                q1h = int(parts[13]); q1a = int(parts[14])
                q2h = int(parts[15]); q2a = int(parts[16])
                half_home = q1h + q2h
                half_away = q1a + q2a
            except (ValueError, IndexError):
                pass
        results.append({
            "status_code": status_code,
            "home_team": home_name, "away_team": away_name,
            "home_team_trad": home_trad, "away_team_trad": away_trad,
            "home_team_official": home_en, "away_team_official": away_en,
            "home_score": home_score, "away_score": away_score,
            "home_half": half_home, "away_half": half_away,
            "league": league,
        })
    return results

def fetch_scores(sport="football", date_str=None):
    if date_str is None:
        now = datetime.utcnow() + timedelta(hours=8)
        date_str = f"{now.year}-{now.month}-{now.day}"
    if sport == "basketball":
        return _fetch_basketball_scores(date_str)
    else:
        return _fetch_football_scores(date_str)

def _fetch_football_scores(date_str):
    type_id = "101"
    url = f"https://cp.titan007.com/buy/JingCai.aspx?typeID={type_id}&oddstype=2&date={date_str}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        print(f"[titan007] 足球请求失败: {e}", file=sys.stderr)
        return []
    all_matches = _parse_m_array(resp.text)
    completed = [m for m in all_matches if m["status_code"] != 0]
    print(f"[titan007] football {date_str}: {len(all_matches)}场, 完场{len(completed)}场", file=sys.stderr)
    return completed

def _fetch_basketball_scores(date_str):
    if len(date_str) == 9 and date_str[5] == '0':
        parts = date_str.split('-')
        if len(parts) == 3:
            date_str = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    url = f"https://bf.titan007.com/nba_date.aspx?date={date_str}&h=0&m=0&s=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://bf.titan007.com/NBA_SC.aspx",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "gb2312"
    except requests.RequestException as e:
        print(f"[titan007] 篮球请求失败: {e}", file=sys.stderr)
        return []
    all_matches = _parse_basketball_xml(resp.text)
    completed = [m for m in all_matches if m["status_code"] == "4"]
    print(f"[titan007] basketball {date_str}: {len(all_matches)}场, 完场{len(completed)}场", file=sys.stderr)
    return completed

def fetch_scores_range(sport, days_back=7, days_forward=1):
    now = datetime.utcnow() + timedelta(hours=8)
    result = {}
    for offset in range(-days_back, days_forward + 1):
        d = now + timedelta(days=offset)
        ds = f"{d.year}-{d.month}-{d.day}"
        dk = d.strftime("%Y-%m-%d")
        matches = fetch_scores(sport, ds)
        if matches:
            result[dk] = matches
    return result

def _match_name(db_name, candidates):
    if not db_name:
        return False
    db_name = db_name.strip()
    for c in candidates:
        if not c:
            continue
        c = c.strip()
        if db_name == c or db_name in c or c in db_name:
            return True
        if db_name in ALIASES:
            for alias in ALIASES[db_name]:
                if alias == c or alias in c or c in alias:
                    return True
        if len(db_name) >= 3 and len(c) >= 3:
            for i in range(len(db_name) - 2):
                if db_name[i:i+3] in c:
                    return True
    return False

def find_match_in_titan_data(db_home, db_away, titan_matches):
    for tm in titan_matches:
        h = _match_name(db_home, [tm["home_team"], tm["home_team_trad"], tm.get("home_team_official", "")])
        a = _match_name(db_away, [tm["away_team"], tm["away_team_trad"], tm.get("away_team_official", "")])
        if h and a:
            return tm
    for tm in titan_matches:
        h = _match_name(db_home, [tm["home_team"], tm["home_team_trad"], tm.get("home_team_official", "")])
        if h:
            return tm
    return None

# ==================== 以下为自动结算逻辑 ====================


def get_db(db_url=None):
    return psycopg2.connect(db_url or DEFAULT_DB_URL)


def _derive_date_from_id(match_id):
    """从 match ID 推导日期，如 '20260705_周日203' -> '2026-07-05'"""
    m = re.match(r'(\d{4})(\d{2})(\d{2})_', match_id)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _get_pred_field(pred_jsonb, top_level_val, *jsonb_keys):
    """优先从 prediction jsonb 取值，fallback 到顶层列"""
    if pred_jsonb and isinstance(pred_jsonb, dict):
        for key in jsonb_keys:
            v = pred_jsonb.get(key)
            if v is not None:
                return v
    return top_level_val


def _normalize_spf(val):
    """归一化足球胜平负: 主胜→胜, 客胜/客负→负"""
    if val is None:
        return None
    val = str(val).strip()
    mapping = {"主胜": "胜", "客胜": "负", "客负": "负", "主负": "负"}
    return mapping.get(val, val)


def _normalize_handicap_spf(val):
    """归一化让球胜平负: 让主胜→让胜, 让客胜→让负, 让客负→让负"""
    if val is None:
        return None
    val = str(val).strip()
    mapping = {"让主胜": "让胜", "让客胜": "让负", "让客负": "让负", "让主负": "让负"}
    return mapping.get(val, val)


def fill_missing_scores(conn):
    """从 titan007 补全已完赛但缺少比分的比赛，同时检查 on_sale 但可能已完赛的比赛"""
    # Bug1 fix: 查顶层 m.status = '已完赛'，而不是 metadata 里的 status
    # 同时也查 on_sale 的比赛（可能已完赛但 status 未更新）
    sql = """
    SELECT m.id, m.sport_type, m.home_team, m.away_team, m.status, m.metadata
    FROM matches m
    WHERE (m.status = '已完赛' OR m.status = 'on_sale')
      AND m.metadata->>'status' != '已取消'
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    missing = []
    on_sale_candidates = []
    for row in rows:
        match_id, sport_type, home_team, away_team, top_status, metadata = row
        md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
        # 跳过已标记为无法补全的比赛
        if md.get("score_unavailable"):
            continue

        if top_status == '已完赛':
            # 已完赛但缺比分
            if md.get("home_score") is None or md.get("away_score") is None:
                missing.append({"id": match_id, "sport_type": sport_type,
                              "home_team": home_team, "away_team": away_team, "metadata": md,
                              "top_status": top_status})
        elif top_status == 'on_sale':
            # on_sale 但可能已完赛（比赛时间已过3小时以上）
            mt = md.get("match_time", "")
            if mt:
                try:
                    # match_time 可能是 "18:30:00" 或 "2026-07-19 18:30:00"
                    if " " in mt:
                        match_dt = datetime.strptime(mt, "%Y-%m-%d %H:%M:%S")
                    else:
                        # 仅有时间，需要从 ID 推导日期
                        date_str = _derive_date_from_id(match_id)
                        if date_str:
                            match_dt = datetime.strptime(f"{date_str} {mt}", "%Y-%m-%d %H:%M:%S")
                        else:
                            continue
                    now = datetime.now()
                    if (now - match_dt).total_seconds() > 3 * 3600:  # 开赛3小时后
                        on_sale_candidates.append({"id": match_id, "sport_type": sport_type,
                                                   "home_team": home_team, "away_team": away_team,
                                                   "metadata": md, "top_status": top_status})
                except (ValueError, TypeError):
                    pass

    all_to_fill = missing + on_sale_candidates
    if not all_to_fill:
        print("[比分补全] 无需补全")
        return 0

    if missing:
        print(f"[比分补全] 发现 {len(missing)} 场缺少比分的已完赛比赛")
    if on_sale_candidates:
        print(f"[比分补全] 发现 {len(on_sale_candidates)} 场 on_sale 但可能已完赛的比赛")

    football_missing = [m for m in all_to_fill if m["sport_type"] == "football"]
    basketball_missing = [m for m in all_to_fill if m["sport_type"] == "basketball"]

    if not football_missing and not basketball_missing:
        return 0

    # 检查比赛日期，超过7天的老比赛 titan007 可能没有数据
    now = datetime.now()
    dates_needed = set()
    old_matches = []
    recent_matches = []

    for m in football_missing:
        mt = m["metadata"].get("match_time", "")
        date_str = None
        if mt:
            try:
                if " " in mt:
                    date_str = mt.split(" ")[0]
                # else: 仅有时间，从 ID 推导
            except ValueError:
                pass

        if not date_str:
            date_str = _derive_date_from_id(m["id"])

        if date_str:
            try:
                match_date = datetime.strptime(date_str, "%Y-%m-%d")
                days_ago = (now - match_date).days
                if days_ago > 7:
                    old_matches.append(m)
                else:
                    recent_matches.append(m)
                    dates_needed.add(date_str)
            except ValueError:
                recent_matches.append(m)
                dates_needed.add(date_str)
        else:
            # 无法确定日期，标记跳过
            print(f"  [标记跳过] {m['id']}: 无法确定比赛日期")
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "no_date"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            conn.commit()

    # 处理超过7天的老比赛：标记为无法补全
    if old_matches:
        print(f"[比分补全] {len(old_matches)} 场比赛超过7天，titan007 可能无数据")
        for m in old_matches:
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "match_too_old"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            print(f"  [标记跳过] {m['id']}: {m['home_team']} vs {m['away_team']} (超过7天)")
        conn.commit()

    if not recent_matches and not basketball_missing:
        print(f"[比分补全] 完成，补全 0 场")
        return 0

    # 查询近期比赛的 titan007 数据
    titan_data = {}
    for ds in dates_needed:
        parts = ds.split("-")
        titan_date = f"{parts[0]}-{int(parts[1])}-{int(parts[2])}"
        matches = fetch_scores("football", titan_date)
        if matches:
            titan_data[ds] = matches
            # Debug: 打印 titan007 返回的队伍名
            print(f"  [titan007] {ds} 共{len(matches)}场完场:")
            for tm in matches:
                print(f"    {tm['home_team']}({tm.get('home_team_official','')}) vs {tm['away_team']}({tm.get('away_team_official','')}) {tm['home_score']}-{tm['away_score']}")

    # 也查篮球的 titan007 数据
    basketball_titan_data = {}
    if basketball_missing:
        for m in basketball_missing:
            date_str = _derive_date_from_id(m["id"])
            if date_str and date_str not in basketball_titan_data:
                parts = date_str.split("-")
                titan_date = f"{parts[0]}-{int(parts[1])}-{int(parts[2])}"
                bmatches = fetch_scores("basketball", titan_date)
                if bmatches:
                    basketball_titan_data[date_str] = bmatches

    updated = 0
    for m in recent_matches:
        mt = m["metadata"].get("match_time", "")
        if mt and " " in mt:
            ds = mt.split(" ")[0]
        else:
            ds = _derive_date_from_id(m["id"]) or ""

        titan_matches = titan_data.get(ds, [])
        if not titan_matches:
            # 标记为无法补全，避免重复查询
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "no_titan_data"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            print(f"  [标记跳过] {m['id']}: 无titan007数据({ds})")
            conn.commit()
            continue

        found = find_match_in_titan_data(m["home_team"], m["away_team"], titan_matches)
        if found and found["home_score"] is not None and found["away_score"] is not None:
            md = m["metadata"]
            md["home_score"] = found["home_score"]
            md["away_score"] = found["away_score"]
            md["status"] = "已完赛"
            if found.get("home_half") is not None:
                md["half_home_score"] = found["home_half"]
            if found.get("away_half") is not None:
                md["half_away_score"] = found["away_half"]
            # 同时更新顶层 status
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb, status = '已完赛' WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            updated += 1
            print(f"  [补全] {m['id']}: {m['home_team']} {found['home_score']}-{found['away_score']} {m['away_team']}")
        else:
            # Debug: 打印匹配失败的详情
            print(f"  [DEBUG] 匹配失败 {m['id']}: DB={m['home_team']} vs {m['away_team']}")
            print(f"  [DEBUG] titan007 候选({ds}):")
            for tm in titan_matches:
                print(f"    {tm['home_team']}/{tm.get('home_team_trad','')}/{tm.get('home_team_official','')} vs {tm['away_team']}/{tm.get('away_team_trad','')}/{tm.get('away_team_official','')}")

            # 标记为无法补全
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "match_not_found"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            print(f"  [标记跳过] {m['id']}: {m['home_team']} vs {m['away_team']} (未匹配)")
            conn.commit()

    # 处理篮球比赛
    for m in basketball_missing:
        date_str = _derive_date_from_id(m["id"]) or ""
        titan_matches = basketball_titan_data.get(date_str, [])
        if not titan_matches:
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "no_titan_data"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            conn.commit()
            continue

        found = find_match_in_titan_data(m["home_team"], m["away_team"], titan_matches)
        if found and found["home_score"] is not None and found["away_score"] is not None:
            md = m["metadata"]
            md["home_score"] = found["home_score"]
            md["away_score"] = found["away_score"]
            md["status"] = "已完赛"
            if found.get("home_half") is not None:
                md["half_home_score"] = found["home_half"]
            if found.get("away_half") is not None:
                md["half_away_score"] = found["away_half"]
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb, status = '已完赛' WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            updated += 1
            print(f"  [补全] {m['id']}: {m['home_team']} {found['home_score']}-{found['away_score']} {m['away_team']}")
        else:
            print(f"  [DEBUG] 匹配失败 {m['id']}: DB={m['home_team']} vs {m['away_team']}")
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "match_not_found"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            conn.commit()

    if updated > 0:
        conn.commit()
    print(f"[比分补全] 完成，补全 {updated} 场")
    return updated


def get_unsettled(conn, match_id=None):
    """获取所有已完赛但未结算的比赛及其预测
    同时从 prediction jsonb 和顶层列读取，优先 jsonb
    如果指定 match_id，只返回该比赛的预测
    """
    # Bug1 fix: 查顶层 m.status = '已完赛'，排除已取消的比赛
    # Bug2 fix: COALESCE 从 prediction jsonb 和顶层列取值，优先 jsonb
    sql = """
    SELECT m.id, m.sport_type, m.home_team, m.away_team, m.metadata,
           p.id as pred_id, p.ai_name, p.sport_type as p_sport,
           COALESCE(p.prediction->>'spf', p.spf) as spf,
           COALESCE(p.prediction->>'handicap_spf', p.handicap_spf) as handicap_spf,
           COALESCE(p.prediction->>'goals', p.goals::text) as goals,
           COALESCE(p.prediction->>'score', p.score) as score,
           COALESCE(p.prediction->>'half_full', p.half_full) as half_full,
           COALESCE(p.prediction->>'win_loss', p.win_loss) as win_loss,
           COALESCE(p.prediction->>'handicap_win_loss', p.handicap_win_loss) as handicap_win_loss,
           COALESCE(p.prediction->>'handicap_result') as handicap_result,
           COALESCE(p.prediction->>'total_points', p.total_points) as total_points,
           COALESCE(p.prediction->>'score_diff_range', p.score_diff_range,
                    p.prediction->>'score_diff') as score_diff_range,
           COALESCE(p.prediction->>'half_win_loss', p.half_win_loss) as half_win_loss
    FROM matches m
    JOIN predictions p ON p.match_id = m.id
    WHERE m.status = '已完赛'
      AND m.metadata->>'status' != '已取消'
      AND (p.is_settled = false OR p.is_settled IS NULL)
    """
    params = []
    if match_id:
        sql += " AND m.id = %s"
        params.append(match_id)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def settle_football(row):
    """
    结算足球预测，返回 (hit_dict, hit_cols_dict)
    hit_dict: 用于写入 hit_status jsonb
    hit_cols_dict: 用于写入 xxx_hit boolean 列
    """
    (match_id, sport_type, home_team, away_team, metadata,
     pred_id, ai_name, p_sport,
     spf, handicap_spf, goals, score, half_full,
     win_loss, handicap_win_loss, handicap_result,
     total_points, score_diff_range, half_win_loss) = row

    md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
    home_score = md.get("home_score")
    away_score = md.get("away_score")
    # 适配新schema: handicap 可能在 metadata->odds->handicap_spf->handicap 或 metadata->odds->hdc->line
    _odds = md.get("odds", {}) or {}
    handicap = md.get("handicap") or _odds.get("handicap_spf", {}).get("handicap") or _odds.get("hdc", {}).get("line")

    if home_score is None or away_score is None:
        return None, None

    home_score = int(home_score)
    away_score = int(away_score)

    hit = {}
    hit_cols = {}

    # 1. spf 胜平负 -> 胜/平/负
    if spf is not None:
        spf_norm = _normalize_spf(spf)
        if home_score > away_score:
            actual = "胜"
        elif home_score == away_score:
            actual = "平"
        else:
            actual = "负"
        is_hit = (spf_norm == actual)
        hit["spf"] = is_hit
        hit_cols["spf_hit"] = is_hit

    # 2. handicap_spf 让球胜平负 -> 让胜/让平/让负
    if handicap_spf is not None and handicap is not None:
        hc_norm = _normalize_handicap_spf(handicap_spf)
        adjusted = home_score + float(handicap)
        if adjusted > away_score:
            actual = "让胜"
        elif adjusted == away_score:
            actual = "让平"
        else:
            actual = "让负"
        is_hit = (hc_norm == actual)
        hit["handicap_spf"] = is_hit
        hit_cols["handicap_spf_hit"] = is_hit

    # 3. goals 进球数 (integer)
    if goals is not None:
        total_goals = home_score + away_score
        is_hit = (int(goals) == total_goals)
        hit["goals"] = is_hit
        hit_cols["goals_hit"] = is_hit

    # 4. score 比分 -> "1-0" 格式
    if score is not None:
        actual_score = f"{home_score}-{away_score}"
        is_hit = (score == actual_score)
        hit["score"] = is_hit
        hit_cols["score_hit"] = is_hit

    # 5. half_full 半全场 -> "胜胜" 格式
    if half_full is not None:
        half_home = md.get("half_home_score")
        half_away = md.get("half_away_score")
        if half_home is not None and half_away is not None:
            half_home = int(half_home)
            half_away = int(half_away)
            half_r = "胜" if half_home > half_away else ("平" if half_home == half_away else "负")
            full_r = "胜" if home_score > away_score else ("平" if home_score == away_score else "负")
            actual_hf = f"{half_r}{full_r}"
            is_hit = (half_full == actual_hf)
            hit["half_full"] = is_hit
            hit_cols["half_full_hit"] = is_hit

    return (hit if hit else None), hit_cols


def parse_score_diff_range(sdr):
    """
    解析胜分差预测值，如 '主6-10胜' -> ('主', 6, 10, '胜')
    或 '客1-5胜' -> ('客', 1, 5, '胜')
    """
    m = re.match(r'([主客])(\d+)-(\d+)(胜|负)', sdr)
    if m:
        return m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    return None


def settle_basketball(row):
    """
    结算篮球预测，返回 (hit_dict, hit_cols_dict)
    兼容多种 win_loss 格式："胜"/"负"、"主胜"/"客胜"/"主负"/"客负"
    兼容 handicap_result（旧key）和 handicap_win_loss
    """
    (match_id, sport_type, home_team, away_team, metadata,
     pred_id, ai_name, p_sport,
     spf, handicap_spf, goals, score, half_full,
     win_loss, handicap_win_loss, handicap_result,
     total_points, score_diff_range, half_win_loss) = row

    md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
    home_score = md.get("home_score")
    away_score = md.get("away_score")
    # 适配新schema: handicap 可能在 metadata->odds->handicap_spf->handicap 或 metadata->odds->hdc->line
    _odds = md.get("odds", {}) or {}
    handicap = md.get("handicap") or _odds.get("handicap_spf", {}).get("handicap") or _odds.get("hdc", {}).get("line")

    if home_score is None or away_score is None:
        return None, None

    home_score = int(home_score)
    away_score = int(away_score)
    diff = abs(home_score - away_score)

    hit = {}
    hit_cols = {}

    # 1. win_loss 胜负 - 归一化多种格式
    if win_loss is not None:
        wl = str(win_loss).strip()
        if wl in ("主胜", "客负"):
            # 主队赢 = away_team(第二队)赢
            predicted_home_wins = False
        elif wl in ("客胜", "主负"):
            # 客队赢 = home_team(第一队)赢
            predicted_home_wins = True
        elif wl == "胜":
            predicted_home_wins = True  # home_team 胜
        elif wl == "负":
            predicted_home_wins = False  # home_team 负
        else:
            predicted_home_wins = None

        if predicted_home_wins is not None:
            actual_home_wins = home_score > away_score
            is_hit = (predicted_home_wins == actual_home_wins)
            hit["win_loss"] = is_hit
            hit_cols["spf_hit"] = is_hit

    # 2. handicap_win_loss / handicap_result 让分胜负
    # 优先用 handicap_win_loss，fallback 到 handicap_result
    hc_val = handicap_win_loss or handicap_result
    if hc_val is not None and handicap is not None:
        try:
            hc = str(hc_val).strip()
            hc_float = float(handicap)
            adjusted = home_score - away_score - hc_float
            if adjusted < 0:
                actual = "让分主胜"  # 主队(第二队)赢盘
            else:
                actual = "让分主负"  # 客队(第一队)赢盘

            # 归一化预测值
            hc_norm = hc
            if hc == "让胜":
                hc_norm = "让分主胜"
            elif hc == "让负":
                hc_norm = "让分主负"

            is_hit = (hc_norm == actual)
            hit["handicap_win_loss"] = is_hit
            hit_cols["handicap_spf_hit"] = is_hit
        except (ValueError, TypeError):
            pass

    # 3. total_points 大小分 -> 大/小
    if total_points is not None:
        total = home_score + away_score
        tp_str = str(total_points).strip()
        if tp_str in ("大", "小", "大分", "小分"):
            tp_short = tp_str[0]  # 大/小
            line = md.get("total_points_line")
            # 适配新schema: total_line 可能在 metadata->odds->hilo->line
            if line is None:
                _odds2 = md.get("odds", {}) or {}
                line = _odds2.get("hilo", {}).get("line")
            if line is not None:
                line = float(line)
                actual = "大" if total > line else "小"
                is_hit = (tp_short == actual)
                hit["total_points"] = is_hit
                hit_cols["goals_hit"] = is_hit
            else:
                # 没有分界线，尝试从metadata的odds中找
                odds = md.get("odds", {}) or {}
                line = odds.get("total_points_line") or odds.get("total_line") or odds.get("hilo", {}).get("line")
                if line is not None:
                    line = float(line)
                    actual = "大" if total > line else "小"
                    is_hit = (tp_short == actual)
                    hit["total_points"] = is_hit
                    hit_cols["goals_hit"] = is_hit
        else:
            # 带数字的格式如 "210.5大"
            nums = re.findall(r'[\d.]+', tp_str)
            if nums:
                line = float(nums[0])
                predicted_big = "大" in tp_str
                actual_big = total > line
                is_hit = (predicted_big == actual_big)
                hit["total_points"] = is_hit
                hit_cols["goals_hit"] = is_hit

    # 4. score_diff_range 胜分差 -> "主6-10胜" 格式
    if score_diff_range is not None:
        parsed = parse_score_diff_range(score_diff_range)
        if parsed:
            side, low, high, winner = parsed
            actual_winner = "主" if home_score > away_score else "客"
            if side == actual_winner and low <= diff <= high:
                is_hit = True
            else:
                is_hit = False
            hit["score_diff_range"] = is_hit
            hit_cols["score_hit"] = is_hit
        else:
            # 尝试简单格式如 "1-5"
            nums = re.findall(r'\d+', score_diff_range)
            if len(nums) >= 2:
                low, high = int(nums[0]), int(nums[1])
                is_hit = (low <= diff <= high)
                hit["score_diff_range"] = is_hit
                hit_cols["score_hit"] = is_hit

    # 5. half_win_loss 半场胜负 -> 胜/负
    if half_win_loss is not None:
        half_home = md.get("half_home_score")
        half_away = md.get("half_away_score")
        if half_home is not None and half_away is not None:
            half_home = int(half_home)
            half_away = int(half_away)
            actual = "胜" if half_home > half_away else "负"
            is_hit = (half_win_loss == actual)
            hit["half_win_loss"] = is_hit
            hit_cols["half_full_hit"] = is_hit

    return (hit if hit else None), hit_cols


def main():
    import argparse
    parser = argparse.ArgumentParser(description='自动结算脚本')
    parser.add_argument('--match-id', dest='match_id', help='指定单场比赛ID进行结算')
    parser.add_argument('result_mode', nargs='?', default='display_only', help='结果模式')
    parser.add_argument('db_url', nargs='?', default=None, help='数据库URL')
    args = parser.parse_args()

    conn = get_db(args.db_url)
    
    # 先从 titan007 补全缺失比分
    try:
        filled = fill_missing_scores(conn)
        if filled > 0:
            print(f"已补全 {filled} 场比赛比分\n")
    except Exception as e:
        print(f"[WARN] 比分补全失败（不影响结算）: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    
    rows = get_unsettled(conn, match_id=args.match_id)

    if not rows:
        print("无待结算记录")
        conn.close()
        return

    settled_count = 0
    stats = {"football": {}, "basketball": {}}
    details = []

    for row in rows:
        match_id = row[0]
        sport_type = row[1]
        home_team = row[2]
        away_team = row[3]
        pred_id = row[5]
        ai_name = row[6]
        p_sport = row[7]

        # 判断运动类型
        st = (p_sport or sport_type or "").lower()
        if st == "basketball":
            hit_dict, hit_cols = settle_basketball(row)
            stat_key = "basketball"
        else:
            hit_dict, hit_cols = settle_football(row)
            stat_key = "football"

        if hit_dict is None:
            continue

        # 更新数据库
        hit_json = json.dumps(hit_dict, ensure_ascii=False)
        set_clauses = ["hit_status = %s::jsonb", "is_settled = true"]
        params = [hit_json]

        # 更新 xxx_hit boolean 列
        for col, val in hit_cols.items():
            set_clauses.append(f"{col} = %s")
            params.append(val)

        params.append(pred_id)
        sql = f"UPDATE predictions SET {', '.join(set_clauses)} WHERE id = %s"

        with conn.cursor() as cur:
            cur.execute(sql, params)

        settled_count += 1

        # 统计
        hits = sum(1 for v in hit_dict.values() if v is True)
        total_dims = len(hit_dict)
        if ai_name not in stats[stat_key]:
            stats[stat_key][ai_name] = {"total": 0, "hits": 0}
        stats[stat_key][ai_name]["total"] += 1
        stats[stat_key][ai_name]["hits"] += hits

        # 详情日志
        hit_str = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in hit_dict.items())
        details.append(f"  [{stat_key}] {ai_name}: {match_id} {home_team} vs {away_team} -> {hit_str} ({hits}/{total_dims})")

    conn.commit()
    conn.close()

    # 输出结果
    print(f"自动结算完成：共结算 {settled_count} 条预测")
    for d in details:
        print(d)

    for st in ["football", "basketball"]:
        if stats[st]:
            print(f"\n{st.upper()} 汇总:")
            for ai, s in stats[st].items():
                print(f"  {ai}: {s['total']}条, 命中{s['hits']}个维度")

    # 检查剩余未结算数
    conn2 = get_db(args.db_url)
    with conn2.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM predictions WHERE is_settled = false OR is_settled IS NULL")
        remaining = cur.fetchone()[0]
    conn2.close()
    print(f"\n剩余未结算预测: {remaining}条")


if __name__ == "__main__":
    main()
