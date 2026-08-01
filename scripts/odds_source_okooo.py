#!/usr/bin/env python3
"""okooo.com赔率数据源 - 备用源

当sporttery.cn被WAF封锁时，从okooo.com获取足球赔率作为备选。
数据为GBK编码HTML，通过curl抓取后正则解析。
"""
import subprocess
import re
from datetime import datetime


def fetch_football_odds(date_str):
    """
    从okooo.com获取指定日期的足球赔率
    参数: date_str = "YYYY-MM-DD"
    返回: list of dict, 每个dict包含:
        {
            'home': str,        # 主队名
            'away': str,        # 客队名
            'league': str,      # 联赛名
            'match_time': str,  # 比赛时间
            'odds_w': float,    # 胜赔
            'odds_d': float,    # 平赔
            'odds_l': float,    # 负赔
            'handicap': float,  # 让球数（负数=主队让球）
            'upper': float,     # 上盘赔率
            'lower': float,     # 下盘赔率
        }
    """
    try:
        result = subprocess.run([
            'curl', '-s', '--max-time', '15',
            '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            '-H', 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8',
            '-H', 'Referer: https://www.okooo.com/soccer/match/',
            f'https://www.okooo.com/soccer/match/?date={date_str}'
        ], capture_output=True, timeout=20)

        html = result.stdout.decode('gbk', errors='replace')

        # 检查是否被WAF（返回405或内容太短）
        if len(html) < 5000 or '405' in html[:1000]:
            print(f"  ⚠️ okooo.com {date_str} 被WAF封锁或无数据 (len={len(html)})")
            return []

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        matches = []

        # 亚盘盘口文字转数值
        HANDICAP_MAP = {
            '平手': 0, '平手/半球': -0.25, '半球': -0.5, '半球/一球': -0.75,
            '一球': -1, '一球/球半': -1.25, '球半': -1.5, '球半/两球': -1.75,
            '两球': -2,
            '受平手/半球': 0.25, '受半球': 0.5, '受半球/一球': 0.75,
            '受一球': 1, '受一球/球半': 1.25, '受球半': 1.5,
        }

        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            clean = [re.sub(r'<[^>]+>', '', td).strip().replace('\xa0', ' ') for td in tds]

            if len(clean) < 13:
                continue

            # 找VS位置来定位主客队
            vs_idx = None
            for idx, val in enumerate(clean):
                if val == 'VS' or val == 'vs':
                    vs_idx = idx
                    break

            if vs_idx is None or vs_idx < 1 or vs_idx + 1 >= len(clean):
                continue

            league = clean[0] if len(clean) > 0 else ''
            match_time_str = clean[1] if len(clean) > 1 else ''
            home = clean[vs_idx - 1]
            away = clean[vs_idx + 1]

            # 跳过非数据行
            if not home or not away or home == '主队' or home == '球队':
                continue

            # 欧赔: 通常在VS之后偏移几个位置
            # 根据TD结构: TD[7]=胜赔, TD[8]=平赔, TD[9]=负赔 (基于VS前的索引体系)
            # 但实际位置需要根据VS的位置来推算
            odds_w = odds_d = odds_l = None
            upper = lower = None
            handicap = None

            # 尝试从固定索引位置获取欧赔（基于标准布局）
            if len(clean) > 9:
                for candidate_idx in [7, 8, 9]:
                    val = clean[candidate_idx] if candidate_idx < len(clean) else None
                    if val and re.match(r'^\d+\.?\d*$', val):
                        pass

            # 更灵活的方式：从VS之后找连续的数字赔率
            odds_candidates = []
            for i in range(vs_idx + 2, min(vs_idx + 15, len(clean))):
                val = clean[i]
                if re.match(r'^\d+\.\d{2}$', val):
                    odds_candidates.append((i, float(val)))

            if len(odds_candidates) >= 3:
                odds_w = odds_candidates[0][1]
                odds_d = odds_candidates[1][1]
                odds_l = odds_candidates[2][1]

            # 验证赔率合理性（欧赔一般在1.01~50之间）
            if odds_w and odds_d and odds_l:
                if not (1.01 <= odds_w <= 50 and 1.01 <= odds_d <= 50 and 1.01 <= odds_l <= 50):
                    odds_w = odds_d = odds_l = None

            # 亚盘部分: 找盘口文字（在欧赔之后）
            handicap_raw = None
            for i in range(vs_idx + 2, len(clean)):
                val = clean[i]
                if val in HANDICAP_MAP:
                    handicap_raw = val
                    handicap = HANDICAP_MAP[val]
                    # 上盘赔率在手盘口前面
                    if i > 0 and re.match(r'^\d+\.\d{2}$', clean[i - 1]):
                        upper = float(clean[i - 1])
                    # 下盘赔率在手盘口后面
                    if i + 1 < len(clean) and re.match(r'^\d+\.\d{2}$', clean[i + 1]):
                        lower = float(clean[i + 1])
                    break

            if not odds_w and not handicap:
                continue

            matches.append({
                'home': home,
                'away': away,
                'league': league,
                'match_time': match_time_str,
                'odds_w': odds_w,
                'odds_d': odds_d,
                'odds_l': odds_l,
                'handicap': handicap,
                'upper': upper,
                'lower': lower,
            })

        print(f"  ✅ okooo.com {date_str} 获取 {len(matches)} 场比赛赔率")
        return matches

    except Exception as e:
        print(f"  ❌ okooo.com 获取失败: {e}")
        return []


