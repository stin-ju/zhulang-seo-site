#!/usr/bin/env python3
"""
fix_missing_scores.py - 从 titan007 抓取缺失比分并更新数据库

数据源: https://bf.titan007.com/football/Over_YYYYMMDD.htm
编码: GBK
结构: HTML表格，每行 <tr> 包含 联赛|时间|状态|主队|比分|客队|半场|...

用法:
  python3 fix_missing_scores.py          # 仅查看匹配结果，不更新
  python3 fix_missing_scores.py --update # 确认更新到数据库
"""

import sys
import re
import json
import requests
import psycopg2
from datetime import datetime, timedelta

DB_URL = "postgresql://postgres:" + process.env.DB_PASSWORD + "@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64) x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"

# 要抓取的 titan007 日期页面（动态：今天 + 前3天）
_now = datetime.now()
TITAN_DATES = [(_now - timedelta(days=i)).strftime('%Y%m%d') for i in range(4)]

# ESPN 日期（用于补充 titan007 没有的比赛，动态：今天 + 前3天）
ESPN_DATES = [(_now - timedelta(days=i)).strftime('%Y%m%d') for i in range(4)]

# ============================================================
# titan007 HTML 解析
# ============================================================
def fetch_titan_matches(date_str):
    """从 titan007 完场比分页面提取所有比赛"""
    url = f"https://bf.titan007.com/football/Over_{date_str}.htm"
    headers = {
        "User-Agent": UA,
        "Referer": "https://bf.titan007.com/",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        print(f"[titan007] {date_str} HTTP {resp.status_code}")
        return []

    # 检测是否为404页面
    if len(resp.content) < 2000:
        print(f"[titan007] {date_str} 页面过小({len(resp.content)}B)，可能无数据")
        return []

    text = resp.content.decode('gbk', errors='replace')
    return parse_titan_html(text, date_str)


def parse_titan_html(text, date_str):
    """解析 titan007 HTML，提取比赛列表"""
    trs = re.findall(r'<tr\s+[^>]*>(.*?)</tr>', text, re.DOTALL)
    matches = []

    for tr in trs:
        # 必须有 showgoallist（完场比分行的标志）
        if 'showgoallist' not in tr:
            continue

        # 提取比分（全场）: showgoallist 后面的第一个比分
        # 格式: <font color=red>X</font>-<font color=blue>Y</font>
        # 或:   <font color=blue>X</font>-<font color=red>Y</font>
        score_match = re.search(
            r"showgoallist\(\d+\)'>(<font\s+color=\w+>\d+</font>-<font\s+color=\w+>\d+</font>)</td>",
            tr
        )
        if not score_match:
            continue

        score_html = score_match.group(1)
        scores = re.findall(r'<font\s+color=\w+>(\d+)</font>', score_html)
        if len(scores) != 2:
            continue
        home_score, away_score = int(scores[0]), int(scores[1])

        # 用 showgoallist 分割主客队区域
        parts = tr.split("showgoallist")
        if len(parts) < 2:
            continue
        home_part = parts[0]
        away_part = parts[1]

        # 提取联赛
        league_m = re.search(r"<span>([^<]+)</span>", tr)
        league = league_m.group(1).strip() if league_m else ''

        # 提取主队名（align=right 的 td 中，跳过排名标签）
        home_team = extract_team_name(home_part, is_home=True)
        # 提取客队名（align=left 的 td 中）
        away_team = extract_team_name(away_part, is_home=False)

        if home_team and away_team:
            matches.append({
                'date': date_str,
                'league': league,
                'home': home_team,
                'away': away_team,
                'home_score': home_score,
                'away_score': away_score,
            })

    print(f"[titan007] {date_str} 解析到 {len(matches)} 场比赛")
    return matches


def extract_team_name(html_part, is_home=True):
    """从 HTML 片段中提取队名"""
    # 去掉所有 span、font、img 标签
    clean = re.sub(r'<span[^>]*>.*?</span>', '', html_part, flags=re.DOTALL)
    clean = re.sub(r'<font[^>]*>.*?</font>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<img[^>]*>', '', clean)
    clean = re.sub(r'<a[^>]*>.*?</a>', '', clean, flags=re.DOTALL)

    # 提取 >文字< 形式的内容
    names = re.findall(r'>([^<]+)<', clean)

    # 过滤：跳过空、太短、排名标签、非队名内容
    skip_words = {'完', '判', '推', '析', '半', '走地', '亚', '欧', '球'}
    candidates = []
    for name in names:
        name = name.strip()
        if not name or len(name) < 2:
            continue
        if name in skip_words:
            continue
        if name.startswith('[') and name.endswith(']'):
            continue
        # 跳过纯数字
        if re.match(r'^\d+$', name):
            continue
        candidates.append(name)

    if is_home:
        # 主队名通常在最后
        return candidates[-1] if candidates else ''
    else:
        # 客队名通常在最前
        return candidates[0] if candidates else ''


# ============================================================
# ESPN 数据抓取（补充 titan007 没有的比赛）
# ============================================================
def fetch_espn_matches(date_str):
    """从 ESPN API 获取某天完赛的足球比赛"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}"
    headers = {"User-Agent": UA}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        print(f"[ESPN] {date_str} 请求失败: {e}")
        return []

    events = data.get('events', [])
    matches = []
    for e in events:
        comp = (e.get('competitions', []) or [{}])[0]
        competitors = comp.get('competitors', []) or []
        home = away = ''
        hs = aws = None
        for c in competitors:
            name = c.get('team', {}).get('displayName', '')
            score = c.get('score', '')
            if c.get('homeAway') == 'home':
                home, hs = name, score
            else:
                away, aws = name, score
        status = comp.get('status', {}).get('type', {}).get('name', '')
        season = e.get('season', {})
        league = ''
        if isinstance(season, dict):
            league = season.get('type', {}).get('abbreviation', '') if isinstance(season.get('type'), dict) else ''
        if status in ('STATUS_FINAL', 'STATUS_FULL_TIME') and hs is not None and aws is not None:
            matches.append({
                'date': date_str,
                'league': league,
                'home': home,
                'away': away,
                'home_score': int(hs),
                'away_score': int(aws),
            })
    print(f"[ESPN] {date_str} 获取 {len(matches)} 场完赛")
    return matches


def fetch_espn_basketball(date_str):
    """从 ESPN API 获取 WNBA 比赛"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates={date_str}"
    headers = {"User-Agent": UA}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except:
        return []

    events = data.get('events', [])
    matches = []
    for e in events:
        comp = (e.get('competitions', []) or [{}])[0]
        competitors = comp.get('competitors', []) or []
        home = away = ''
        hs = aws = None
        for c in competitors:
            name = c.get('team', {}).get('displayName', '')
            score = c.get('score', '')
            if c.get('homeAway') == 'home':
                home, hs = name, score
            else:
                away, aws = name, score
        status = comp.get('status', {}).get('type', {}).get('name', '')
        if status in ('STATUS_FINAL', 'STATUS_FULL_TIME') and hs is not None and aws is not None:
            matches.append({
                'date': date_str,
                'league': 'WNBA',
                'home': home,
                'away': away,
                'home_score': int(hs),
                'away_score': int(aws),
            })
    print(f"[ESPN WNBA] {date_str} 获取 {len(matches)} 场完赛")
    return matches


# ============================================================
# 队名模糊匹配
# ============================================================
def normalize(name):
    """标准化队名用于匹配"""
    if not name:
        return ''
    return name.lower().strip()


def fuzzy_match(db_home, db_away, titan_home, titan_away):
    """模糊匹配两对队名，支持包含关系"""
    db_h = normalize(db_home)
    db_a = normalize(db_away)
    t_h = normalize(titan_home)
    t_a = normalize(titan_away)

    if not db_h or not db_a or not t_h or not t_a:
        return False, None

    # 正向匹配: db_home <-> titan_home, db_away <-> titan_away
    if team_match(db_h, t_h) and team_match(db_a, t_a):
        return True, 'normal'
    # 反向匹配: db_home <-> titan_away, db_away <-> titan_home
    if team_match(db_h, t_a) and team_match(db_a, t_h):
        return True, 'reversed'
    return False, None


def team_match(a, b):
    """两个队名是否匹配（包含关系 + 常见翻译差异）"""
    if not a or not b:
        return False
    # 完全相等
    if a == b:
        return True
    # 包含关系（至少2个字符）
    if len(a) >= 2 and len(b) >= 2:
        if a in b or b in a:
            return True

    # 特殊处理：去常见前后缀后再比较
    a_stripped = strip_suffixes(a)
    b_stripped = strip_suffixes(b)
    if a_stripped and b_stripped and len(a_stripped) >= 2 and len(b_stripped) >= 2:
        if a_stripped == b_stripped:
            return True
        if a_stripped in b_stripped or b_stripped in a_stripped:
            return True

    # 特殊处理：FC/队 等前后缀互换
    # "首尔FC" vs "FC首尔", "安养FC" vs "FC安养"
    a_fc = re.sub(r'^fc\s*', '', a).replace('fc', '').strip()
    b_fc = re.sub(r'^fc\s*', '', b).replace('fc', '').strip()
    if a_fc and b_fc and len(a_fc) >= 2:
        if a_fc in b_fc or b_fc in a_fc or a_fc == b_fc:
            return True

    # 特殊处理：KFUM奥斯陆 vs 奥斯KFUM
    a_parts = set(re.split(r'[\s\-/]+', a))
    b_parts = set(re.split(r'[\s\-/]+', b))
    if len(a_parts) >= 2 and len(b_parts) >= 2:
        if a_parts == b_parts:
            return True
        # 至少一半词素相同
        overlap = a_parts & b_parts
        if len(overlap) >= min(len(a_parts), len(b_parts)) * 0.5 and len(overlap) >= 1:
            # 额外检查：总字符相似度
            all_chars_a = set(a.replace(' ', ''))
            all_chars_b = set(b.replace(' ', ''))
            char_overlap = all_chars_a & all_chars_b
            if len(char_overlap) / max(len(all_chars_a), len(all_chars_b)) > 0.6:
                return True

    # 特殊翻译映射表（中文翻译差异）
    TRANSLATION_MAP = {
        '桑纳菲': '桑德菲杰',
        '埃夫斯堡': '埃尔夫斯堡',
        '布鲁马波': '布洛马波卡纳',
        '韦斯特罗': '瓦斯特拉斯',
        '克里斯蒂': '克里斯蒂安松',
    }
    for cn, alt in TRANSLATION_MAP.items():
        if (cn in a and alt in b) or (alt in a and cn in b):
            return True
        if (cn in b and alt in a) or (alt in b and cn in a):
            return True

    # 中英文映射（ESPN数据是英文，数据库是中文）
    EN_CN_MAP = {
        'france': '法国', 'spain': '西班牙', 'england': '英格兰', 'argentina': '阿根廷',
        'germany': '德国', 'brazil': '巴西', 'portugal': '葡萄牙', 'netherlands': '荷兰',
        'belgium': '比利时', 'italy': '意大利', 'uruguay': '乌拉圭', 'colombia': '哥伦比亚',
        'usa': '美国', 'mexico': '墨西哥', 'japan': '日本', 'korea': '韩国',
        'australia': '澳大利亚', 'canada': '加拿大', 'usa': '美国',
        'seattle': '西雅图', 'portland': '波特兰', 'chicago': '芝加哥', 'vancouver': '温哥华',
        'montreal': '蒙特利尔', 'toronto': '多伦多', 'st louis': '圣路易',
        'minnesota': '明尼苏达', 'kansas': '堪萨斯', 'san diego': '圣迭戈',
        'new york': '纽约', 'los angeles': '洛杉矶', 'boston': '波士顿',
        'houston': '休斯顿', 'dallas': '达拉斯', 'orlando': '奥兰多',
        'gyor': '杰尔', 'gyori': '杰尔', 'vikings': '维京', 'vikingur': '维京',
        'reykjavik': '雷克雅未克', 'new saints': '新圣徒', 'saints': '圣徒',
        'sabah': '萨巴赫', 'sutjeska': '苏捷斯卡', 'kairat': '凯拉特',
        'almaty': '阿拉木图', 'klaksvik': '克拉克斯维克', 'atert': '阿特',
        'bissen': '比森',
        'mystics': '神秘人', 'washington': '华盛顿',
        'tempo': '节奏', 'sun': '太阳', 'connecticut': '康涅狄格',
        'fire': '火焰', 'sky': '天空', 'storm': '风暴', 'sparks': '火花',
        'fever': '狂热', 'lynx': '山猫', 'aces': '王牌', 'mercury': '水星',
        'liberty': '自由人', 'dream': '梦想', 'wing': '飞翼', 'wings': '飞翼',
        'valkyries': '女武神',
    }
    # 尝试英文→中文转换后匹配
    for en, cn in EN_CN_MAP.items():
        if en in a and cn in b:
            return True
        if en in b and cn in a:
            return True

    return False


def strip_suffixes(name):
    """去掉队名常见后缀"""
    suffixes = ['队', 'fc', 'FC', 'f.c.', 'F.C.', 'cf', 'CF', '联队', '竞技', '体育']
    result = name
    for s in suffixes:
        if result.endswith(s) and len(result) > len(s) + 1:
            result = result[:-len(s)]
        if result.startswith(s) and len(result) > len(s) + 1:
            result = result[len(s):]
    return result.strip()


# ============================================================
# 数据库操作
# ============================================================
def get_missing_matches():
    """查询数据库中缺比分的比赛"""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, sport_type, home_team, away_team, metadata
        FROM matches
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    missing = []
    for row in rows:
        mid, sport, home, away, metadata = row
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}
        metadata = metadata or {}

        hs = metadata.get('home_score')
        aws = metadata.get('away_score')
        if hs is None or aws is None:
            missing.append({
                'id': mid,
                'home': home,
                'away': away,
                'match_date': metadata.get('match_date', ''),
                'match_time': metadata.get('match_time', ''),
                'status': metadata.get('status', ''),
                'sport_type': sport,
                'metadata': metadata,
            })
    return missing


