#!/usr/bin/env python3
"""basketball_score_client - 多数据源篮球比分抓取（容错机制）
数据源优先级：ESPN(WNBA) > 体彩官网 > NBA CDN > 球探网篮球
"""
import re, sys, json, requests
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

def _safe_int(val, default=0):
    if val is None or val == "" or val == "null":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _normalize_team(name):
    if not name:
        return ""
    name = name.strip()
    for prefix in ["FC ", "fc "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name

def _match_team(name1, name2):
    if not name1 or not name2:
        return False
    n1 = name1.strip()
    n2 = name2.strip()
    if n1 == n2:
        return True
    if n1 in n2 or n2 in n1:
        return True
    ALIASES = {
        "飞马": "飞翼", "飞翼": "飞马",
        "女武神": "金州女武神",
    }
    for short, full in ALIASES.items():
        if (short in n1 and full in n2) or (full in n1 and short in n2):
            return True
    shorter, longer = (n1, n2) if len(n1) <= len(n2) else (n2, n1)
    if len(shorter) >= 2:
        for length in range(min(len(shorter), 4), 1, -1):
            for i in range(len(shorter) - length + 1):
                sub = shorter[i:i+length]
                if sub in longer:
                    return True
    return False

def fetch_espn(date_str):
    results = []
    espn_date = date_str.replace("-", "")
    for league in ["wnba", "nba"]:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard?dates={espn_date}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"[ESPN-{league}] HTTP {resp.status_code}", file=sys.stderr)
                continue
            data = resp.json()
            events = data.get("events", [])
            for event in events:
                competitions = event.get("competitions", [])
                if not competitions:
                    continue
                comp = competitions[0]
                status_type = comp.get("status", {}).get("type", {})
                if status_type.get("completed") != True:
                    continue
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue
                home = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not home or not away:
                    continue
                results.append({
                    "home_team": home.get("team", {}).get("displayName", ""),
                    "away_team": away.get("team", {}).get("displayName", ""),
                    "home_score": _safe_int(home.get("score")),
                    "away_score": _safe_int(away.get("score")),
                    "status": "已完赛",
                    "source": f"espn-{league}"
                })
            print(f"[ESPN-{league}] {date_str}: 找到 {len([r for r in results if r['source'] == f'espn-{league}'])} 场完赛", file=sys.stderr)
        except Exception as e:
            print(f"[ESPN-{league}] 错误: {e}", file=sys.stderr)
    return results

def fetch_sporttery(date_str):
    try:
        url = "https://webapi.sporttery.cn/gateway/jc/basketball/getMatchPageV1.qry"
        params = {"matchPage": 1, "matchBeginDate": date_str, "matchEndDate": date_str}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[体彩] HTTP {resp.status_code}", file=sys.stderr)
            return []
        data = resp.json()
        if data.get("value") is None:
            print(f"[体彩] 无数据", file=sys.stderr)
            return []
        match_list = data.get("value", {}).get("matchInfoList", [])
        if not match_list:
            match_list = data.get("value", {}).get("list", [])
        results = []
        for match in match_list:
            home_score = _safe_int(match.get("homeScore", 0) or match.get("home_score", 0))
            away_score = _safe_int(match.get("awayScore", 0) or match.get("away_score", 0))
            if home_score == 0 and away_score == 0:
                continue
            results.append({
                "home_team": match.get("homeTeamAbb", "") or match.get("home_team", ""),
                "away_team": match.get("awayTeamAbb", "") or match.get("away_team", ""),
                "home_score": home_score,
                "away_score": away_score,
                "status": "已完赛",
                "source": "sporttery"
            })
        print(f"[体彩] {date_str}: {len(results)}场有比分", file=sys.stderr)
        return results
    except Exception as e:
        print(f"[体彩] 错误: {e}", file=sys.stderr)
        return []

def fetch_nba_cdn(date_str):
    try:
        url = f"https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
        resp = requests.get(url, headers={**HEADERS, "Origin": "https://www.nba.com", "Referer": "https://www.nba.com/"}, timeout=15)
        if resp.status_code != 200:
            print(f"[NBA-CDN] HTTP {resp.status_code}", file=sys.stderr)
            return []
        data = resp.json()
        results = []
        league_dates = data.get("leagueSchedule", {}).get("dates", []) if "leagueSchedule" in data else data.get("dates", [])
        for day in league_dates:
            games = day.get("games", []) if isinstance(day, dict) else []
            for game in games:
                game_date = game.get("gameDate", "") or game.get("gameTimeUTC", "")
                if date_str not in game_date:
                    continue
                game_status = game.get("gameStatus", 0) or game.get("statusNum", 0)
                if game_status != 3:
                    continue
                home = game.get("homeTeam", {})
                away = game.get("awayTeam", {})
                results.append({
                    "home_team": home.get("teamName", "") or home.get("name", ""),
                    "away_team": away.get("teamName", "") or away.get("name", ""),
                    "home_score": _safe_int(home.get("score", 0)),
                    "away_score": _safe_int(away.get("score", 0)),
                    "status": "已完赛",
                    "source": "nba-cdn"
                })
        print(f"[NBA-CDN] {date_str}: {len(results)}场完赛", file=sys.stderr)
        return results
    except Exception as e:
        print(f"[NBA-CDN] 错误: {e}", file=sys.stderr)
        return []