def fuzzy_match_team(db_team_name, okooo_team_name):
    """模糊匹配队伍名（处理竞彩和okooo命名差异）"""
    a = db_team_name.strip()
    b = okooo_team_name.strip()

    # 完全匹配
    if a == b:
        return True
    # 子串匹配
    if a in b or b in a:
        return True
    # 去FC后缀
    a_clean = a.replace('FC', '').strip()
    b_clean = b.replace('FC', '').strip()
    if a_clean and b_clean and (a_clean in b_clean or b_clean in a_clean):
        return True
    # 去常见后缀变体
    for suffix in ['FC', 'CF', 'United', 'City', 'SC', 'AC']:
        a_clean = a.replace(suffix, '').strip()
        b_clean = b.replace(suffix, '').strip()
        if a_clean and b_clean and (a_clean in b_clean or b_clean in a_clean):
            return True
    # 字符重叠度（处理中文翻译差异）
    if len(a) >= 2 and len(b) >= 2:
        overlap = len(set(a) & set(b))
        ratio = overlap / max(len(a), len(b))
        if ratio > 0.6:
            return True
    return False


def match_okooo_to_db(missing_matches, okooo_odds):
    """
    将okooo赔率匹配到数据库比赛
    参数:
        missing_matches: list of (match_uid, sport_type, teams) - 缺赔率的比赛
        okooo_odds: list of dict - okooo返回的赔率数据
    返回: dict of {match_uid: odds_dict}
        odds_dict的key与数据库字段对齐: win_odds/draw_odds/lose_odds/handicap等
    """
    result = {}
    used_indices = set()

    for match_uid, sport_type, teams in missing_matches:
        if sport_type != 'football':
            continue

        if not teams or 'VS' not in str(teams):
            continue

        parts = str(teams).split('VS')
        if len(parts) != 2:
            continue
        db_home, db_away = parts[0].strip(), parts[1].strip()

        for i, odds in enumerate(okooo_odds):
            if i in used_indices:
                continue
            if (fuzzy_match_team(db_home, odds['home']) and
                fuzzy_match_team(db_away, odds['away'])):
                # 转换为数据库字段格式
                db_odds = {}
                if odds.get('odds_w'):
                    db_odds['win_odds'] = odds['odds_w']
                if odds.get('odds_d'):
                    db_odds['draw_odds'] = odds['odds_d']
                if odds.get('odds_l'):
                    db_odds['lose_odds'] = odds['odds_l']
                if odds.get('handicap') is not None:
                    db_odds['handicap'] = odds['handicap']

                if db_odds:
                    result[match_uid] = db_odds
                    used_indices.add(i)
                    print(f"    🔗 okooo匹配: {db_home}≈{odds['home']} / {db_away}≈{odds['away']}")
                break

    return result


def fetch_okooo_multi_day(days=3):
    """
    获取多天的okooo赔率数据
    参数: days - 获取从今天起几天的数据
    返回: list of dict (所有天的赔率合并)
    """
    from datetime import timedelta
    all_odds = []
    today = datetime.now().date()

    for i in range(days):
        date_str = (today + timedelta(days=i)).strftime('%Y-%m-%d')
        odds = fetch_football_odds(date_str)
        if odds:
            all_odds.extend(odds)

    return all_odds