def update_scores(updates):
    """批量更新比分到数据库，同时更新 status 为'已完赛'"""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    updated = 0
    for item in updates:
        match_id = item['match_id']
        home_score = item['home_score']
        away_score = item['away_score']

        # 检查比赛是否存在
        cur.execute("SELECT id FROM matches WHERE id = %s", (match_id,))
        row = cur.fetchone()
        if not row:
            print(f"  [跳过] {match_id} 不存在")
            continue

        # 用 jsonb_set 将比分写入 metadata，同时更新 status 为'已完赛'
        cur.execute("""
            UPDATE matches SET
                metadata = jsonb_set(
                    jsonb_set(COALESCE(metadata, '{}'), '{home_score}', to_jsonb(%s::int)),
                    '{away_score}', to_jsonb(%s::int)
                ),
                status = '已完赛'
            WHERE id = %s
        """, (home_score, away_score, match_id))
        updated += 1
        print(f"  已更新: {match_id} -> {home_score}:{away_score}, status=已完赛")

    cur.close()
    conn.close()
    return updated


# ============================================================
# 主逻辑
# ============================================================
def main():
    do_update = '--update' in sys.argv

    print("=" * 60)
    print("titan007 比分抓取 & 数据库更新脚本")
    print(f"模式: {'更新模式' if do_update else '预览模式（不更新）'}")
    print("=" * 60)

    # 1. 抓取 titan007 数据
    print("\n[1] 抓取 titan007 数据...")
    all_titan = []
    for date_str in TITAN_DATES:
        matches = fetch_titan_matches(date_str)
        all_titan.extend(matches)
    print(f"    titan007 共获取 {len(all_titan)} 场比赛")

    # 1b. 抓取 ESPN 数据（补充）
    print("\n[1b] 抓取 ESPN 数据（补充）...")
    all_espn = []
    for date_str in ESPN_DATES:
        matches = fetch_espn_matches(date_str)
        all_espn.extend(matches)
    # WNBA
    for date_str in ESPN_DATES:
        matches = fetch_espn_basketball(date_str)
        all_espn.extend(matches)
    print(f"    ESPN 共获取 {len(all_espn)} 场比赛")

    # 合并所有外部数据
    all_external = all_titan + all_espn
    print(f"    合计 {len(all_external)} 场外部数据")

    # 2. 查询数据库缺比分的比赛
    print("\n[2] 查询数据库缺比分的比赛...")
    missing = get_missing_matches()
    print(f"    共 {len(missing)} 场缺比分")

    # 3. 匹配
    print("\n[3] 队名匹配...")
    matched = []
    unmatched_db = []

    for db_match in missing:
        found = False
        for ext_match in all_external:
            ok, direction = fuzzy_match(
                db_match['home'], db_match['away'],
                ext_match['home'], ext_match['away']
            )
            if ok:
                hs = ext_match['home_score']
                aws = ext_match['away_score']
                if direction == 'reversed':
                    hs, aws = aws, hs

                matched.append({
                    'match_id': db_match['id'],
                    'db_home': db_match['home'],
                    'db_away': db_match['away'],
                    'ext_home': ext_match['home'],
                    'ext_away': ext_match['away'],
                    'home_score': hs,
                    'away_score': aws,
                    'league': ext_match['league'],
                    'date': ext_match['date'],
                    'direction': direction,
                    'db_date': db_match['match_date'],
                    'db_status': db_match['status'],
                    'sport': db_match.get('sport_type', ''),
                })
                found = True
                break

        if not found:
            unmatched_db.append(db_match)

    # 4. 输出结果
    print(f"\n{'=' * 60}")
    print(f"匹配结果: {len(matched)} 场匹配成功, {len(unmatched_db)} 场未匹配")
    print(f"{'=' * 60}")

    if matched:
        print(f"\n✅ 匹配成功的比赛 ({len(matched)}场):")
        print("-" * 60)
        for i, m in enumerate(matched, 1):
            rev = " [主客反转]" if m['direction'] == 'reversed' else ""
            print(f"  {i:2d}. [{m['db_date']}] {m['db_home']} vs {m['db_away']}")
            print(f"      外部: {m['ext_home']} {m['home_score']}-{m['away_score']} {m['ext_away']} [{m['league']}]{rev}")
            print(f"      DB ID: {m['match_id']} | 状态: {m['db_status']}")

    if unmatched_db:
        print(f"\n❌ 未匹配的比赛 ({len(unmatched_db)}场):")
        print("-" * 60)
        for m in unmatched_db:
            print(f"  [{m['match_date']}] {m['id']}: {m['home']} vs {m['away']} (状态:{m['status']})")

    # 5. 更新
    if do_update and matched:
        print(f"\n[4] 开始更新数据库...")
        updated = update_scores(matched)
        print(f"\n✅ 成功更新 {updated} 场比赛比分")
    elif not do_update:
        print(f"\n💡 当前为预览模式。确认无误后执行:")
        print(f"   python3 scripts/fix_missing_scores.py --update")


if __name__ == '__main__':
    main()
