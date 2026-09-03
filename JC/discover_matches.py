#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""
自动发现竞彩新比赛并入库（赔率完整版 v3）

核心架构:
  1. 发现层: uniform 端点 → 获取所有比赛(含未开售)
  2. 赔率层: jc 端点 → 获取在售比赛的赔率
  3. 补全层: 对已入库但缺赔率的比赛，在开售后自动补全

API端点:
  足球 uniform: /gateway/uniform/football/getMatchListV1.qry  (全量比赛列表)
  足球 jc:      /gateway/jc/football/getMatchCalculatorV1.qry (在售+赔率)
  篮球 uniform: /gateway/uniform/basketball/getMatchListV1.qry (全量比赛列表)
  篮球 jc:      /gateway/jc/basketball/getMatchCalculatorV1.qry (在售+赔率)

用法:
  python3 discover_matches.py              # 发现+赔率更新
  python3 discover_matches.py --verify     # 仅校验不入库
  python3 discover_matches.py --odds-only  # 仅补全赔率(不发现新比赛)
"""
import os
import sys
import json
import time
import re

# ====== psycopg2 自愈逻辑 ======
import importlib, subprocess, shutil
try:
    import psycopg2
    psycopg2.__version__
    from psycopg2._psycopg import __file__ as _test
except Exception:
    _target = '/opt/bytefaas/site-packages' if __import__('os').path.exists('/opt/bytefaas/site-packages') else None
    _pip = [__import__('sys').executable, '-m', 'pip', 'install', 'psycopg2-binary', '--no-cache-dir', '--force-reinstall']
    if _target:
        for _p in [_target+'/psycopg2', _target+'/psycopg2_binary']:
            if __import__('os').path.isdir(_p): shutil.rmtree(_p, ignore_errors=True)
        _pip += ['--target', _target]
        if _target not in __import__('sys').path: __import__('sys').path.insert(0, _target)
    subprocess.check_call(_pip, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _m in list(__import__('sys').modules):
        if 'psycopg2' in _m: del __import__('sys').modules[_m]
    import psycopg2
# ====== psycopg2 自愈结束 ======

from datetime import datetime, timedelta

from sporttery_client import api_get
from odds_source_okooo import fetch_football_odds as okooo_fetch, match_okooo_to_db, fetch_okooo_multi_day
from odds_source_zgzcw import fetch_football_odds as zgzcw_fetch, match_zgzcw_to_db
from odds_source_500 import fetch_football_odds as fetch500_fb, fetch_basketball_odds as fetch500_bk, match_500_to_db

DB_URL = os.environ.get('DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

WEEKDAY_CN = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}


def safe_float(val):
    """安全转float，失败返回None"""
    if val is None or val == '' or val == '-':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def make_match_uid(match_date_str, match_num):
    """生成 match_uid = YYYYMMDD_体彩编号"""
    date_clean = str(match_date_str).replace('-', '')[:8]
    if len(date_clean) != 8 or not date_clean.isdigit():
        date_clean = datetime.now().strftime('%Y%m%d')
    return f"{date_clean}_{match_num}"


def matchnum_to_id(match_num_str):
    """将体彩编号转为数据库ID"""
    if not match_num_str:
        return None
    if re.match(r'^周[一二三四五六日]\d{3}$', str(match_num_str)):
        return match_num_str
    s = str(match_num_str)
    if len(s) >= 3 and s[0].isdigit():
        day_idx = int(s[0]) - 1
        num = s[1:]
        weekday = WEEKDAY_CN.get(day_idx, f'周{day_idx+1}')
        return f"{weekday}{num}"
    return match_num_str


# ============================================================
# 第一层: 比赛发现 (uniform 端点, 全量) + 赔率提取
# ============================================================

def parse_uniform_odds_list(odds_list, sport_type='football'):
    """
    解析 uniform 端点 oddsList 中的赔率数据。
    uniform 的 oddsList 直接包含每个玩法的赔率，不依赖 jc 端点。

    足球:
      HAD → win_odds/draw_odds/lose_odds (胜平负)
      HHAD → handicap_win/draw/lose_odds + handicap (让球胜平负)

    篮球:
      MNL → win_odds/lose_odds (胜负)
      HDC → spread_odds + spread_line (让分)
      HILO → total_points_odds + total_line (大小分)
    """
    odds = {}
    if not odds_list:
        return odds

    for pool in odds_list:
        pool_code = pool.get('poolCode', '')

        if sport_type == 'football':
            if pool_code == 'HAD':
                # 胜平负
                w = safe_float(pool.get('h'))
                d = safe_float(pool.get('d'))
                l = safe_float(pool.get('a'))
                if w: odds['win_odds'] = w
                if d: odds['draw_odds'] = d
                if l: odds['lose_odds'] = l
            elif pool_code == 'HHAD':
                # 让球胜平负
                w = safe_float(pool.get('h'))
                d = safe_float(pool.get('d'))
                l = safe_float(pool.get('a'))
                if w: odds['handicap_win_odds'] = w
                if d: odds['handicap_draw_odds'] = d
                if l: odds['handicap_lose_odds'] = l
                gv = pool.get('goalLine')
                if gv: odds['handicap'] = safe_float(gv)

        elif sport_type == 'basketball':
            if pool_code == 'MNL':
                # 胜负（纯胜/负）
                w = safe_float(pool.get('h'))
                l = safe_float(pool.get('a'))
                if w: odds['win_odds'] = w
                if l: odds['lose_odds'] = l
            elif pool_code == 'HDC':
                # 让分胜负
                h = safe_float(pool.get('h'))
                a = safe_float(pool.get('a'))
                if h is not None or a is not None:
                    odds['spread_odds'] = json.dumps({'home': h, 'away': a}, ensure_ascii=False)
                gv = pool.get('goalLine')
                if gv:
                    # goalLine 格式: "-4.50" 或 "+4.50"
                    odds['spread_line'] = safe_float(gv)
            elif pool_code == 'HILO':
                # 大小分
                over = safe_float(pool.get('h'))
                under = safe_float(pool.get('a'))
                if over is not None or under is not None:
                    odds['total_points_odds'] = json.dumps({'over': over, 'under': under}, ensure_ascii=False)
                gv = pool.get('goalLine')
                if gv:
                    odds['total_line'] = safe_float(gv)

    return odds


def discover_football_matches():
    """
    从 uniform 端点发现所有足球比赛（含未开售）。
    同时从 oddsList 提取赔率作为 jc 端点的补充。
    """
    url = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchListV1.qry?clientCode=3001"
    data = api_get(url)
    if not data or data.get('errorCode') != '0':
        print("  ⚠️ 足球 uniform API 无数据")
        return []

    matches = []
    seen_uids = set()

    for group in data.get('value', {}).get('matchInfoList', []):
        for m in group.get('subMatchList', []):
            match_num = m.get('matchNumStr', '')
            match_date = m.get('matchDate', '')
            uid = make_match_uid(match_date, match_num)

            if uid in seen_uids:
                continue
            seen_uids.add(uid)

            match_time_str = m.get('matchTime', '')
            full_time = ''
            if match_date and match_time_str:
                full_time = f"{match_date} {match_time_str}"

            # 从 oddsList 提取赔率（uniform 端点自带）
            uniform_odds = parse_uniform_odds_list(m.get('oddsList', []), sport_type='football')

            matches.append({
                'matchId': m.get('matchId'),
                'matchNum': match_num,
                'matchDate': match_date,
                'matchTime': full_time,
                'home': m.get('homeTeamAbbName', ''),
                'away': m.get('awayTeamAbbName', ''),
                'league': m.get('leagueAbbName', ''),
                'matchStatus': m.get('matchStatus', ''),
                'match_uid': uid,
                'sport_type': 'football',
                'source': 'sporttery.cn/uniform',
                'uniform_odds': uniform_odds  # uniform 端点直接提取的赔率
            })

    return matches


def discover_basketball_matches():
    """
    从 uniform 端点发现所有篮球比赛（含未开售）。
    同时从 oddsList 提取赔率——这是解决篮球赔率缺失的关键！
    uniform 端点直接返回 MNL/HDC/HILO 赔率，无需依赖 jc 端点。
    """
    url = "https://webapi.sporttery.cn/gateway/uniform/basketball/getMatchListV1.qry?clientCode=3001"
    data = api_get(url)
    if not data or data.get('errorCode') != '0':
        print("  ⚠️ 篮球 uniform API 无数据")
        return []

    matches = []
    seen_uids = set()

    for group in data.get('value', {}).get('matchInfoList', []):
        for m in group.get('subMatchList', []):
            match_num = m.get('matchNumStr', '')
            match_date = m.get('matchDate', '')
            uid = make_match_uid(match_date, match_num)

            if uid in seen_uids:
                continue
            seen_uids.add(uid)

            match_time_str = m.get('matchTime', '')
            full_time = ''
            if match_date and match_time_str:
                full_time = f"{match_date} {match_time_str}"

            # 从 oddsList 提取赔率（关键！直接解决篮球赔率缺失）
            uniform_odds = parse_uniform_odds_list(m.get('oddsList', []), sport_type='basketball')

            matches.append({
                'matchId': m.get('matchId'),
                'matchNum': match_num,
                'matchDate': match_date,
                'matchTime': full_time,
                'home': m.get('homeTeamAbbName', ''),   # uniform API里home是主队
                'away': m.get('awayTeamAbbName', ''),    # away是客队
                'league': m.get('leagueAbbName', ''),
                'matchStatus': m.get('matchStatus', ''),
                'match_uid': uid,
                'sport_type': 'basketball',
                'source': 'sporttery.cn/uniform',
                'uniform_odds': uniform_odds  # uniform 端点直接提取的赔率
            })

    return matches


# ============================================================
# 第二层: 赔率获取 (jc 端点, 含赔率)
# ============================================================

def parse_football_odds(m):
    """从 jc/football 的 subMatch 中提取赔率"""
    odds = {}

    # HAD = 胜平负
    had = m.get('had', {})
    if had:
        w = safe_float(had.get('h'))
        d = safe_float(had.get('d'))
        l = safe_float(had.get('a'))
        if w: odds['win_odds'] = w
        if d: odds['draw_odds'] = d
        if l: odds['lose_odds'] = l

    # HHAD = 让球胜平负
    hhad = m.get('hhad', {})
    if hhad:
        w = safe_float(hhad.get('h'))
        d = safe_float(hhad.get('d'))
        l = safe_float(hhad.get('a'))
        if w: odds['handicap_win_odds'] = w
        if d: odds['handicap_draw_odds'] = d
        if l: odds['handicap_lose_odds'] = l
        gv = hhad.get('goalLineValue')
        if gv: odds['handicap'] = safe_float(gv)

    # TTG = 总进球数
    ttg = m.get('ttg', {})
    if ttg:
        goals = {}
        idx_map = {'a': '0', 'b': '1', 'c': '2', 'd': '3', 'e': '4', 'f': '5', 'g': '6+'}
        for key, label in idx_map.items():
            if key in ttg and ttg[key]:
                goals[label] = safe_float(ttg[key])
        if goals:
            odds['goals_odds'] = json.dumps(goals, ensure_ascii=False)

    # HAFU = 半全场
    hafu = m.get('hafu', {})
    if hafu:
        hf = {}
        keys_map = {
            'a': '胜胜', 'b': '胜平', 'c': '胜负',
            'd': '平胜', 'e': '平平', 'f': '平负',
            'g': '负胜', 'h': '负平', 'i': '负负'
        }
        for key, label in keys_map.items():
            if key in hafu and hafu[key]:
                hf[label] = safe_float(hafu[key])
        if hf:
            odds['half_full_odds'] = json.dumps(hf, ensure_ascii=False)

    # CRS = 比分
    crs = m.get('crs', {})
    if crs:
        scores = {}
        for key, val in crs.items():
            if key.startswith(('a','b','c','d','e','f','g','h','i','j','k','l','m','n','o')) and val:
                scores[key] = safe_float(val)
        if scores:
            odds['score_odds'] = json.dumps(scores, ensure_ascii=False)

    return odds


def parse_basketball_odds(m):
    """从 jc/basketball 的 subMatch 中提取赔率"""
    odds = {}

    # mnl = 胜负（纯胜/负）
    mnl = m.get('mnl', {})
    if mnl:
        w = safe_float(mnl.get('h'))
        l = safe_float(mnl.get('a'))
        if w: odds['win_odds'] = w
        if l: odds['lose_odds'] = l

    # hdc = 让分胜负
    hdc = m.get('hdc', {})
    if hdc:
        h = safe_float(hdc.get('h'))
        a = safe_float(hdc.get('a'))
        if h is not None or a is not None:
            odds['spread_odds'] = json.dumps({'home': h, 'away': a}, ensure_ascii=False)
        gv = hdc.get('goalLineValue')
        if gv: odds['spread_line'] = safe_float(gv)

    # hilo = 大小分
    hilo = m.get('hilo', {})
    if hilo:
        over = safe_float(hilo.get('h'))
        under = safe_float(hilo.get('l'))
        if over is not None or under is not None:
            odds['total_points_odds'] = json.dumps({'over': over, 'under': under}, ensure_ascii=False)
        gv = hilo.get('goalLineValue')
        if gv: odds['total_line'] = safe_float(gv)

    # wnm = 胜分差
    wnm = m.get('wnm', {})
    if wnm:
        diff_ranges = {}
        for key, val in wnm.items():
            if key.startswith('l') and key[1:].isdigit() and val:
                diff_ranges[key] = safe_float(val)
        if diff_ranges:
            odds['score_diff_odds'] = json.dumps(diff_ranges, ensure_ascii=False)

    return odds


def fetch_uniform_all_odds():
    """
    从 uniform 端点获取所有比赛（足球+篮球）的赔率。
    uniform 端点直接返回 oddsList，不依赖 jc 端点。
    返回: {match_uid: odds_dict}
    """
    odds_map = {}

    # 足球 uniform
    fb_url = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchListV1.qry?clientCode=3001"
    fb_data = api_get(fb_url)
    if fb_data and fb_data.get('errorCode') == '0':
        for group in fb_data.get('value', {}).get('matchInfoList', []):
            for m in group.get('subMatchList', []):
                match_num = m.get('matchNumStr', '')
                match_date = m.get('matchDate', '')
                uid = make_match_uid(match_date, match_num)
                odds = parse_uniform_odds_list(m.get('oddsList', []), sport_type='football')
                if odds:
                    odds_map[uid] = odds

    # 篮球 uniform
    bk_url = "https://webapi.sporttery.cn/gateway/uniform/basketball/getMatchListV1.qry?clientCode=3001"
    bk_data = api_get(bk_url)
    if bk_data and bk_data.get('errorCode') == '0':
        for group in bk_data.get('value', {}).get('matchInfoList', []):
            for m in group.get('subMatchList', []):
                match_num = m.get('matchNumStr', '')
                match_date = m.get('matchDate', '')
                uid = make_match_uid(match_date, match_num)
                odds = parse_uniform_odds_list(m.get('oddsList', []), sport_type='basketball')
                if odds:
                    odds_map[uid] = odds

    return odds_map


def fetch_all_odds():
    """从 jc 端点获取所有在售比赛的赔率，返回 {match_uid: odds_dict}"""
    odds_map = {}
    today = datetime.now().date()

    # 足球赔率
    for i in range(5):
        date_str = (today + timedelta(days=i)).strftime('%Y-%m-%d')
        url = f"https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?clientCode=3001&matchDay={date_str}"
        data = api_get(url)
        if not data or data.get('errorCode') != '0':
            continue
        seen_today = set()
        for group in data.get('value', {}).get('matchInfoList', []):
            for m in group.get('subMatchList', []):
                match_num = m.get('matchNumStr', '') or m.get('matchNum', '')
                match_date = m.get('matchDate', '')
                uid = make_match_uid(match_date, match_num)
                if uid in seen_today:
                    continue
                seen_today.add(uid)
                odds = parse_football_odds(m)
                if odds:
                    odds_map[uid] = odds
        time.sleep(0.2)

    # 篮球赔率
    for i in range(5):
        date_str = (today + timedelta(days=i)).strftime('%Y-%m-%d')
        url = f"https://webapi.sporttery.cn/gateway/jc/basketball/getMatchCalculatorV1.qry?clientCode=3001&matchDay={date_str}"
        data = api_get(url)
        if not data or data.get('errorCode') != '0':
            continue
        seen_today = set()
        for group in data.get('value', {}).get('matchInfoList', []):
            for m in group.get('subMatchList', []):
                match_num = m.get('matchNumStr', '') or m.get('matchNum', '')
                match_date = m.get('matchDate', '')
                uid = make_match_uid(match_date, match_num)
                if uid in seen_today:
                    continue
                seen_today.add(uid)
                odds = parse_basketball_odds(m)
                if odds:
                    odds_map[uid] = odds
        time.sleep(0.2)

    return odds_map


# ============================================================
# 数据库操作
# ============================================================

def get_db():
    conn = psycopg2.connect(DB_URL)
    conn.set_client_encoding('UTF8')
    return conn


def get_existing_match_uids():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT match_uid FROM matches WHERE match_uid IS NOT NULL")
        uids = set(r[0] for r in cur.fetchall())
    except Exception:
        conn.rollback()
        cur.execute("SELECT id FROM matches")
        uids = set(r[0] for r in cur.fetchall())
    cur.close()
    conn.close()
    return uids


def get_matches_missing_odds():
    """
    获取缺赔率的比赛（适配新schema: metadata JSONB）。
    包含:
      - on_sale 比赛（在售但缺赔率）
      - pending 篮球比赛（未开售但可能从 uniform 获得赔率）
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, sport_type, home_team || 'VS' || away_team
        FROM matches
        WHERE metadata->>'status' IN ('on_sale', 'pending')
        AND (
            (sport_type = 'football' AND (
                metadata->'odds'->>'spf' IS NULL
            ))
            OR
            (sport_type = 'basketball' AND (
                metadata->'odds'->>'mnl' IS NULL
                OR metadata->'odds'->>'hdc' IS NULL
            ))
        )
        AND (status IS NULL OR status NOT IN ('已完赛', '已结算'))
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [(r[0], r[1], r[2]) for r in rows]


