#!/usr/bin/env python3
"""
traditional_lottery_predict.py - 传统彩7AI预测脚本

功能:
  1. 从体彩官网抓取胜负彩14场赛程
  2. 调用7个AI生成预测（胜负彩spf、半全场bqc、进球彩zjq）
  3. 将预测结果写入 traditional_predictions 表

用法:
  python3 traditional_lottery_predict.py                    # 抓取赛程 + 7AI预测
  python3 traditional_lottery_predict.py --issue 26101      # 指定期号
  python3 traditional_lottery_predict.py --game 胜负彩      # 只预测胜负彩
  python3 traditional_lottery_predict.py --force            # 强制覆盖已有预测
"""

import os
import sys
import re
import json
import time
import subprocess
import traceback
import requests
import psycopg2
from datetime import datetime

# ============ 配置 ============
DB_URL = os.environ.get('DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

LIST_URL = 'http://www.sporttery.cn/ctzc/zcgg/index.html'
BASE_URL = 'http://www.sporttery.cn'

HEADERS = [
    '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    '-H', 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8',
]

AI_NAMES = ["扣子", "豆包", "文心", "混元", "DeepSeek", "智谱清言", "MiniMax"]

# 每个AI配置多个备用模型，按优先级排序，主模型失败时自动切换
AI_CONFIGS = {
    "DeepSeek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "models": ["deepseek-chat", "deepseek-chat-v2"],
    },
    "MiniMax": {
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "models": ["MiniMax-Text-01", "abab6.5s-chat"],
    },
    "豆包": {
        "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "key_env": "DOUBAO_API_KEY",
        "models": ["doubao-seed-2-0-mini-260428", "doubao-seed-1-6-lite-32k-250428"],
    },
    "智谱清言": {
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "ZHIPU_API_KEY",
        "models": ["glm-4-flash", "glm-4-air", "glm-4-flashx"],
    },
    "文心": {
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "models": ["ernie-4.0-8k-latest", "ernie-3.5-8k", "ernie-speed-8k"],
    },
    "混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "models": ["hunyuan-lite", "hunyuan-turbo", "hunyuan-standard"],
    },
    "扣子": {
        "url": "https://api.coze.cn/v3/chat/completions",
        "key_env": "COZE_API_KEY",
        "models": ["doubao-seed-2-0-mini-260428", "deepseek-v3"],
    },
}

RATE_LIMIT_KEYWORDS = [
    "Arrearage", "Overdue", "quota", "QuotaExceeded", "insufficient",
    "SetLimitExceeded", "LimitExceeded", "ServerOverloaded",
    "RequestBurstTooFast", "RateLimitExceeded", "TooManyRequests", "429",
    "402", "balance", "Payment Required",
]


# ============ 赛程抓取 ============

def fetch_html(url):
    try:
        cmd = ['curl', '-sL', '--max-time', '15'] + HEADERS + [url]
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        html = result.stdout.decode('utf-8', errors='replace')
        if len(html) < 500:
            return None
        return html
    except Exception as e:
        print(f"  [ERR] 请求失败: {e}")
        return None


def find_schedule_links(html):
    links = re.findall(r'href="([^"]+)"[^>]*>[^<]*竞猜场次安排[^<]*<', html)
    if not links:
        links = re.findall(r'href="(/ctzc/zcgg/\d+/\d+\.html)"', html)
    return links


def parse_schedule_page(html):
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

        for ri in range(1, min(len(rows), 20)):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', rows[ri], re.DOTALL)
            cells_clean = [re.sub(r'<[^>]+>', '', c).replace('&nbsp;', ' ').strip() for c in cells]
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
                'num': str(int(match_num)).zfill(2),
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

        results.append({
            'issue': issue_match.group(1),
            'matches': matches,
        })

    return results


def fetch_schedules():
    """从体彩官网抓取最新在售赛程"""
    print("[1] 获取公告列表...")
    list_html = fetch_html(LIST_URL)
    if not list_html:
        print("  无法获取公告列表页")
        return []

    links = find_schedule_links(list_html)
    print(f"  找到 {len(links)} 个公告链接")

    all_issues = []
    seen = set()

    for link in links[:3]:
        url = BASE_URL + link if link.startswith('/') else link
        print(f"  解析: {url}")
        time.sleep(1)

        page_html = fetch_html(url)
        if not page_html:
            continue

        issues = parse_schedule_page(page_html)
        for issue in issues:
            if issue['issue'] not in seen and len(issue['matches']) == 14:
                seen.add(issue['issue'])
                all_issues.append(issue)
                print(f"    第{issue['issue']}期: {len(issue['matches'])}场")

    return all_issues


