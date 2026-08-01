#!/usr/bin/env python3
"""500.com (500彩票网) 赔率数据源 - 备选源

同时支持足球和篮球。HTML页面GBK/GB2312编码，curl直接抓取后正则解析。
使用竞彩编号与数据库精确匹配。

足球: trade.500.com/jczq/     → SPF(胜平负) + RQSPF(让球胜平负)
篮球: trade.500.com/jclq/     → SF(胜负) 赔率
"""
import subprocess
import re


_HEADERS = [
    '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    '-H', 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8',
]

# 500.com 足球URL
_FOOTBALL_URL = "https://trade.500.com/jczq/"
# 500.com 篮球URL (默认/单关)
_BASKETBALL_URL = "https://trade.500.com/jclq/"


def _fetch_html(url, encoding='gb2312'):
    """抓取500.com页面"""
    try:
        cmd = ['curl', '-s', '--max-time', '15'] + _HEADERS + [url]
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        html = result.stdout.decode(encoding, errors='replace')
        if len(html) < 1000:
            return None
        return html
    except Exception as e:
        print(f"  ❌ 500.com 请求失败: {e}")
        return None


def _extract_match_no(text):
    """提取竞彩编号 (周X + 3位数字)"""
    m = re.search(r'(周[一二三四五六日]\d{3})', text)
    return m.group(1) if m else None


def _extract_odds_from_concat(odds_str):
    """从拼接的赔率字符串中提取浮点数列表
    500.com格式: "1.603.554.503.053.162.06" → [1.60, 3.55, 4.50, 3.05, 3.16, 2.06]
    """
    # 用正则匹配连续的浮点数
    nums = re.findall(r'\d+\.\d{2}', odds_str)
    return [float(n) for n in nums]


def fetch_football_odds():
    """
    从500.com获取竞彩足球赔率。
    返回: dict of {matchNo: odds_dict}
        matchNo: "周日091" 等
        odds_dict: win_odds, draw_odds, lose_odds, handicap_odds (让球胜/平/负), handicap
    """
    html = _fetch_html(_FOOTBALL_URL)
    if not html:
        return {}

    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    result = {}

    for tr in trs:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', td).strip().replace('\n', ' ').replace('\r', '').replace('\t', ' ').strip() for td in tds]
        clean = [c for c in clean if c]

        if len(clean) < 6:
            continue

        # TD[0] = 竞彩编号
        match_no = _extract_match_no(clean[0])
        if not match_no:
            continue

        odds = {}

        # TD[5] = 拼接赔率 (6个值: SPF胜平负 + RQSPF让球胜平负)
        odds_str = clean[5] if len(clean) > 5 else ''
        odds_list = _extract_odds_from_concat(odds_str)

        if len(odds_list) >= 6:
            # 前3个: 胜平负
            odds['win_odds'] = odds_list[0]
            odds['draw_odds'] = odds_list[1]
            odds['lose_odds'] = odds_list[2]
            # 后3个: 让球胜平负
            odds['rqspf_win'] = odds_list[3]
            odds['rqspf_draw'] = odds_list[4]
            odds['rqspf_lose'] = odds_list[5]
        elif len(odds_list) >= 3:
            odds['win_odds'] = odds_list[0]
            odds['draw_odds'] = odds_list[1]
            odds['lose_odds'] = odds_list[2]

        # TD[3] = 主队名 (可能包含排名如[5])
        home_raw = clean[3] if len(clean) > 3 else ''
        odds['match_home'] = re.sub(r'\[\d+\]', '', home_raw).strip()

        if odds:
            result[match_no] = odds

    print(f"  ✅ 500.com 获取 {len(result)} 场足球赔率")
    return result


def fetch_basketball_odds():
    """
    从500.com获取竞彩篮球赔率。
    返回: dict of {matchNo: odds_dict}
        matchNo: "周六302" 等
        odds_dict: win_odds(主胜), lose_odds(主负)
    """
    html = _fetch_html(_BASKETBALL_URL)
    if not html:
        return {}

    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    result = {}

    for tr in trs:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', td).strip().replace('\n', ' ').replace('\r', '').replace('\t', ' ').strip() for td in tds]
        clean = [c for c in clean if c]

        if len(clean) < 5:
            continue

        # TD[0] = 竞彩编号
        match_no = _extract_match_no(clean[0])
        if not match_no:
            continue

        odds = {}

        # 找赔率值: 最后一个TD通常包含赔率 (如 "1.10 6.03")
        odds_str = clean[-1] if clean else ''
        odds_nums = [float(x) for x in re.findall(r'\d+\.\d{2}', odds_str)]

        if len(odds_nums) >= 2:
            # 篮球胜负赔率: 主负, 主胜 (500.com顺序)
            odds['lose_odds'] = odds_nums[0]  # 主负
            odds['win_odds'] = odds_nums[1]   # 主胜
        elif len(odds_nums) == 1:
            odds['win_odds'] = odds_nums[0]

        # TD[3] = 对阵信息
        matchup = clean[3] if len(clean) > 3 else ''
        vs_match = re.search(r'(.+?)VS(.+)', matchup)
        if vs_match:
            odds['match_home'] = re.sub(r'\[.*?\]', '', vs_match.group(1)).strip()
            odds['match_guest'] = re.sub(r'\[.*?\]', '', vs_match.group(2)).strip()

        # 跳过"未开售"的比赛 (赔率可能为空或无效)
        if '未开售' in ' '.join(clean[4:6]) if len(clean) > 5 else False:
            # 仍然保留，让调用方决定是否使用
            pass

        if odds:
            result[match_no] = odds

    print(f"  ✅ 500.com 获取 {len(result)} 场篮球赔率")
    return result


def match_500_to_db(missing_matches, data_500, sport_type='football'):
    """
    将500.com赔率匹配到数据库比赛。
    利用竞彩编号直接匹配。
    
    参数:
        missing_matches: list of (match_uid, sport_type, teams)
        data_500: dict of {matchNo: odds_dict}
        sport_type: 'football' 或 'basketball'
    返回: dict of {match_uid: odds_dict}
    """
    result = {}

    for match_uid, st, teams in missing_matches:
        if st != sport_type:
            continue

        # 从match_uid提取竞彩编号
        parts = match_uid.split('_', 1)
        if len(parts) != 2:
            continue
        match_no = parts[1]

        if match_no not in data_500:
            continue

        src = data_500[match_no]
        db_odds = {}

        if sport_type == 'football':
            if 'win_odds' in src:
                db_odds['win_odds'] = src['win_odds']
            if 'draw_odds' in src:
                db_odds['draw_odds'] = src['draw_odds']
            if 'lose_odds' in src:
                db_odds['lose_odds'] = src['lose_odds']
        elif sport_type == 'basketball':
            if 'win_odds' in src:
                db_odds['win_odds'] = src['win_odds']
            if 'lose_odds' in src:
                db_odds['lose_odds'] = src['lose_odds']

        if db_odds:
            db_odds['_source'] = '500.com'
            result[match_uid] = db_odds
            home = src.get('match_home', '?')
            guest = src.get('match_guest', '?')
            print(f"    🔗 500.com匹配: {match_no} {home} vs {guest}")

    return result