def convert_odds_to_new_format(old_odds, sport_type='football'):
    """将旧格式赔率转为新schema的嵌套格式"""
    if not old_odds:
        return {}
    new_odds = {}
    if sport_type == 'football':
        # 胜平负
        spf = {}
        if old_odds.get('win_odds') is not None: spf['win'] = old_odds['win_odds']
        if old_odds.get('draw_odds') is not None: spf['draw'] = old_odds['draw_odds']
        if old_odds.get('lose_odds') is not None: spf['lose'] = old_odds['lose_odds']
        if spf: new_odds['spf'] = spf
        # 让球胜平负
        hspf = {}
        if old_odds.get('handicap_win_odds') is not None: hspf['win'] = old_odds['handicap_win_odds']
        if old_odds.get('handicap_draw_odds') is not None: hspf['draw'] = old_odds['handicap_draw_odds']
        if old_odds.get('handicap_lose_odds') is not None: hspf['lose'] = old_odds['handicap_lose_odds']
        if old_odds.get('handicap') is not None: hspf['handicap'] = old_odds['handicap']
        if hspf: new_odds['handicap_spf'] = hspf
        # 总进球
        if old_odds.get('goals_odds'):
            try:
                g = old_odds['goals_odds']
                new_odds['goals'] = json.loads(g) if isinstance(g, str) else g
            except: pass
        # 半全场
        if old_odds.get('half_full_odds'):
            try:
                hf = old_odds['half_full_odds']
                new_odds['half_full'] = json.loads(hf) if isinstance(hf, str) else hf
            except: pass
        # 比分
        if old_odds.get('score_odds'):
            try:
                sc = old_odds['score_odds']
                new_odds['score'] = json.loads(sc) if isinstance(sc, str) else sc
            except: pass
    elif sport_type == 'basketball':
        # 胜负
        mnl = {}
        if old_odds.get('win_odds') is not None: mnl['win'] = old_odds['win_odds']
        if old_odds.get('lose_odds') is not None: mnl['lose'] = old_odds['lose_odds']
        if mnl: new_odds['mnl'] = mnl
        # 让分
        hdc = {}
        if old_odds.get('spread_odds'):
            try:
                sp = old_odds['spread_odds']
                if isinstance(sp, str): sp = json.loads(sp)
                if isinstance(sp, dict):
                    if sp.get('home') is not None: hdc['win'] = sp['home']
                    if sp.get('away') is not None: hdc['lose'] = sp['away']
            except: pass
        if old_odds.get('spread_line') is not None: hdc['line'] = old_odds['spread_line']
        if hdc: new_odds['hdc'] = hdc
        # 大小分
        hilo = {}
        if old_odds.get('total_points_odds'):
            try:
                tp = old_odds['total_points_odds']
                if isinstance(tp, str): tp = json.loads(tp)
                if isinstance(tp, dict):
                    if tp.get('over') is not None: hilo['over'] = tp['over']
                    if tp.get('under') is not None: hilo['under'] = tp['under']
            except: pass
        if old_odds.get('total_line') is not None: hilo['line'] = old_odds['total_line']
        if hilo: new_odds['hilo'] = hilo
        # 胜分差
        if old_odds.get('score_diff_odds'):
            try:
                sd = old_odds['score_diff_odds']
                new_odds['score_diff'] = json.loads(sd) if isinstance(sd, str) else sd
            except: pass
    return new_odds


