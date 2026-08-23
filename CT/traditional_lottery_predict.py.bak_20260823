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

AI_CONFIGS = {
    "DeepSeek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "MiniMax": {
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model": "MiniMax-Text-01",
    },
    "豆包": {
        "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "key_env": "DOUBAO_API_KEY",
        "model": "doubao-seed-2-0-mini-260428",
    },
    "智谱清言": {
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "ZHIPU_API_KEY",
        "model": "glm-4-flash",
    },
    "文心": {
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "model": "ernie-4.0-8k-latest",
    },
    "混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "key_default": "REMOVED",
        "model": "hy-mt2-lite",
    },
    "扣子": {
        "url": "https://7hsjv6c4cn.coze.site/stream_run",
        "key_env": "COZE_PROJECT_API_TOKEN",
        "key_default": "REMOVED",
        "model": None,
        "format": "coze_code",
        "project_id": 7667164681706078217,
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
        match_time = m.get('time', m.get('date', ''))
        match_lines.append(f"  {m['num']}. [{m['league']}] {m['home']} vs {m['away']} ({match_time})")

    match_text = "\n".join(match_lines)

    if game_type == "胜负彩":
        return f"""你是专业足球预测分析师。请预测以下14场胜负彩比赛的胜平负结果。

## 比赛列表
{match_text}

## 预测要求
1. 请联网搜索每场比赛的球队近期状态、历史交锋、伤停信息
2. 综合考虑实力、状态、主客场等因素
3. 每场给出最可能的单一结果（胜/平/负）

## 输出格式（严格JSON数组，不要输出其他内容）:
```json
[
  {{"match": "01", "spf": "3", "analysis": "简要分析", "intelligence": {{"home_recent_form": "主队近况", "away_recent_form": "客队近况", "head_to_head": "交锋记录", "home_injuries": "主队伤停", "away_injuries": "客队伤停", "league_position": "联赛排名", "key_factors": "关键因素"}}}},
  ...
]
```
其中 spf: "3"=胜, "1"=平, "0"=负
**重要**：intelligence字段必须通过联网搜索填写真实数据，每个字段都要有具体内容。"""

    elif game_type == "半全场":
        return f"""你是专业足球预测分析师。请预测以下14场比赛的半全场结果。

## 比赛列表
{match_text}

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
        return f"""你是专业足球预测分析师。请预测以下14场比赛的进球数。

## 比赛列表
{match_text}

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


def call_coze_code(url, token, prompt, project_id=None):
    """调用扣子编程（Coze Code）项目部署的API端点
    官方文档: https://docs.coze.cn/dev_how_to_guides_qeesmmos
    请求格式:
    {
      "content": {"query": {"prompt": [{"type": "text", "content": {"text": "..."}}]}},
      "type": "query",
      "session_id": "...",
      "project_id": 7667164681706078217
    }
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "content": {
            "query": {
                "prompt": [
                    {
                        "type": "text",
                        "content": {
                            "text": prompt,
                        },
                    }
                ],
            },
        },
        "type": "query",
        "session_id": f"ct_predict_{int(time.time())}",
    }
    if project_id:
        payload["project_id"] = project_id

    print(f"  [扣子API] 请求URL: {url}")
    print(f"  [扣子API] project_id: {project_id}")

    resp = requests.post(url, headers=headers, json=payload, timeout=120)

    # 详细记录错误信息
    if resp.status_code != 200:
        error_body = resp.text[:500]
        print(f"  [扣子API] HTTP {resp.status_code}: {error_body}")
        resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    print(f"  [扣子API] 响应Content-Type: {content_type}")

    # 尝试JSON响应
    if "json" in content_type:
        data = resp.json()
        print(f"  [扣子API] JSON响应keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], dict):
                messages = data["data"].get("messages", [])
                for msg in reversed(messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        return msg["content"]
            if "messages" in data:
                for msg in reversed(data["messages"]):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        return msg["content"]
            if "result" in data:
                return str(data["result"])
            if "text" in data:
                return str(data["text"])
        return json.dumps(data, ensure_ascii=False)

    # SSE流式响应：收集所有answer分片并拼接
    answer_chunks = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                if isinstance(evt, dict):
                    evt_type = evt.get("type", "")
                    if evt_type == "answer":
                        content = evt.get("content", {})
                        if isinstance(content, dict):
                            chunk = content.get("answer")
                            if chunk:
                                answer_chunks.append(chunk)
            except json.JSONDecodeError:
                pass
    if answer_chunks:
        full_answer = "".join(answer_chunks)
        print(f"  [扣子API] SSE拼接完成，回答长度: {len(full_answer)}")
        return full_answer

    # 回退：直接返回原始文本
    print(f"  [扣子API] 回退返回原始文本，长度: {len(resp.text)}")
    return resp.text


def call_ai_api(ai_name, prompt, timeout=120):
    """调用单个AI的API"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        return None

    fmt = config.get("format", "openai")

    # 扣子走Coze Code API
    if fmt == "coze_code":
        token = os.environ.get(config.get("key_env", ""), "") or config.get("key_default", "")
        if not token:
            print(f"  [{ai_name}] API Token未配置")
            return None
        return call_coze_code(config["url"], token, prompt, config.get("project_id"))

    key = os.environ.get(config["key_env"], "")
    if not key:
        print(f"  [{ai_name}] API Key未配置，跳过")
        return None

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
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
        error_str = str(e)
        if any(kw in error_str for kw in RATE_LIMIT_KEYWORDS):
            print(f"  [{ai_name}] 额度/限流: {error_str[:100]}")
        else:
            print(f"  [{ai_name}] 调用失败: {error_str[:100]}")
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


def generate_ren9(predictions):
    """根据预测结果生成任9推荐（选9场最有把握的）
    策略：优先选非平局场次（主胜/客胜更有把握），不足9场再用平局补齐
    """
    non_draws = []  # 非平局场次 (spf=0或2)
    draws = []      # 平局场次 (spf=1)
    
    for p in predictions:
        spf = str(p.get('spf', ''))
        match_num = str(p.get('match', '')).lstrip('0') or '0'
        if spf in ('0', '2', '3'):  # 客胜或主胜
            non_draws.append(match_num)
        else:
            draws.append(match_num)
    
    # 优先选非平局，不足9场用平局补齐
    ren9 = non_draws[:9]
    if len(ren9) < 9:
        ren9.extend(draws[:9 - len(ren9)])
    
    return ren9[:9]


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

    # 生成任9推荐（仅胜负彩）
    ren9_json = None
    if game_type == '胜负彩':
        ren9_picks = generate_ren9(predictions)
        ren9_json = json.dumps(ren9_picks, ensure_ascii=False)

    # 检查是否已存在
    cur.execute(
        "SELECT id FROM traditional_predictions WHERE issue = %s AND game_type = %s AND ai_name = %s",
        (issue, game_type, ai_name)
    )
    existing = cur.fetchone()

    if existing:
        if ren9_json is not None:
            cur.execute("""
                UPDATE traditional_predictions
                SET predictions = %s::jsonb, matches_info = %s::jsonb, ren9 = %s::jsonb, created_at = NOW()
                WHERE issue = %s AND game_type = %s AND ai_name = %s
            """, (json.dumps(predictions, ensure_ascii=False),
                  json.dumps(matches_info, ensure_ascii=False),
                  ren9_json,
                  issue, game_type, ai_name))
        else:
            cur.execute("""
                UPDATE traditional_predictions
                SET predictions = %s::jsonb, matches_info = %s::jsonb, created_at = NOW()
                WHERE issue = %s AND game_type = %s AND ai_name = %s
            """, (json.dumps(predictions, ensure_ascii=False),
                  json.dumps(matches_info, ensure_ascii=False),
                  issue, game_type, ai_name))
    else:
        if ren9_json is not None:
            cur.execute("""
                INSERT INTO traditional_predictions (game_type, ai_name, issue, predictions, ren9, matches_info, created_at)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, NOW())
            """, (game_type, ai_name, issue,
                  json.dumps(predictions, ensure_ascii=False),
                  ren9_json,
                  json.dumps(matches_info, ensure_ascii=False)))
        else:
            cur.execute("""
                INSERT INTO traditional_predictions (game_type, ai_name, issue, predictions, matches_info, created_at)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, NOW())
            """, (game_type, ai_name, issue,
                  json.dumps(predictions, ensure_ascii=False),
                  json.dumps(matches_info, ensure_ascii=False)))

    conn.commit()
    conn.close()


# ============ 情报库函数 ============

def save_ct_intelligence(issue, match_num, match_data, intelligence_json):
    """将扣子生成的情报存入match_intelligence表"""
    try:
        conn = get_db()
        cur = conn.cursor()
        match_id = f"CT_{issue}_{match_num}"
        home_team = match_data.get("home", "")
        away_team = match_data.get("away", "")
        league = match_data.get("league", "")
        
        # 构造summary
        parts = []
        for k, v in intelligence_json.items():
            if v and str(v).strip() not in ("", "暂无", "待查"):
                label = {"home_recent_form": "主队近况", "away_recent_form": "客队近况", 
                         "head_to_head": "交锋", "home_injuries": "主伤停", "away_injuries": "客伤停",
                         "league_position": "排名", "key_factors": "关键因素"}.get(k, k)
                parts.append(f"{label}: {v}")
        summary = "\n".join(parts) if parts else json.dumps(intelligence_json, ensure_ascii=False)
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT id FROM match_intelligence WHERE match_id = %s", (match_id,))
        if cur.fetchone():
            cur.execute("UPDATE match_intelligence SET basic_data=%s, summary=%s, updated_at=%s WHERE match_id=%s",
                        (json.dumps(intelligence_json, ensure_ascii=False), summary, now, match_id))
        else:
            cur.execute("""INSERT INTO match_intelligence (match_id, home_team, away_team, league, basic_data, summary, created_at, updated_at)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (match_id, home_team, away_team, league,
                         json.dumps(intelligence_json, ensure_ascii=False), summary, now, now))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"  [情报库] 保存CT {issue}_{match_num} 失败: {e}")
        return False


def get_ct_intelligence(issue, match_num):
    """从DB读取CT比赛情报"""
    try:
        conn = get_db()
        cur = conn.cursor()
        match_id = f"CT_{issue}_{match_num}"
        cur.execute("SELECT basic_data, summary FROM match_intelligence WHERE match_id=%s ORDER BY updated_at DESC LIMIT 1", (match_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            bd = row[0]
            if isinstance(bd, str):
                try: bd = json.loads(bd)
                except: bd = {}
            return {"basic_data": bd, "summary": row[1] or ""}
        return None
    except Exception as e:
        print(f"  [情报库] 读取CT情报失败: {e}")
        return None


def format_ct_intelligence_for_prompt(matches, issue):
    """为CT彩构建情报文本，注入其他AI的prompt"""
    lines = []
    for m in matches:
        intel = get_ct_intelligence(issue, m["num"])
        if not intel:
            continue
        bd = intel.get("basic_data", {})
        if not bd:
            continue
        
        parts = []
        if bd.get("home_recent_form"): parts.append(f"近况:{bd['home_recent_form']}")
        if bd.get("away_recent_form"): parts.append(f"客况:{bd['away_recent_form']}")
        if bd.get("head_to_head"): parts.append(f"交锋:{bd['head_to_head']}")
        if bd.get("home_injuries"): parts.append(f"主伤停:{bd['home_injuries']}")
        if bd.get("away_injuries"): parts.append(f"客伤停:{bd['away_injuries']}")
        if bd.get("league_position"): parts.append(f"排名:{bd['league_position']}")
        if bd.get("key_factors"): parts.append(f"关键:{bd['key_factors']}")
        
        if parts:
            lines.append(f"  {m['num']}. [{m['league']}] {m['home']} vs {m['away']} | {'; '.join(parts)}")
    
    if not lines:
        return ""
    
    return "\n\n## 情报数据（联网搜索获取）\n" + "\n".join(lines) + "\n\n请结合以上情报做出预测。\n"


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
        base_prompt = build_ct_prompt(matches, game_type)

        # ===== 情报库：扣子先跑，生成情报 =====
        coze_pre_raw = None
        coze_pre_parsed = None
        
        if "扣子" not in existing:
            print(f"  [情报库] 扣子先跑，生成情报数据...", end=' ', flush=True)
            coze_pre_raw = call_ai_api("扣子", base_prompt)
            if coze_pre_raw:
                coze_pre_parsed = parse_ct_response(coze_pre_raw, game_type)
                if coze_pre_parsed:
                    # 提取每场比赛的情报并保存
                    saved_count = 0
                    for pred_item in coze_pre_parsed:
                        match_num = str(pred_item.get("match", "")).strip()
                        intel = pred_item.pop("intelligence", None)
                        if intel and isinstance(intel, dict):
                            # 找到对应的比赛数据（兼容"1"和"01"两种格式）
                            match_data = next((m for m in matches if str(m["num"]).lstrip('0') == match_num.lstrip('0')), {})
                            has_content = any(v for v in intel.values() if v and str(v).strip() not in ("", "暂无", "待查"))
                            if has_content and match_data:
                                save_ct_intelligence(issue, match_num, match_data, intel)
                                saved_count += 1
                    print(f"完成 (保存{saved_count}场情报)")
                else:
                    print("解析失败")
            else:
                print("无响应")
        
        # 构建带情报的prompt给其他AI
        intel_text = format_ct_intelligence_for_prompt(matches, issue)
        prompt = base_prompt + intel_text if intel_text else base_prompt
        if intel_text:
            print(f"  [情报库] 情报已注入其他AI的prompt")

        for ai_name in AI_NAMES:
            if ai_name in existing:
                print(f"  [{ai_name}] 已有预测，跳过")
                continue

            print(f"  [{ai_name}] 预测中...", end=' ', flush=True)
            
            # 扣子已经预跑过，直接用预跑结果
            if ai_name == "扣子" and coze_pre_raw:
                raw = coze_pre_raw
            else:
                raw = call_ai_api(ai_name, prompt)

            if raw:
                parsed = parse_ct_response(raw, game_type)
                if parsed and len(parsed) >= len(matches):
                    # 清理intelligence字段（不需要存入predictions表）
                    for item in parsed:
                        item.pop("intelligence", None)
                    save_predictions(issue, game_type, matches, ai_name, parsed)
                    print(f"完成 ({len(parsed)}场)")
                else:
                    print(f"解析失败 (got {len(parsed) if parsed else 0} fields)")
            else:
                print("无响应")

            time.sleep(1)

    print(f"\n第{issue}期预测完成!")
    return results



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