# ============ AI调用 ============

def build_ct_prompt(matches, game_type="胜负彩"):
    """构建传统彩预测prompt"""
    match_lines = []
    for m in matches:
        match_lines.append(f"  {m['num']}. [{m['league']}] {m['home']} vs {m['away']} ({m['date']})")

    match_text = "\n".join(match_lines)

    if game_type == "胜负彩":
        return f"""你是专业足球预测分析师。请预测以下14场胜负彩比赛的胜平负结果。

## 比赛列表
{match_text}

## 预测要求
1. 请联网搜索每场比赛的球队近期状态、历史交锋、伤停信息
2. 综合考虑实力、状态、主客场等因素
3. 每场给出最可能的单一结果（胜/平/负）
4. 同时从14场中选出你认为最有把握的9场作为任9推荐

## 输出格式（严格JSON数组，不要输出其他内容）:
```json
[
  {{"match": "01", "spf": "3", "analysis": "简要分析", "r9": true}},
  {{"match": "02", "spf": "1", "analysis": "...", "r9": false}},
  ...
]
```
其中 spf: "3"=胜, "1"=平, "0"=负
r9: true表示这场比赛入选你的任9推荐（必须恰好9场为true）"""

    elif game_type == "半全场":
        return f"""你是专业足球预测分析师。请预测以下6场半全场比赛的半全场结果。

## 比赛列表
{match_text}

注意：只预测前6场比赛（01-06）

## 预测要求
1. 请联网搜索每场比赛的球队近期状态
2. 预测每场比赛半场和全场的胜平负组合

## 输出格式（严格JSON数组）:
```json
[
  {{"match": "01", "bqc": "31", "analysis": "简要分析"}},
  ...
]
```
其中 bqc: 两位数，第一位=半场结果(3胜/1平/0负)，第二位=全场结果(3胜/1平/0负)
例如: "31"=半场胜全场平, "33"=半场胜全场胜, "00"=半场负全场负"""

    elif game_type == "进球彩":
        return f"""你是专业足球预测分析师。请预测以下4场比赛的进球数。

## 比赛列表
{match_text}

注意：只预测前4场比赛（01-04）

## 预测要求
1. 请联网搜索每场比赛的球队近期进攻/防守数据
2. 预测每场比赛主队和客队的进球数

## 输出格式（严格JSON数组）:
```json
[
  {{"match": "01", "zjq": "2", "analysis": "简要分析"}},
  ...
]
```
其中 zjq: 总进球数，"0"=0球, "1"=1球, "2"=2球, "3"=3球及以上"""

    return ""


def call_ai_api(ai_name, prompt, timeout=120):
    """调用单个AI的API，自动切换备用模型"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        return None

    key = os.environ.get(config["key_env"], "")
    if not key:
        print(f"  [{ai_name}] API Key未配置，跳过")
        return None

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    # 尝试每个模型，直到成功或全部失败
    models = config.get("models", [config.get("model", "")])
    last_error = None
    
    for model in models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        try:
            resp = requests.post(config["url"], headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            last_error = str(e)
            error_str = last_error
            if any(kw in error_str for kw in RATE_LIMIT_KEYWORDS):
                print(f"  [{ai_name}] {model} 额度/限流，切换备用模型...")
            else:
                print(f"  [{ai_name}] {model} 调用失败，切换备用模型...")
            continue
    
    # 所有模型都失败
    print(f"  [{ai_name}] 所有模型均失败: {last_error[:100] if last_error else '未知错误'}")
    return None


def parse_ct_response(text, game_type):
    """解析AI返回的传统彩预测JSON"""
    if not text:
        return None

    # 尝试提取JSON数组
    json_match = re.search(r'```json\s*(\[.*?\])\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass

    json_match = re.search(r'\[\s*\{.*?\}\s*\]', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except:
            pass

    return None


# ============ 数据库操作 ============

def get_db():
    return psycopg2.connect(DB_URL)


def get_existing_predictions(issue, game_type):
    """获取指定期号+类型已有的AI预测"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT ai_name FROM traditional_predictions WHERE issue = %s AND game_type = %s",
        (issue, game_type)
    )
    existing = {row[0] for row in cur.fetchall()}
    conn.close()
    return existing


