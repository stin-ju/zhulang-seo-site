#!/usr/bin/env python3
"""titan007_client - 从 titan007 抓取完场比分
足球: cp.titan007.com (竞彩页面)
篮球: bf.titan007.com (篮球赛程页面)
"""
import re, sys, requests
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
FOOTBALL_TYPE_IDS = {"football": "101", "basketball": "102"}

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
        
        # 主队名: "明尼苏达天猫[1],明尼苏达天貓[1],Minnesota Lynx[1]"
        home_parts = parts[8].split(',')
        home_name = re.sub(r'\[\d+\]', '', home_parts[0]).strip() if home_parts else ''
        home_trad = re.sub(r'\[\d+\]', '', home_parts[1]).strip() if len(home_parts) > 1 else ''
        home_en = re.sub(r'\[\d+\]', '', home_parts[2]).strip() if len(home_parts) > 2 else ''
        
        # 客队名
        away_parts = parts[10].split(',')
        away_name = re.sub(r'\[\d+\]', '', away_parts[0]).strip() if away_parts else ''
        away_trad = re.sub(r'\[\d+\]', '', away_parts[1]).strip() if len(away_parts) > 1 else ''
        away_en = re.sub(r'\[\d+\]', '', away_parts[2]).strip() if len(away_parts) > 2 else ''
        
        try:
            home_score = int(parts[11])
            away_score = int(parts[12])
        except (ValueError, IndexError):
            continue
        
        # 每节得分 → 半场得分
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


def fetch_over_scores(sport, date_str):
    """从 bf.titan007.com 获取完场比分（覆盖全部比赛，不限于竞彩）"""
    import re
    date_fmt = date_str.replace('-', '')
    
    if sport == 'football':
        url = 'https://bf.titan007.com/football/Over_' + date_fmt + '.htm'
    elif sport == 'basketball':
        url = 'https://bf.titan007.com/basketball/Over_' + date_fmt + '.htm'
    else:
        return {}
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://bf.titan007.com/',
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = 'gb2312'
        html = resp.text
    except Exception as e:
        print('  [bf_titan007] request failed:', e)
        return {}
    
    results = {}
    rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 6:
            continue
        
        score_text = re.sub(r'<[^>]+>', '', cells[4]).strip()
        score_match = re.match(r'(\d+)\s*[-:]\s*(\d+)', score_text)
        if not score_match:
            continue
        
        home_score = int(score_match.group(1))
        away_score = int(score_match.group(2))
        
        home_raw = re.sub(r'<[^>]+>', '', cells[3]).strip()
        home_name = re.sub(r'\[[^\]]*\]', '', home_raw).strip()
        
        away_raw = re.sub(r'<[^>]+>', '', cells[5]).strip()
        away_name = re.sub(r'\[[^\]]*\]', '', away_raw).strip()
        
        if home_name and away_name:
            results[home_name] = (home_score, away_name, away_score)
    
    print('  [bf_titan007]', sport, date_str + ': got', len(results), 'matches')
    return results

def fetch_scores(sport="football", date_str=None):
    """获取指定日期和运动类型的完场比分
    sport: "football" 或 "basketball"
    date_str: "2026-8-3" 或 "2026-08-03" 格式
    """
    if date_str is None:
        now = datetime.utcnow() + timedelta(hours=8)
        date_str = f"{now.year}-{now.month}-{now.day}"
    
    if sport == "basketball":
        return _fetch_basketball_scores(date_str)
    else:
        return _fetch_football_scores(date_str)

def _fetch_football_scores(date_str):
    """从 cp.titan007.com 获取足球比分"""
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
    """从 bf.titan007.com 获取篮球比分"""
    # 确保日期格式正确: 2026-08-03
    if len(date_str) == 9 and date_str[5] == '0':
        # "2026-8-3" → "2026-08-03"
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
    completed = [m for m in all_matches if m["status_code"] == "4"]  # 4=完场
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
        # 检查别名映射
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
    # 精确匹配（主客队都匹配）
    for tm in titan_matches:
        h = _match_name(db_home, [tm["home_team"], tm["home_team_trad"], tm.get("home_team_official", "")])
        a = _match_name(db_away, [tm["away_team"], tm["away_team_trad"], tm.get("away_team_official", "")])
        if h and a:
            return tm
    # 宽松匹配（只匹配主队）
    for tm in titan_matches:
        h = _match_name(db_home, [tm["home_team"], tm["home_team_trad"], tm.get("home_team_official", "")])
        if h:
            return tm
    return None
