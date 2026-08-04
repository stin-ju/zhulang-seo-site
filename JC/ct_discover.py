#!/usr/bin/env python3
"""
CT传统彩票赛程抓取脚本 - 从竞彩网抓取胜负彩14场赛程

数据源: http://www.sporttery.cn/ctzc/zcgg/index.html
抓取内容: 胜负游戏（14场和任选9场）每期对阵、时间

用法:
  python3 ct_discover.py              # 抓取+入库
  python3 ct_discover.py --verify     # 仅校验不入库
  python3 ct_discover.py --force      # 强制更新已有比赛信息
"""
import os
import sys
import re
import json
import time
import subprocess
import psycopg2
from datetime import datetime

DB_URL = os.environ.get('DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

LIST_URL = 'http://www.sporttery.cn/ctzc/zcgg/index.html'
BASE_URL = 'http://www.sporttery.cn'

WEEKDAY_CN = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}

_HEADERS = [
    '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    '-H', 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8',
]


def fetch_html(url):
    """抓取网页"""
    try:
        cmd = ['curl', '-sL', '--max-time', '15'] + _HEADERS + [url]
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        html = result.stdout.decode('utf-8', errors='replace')
        if len(html) < 500:
            print(f"  [ERR] 页面太短({len(html)}字节): {url}")
            return None
        return html
    except Exception as e:
        print(f"  [ERR] 请求失败: {e}")
        return None


def find_schedule_links(html):
    """从列表页找到竞猜场次安排的公告链接"""
    links = re.findall(r'href="([^"]+)"[^>]*>[^<]*竞猜场次安排[^<]*<', html)
    if not links:
        links = re.findall(r'href="(/ctzc/zcgg/\d+/\d+\.html)"', html)
    return links


def parse_schedule_page(html):
    """解析单期赛程公告页面，返回多期数据"""
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    results = []

    for table_html in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        if len(rows) < 15:
            continue

        header_cells = re.findall(r'<td[^>]*>(.*?)</td>', rows[0], re.DOTALL)
        header_text = [re.sub(r'<[^>]+>', '', c).strip() for c in header_cells]
        if '期号' not in header_text and '序号' not in header_text:
            continue

        matches = []
        current_issue = None
        current_league = None

        for ri in range(1, min(len(rows), 16)):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', rows[ri], re.DOTALL)
            cells_clean = []
            for c in cells:
                text = re.sub(r'<[^>]+>', '', c).strip()
                text = text.replace('&nbsp;', ' ').strip()
                cells_clean.append(text)

            if not cells_clean or all(not c for c in cells_clean):
                continue

            num_cells = len(cells_clean)

            if num_cells == 6:
                current_issue = cells_clean[0]
                current_league = cells_clean[1]
                match_num = cells_clean[2]
                home = cells_clean[3]
                away = cells_clean[4]
                date = cells_clean[5]
            elif num_cells == 5:
                current_league = cells_clean[0]
                match_num = cells_clean[1]
                home = cells_clean[2]
                away = cells_clean[3]
                date = cells_clean[4]
            elif num_cells == 4:
                match_num = cells_clean[0]
                home = cells_clean[1]
                away = cells_clean[2]
                date = cells_clean[3]
            else:
                continue

            if not current_issue:
                continue

            try:
                int(match_num)
            except (ValueError, TypeError):
                continue

            matches.append({
                'num': int(match_num),
                'league': current_league or '',
                'home': home,
                'away': away,
                'date': date,
            })

        if not matches or not current_issue:
            continue

        issue_match = re.search(r'(\d{5})', current_issue)
        if not issue_match:
            continue
        issue_num = issue_match.group(1)

        sale_info = {}
        for row_html in rows:
            row_text = re.sub(r'<[^>]+>', '', row_html).replace('&nbsp;', ' ').strip()
            if '开售时间' in row_text:
                m1 = re.search(r'开售时间[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', row_text)
                m2 = re.search(r'停售时间[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', row_text)
                m3 = re.search(r'开奖日期[：:]\s*(\d{4}-\d{2}-\d{2})', row_text)
                if m1: sale_info['sell_start'] = m1.group(1).strip()
                if m2: sale_info['sell_end'] = m2.group(1).strip()
                if m3: sale_info['draw_date'] = m3.group(1).strip()

        results.append({
            'issue': issue_num,
            'matches': matches,
            'sale_info': sale_info,
        })

    return results


def get_db():
    return psycopg2.connect(DB_URL)