def save_predictions(issue, game_type, matches, ai_name, predictions):
    """保存预测到数据库"""
    conn = get_db()
    cur = conn.cursor()

    # 构建 matches_info
    matches_info = []
    for m in matches:
        matches_info.append({
            'id': f'{issue}_{m["num"]}',
            'num': m['num'],
            'home': m['home'],
            'away': m['away'],
            'time': m['date'],
            'issue': issue,
            'league': m['league'],
        })

    # 检查是否已存在
    cur.execute(
        "SELECT id FROM traditional_predictions WHERE issue = %s AND game_type = %s AND ai_name = %s",
        (issue, game_type, ai_name)
    )
    existing = cur.fetchone()

    if existing:
        cur.execute("""
            UPDATE traditional_predictions
            SET predictions = %s::jsonb, matches_info = %s::jsonb, created_at = NOW()
            WHERE issue = %s AND game_type = %s AND ai_name = %s
        """, (json.dumps(predictions, ensure_ascii=False),
              json.dumps(matches_info, ensure_ascii=False),
              issue, game_type, ai_name))
    else:
        cur.execute("""
            INSERT INTO traditional_predictions (game_type, ai_name, issue, predictions, matches_info, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, NOW())
        """, (game_type, ai_name, issue,
              json.dumps(predictions, ensure_ascii=False),
              json.dumps(matches_info, ensure_ascii=False)))

    conn.commit()
    conn.close()


# ============ 主流程 ============

def predict_issue(issue_data, game_types, force=False):
    """对单期赛程进行7AI预测"""
    issue = issue_data['issue']
    matches = issue_data['matches']

    print(f"\n{'='*50}")
    print(f"第{issue}期预测 - {len(matches)}场比赛")
    print(f"{'='*50}")

    for m in matches:
        print(f"  {m['num']} [{m['league']}] {m['home']} vs {m['away']} ({m['date']})")

    results = {}

    for game_type in game_types:
        print(f"\n--- {game_type} ---")

        existing = get_existing_predictions(issue, game_type) if not force else set()
        prompt = build_ct_prompt(matches, game_type)

        for ai_name in AI_NAMES:
            if ai_name in existing:
                print(f"  [{ai_name}] 已有预测，跳过")
                continue

            print(f"  [{ai_name}] 预测中...", end=' ', flush=True)
            raw = call_ai_api(ai_name, prompt)

            if raw:
                parsed = parse_ct_response(raw, game_type)
                if parsed and len(parsed) >= len(matches):
                    save_predictions(issue, game_type, matches, ai_name, parsed)
                    print(f"完成 ({len(parsed)}场)")
                else:
                    print(f"解析失败 (got {len(parsed) if parsed else 0} fields)")
            else:
                print("无响应")

            time.sleep(1)

    print(f"\n第{issue}期预测完成!")
    return results


def generate_template(matches, game_type):
    """扣子模板预测 - 基于简单规则"""
    preds = []
    if game_type == "胜负彩":
        # 前9场作为任9推荐
        for i, m in enumerate(matches):
            preds.append({
                "match": m['num'], 
                "spf": "3", 
                "analysis": "模板预测",
                "r9": i < 9  # 前9场为true
            })
    elif game_type == "半全场":
        # 只预测前6场
        for m in matches[:6]:
            preds.append({"match": m['num'], "bqc": "33", "analysis": "模板预测"})
    elif game_type == "进球彩":
        # 只预测前4场
        for m in matches[:4]:
            preds.append({"match": m['num'], "zjq": "2", "analysis": "模板预测"})
    return preds


def main():
    import argparse

    parser = argparse.ArgumentParser(description='传统彩7AI预测')
    parser.add_argument('--issue', type=str, help='指定期号')
    parser.add_argument('--game', type=str, help='指定玩法(胜负彩/半全场/进球彩/全部)')
    parser.add_argument('--force', action='store_true', help='强制覆盖已有预测')
    parser.add_argument('--get', action='store_true', help='只抓取赛程不预测')
    args = parser.parse_args()

    if args.game and args.game != '全部':
        game_types = [args.game]
    else:
        game_types = ['胜负彩', '半全场', '进球彩']

    print(f"传统彩7AI预测")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"玩法: {', '.join(game_types)}")

    # 抓取赛程
    schedules = fetch_schedules()
    if not schedules:
        print("未抓取到赛程")
        sys.exit(1)

    # 过滤期号
    if args.issue:
        schedules = [s for s in schedules if s['issue'] == args.issue]
        if not schedules:
            print(f"未找到第{args.issue}期赛程")
            sys.exit(1)

    if args.get:
        # 只输出赛程信息
        output = {
            'issues': [{'issue': s['issue'], 'matches': len(s['matches'])} for s in schedules]
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)

    # 逐期预测
    for issue_data in schedules:
        predict_issue(issue_data, game_types, force=args.force)

    print("\n全部完成!")


if __name__ == '__main__':
    main()