def fetch_titan_basketball(date_str):
    try:
        from datetime import datetime as dt
        now = dt.utcnow() + timedelta(hours=8)
        url = f"https://bf.titan007.com/nba_date.aspx?date={date_str}&h={now.hour}&m={now.minute}&s=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://bf.titan007.com/NBA_SC.aspx",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "gb2312"
        xml_text = resp.text
        results = []
        for m in re.finditer(r'<!\[CDATA\[(.+?)\]\]>', xml_text, re.DOTALL):
            fields = m.group(1).split('^')
            if len(fields) < 13:
                continue
            status_code = _safe_int(fields[5])
            if status_code != -1:
                continue
            home_info = fields[8]
            away_info = fields[10]
            home_team = re.sub(r'\[\d+\]', '', home_info.split(',')[0]).strip()
            away_team = re.sub(r'\[\d+\]', '', away_info.split(',')[0]).strip()
            home_score = _safe_int(fields[11])
            away_score = _safe_int(fields[12])
            if home_score == 0 and away_score == 0:
                continue
            results.append({
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "status": "已完赛",
                "source": "titan-basketball"
            })
        print(f"[球探篮球] {date_str}: {len(results)}场完赛", file=sys.stderr)
        return results
    except Exception as e:
        print(f"[球探篮球] 错误: {e}", file=sys.stderr)
        return []

def fetch_okooo(date_str):
    try:
        date_compact = date_str.replace("-", "")
        url = f"https://www.okooo.com/basketball/score/{date_compact}/"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[爱波] HTTP {resp.status_code}", file=sys.stderr)
            return []
        resp.encoding = "utf-8"
        html = resp.text
        results = []
        pattern = r'class="[^"]*team[^"]*"[^>]*>([^<]+)</[^>]*>.*?(\d+)\s*[-:]\s*(\d+).*?class="[^"]*team[^"]*"[^>]*>([^<]+)</[^>]*>'
        for m in re.finditer(pattern, html, re.DOTALL):
            home = m.group(1).strip()
            home_score = _safe_int(m.group(2))
            away_score = _safe_int(m.group(3))
            away = m.group(4).strip()
            if home and away and (home_score > 0 or away_score > 0):
                results.append({
                    "home_team": home,
                    "away_team": away,
                    "home_score": home_score,
                    "away_score": away_score,
                    "status": "已完赛",
                    "source": "okooo"
                })
        print(f"[爱波] {date_str}: {len(results)}场完赛", file=sys.stderr)
        return results
    except Exception as e:
        print(f"[爱波] 错误: {e}", file=sys.stderr)
        return []

def fetch_scores(date_str, sources=None):
    if sources is None:
        sources = ["espn", "sporttery", "titan-basketball", "nba-cdn", "okooo"]
    source_funcs = {
        "espn": fetch_espn,
        "sporttery": fetch_sporttery,
        "titan-basketball": fetch_titan_basketball,
        "nba-cdn": fetch_nba_cdn,
        "okooo": fetch_okooo,
    }
    all_matches = []
    seen_games = set()
    for source in sources:
        func = source_funcs.get(source)
        if not func:
            continue
        try:
            matches = func(date_str)
            for m in matches:
                key = tuple(sorted([m["home_team"][:6], m["away_team"][:6]]))
                if key not in seen_games:
                    seen_games.add(key)
                    all_matches.append(m)
        except Exception as e:
            print(f"[{source}] 跳过: {e}", file=sys.stderr)
    print(f"[篮球总分] {date_str}: 总计 {len(all_matches)} 场（{len(sources)}个数据源）", file=sys.stderr)
    return all_matches

def find_match_in_data(db_home, db_away, matches):
    if not matches:
        return None
    for m in matches:
        if db_home == m["home_team"] and db_away == m["away_team"]:
            return m
    for m in matches:
        if db_home == m["away_team"] and db_away == m["home_team"]:
            return {
                "home_team": db_home,
                "away_team": db_away,
                "home_score": m["away_score"],
                "away_score": m["home_score"],
                "status": m["status"],
                "source": m["source"] + "(rev)"
            }
    for m in matches:
        h = _match_team(db_home, m["home_team"])
        a = _match_team(db_away, m["away_team"])
        if h and a:
            return m
    for m in matches:
        h = _match_team(db_home, m["away_team"])
        a = _match_team(db_away, m["home_team"])
        if h and a:
            return {
                "home_team": db_home,
                "away_team": db_away,
                "home_score": m["away_score"],
                "away_score": m["home_score"],
                "status": m["status"],
                "source": m["source"] + "(rev)"
            }
    return None

if __name__ == "__main__":
    test_date = sys.argv[1] if len(sys.argv) > 1 else (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
    print(f"测试日期: {test_date}", file=sys.stderr)
    matches = fetch_scores(test_date)
    print(f"\n共 {len(matches)} 场比赛:", file=sys.stderr)
    for m in matches[:10]:
        print(f"  {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']} ({m['source']})", file=sys.stderr)