def _extract_handicap(odds_dict):
    """从 odds 中提取让球数（足球: handicap_spf.handicap / 篮球: hdc.line）"""
    if not odds_dict:
        return None
    h = odds_dict.get('handicap_spf', {}).get('handicap')
    if h is not None:
        return h
    h = odds_dict.get('hdc', {}).get('line')
    if h is not None:
        return h
    return None


def upsert_match(match_data, odds=None):
    """
    插入或更新比赛（含赔率）——适配新schema。
    
    赔率优先级: jc端点赔率 > uniform端点oddsList赔率
    selling_status: 根据 matchStatus 决定
      - "Selling" → on_sale（在售）
      - "Define" → pending（未开售）
      - 其他 → on_sale（默认）
    """
    sport_type = match_data.get('sport_type', 'football')
    home = match_data.get('home', '')
    away = match_data.get('away', '')
    db_id = matchnum_to_id(match_data.get('matchNum', ''))
    match_uid = match_data.get('match_uid')

    if not db_id or not match_uid:
        return False

    # 合并赔率: jc端点优先，uniform_odds作为补充
    uniform_odds = match_data.get('uniform_odds', {})
    merged_odds = dict(uniform_odds)
    if odds:
        merged_odds.update(odds)
    final_odds = merged_odds if merged_odds else None
    
    # 转换赔率格式为新schema嵌套格式
    new_format_odds = convert_odds_to_new_format(final_odds, sport_type)

    # 根据 matchStatus 决定 selling_status
    match_status = match_data.get('matchStatus', '')
    if match_status == 'Define':
        selling_status = 'pending'
    else:
        selling_status = 'on_sale'

    # 提取比赛时间
    mt = match_data.get('matchTime', '')
    match_date = mt.split(' ')[0] if mt and ' ' in mt else match_data.get('matchDate', '')

    conn = get_db()
    cur = conn.cursor()
    try:
        # 检查是否已存在（按id查）
        cur.execute("SELECT id, metadata FROM matches WHERE id = %s", (match_uid,))
        existing = cur.fetchone()

        if existing:
            # 已存在 → 更新metadata中的赔率和状态
            old_meta = existing[1] if isinstance(existing[1], dict) else json.loads(existing[1]) if existing[1] else {}
            old_odds = old_meta.get('odds', {})
            
            # 合并赔率（新赔率覆盖旧的）
            if new_format_odds:
                for k, v in new_format_odds.items():
                    old_odds[k] = v
            
            old_meta['odds'] = old_odds
            # 提取让球到顶层
            _hdc = _extract_handicap(old_odds)
            if _hdc is not None:
                old_meta['handicap'] = _hdc
            # 保留已完赛状态：如果比赛已有比分且metadata标记为已完赛，不覆盖
            if old_meta.get('status') == '已完赛' and old_meta.get('home_score') is not None:
                pass  # 保持已完赛不变
            else:
                old_meta['status'] = selling_status
            old_meta['source'] = match_data.get('source', old_meta.get('source', 'unknown'))
            old_meta['lastOddsUpdate'] = datetime.now().strftime('%Y-%m-%d %H:%M') if new_format_odds else old_meta.get('lastOddsUpdate')
            
            cur.execute("UPDATE matches SET metadata = %s WHERE id = %s", 
                        (json.dumps(old_meta, ensure_ascii=False), match_uid))
            conn.commit()
            
            if new_format_odds:
                print(f"  🔄 {match_uid} 更新赔率: {list(new_format_odds.keys())} [{selling_status}]")
                return 'updated'
            else:
                return 'exists'

        # 不存在 → 按旧id检查（旧schema遗留数据可能用体彩编号做id）
        cur.execute("SELECT id, metadata FROM matches WHERE id = %s", (db_id,))
        existing2 = cur.fetchone()
        
        if existing2 and existing2[0] != match_uid:
            old_id = existing2[0]
            old_meta2 = existing2[1] if isinstance(existing2[1], dict) else json.loads(existing2[1]) if existing2[1] else {}
            old_status = old_meta2.get('status', '')
            # 如果旧记录已结束，归档释放编号
            if old_status in ('已确认', '已取消', '已结算', '已完赛', 'stopped'):
                archive_id = f"z_{old_id}" if len(f"z_{old_id}") <= 30 else f"z{old_id[:25]}"
                cur.execute("UPDATE matches SET id = %s WHERE id = %s", (archive_id, db_id))
                conn.commit()
                print(f"  🔄 {db_id} 旧记录已归档({old_id})，释放编号给新比赛")
            else:
                print(f"  ⏭️ {db_id} 编号被占用({old_id})，跳过")
                return False

        # 全新插入（新schema: id, sport_type, home_team, away_team, metadata, status）
        metadata = {
            'odds': new_format_odds if new_format_odds else {},
            'league': match_data.get('league', ''),
            'source': match_data.get('source', 'sporttery.cn'),
            'status': selling_status,
            'match_date': match_date,
            'match_time': match_data.get('matchTime', ''),
            'original_id': db_id,
            'lastOddsUpdate': datetime.now().strftime('%Y-%m-%d %H:%M') if new_format_odds else None
        }
        # 提取让球到顶层（确保 metadata.handicap 有值）
        _hdc = _extract_handicap(new_format_odds)
        if _hdc is not None:
            metadata['handicap'] = _hdc
        
        cur.execute("""
            INSERT INTO matches (id, sport_type, home_team, away_team, metadata, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (match_uid, sport_type, home, away, json.dumps(metadata, ensure_ascii=False), '未开赛'))
        conn.commit()

        odds_keys = list((new_format_odds or {}).keys())
        print(f"  ✅ {match_uid} ({db_id}) {home}VS{away} {match_data.get('matchTime', '')} [{sport_type}] 赔率:{odds_keys} [{selling_status}]")
        return 'new'

    except Exception as e:
        conn.rollback()
        print(f"  ❌ 操作失败 {match_uid}: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def update_odds_for_uids(odds_map, target_uids=None, sport_type_hint='football'):
    """为指定比赛更新赔率（适配新schema metadata JSONB）"""
    updated = 0
    conn = get_db()
    cur = conn.cursor()

    for uid, odds in odds_map.items():
        if target_uids and uid not in target_uids:
            continue
        if not odds:
            continue

        # 转换赔率格式
        new_odds = convert_odds_to_new_format(odds, sport_type_hint)
        if not new_odds:
            continue

        try:
            # 读取当前metadata，合并赔率
            cur.execute("SELECT metadata FROM matches WHERE id = %s", (uid,))
            row = cur.fetchone()
            if not row:
                continue
            
            meta = row[0] if isinstance(row[0], dict) else json.loads(row[0]) if row[0] else {}
            old_odds = meta.get('odds', {})
            for k, v in new_odds.items():
                old_odds[k] = v
            meta['odds'] = old_odds
            meta['lastOddsUpdate'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            # 提取让球到顶层
            _hdc = _extract_handicap(old_odds)
            if _hdc is not None:
                meta['handicap'] = _hdc
            if meta.get('status') not in ('on_sale', 'pending') and not (meta.get('status') == '已完赛' and meta.get('home_score') is not None):
                meta['status'] = 'on_sale'
            
            cur.execute("UPDATE matches SET metadata = %s WHERE id = %s",
                       (json.dumps(meta, ensure_ascii=False), uid))
            if cur.rowcount > 0:
                conn.commit()
                updated += 1
                print(f"  🔄 {uid} 赔率更新: {list(new_odds.keys())}")
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            print(f"  ❌ {uid} 赔率更新失败: {e}")

    cur.close()
    conn.close()
    return updated


def verify_integrity():
    """检查数据完整性（适配新schema）"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, sport_type, home_team || 'VS' || away_team,
               metadata->>'match_time' as match_time,
               metadata->>'status' as selling_status,
               metadata->'odds' as odds_data
        FROM matches
        WHERE metadata->>'status' IN ('on_sale', 'pending')
        AND (status IS NULL OR status NOT IN ('已完赛', '已结算'))
        ORDER BY metadata->>'match_time'
    """)

    missing_list = []
    ok_list = []

    for row in cur.fetchall():
        mid, sport, teams, mtime, sstatus, odds_data = row
        tag = f"[{sstatus}]" if sstatus != 'on_sale' else ''
        
        if isinstance(odds_data, str):
            try:
                odds_data = json.loads(odds_data)
            except:
                odds_data = {}
        if not odds_data:
            odds_data = {}
        
        if sport == 'football':
            missing = []
            if not odds_data.get('spf'):
                missing.append('胜平负')
            if missing:
                missing_list.append(f"足球 {mid} ({teams}) {tag} 缺: {', '.join(missing)}")
            else:
                ok_list.append(f"足球 {mid}")
        elif sport == 'basketball':
            missing = []
            if not odds_data.get('mnl'):
                missing.append('胜负')
            if not odds_data.get('hdc'):
                missing.append('让分')
            if not odds_data.get('hilo'):
                missing.append('大小分')
            if missing:
                missing_list.append(f"篮球 {mid} ({teams}) {tag} 缺: {', '.join(missing)}")
            else:
                ok_list.append(f"篮球 {mid}")

    cur.close()
    conn.close()
    return ok_list, missing_list


# ============================================================
# 多源容错: 备选赔率源 (zgzcw.com → 500.com → okooo.com)
# ============================================================

def try_zgzcw_fallback(missing_matches):
    """尝试从 zgzcw.com 获取足球赔率"""
    football_missing = [(uid, st, teams) for uid, st, teams in missing_matches if st == 'football']
    if not football_missing:
        return {}
    print(f"\n  🔍 尝试 zgzcw.com 备选源 ({len(football_missing)}场足球缺赔率)...")
    zgzcw_data = zgzcw_fetch()
    if not zgzcw_data:
        print(f"  ⚠️ zgzcw.com 无数据返回")
        return {}
    print(f"  📊 zgzcw.com 共获取 {len(zgzcw_data)} 场比赛赔率")
    matched = match_zgzcw_to_db(football_missing, zgzcw_data)
    if matched:
        print(f"  ✅ zgzcw.com 成功匹配 {len(matched)} 场")
    else:
        print(f"  ⚠️ zgzcw.com 未匹配到缺赔率的比赛")
    return matched


def try_500_fallback(missing_matches, sport_type='football'):
    """尝试从 500.com 获取赔率"""
    filtered = [(uid, st, teams) for uid, st, teams in missing_matches if st == sport_type]
    if not filtered:
        return {}
    print(f"\n  🔍 尝试 500.com 备选源 ({len(filtered)}场{sport_type}缺赔率)...")
    if sport_type == 'football':
        data = fetch500_fb()
    else:
        data = fetch500_bk()
    if not data:
        print(f"  ⚠️ 500.com 无数据返回")
        return {}
    print(f"  📊 500.com 共获取 {len(data)} 场{sport_type}赔率")
    matched = match_500_to_db(filtered, data, sport_type=sport_type)
    if matched:
        print(f"  ✅ 500.com 成功匹配 {len(matched)} 场")
    else:
        print(f"  ⚠️ 500.com 未匹配到缺赔率的比赛")
    return matched


def try_okooo_fallback(missing_matches):
    """尝试从 okooo.com 获取足球赔率"""
    football_missing = [(uid, st, teams) for uid, st, teams in missing_matches if st == 'football']
    if not football_missing:
        return {}
    print(f"\n  🔍 尝试 okooo.com 备选源 ({len(football_missing)}场足球缺赔率)...")
    okooo_data = fetch_okooo_multi_day(days=3)
    if not okooo_data:
        print(f"  ⚠️ okooo.com 无数据返回")
        return {}
    print(f"  📊 okooo.com 共获取 {len(okooo_data)} 场比赛数据")
    matched = match_okooo_to_db(football_missing, okooo_data)
    if matched:
        print(f"  ✅ okooo.com 成功匹配 {len(matched)} 场")
    else:
        print(f"  ⚠️ okooo.com 未能匹配到任何比赛")
    return matched


def run_multi_source_fallback(missing_matches):
    """多源容错链: zgzcw → 500.com → okooo"""
    total_filled = 0
    remaining = list(missing_matches)

    zgzcw_result = try_zgzcw_fallback(remaining)
    if zgzcw_result:
        updated = update_odds_for_uids(zgzcw_result, target_uids=set(zgzcw_result.keys()))
        total_filled += updated
        remaining = get_matches_missing_odds()

    for sport in ['football', 'basketball']:
        still_missing = [(uid, st, t) for uid, st, t in remaining if st == sport]
        if still_missing:
            r500 = try_500_fallback(still_missing, sport_type=sport)
            if r500:
                updated = update_odds_for_uids(r500, target_uids=set(r500.keys()))
                total_filled += updated
                remaining = get_matches_missing_odds()

    still_football = [(uid, st, t) for uid, st, t in remaining if st == 'football']
    if still_football:
        okooo_result = try_okooo_fallback(remaining)
        if okooo_result:
            updated = update_odds_for_uids(okooo_result, target_uids=set(okooo_result.keys()))
            total_filled += updated

    return total_filled


def is_sporttery_odds_failed(odds_map):
    """判断sporttery赔率是否获取失败"""
    return len(odds_map) == 0


# ============================================================
# 主流程
# ============================================================

def main():
    verify_only = '--verify' in sys.argv
    odds_only = '--odds-only' in sys.argv
    
    # Parse --days argument
    days = 5
    for i, arg in enumerate(sys.argv):
        if arg == '--days' and i + 1 < len(sys.argv):
            try:
                days = int(sys.argv[i + 1])
            except ValueError:
                pass

    print(f"🔍 竞彩赛事扫描 + 赔率抓取 v3（新schema适配版）")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   扫描天数: {days}")

    # ========== 第一步: 获取赔率数据 ==========
    print(f"\n{'='*50}")
    print(f"📡 获取赔率数据 (jc 端点)")
    print(f"{'='*50}")
    odds_map = fetch_all_odds()
    print(f"  共获取 {len(odds_map)} 场比赛的赔率")

    if odds_only:
        print(f"\n{'='*50}")
        print(f"🔄 仅更新赔率模式")
        print(f"{'='*50}")
        missing = get_matches_missing_odds()
        missing_uids = {r[0] for r in missing}

        updated = update_odds_for_uids(odds_map, target_uids=missing_uids)
        print(f"  sporttery jc赔率更新: {updated}场")

        remaining = get_matches_missing_odds()
        if remaining:
            print(f"\n  📡 尝试 uniform 端点赔率...")
            uniform_odds = fetch_uniform_all_odds()
            remaining_uids = {r[0] for r in remaining}
            updated2 = update_odds_for_uids(uniform_odds, target_uids=remaining_uids)
            print(f"  uniform赔率更新: {updated2}场")

        remaining = get_matches_missing_odds()
        if remaining:
            print(f"\n{'='*50}")
            print(f"🔄 多源容错: 尝试备选数据源（仅取体彩赔率）")
            print(f"{'='*50}")
            filled = run_multi_source_fallback(remaining)
            print(f"  备选源共补全: {filled}场")

        print(f"\n  赔率更新完成")
        # 输出 JSON 摘要供 server.js 解析
        result_summary = {"new": 0, "new_matches_count": 0, "status": "ok", "message": "仅赔率更新模式"}
        print(json.dumps(result_summary, ensure_ascii=False))
        return 0

    # ========== 第二步: 发现比赛 ==========
    if not verify_only:
        existing_uids = get_existing_match_uids()
        new_count = 0

        # 足球发现
        print(f"\n{'='*50}")
        print(f"📌 发现足球比赛 (uniform 端点)")
        print(f"{'='*50}")
        fb_matches = discover_football_matches()
        print(f"  发现 {len(fb_matches)} 场足球")

        for m in fb_matches:
            uid = m['match_uid']
            odds = odds_map.get(uid)
            result = upsert_match(m, odds=odds)
            if result == 'new':
                new_count += 1
                existing_uids.add(uid)

        # 篮球发现
        print(f"\n{'='*50}")
        print(f"📌 发现篮球比赛 (uniform 端点)")
        print(f"{'='*50}")
        bk_matches = discover_basketball_matches()
        print(f"  发现 {len(bk_matches)} 场篮球")

        for m in bk_matches:
            uid = m['match_uid']
            odds = odds_map.get(uid)
            result = upsert_match(m, odds=odds)
            if result == 'new':
                new_count += 1
                existing_uids.add(uid)

        # ========== 第三步: 补全已有比赛的赔率 ==========
        print(f"\n{'='*50}")
        print(f"🔄 补全已入库比赛的赔率")
        print(f"{'='*50}")
        missing = get_matches_missing_odds()
        missing_uids = {r[0] for r in missing}

        if missing_uids and odds_map:
            updated = update_odds_for_uids(odds_map, target_uids=missing_uids)
            print(f"  sporttery jc补全赔率: {updated}场")
        elif not missing_uids:
            print(f"  ✅ 所有在售比赛赔率已完整")
        else:
            print(f"  ⚠️ {len(missing)}场缺赔率，sporttery jc暂无对应数据")

        remaining_after_jc = get_matches_missing_odds()
        if remaining_after_jc:
            print(f"\n  📡 尝试 uniform 端点赔率补全 ({len(remaining_after_jc)}场仍缺)...")
            uniform_odds = fetch_uniform_all_odds()
            remaining_uids = {r[0] for r in remaining_after_jc}
            updated2 = update_odds_for_uids(uniform_odds, target_uids=remaining_uids)
            print(f"  uniform补全赔率: {updated2}场")

        remaining_missing = get_matches_missing_odds()
        if remaining_missing:
            print(f"\n{'='*50}")
            print(f"🔄 多源容错: 尝试备选数据源（仅取体彩赔率）")
            print(f"{'='*50}")
            filled = run_multi_source_fallback(remaining_missing)
            print(f"  备选源共补全: {filled}场")

    # ========== 第四步: 校验 ==========
    print(f"\n{'='*50}")
    print(f"📊 数据完整性校验")
    print(f"{'='*50}")
    ok_list, missing_list = verify_integrity()

    print(f"  ✅ 赔率完整: {len(ok_list)}场")
    if missing_list:
        print(f"  ⚠️ 赔率缺失: {len(missing_list)}场")
        for item in missing_list:
            print(f"    ❌ {item}")
    else:
        print(f"  🎉 所有在售比赛赔率完整！")

    # 数据库统计
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sport_type, COUNT(*) AS total, 
               COUNT(CASE WHEN metadata->>'status'='on_sale' THEN 1 END) AS on_sale
        FROM matches 
        GROUP BY sport_type ORDER BY sport_type
    """)
    for sport, total, on_sale in cur.fetchall():
        print(f"  📈 {sport}: 共{total}场, 在售{on_sale}场")
    cur.close()
    conn.close()

    # 输出 JSON 摘要供 server.js 解析（关键：确保 runJcDiscover 能正确识别新比赛数）
    result_summary = {
        "new": new_count if not verify_only else 0,
        "new_matches_count": new_count if not verify_only else 0,
        "status": "ok",
        "message": f"发现{new_count if not verify_only else 0}场新比赛"
    }
    print(json.dumps(result_summary, ensure_ascii=False))

    return 0


if __name__ == '__main__':
    sys.exit(main())