def save_to_db(issues, verify_only=False, force=False):
    """保存赛程到数据库"""
    if not issues:
        print("无新赛程需要入库")
        return 0

    conn = get_db()
    total_saved = 0

    for issue_data in issues:
        issue = issue_data['issue']
        matches = issue_data['matches']
        sale_info = issue_data.get('sale_info', {})

        print(f"\n第{issue}期: {len(matches)}场比赛")
        if sale_info:
            print(f"   开售: {sale_info.get('sell_start', '?')}")
            print(f"   停售: {sale_info.get('sell_end', '?')}")
            print(f"   开奖: {sale_info.get('draw_date', '?')}")

        for m in matches:
            match_id = f"CT{issue}_{m['num']:02d}"

            with conn.cursor() as cur:
                cur.execute("SELECT id, metadata FROM matches WHERE id = %s", (match_id,))
                existing = cur.fetchone()

            if existing and not force:
                old_md = existing[1] if isinstance(existing[1], dict) else (
                    json.loads(existing[1]) if existing[1] else {})
                old_home = old_md.get('home_team', old_md.get('home', ''))
                if old_home and old_home != '待定':
                    print(f"  跳过 {match_id}: 已存在 ({old_home} vs {old_md.get('away_team', old_md.get('away', ''))})")
                    continue

            metadata = {
                'match_type': 'ct',
                'issue': issue,
                'issue_num': m['num'],
                'league': m['league'],
                'source': '竞彩网',
                'match_time': f"{m['date']} 00:00" if m['date'] else None,
                'sell_status': 'on_sale',
                'status': 'on_sale',
            }
            if sale_info:
                metadata.update(sale_info)

            if verify_only:
                print(f"  [校验] {match_id}: {m['home']} vs {m['away']} ({m['date']}) [{m['league']}]")
                continue

            with conn.cursor() as cur:
                if existing:
                    cur.execute("""
                        UPDATE matches SET
                            home_team = %s,
                            away_team = %s,
                            metadata = %s::jsonb
                        WHERE id = %s
                    """, (m['home'], m['away'], json.dumps(metadata, ensure_ascii=False), match_id))
                    print(f"  更新 {match_id}: {m['home']} vs {m['away']} ({m['date']}) [{m['league']}]")
                else:
                    cur.execute("""
                        INSERT INTO matches (id, sport_type, home_team, away_team, metadata, status)
                        VALUES (%s, 'football', %s, %s, %s::jsonb, '未开赛')
                        ON CONFLICT (id) DO NOTHING
                    """, (match_id, m['home'], m['away'], json.dumps(metadata, ensure_ascii=False)))
                    print(f"  新增 {match_id}: {m['home']} vs {m['away']} ({m['date']}) [{m['league']}]")

            total_saved += 1

        conn.commit()

    conn.close()
    return total_saved


def main():
    verify = '--verify' in sys.argv
    force = '--force' in sys.argv

    print("=" * 50)
    print("CT传统彩票赛程抓取")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模式: {'校验' if verify else '入库'} {'(强制更新)' if force else ''}")
    print("=" * 50)

    print("\n[1] 获取公告列表...")
    list_html = fetch_html(LIST_URL)
    if not list_html:
        print("无法获取公告列表页")
        sys.exit(1)

    links = find_schedule_links(list_html)
    print(f"  找到 {len(links)} 个竞猜场次安排链接")

    if not links:
        print("未找到赛程公告链接")
        sys.exit(1)

    all_issues = []
    seen_issues = set()

    for link in links[:2]:
        url = BASE_URL + link if link.startswith('/') else link
        print(f"\n[2] 解析公告: {url}")
        time.sleep(1)

        page_html = fetch_html(url)
        if not page_html:
            print(f"  获取失败")
            continue

        issues = parse_schedule_page(page_html)
        print(f"  解析出 {len(issues)} 期赛程")

        for issue in issues:
            if issue['issue'] not in seen_issues:
                seen_issues.add(issue['issue'])
                all_issues.append(issue)
                print(f"  第{issue['issue']}期: {len(issue['matches'])}场")

    if not all_issues:
        print("\n未解析到任何赛程数据")
        sys.exit(1)

    # 过滤: 只保留14场胜负彩（14场比赛的期次）
    issues_14 = [i for i in all_issues if len(i['matches']) == 14]
    other = [i for i in all_issues if len(i['matches']) != 14]
    if other:
        print(f"  跳过非14场赛事: {[i['issue'] + '(' + str(len(i['matches'])) + '场)' for i in other]}")
    
    print(f"\n[3] 处理赛程数据（共{len(issues_14)}期14场胜负彩）...")
    saved = save_to_db(issues_14, verify_only=verify, force=force)

    print(f"\n完成! 共处理 {len(all_issues)} 期, {'校验' if verify else '入库'} {saved} 场")

    return {
        'issues': len(all_issues),
        'saved': saved,
        'issue_list': [i['issue'] for i in all_issues],
    }


if __name__ == '__main__':
    result = main()
    print(json.dumps(result, ensure_ascii=False))
