#!/usr/bin/env python3
"""titan007_client - 从 cp.titan007.com 抓取完场比分"""
import re, sys, requests
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
TYPE_IDS = {"football": "101", "basketball": "102"}

def _safe_int(val, default=0):
    if val is None or val == "" or val == "null":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

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
            "home_score": _safe_int(d.get(5)), "away_score": _safe_int(d.get(6)),
            "home_half": _safe_int(d.get(7)), "away_half": _safe_int(d.get(8)),
            "match_time": d.get(1, "").strip(),
        })
    return results

def fetch_scores(sport="football", date_str=None):
    if date_str is None:
        now = datetime.utcnow() + timedelta(hours=8)
        date_str = f"{now.year}-{now.month}-{now.day}"
    type_id = TYPE_IDS.get(sport)
    if not type_id:
        raise ValueError(f"Unknown sport: {sport}")
    url = f"https://cp.titan007.com/buy/JingCai.aspx?typeID={type_id}&oddstype=2&date={date_str}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        print(f"[titan007] 请求失败: {e}", file=sys.stderr)
        return []
    all_matches = _parse_m_array(resp.text)
    completed = [m for m in all_matches if m["status_code"] != 0]
    print(f"[titan007] {sport} {date_str}: {len(all_matches)}场, 完场{len(completed)}场", file=sys.stderr)
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
        if len(db_name) >= 3 and len(c) >= 3:
            for i in range(len(db_name) - 2):
                if db_name[i:i+3] in c:
                    return True
    return False

def find_match_in_titan_data(db_home, db_away, titan_matches):
    for tm in titan_matches:
        h = _match_name(db_home, [tm["home_team"], tm["home_team_trad"], tm["home_team_official"]])
        a = _match_name(db_away, [tm["away_team"], tm["away_team_trad"], tm["away_team_official"]])
        if h and a:
            return tm
    for tm in titan_matches:
        h = _match_name(db_home, [tm["home_team"], tm["home_team_trad"], tm["home_team_official"]])
        if h:
            return tm
    return None
