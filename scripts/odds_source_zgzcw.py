#!/usr/bin/env python3
"""zgzcw.com (中国足彩网) 赔率数据源 - 备选源

JSON API接口，无需WAF绕过。使用竞彩编号(matchNo)与数据库精确匹配。
- lotteryId=23: 比分(sp:30值) + 欧赔(europeSp:3值) + 亚盘(yapan)
- lotteryId=24: 总进球数(sp:8值) + 欧赔 + 亚盘
- lotteryId=25: 半全场(sp:9值) + 欧赔 + 亚盘
"""
import subprocess
import json
import re


# zgzcw lotteryId 映射
# 23=比分, 24=总进球, 25=半全场; 所有页面都包含europeSp(胜平负赔率)
_ZGZCW_SPF_URL = "https://cp.zgzcw.com/lottery/jcplayvs.action?lotteryId=23&isdg=0"
_HEADERS = [
    '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    '-H', 'Accept: application/json, text/plain, */*',
    '-H', 'Referer: https://cp.zgzcw.com/lottery/jcplayvsForJsp.action?lotteryId=23',
]


def _fetch_json(url):
    """请求zgzcw JSON API"""
    try:
        cmd = ['curl', '-s', '--max-time', '15'] + _HEADERS + [url]
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        text = result.stdout.decode('utf-8', errors='replace')
        if len(text) < 50:
            return None
        data = json.loads(text)
        if 'matchInfo' in data:
            return data
        return None
    except Exception as e:
        print(f"  ❌ zgzcw.com 请求失败: {e}")
        return None


# 亚盘盘口文字 → 数值映射
_HANDICAP_TEXT_MAP = {
    '平手': 0, '平手/半球': -0.25, '半球': -0.5, '半球/一球': -0.75,
    '一球': -1, '一球/球半': -1.25, '球半': -1.5, '球半/两球': -1.75,
    '两球': -2, '两球/两球半': -2.25, '两球半': -2.5,
    '受平手/半球': 0.25, '受半球': 0.5, '受半球/一球': 0.75,
    '受一球': 1, '受一球/球半': 1.25, '受球半': 1.5, '受球半/两球': 1.75,
    '受两球': 2,
}


def parse_yapan(yapan_str):
    """解析亚盘字符串 '0.900 半球 0.900' → (upper, handicap_val, lower)"""
    if not yapan_str:
        return None, None, None
    parts = yapan_str.strip().split()
    if len(parts) < 3:
        return None, None, None
    try:
        upper = float(parts[0])
        lower = float(parts[-1])
        handicap_text = ' '.join(parts[1:-1])
        handicap_val = _HANDICAP_TEXT_MAP.get(handicap_text)
        return upper, handicap_val, lower
    except (ValueError, IndexError):
        return None, None, None


def fetch_football_odds():
    """
    从zgzcw.com获取竞彩足球赔率。
    返回: dict of {matchNo: odds_dict}
        matchNo 格式: "周日091", "周一093" 等 (与sporttery相同)
        odds_dict 包含:
            win_odds, draw_odds, lose_odds (float)
            handicap (float, 亚盘让球)
            upper, lower (float, 亚盘上下盘赔率)
            match_home, match_guest (str, 主客队名)
            match_name (str, 联赛名)
            match_start_time (str, 比赛时间)
    """
    data = _fetch_json(_ZGZCW_SPF_URL)
    if not data:
        return {}

    matches = data.get('matchInfo', [])
    if not matches:
        print("  ⚠️ zgzcw.com 无足球数据")
        return {}

    result = {}
    for m in matches:
        match_no = m.get('matchNo', '').strip()
        if not match_no:
            continue

        # 欧赔 (胜平负)
        europe_sp = m.get('europeSp', '').strip().split()
        odds = {}
        if len(europe_sp) >= 3:
            try:
                odds['win_odds'] = float(europe_sp[0])
                odds['draw_odds'] = float(europe_sp[1])
                odds['lose_odds'] = float(europe_sp[2])
            except ValueError:
                pass

        # 亚盘
        yapan_str = m.get('yapan', '').strip()
        upper, handicap, lower = parse_yapan(yapan_str)
        if handicap is not None:
            odds['handicap'] = handicap
            odds['upper'] = upper
            odds['lower'] = lower

        # 队伍名
        odds['match_home'] = m.get('matchHome', '').strip()
        odds['match_guest'] = m.get('matchGuest', '').strip()
        odds['match_name'] = m.get('matchName', '').strip()
        odds['match_start_time'] = m.get('matchStartTime', '').strip()

        if odds:
            result[match_no] = odds

    print(f"  ✅ zgzcw.com 获取 {len(result)} 场足球赔率")
    return result


def match_zgzcw_to_db(missing_matches, zgzcw_odds):
    """
    将zgzcw赔率匹配到数据库比赛。
    利用竞彩编号直接匹配 (match_uid格式: YYYYMMDD_周XNNN → 提取周XNNN)
    
    参数:
        missing_matches: list of (match_uid, sport_type, teams)
        zgzcw_odds: dict of {matchNo: odds_dict}
    返回: dict of {match_uid: odds_dict}
    """
    result = {}
    
    for match_uid, sport_type, teams in missing_matches:
        if sport_type != 'football':
            continue
        
        # 从match_uid提取竞彩编号 (格式: 20260705_周日091 → 周日091)
        parts = match_uid.split('_', 1)
        if len(parts) != 2:
            continue
        match_no = parts[1]
        
        if match_no in zgzcw_odds:
            zgzcw_data = zgzcw_odds[match_no]
            db_odds = {}
            if 'win_odds' in zgzcw_data:
                db_odds['win_odds'] = zgzcw_data['win_odds']
            if 'draw_odds' in zgzcw_data:
                db_odds['draw_odds'] = zgzcw_data['draw_odds']
            if 'lose_odds' in zgzcw_data:
                db_odds['lose_odds'] = zgzcw_data['lose_odds']
            if 'handicap' in zgzcw_data:
                db_odds['handicap'] = zgzcw_data['handicap']
            if db_odds:
                db_odds['_source'] = 'zgzcw.com'
                result[match_uid] = db_odds
                home = zgzcw_data.get('match_home', '?')
                guest = zgzcw_data.get('match_guest', '?')
                print(f"    🔗 zgzcw匹配: {match_no} {home} vs {guest}")
    
    return result
