#!/usr/local/bin/python3
"""
traditional_lottery_predict_v4.py - 传统彩7AI预测（v4 写 predictions 表版）

基于 v3 (JC/traditional_lottery_predict.py) 改造，核心变更：
  1. save_predictions 改写 predictions 表（而非 traditional_predictions）
  2. 用 UPSERT (ON CONFLICT match_id, ai_name DO UPDATE)，每场比赛每个AI一条记录
  3. 写入时带 ct_issue（如 CT26098）、ct_ren9（jsonb数组）、ct_game_type（玩法名）
  4. match_id 格式为 CT26098_01，从 matches_info 的 match_id 字段获取（= matches 表 id）
  5. spf_pred / score_pred / goals_pred / half_full_pred 从 predictions 数组中对应场次提取
  6. get_predictions 改为从 predictions 表 WHERE ct_issue IS NOT NULL 查询
  7. fetch_matches_from_db 跳过已有预测的期号（查 predictions 表 WHERE match_id LIKE 'CT期号_%'）
其余逻辑（AI调用、prompt、扣子本地搜索情报）保持不变。

用法:
  python3 traditional_lottery_predict_v4.py                 # 预测最新一期
  python3 traditional_lottery_predict_v4.py --issue 26104   # 预测指定期号
  python3 traditional_lottery_predict_v4.py --game 胜负彩   # 只预测胜负彩
  python3 traditional_lottery_predict_v4.py --force         # 强制重新预测
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import aiohttp

import json
import re
import time
import psycopg2
from datetime import datetime

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres")

# AI配置 - 与 multi_ai_predict.py 保持一致
AI_CONFIGS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "REMOVED"),
        "model": "deepseek-chat",
        "max_tokens": 1500,
    },
    "MiniMax": {
        "base_url": "https://api.minimaxi.com/v1/chat/completions",
        "api_key": os.environ.get("MINIMAX_API_KEY", "sk-api-taOJjMl9mnCFBuHWKkQ0_2mDhJpDV_ecQ4S6VEQvuBO180a10T7jIUDLxwsQUfHy4fpGy5Mk18sOVhWRyJBVGhfCsNXiwjAbFGgKIo_7oxFzzn1YoARPcHI"),
        "model": "MiniMax-Text-01",
        "max_tokens": 1500,
    },
    "文心": {
        "base_url": "https://qianfan.baidubce.com/v2/chat/completions",
        "api_key": os.environ.get("WENXIN_API_KEY", "REMOVED"),
        "model": "ernie-4.0-8k-latest",
        "max_tokens": 1500,
    },
    "智谱清言": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_key": os.environ.get("ZHIPU_API_KEY", "REMOVED"),
        "model": "glm-4-flash",
        "max_tokens": 1500,
    },
    "混元": {
        "base_url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "api_key": os.environ.get("HUNYUAN_API_KEY", "REMOVED"),
        "model": "hy-mt2-lite",
        "max_tokens": 1500,
    },
    "豆包": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key": os.environ.get("DOUBAO_API_KEY", "ark-e27a1337-a759-46fb-b30c-efe5ce5541bd-2a204"),
        "model": "ep-20260706041055-2mgpf",
        "max_tokens": 1500,
        "timeout": 60,
    },
    "扣子": {
        "base_url": "https://7hsjv6c4cn.coze.site/stream_run",
        "api_key": os.environ.get("COZE_PROJECT_API_TOKEN", "REMOVED"),
        "model": None,
        "max_tokens": 1500,
        "timeout": 120,
        "format": "coze_code",
        "project_id": 7667164681706078217,
    },
}

# 4个维度的Prompt模板
PROMPTS = {
    "胜负彩": """你是专业传统足彩分析师，请为以下胜负彩14场比赛生成预测。

## 比赛列表
{matches}

## 输出要求
为每场比赛输出：
- match: 场次编号(01-14)
- spf: 胜平负预测(3=主胜, 1=平, 0=客胜)
- r9: 是否推荐任9(true/false)
- analysis: 50字内分析

## 输出格式
输出JSON数组：
[{{"match": "01", "spf": "3", "r9": true, "analysis": "..."}}, ...]
必须包含所有14场比赛。""",
    "半全场": """你是专业传统足彩分析师，请为以下半全场14场比赛生成预测。

## 比赛列表
{matches}

## 输出要求
为每场比赛输出：
- match: 场次编号(01-14)
- bqc: 半全场预测(两位数字，第一位=半场结果3主胜/1平/0客胜，第二位=全场结果)
- r9: 是否推荐任9(true/false)
- analysis: 50字内分析

## 输出格式
输出JSON数组：
[{{"match": "01", "bqc": "31", "r9": true, "analysis": "..."}}, ...]
必须包含所有14场比赛。""",
    "进球彩": """你是专业传统足彩分析师，请为以下进球彩14场比赛生成预测。

## 比赛列表
{matches}

## 输出要求
为每场比赛输出：
- match: 场次编号(01-14)
- zjq_home: 主队进球数档位(0/1/2/3，3代表3球及以上)
- zjq_away: 客队进球数档位(0/1/2/3)
- r9: 是否推荐任9(true/false)
- analysis: 50字内分析

## 输出格式
输出JSON数组：
[{{"match": "01", "zjq_home": "1", "zjq_away": "0", "r9": true, "analysis": "..."}}, ...]
必须包含所有14场比赛。""",
    "任9": """你是专业传统足彩分析师，请为以下任9场比赛生成预测（从14场中选9场最有把握的）。

## 比赛列表
{matches}

## 输出要求
从14场比赛中选出9场，为每场输出：
- match: 场次编号(01-14)
- spf: 胜平负预测(3=主胜, 1=平, 0=客胜)
- r9: 是否被选入任9(true/false)
- analysis: 50字内分析

## 输出格式
输出JSON数组：
[{{"match": "01", "spf": "3", "r9": true, "analysis": "..."}}, ...]
必须且只能选出9场(r9=true)，必须包含被选中的9场。""",
}

# 扣子情报搜集 prompt
CT_INTELLIGENCE_PROMPT = """你是专业足球情报分析师。请为以下比赛搜集最新情报：

- 期号: {issue}，场次: {num}
- 联赛: {league}
- 对阵: {home_team} vs {away_team}
- 比赛时间: {match_time}

请联网搜索并返回以下格式（严格JSON对象）:
```json
{{
  "intelligence": {{
    "home_recent_form": "主队近况",
    "away_recent_form": "客队近况",
    "head_to_head": "历史交锋",
    "home_injuries": "主队伤停",
    "away_injuries": "客队伤停",
    "league_position": "联赛排名",
    "key_factors": "关键因素"
  }},
  "prediction": {{
    "spf": "3",
    "analysis": "简要预测分析"
  }}
}}
```
必须通过联网搜索填写真实数据。"""


# ============================================================
# 数据库操作
# ============================================================

def get_db():
    return psycopg2.connect(DB_URL)


def get_ct_matches(conn, issue=None):
    """从matches表获取CT比赛"""
    cur = conn.cursor()

    if issue:
        cur.execute("""
            SELECT id, home_team, away_team, metadata
            FROM matches
            WHERE metadata->>'match_type' = 'ct'
              AND metadata->>'issue' = %s
            ORDER BY (metadata->>'issue_num')::int
        """, (issue,))
    else:
        # 获取最新一期
        cur.execute("""
            SELECT id, home_team, away_team, metadata
            FROM matches
            WHERE metadata->>'match_type' = 'ct'
            ORDER BY metadata->>'issue' DESC, (metadata->>'issue_num')::int
            LIMIT 14
        """)

    rows = cur.fetchall()
    conn.commit()

    if not rows:
        return None, []

    first_meta = rows[0][3] if isinstance(rows[0][3], dict) else json.loads(rows[0][3]) if rows[0][3] else {}
    current_issue = first_meta.get('issue')

    matches = []
    for row in rows:
        meta = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}
        matches.append({
            "id": row[0],
            "match_id": row[0],
            "num": str(meta.get('issue_num', '')).zfill(2),
            "home": row[1] or meta.get('home_team', '待定'),
            "away": row[2] or meta.get('away_team', '待定'),
            "league": meta.get('league', ''),
            "time": meta.get('match_time', ''),
            "issue": current_issue,
        })

    return current_issue, matches


def fetch_matches_from_db(issue=None):
    """从 matches 表读取赛程，并跳过已有预测的期号。

    - 默认预测最新一期（不受 status 限制，所有抓取到的 CT 比赛都跑预测）
    - 若该期号在 predictions 表已有预测（match_id LIKE 'CT{issue}_%'）且非强制，
      则返回空列表，由调用方跳过。
    """
    conn = get_db()
    try:
        # 先看指定/最新一期是否已存在预测
        if issue:
            cur = conn.cursor()
            cur.execute("SELECT id FROM predictions WHERE match_id LIKE %s LIMIT 1", (f"CT{issue}_%",))
            has_pred = cur.fetchone() is not None
            cur.close()
            if has_pred:
                print(f"期号{issue} 已有预测，跳过 (fetch_matches_from_db)")
                return issue, []
            return get_ct_matches(conn, issue)

        # 未指定期号：找最新一期且未预测的期号
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT metadata->>'issue' AS iss
            FROM matches
            WHERE metadata->>'match_type' = 'ct'
            ORDER BY iss DESC
            LIMIT 5
        """)
        candidates = [r[0] for r in cur.fetchall()]
        cur.close()

        for cand in candidates:
            if not cand:
                continue
            cur = conn.cursor()
            cur.execute("SELECT id FROM predictions WHERE match_id LIKE %s LIMIT 1", (f"CT{cand}_%",))
            has_pred = cur.fetchone() is not None
            cur.close()
            if has_pred:
                print(f"期号{cand} 已有预测，跳过 (fetch_matches_from_db)")
                continue
            issue, matches = get_ct_matches(conn, cand)
            return issue, matches

        print("所有候选期号均已有预测 (fetch_matches_from_db)")
        return None, []
    finally:
        conn.close()


def get_predictions(issue=None, game_type=None):
    """从 predictions 表查询 CT 已有预测的 AI（ct_issue IS NOT NULL）。

    Returns:
        set: 已有预测的 (issue) 集合；主要用于期号级跳过判断。
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        if issue and game_type:
            cur.execute("""
                SELECT DISTINCT ai_name FROM predictions
                WHERE ct_issue = %s AND ct_game_type = %s
            """, (f"CT{issue}" if not str(issue).startswith('CT') else issue, game_type))
        elif issue:
            cur.execute("""
                SELECT DISTINCT ai_name FROM predictions
                WHERE ct_issue = %s
            """, (f"CT{issue}" if not str(issue).startswith('CT') else issue,))
        else:
            cur.execute("SELECT DISTINCT ai_name FROM predictions WHERE ct_issue IS NOT NULL")
        existing = set(row[0] for row in cur.fetchall())
        cur.close()
        return existing
    finally:
        conn.close()


# ============================================================
# 情报库操作
# ============================================================

def save_match_intelligence(match, intelligence_data):
    """将情报告写入 match_intelligence 表（upsert）"""
    conn = get_db()
    try:
        cur = conn.cursor()
        match_id = match.get("match_id") or f"CT{match['issue']}_{match['num']}"

        cur.execute("SELECT id FROM match_intelligence WHERE match_id = %s", (match_id,))
        existing = cur.fetchone()

        basic_data = intelligence_data.get("basic_data")
        if isinstance(basic_data, dict):
            basic_data = json.dumps(basic_data, ensure_ascii=False)

        expert_opinions = intelligence_data.get("expert_opinions")
        if isinstance(expert_opinions, dict):
            expert_opinions = json.dumps(expert_opinions, ensure_ascii=False)

        market_sentiment = intelligence_data.get("market_sentiment")
        if isinstance(market_sentiment, dict):
            market_sentiment = json.dumps(market_sentiment, ensure_ascii=False)

        summary = intelligence_data.get("summary", "")
        match_time = match.get("time")
        home_team = match.get("home", "")
        away_team = match.get("away", "")
        league = match.get("league", "")

        if existing:
            cur.execute("""
                UPDATE match_intelligence
                SET home_team = %s, away_team = %s, match_time = %s, league = %s,
                    basic_data = %s::jsonb, expert_opinions = %s::jsonb,
                    market_sentiment = %s::jsonb,
                    summary = %s, updated_at = NOW()
                WHERE match_id = %s
            """, (home_team, away_team, match_time, league,
                  basic_data, expert_opinions, market_sentiment,
                  summary, match_id))
        else:
            cur.execute("""
                INSERT INTO match_intelligence
                (match_id, home_team, away_team, match_time, league,
                 basic_data, expert_opinions, market_sentiment, summary)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            """, (match_id, home_team, away_team, match_time, league,
                  basic_data, expert_opinions, market_sentiment, summary))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 写入情报告失败 match={match.get('id')}: {e}")
        return False
    finally:
        conn.close()


def fetch_match_intelligence(match_id):
    """从 match_intelligence 表读取情报"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT basic_data, expert_opinions, market_sentiment, summary
            FROM match_intelligence
            WHERE match_id = %s
        """, (match_id,))
        row = cur.fetchone()

        if not row:
            return None

        def parse_jsonb(val):
            if val is None:
                return None
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            return val

        return {
            "basic_data": parse_jsonb(row[0]),
            "expert_opinions": parse_jsonb(row[1]),
            "market_sentiment": parse_jsonb(row[2]),
            "summary": row[3] or "",
        }
    except Exception as e:
        print(f"[ERROR] 读取情报告失败 match={match_id}: {e}")
        return None
    finally:
        conn.close()


def format_intelligence_section(intelligence):
    """将情报数据格式化为prompt文本块"""
    if not intelligence:
        return ""
    lines = []
    basic = intelligence.get("basic_data") or {}
    if isinstance(basic, dict):
        labels = {
            "home_recent_form": "主队近况",
            "away_recent_form": "客队近况",
            "head_to_head": "历史交锋",
            "home_injuries": "主队伤停",
            "away_injuries": "客队伤停",
            "league_position": "联赛排名",
            "key_factors": "关键因素",
        }
        for k, label in labels.items():
            v = basic.get(k)
            if v:
                lines.append(f"- {label}: {v}")
    summary = intelligence.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append(f"- 综合: {summary.strip()}")
    return "\n".join(lines)


def build_matches_text(matches):
    """构建比赛列表文本"""
    lines = []
    for m in matches:
        lines.append(f"{m['num']}. [{m['league']}] {m['home']} vs {m['away']} ({m['time']})")
    return "\n".join(lines)


def build_matches_info(matches):
    """构建matches_info JSON，每项含 match_id（格式 CT26098_01 = matches 表 id）"""
    return [{
        "match_id": m.get("match_id") or m["id"],
        "id": m["id"],
        "num": m["num"],
        "home": m["home"],
        "away": m["away"],
        "league": m["league"],
        "time": m["time"],
        "issue": m["issue"],
    } for m in matches]


# ============================================================
# AI 调用（扣子本地搜索 + OpenAI 格式）
# ============================================================

async def call_ai_api(session, ai_name, prompt, sem):
    """调用单个AI API"""
    config = AI_CONFIGS[ai_name]

    async with sem:
        try:
            # 扣子专用逻辑（Coze Code 本地搜索）
            if config.get("format") == "coze_code":
                headers = {
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "content": {
                        "query": {
                            "prompt": [{"type": "text", "content": {"text": prompt}}]
                        }
                    },
                    "type": "query",
                    "session_id": f"ct_predict_{int(time.time())}",
                }
                if config.get("project_id"):
                    payload["project_id"] = config["project_id"]

                timeout = aiohttp.ClientTimeout(total=config.get("timeout", 120))
                async with session.post(
                    config["base_url"],
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        print(f"  [WARN] {ai_name} HTTP {resp.status}: {text[:200]}")
                        return None

                    content_type = resp.headers.get("Content-Type", "")

                    if "json" in content_type:
                        data = await resp.json()
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

                    # SSE流式响应
                    answer_chunks = []
                    async for line in resp.content:
                        line_str = line.decode("utf-8").strip()
                        if not line_str:
                            continue
                        if line_str.startswith("data:"):
                            line_str = line_str[5:].strip()
                            if not line_str:
                                continue
                            try:
                                evt = json.loads(line_str)
                                if isinstance(evt, dict):
                                    if evt.get("type") == "answer":
                                        content = evt.get("content", {})
                                        if isinstance(content, dict):
                                            chunk = content.get("answer")
                                            if chunk:
                                                answer_chunks.append(chunk)
                            except json.JSONDecodeError:
                                pass
                    if answer_chunks:
                        full_answer = "".join(answer_chunks)
                        return full_answer

                    return await resp.text()

            # 标准OpenAI格式
            headers = {
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": config["max_tokens"],
                "temperature": 0.7,
            }

            timeout = aiohttp.ClientTimeout(total=config.get("timeout", 60))
            async with session.post(
                config["base_url"],
                headers=headers,
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"  [WARN] {ai_name} HTTP {resp.status}: {text[:200]}")
                    return None

                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content if content else None

        except asyncio.TimeoutError:
            print(f"  [WARN] {ai_name} 超时")
            return None
        except Exception as e:
            print(f"  [WARN] {ai_name} 异常: {e}")
            return None


def normalize_bqc(value):
    """标准化半全场bqc字段，将混合格式转为两位数字代码"""
    if not value:
        return value

    value = str(value).strip()

    if re.match(r'^[013][013]$', value):
        return value

    result_map = {'胜': '3', '平': '1', '负': '0'}

    match = re.match(r'^([013])([胜平负])$', value)
    if match:
        first = match.group(1)
        second_char = match.group(2)
        second = result_map.get(second_char, '')
        if second:
            return first + second

    match = re.match(r'^([胜平负])([胜平负])$', value)
    if match:
        first_char = match.group(1)
        second_char = match.group(2)
        first = result_map.get(first_char, '')
        second = result_map.get(second_char, '')
        if first and second:
            return first + second

    return value


def parse_prediction(content, game_type, match_count):
    """解析AI返回的预测"""
    if not content:
        return None

    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    content = content.strip()

    json_match = re.search(r'\[[\s\S]*?\](?=\s*[^\[\{]|\s*$)', content)
    if json_match:
        try:
            predictions = json.loads(json_match.group())
            if isinstance(predictions, list) and len(predictions) > 0:
                return predictions
        except json.JSONDecodeError:
            pass

    json_match = re.search(r'\{[\s\S]*?\}(?=\s*[^\[\{]|\s*$)', content)
    if json_match:
        try:
            obj = json.loads(json_match.group())
            if isinstance(obj, dict):
                return [obj]
        except json.JSONDecodeError:
            pass

    try:
        data = json.loads(content)
        if isinstance(data, list) and len(data) > 0:
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    print(f"  [DEBUG] 解析失败，原始内容前200字符: {content[:200]}")
    return None


async def call_kouzi_intelligence(session, match, sem):
    """扣子专用：搜集单场比赛情报"""
    config = AI_CONFIGS["扣子"]

    prompt = CT_INTELLIGENCE_PROMPT.format(
        issue=match.get("issue", ""),
        num=match.get("num", ""),
        league=match.get("league", ""),
        home_team=match.get("home", ""),
        away_team=match.get("away", ""),
        match_time=match.get("time", ""),
    )

    match_id = match.get("match_id") or f"CT{match['issue']}_{match['num']}"

    async with sem:
        try:
            headers = {
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            }
            payload = {
                "content": {
                    "query": {
                        "prompt": [{"type": "text", "content": {"text": prompt}}]
                    }
                },
                "type": "query",
                "session_id": f"ct_intel_{match_id}_{int(time.time())}",
            }
            if config.get("project_id"):
                payload["project_id"] = config["project_id"]

            timeout = aiohttp.ClientTimeout(total=config.get("timeout", 120))
            async with session.post(
                config["base_url"],
                headers=headers,
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return None, f"HTTP {resp.status}: {text[:100]}"

                content_type = resp.headers.get("Content-Type", "")

                answer_chunks = []
                async for line in resp.content:
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    if line_str.startswith("data:"):
                        line_str = line_str[5:].strip()
                        if not line_str:
                            continue
                        try:
                            evt = json.loads(line_str)
                            if isinstance(evt, dict):
                                if evt.get("type") == "answer":
                                    content = evt.get("content", {})
                                    if isinstance(content, dict):
                                        chunk = content.get("answer")
                                        if chunk:
                                            answer_chunks.append(chunk)
                        except json.JSONDecodeError:
                            pass

                if answer_chunks:
                    return "".join(answer_chunks), None

                if "json" in content_type:
                    data = await resp.json()
                    if isinstance(data, dict):
                        if "result" in data:
                            return str(data["result"]), None
                        if "text" in data:
                            return str(data["text"]), None
                    return json.dumps(data, ensure_ascii=False), None

                return await resp.text(), None

        except asyncio.TimeoutError:
            return None, "超时"
        except Exception as e:
            return None, str(e)


def parse_kouzi_intelligence_response(raw_text):
    """解析扣子返回的情报+预测JSON"""
    if not raw_text:
        return None, None

    content = re.sub(r'```json\s*', '', raw_text)
    content = re.sub(r'```\s*', '', content)
    content = content.strip()

    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, dict):
                intelligence = data.get("intelligence")
                prediction = data.get("prediction")
                return intelligence, prediction
        except json.JSONDecodeError:
            pass

    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data.get("intelligence"), data.get("prediction")
    except json.JSONDecodeError:
        pass

    print(f"  [DEBUG] 情报解析失败，原始内容前200字符: {content[:200]}")
    return None, None


# ============================================================
# 保存到 predictions 表（v4 核心）
# ============================================================

def _extract_dim(pred, game_type):
    """从单场预测 dict 提取各维度字段"""
    spf = pred.get("spf")
    bqc = pred.get("bqc")
    zjq_home = pred.get("zjq_home")
    zjq_away = pred.get("zjq_away")

    spf_pred = None
    score_pred = None
    goals_pred = None
    half_full_pred = None
    handicap_spf_pred = None

    if game_type == "胜负彩":
        spf_pred = str(spf) if spf is not None else None
    elif game_type == "半全场":
        half_full_pred = normalize_bqc(bqc) if bqc is not None else None
    elif game_type == "进球彩":
        # 进球彩没有单值 spf，落到 prediction JSONB（含 zjq_home/zjq_away）
        pass
    elif game_type == "任9":
        spf_pred = str(spf) if spf is not None else None

    return spf_pred, score_pred, goals_pred, half_full_pred, handicap_spf_pred


def save_predictions(issue, game_type, matches, ai_name, predictions):
    """将某一 AI 的预测写入 predictions 表（UPSERT，每场比赛每个AI一条记录）。

    变更点（相对 v3）:
      - 目标表由 traditional_predictions 改为 predictions
      - 用 ON CONFLICT (match_id, ai_name) DO UPDATE
      - 写入 ct_issue / ct_ren9(jsonb数组) / ct_game_type
      - match_id 源自 matches_info 的 match_id（格式 CT26098_01）
      - spf_pred/score_pred/goals_pred/half_full_pred 从 predictions 数组对应场次提取

    Args:
        issue: 期号（不包含 CT 前缀，如 26121）
        game_type: 玩法名（胜负彩/半全场/进球彩/任9）
        matches: 比赛列表（含 match_id）
        ai_name: AI 名称
        predictions: parse 出的预测 dict 数组
    """
    conn = get_db()
    saved = 0
    try:
        cur = conn.cursor()
        ct_issue = f"CT{issue}" if not str(issue).startswith('CT') else str(issue)
        matches_info = build_matches_info(matches)

        # 任9/推荐场次作为 ct_ren9 jsonb 数组
        ct_ren9 = None
        if predictions:
            picks = [str(p.get("match", "")).zfill(2) for p in predictions if p.get("r9") or p.get("ren9")]
            if picks:
                ct_ren9 = json.dumps(picks, ensure_ascii=False)

        # 以 match_id 为键，把 predictions 数组按场次归位
        pred_by_num = {}
        for p in predictions:
            num = str(p.get("match", "")).strip().zfill(2)
            pred_by_num[num] = p

        for mi in matches_info:
            match_id = mi["match_id"]
            num = mi["num"]
            pred = pred_by_num.get(num, {})

            spf_pred, score_pred, goals_pred, half_full_pred, handicap_spf_pred = _extract_dim(pred, game_type)

            cur.execute("""
                INSERT INTO predictions
                  (match_id, ai_name, prediction, analysis, is_settled,
                   spf_pred, score_pred, goals_pred, half_full_pred, handicap_spf_pred,
                   sport_type, ct_issue, ct_ren9, ct_game_type, raw_response)
                VALUES (%s, %s, %s::jsonb, %s, false, %s, %s, %s, %s, %s, 'CT', %s, %s::jsonb, %s, %s)
                ON CONFLICT (match_id, ai_name) DO UPDATE SET
                   prediction = EXCLUDED.prediction,
                   analysis = EXCLUDED.analysis,
                   spf_pred = EXCLUDED.spf_pred,
                   score_pred = EXCLUDED.score_pred,
                   goals_pred = EXCLUDED.goals_pred,
                   half_full_pred = EXCLUDED.half_full_pred,
                   handicap_spf_pred = EXCLUDED.handicap_spf_pred,
                   ct_issue = EXCLUDED.ct_issue,
                   ct_ren9 = EXCLUDED.ct_ren9,
                   ct_game_type = EXCLUDED.ct_game_type,
                   raw_response = EXCLUDED.raw_response
            """, (
                match_id,
                ai_name,
                json.dumps(pred, ensure_ascii=False),
                pred.get("analysis", "") or "",
                spf_pred,
                score_pred,
                goals_pred,
                half_full_pred,
                handicap_spf_pred,
                ct_issue,
                ct_ren9,
                game_type,
                json.dumps(pred, ensure_ascii=False),
            ))
            saved += 1

        conn.commit()
        if ct_ren9:
            print(f"  [入库] {ai_name}: {saved}场写入 predictions (ct_ren9={picks})")
        else:
            print(f"  [入库] {ai_name}: {saved}场写入 predictions (ct_issue={ct_issue}, {game_type})")
        return saved
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 写入 predictions 失败 ai={ai_name}: {e}")
        return 0
    finally:
        cur.close()
        conn.close()


# ============================================================
# 预测主流程（保留 v3 两阶段：扣子情报 + 其余6AI预测）
# ============================================================

async def predict_for_game_type_with_intel(game_type, matches, ai_names, intelligence_cache, force=False):
    """为单个维度生成预测（带情报增强），写 predictions 表"""
    print(f"\n--- {game_type} ---")

    conn = get_db()
    issue = matches[0]["issue"] if matches else None

    if not issue:
        print("无比赛数据")
        conn.close()
        return 0

    ct_issue = f"CT{issue}" if not str(issue).startswith('CT') else str(issue)

    # 检查该期该玩法下已有哪些 AI 有预测（从 predictions 表查）
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ai_name FROM predictions
        WHERE ct_issue = %s AND ct_game_type = %s
    """, (ct_issue, game_type))
    existing = set(row[0] for row in cur.fetchall())
    conn.commit()

    if existing and not force:
        print(f"期号{issue}的{game_type}已有预测: {existing}")
        conn.close()
        return 0

    # force 模式：删除旧的该期该玩法 CT 预测
    if force and existing:
        cur.execute("""
            DELETE FROM predictions
            WHERE ct_issue = %s AND ct_game_type = %s
        """, (ct_issue, game_type))
        conn.commit()
        print(f"已删除旧预测记录（predictions，{game_type}）")
        existing = set()

    matches_text = build_matches_text(matches)
    matches_info = build_matches_info(matches)
    prompt_template = PROMPTS.get(game_type, PROMPTS["胜负彩"])
    base_prompt = prompt_template.format(matches=matches_text)

    if intelligence_cache:
        intel_lines = ["\n\n## 已搜集情报（来自联网搜索）"]
        for match in matches:
            match_id = match.get("match_id") or f"CT{match['issue']}_{match['num']}"
            intel = intelligence_cache.get(match_id)
            if intel:
                intel_section = format_intelligence_section(intel)
                if intel_section:
                    intel_lines.append(f"\n### 第{match['num']}场 {match['home']} vs {match['away']}")
                    intel_lines.append(intel_section)

        if len(intel_lines) > 1:
            insert_marker = "## 输出格式"
            if insert_marker in base_prompt:
                idx = base_prompt.index(insert_marker)
                base_prompt = base_prompt[:idx] + "\n".join(intel_lines) + "\n\n" + base_prompt[idx:]
            else:
                base_prompt += "\n".join(intel_lines)

    print(f"期号: {issue}, 比赛数: {len(matches)}, 情报数: {len(intelligence_cache)}")

    sem = asyncio.Semaphore(3)
    total_saved = 0

    async with aiohttp.ClientSession() as session:
        for ai_name in ai_names:
            if ai_name in existing and not force:
                continue

            try:
                content = await call_ai_api(session, ai_name, base_prompt, sem)

                if not content:
                    print(f"  [WARN] {ai_name}: 无响应")
                    continue

                predictions = parse_prediction(content, game_type, len(matches))
                if not predictions:
                    print(f"  [WARN] {ai_name}: 解析失败")
                    continue

                # 半全场维度：标准化 bqc 字段
                if game_type == "半全场" and predictions:
                    for p in predictions:
                        if 'bqc' in p:
                            p['bqc'] = normalize_bqc(p['bqc'])

                # 立即入库（predictions 表）
                n = save_predictions(issue, game_type, matches, ai_name, predictions)
                total_saved += n
                print(f"  [OK] {ai_name}: {n}场写入 predictions")

            except Exception as e:
                print(f"  [FAIL] {ai_name}: {e}")
                conn.rollback()

    conn.close()
    return total_saved


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", help="指定期号")
    parser.add_argument("--force", action="store_true", help="强制重新预测")
    parser.add_argument("--game", help="指定维度(胜负彩/半全场/进球彩/任9)")
    args = parser.parse_args()

    issue, matches = fetch_matches_from_db(args.issue)
    if not matches:
        print("没有需要预测的CT比赛（可能已全部预测）")
        return

    print(f"期号: {issue}, 比赛数: {len(matches)}")
    for m in matches[:3]:
        print(f"  {m['num']}. {m['home']} vs {m['away']}")
    if len(matches) > 3:
        print(f"  ... 共{len(matches)}场")

    game_types = [args.game] if args.game else ["胜负彩", "半全场", "进球彩", "任9"]

    # ===== Phase 1: 扣子情报搜集（本地搜索） =====
    print(f"\n{'='*50}")
    print(f"[Phase 1] 扣子情报搜集 ({len(matches)} 场比赛)")
    print(f"{'='*50}")

    kouzi_intelligence = {}
    sem = asyncio.Semaphore(3)
    timeout = aiohttp.ClientTimeout(total=120)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for match in matches:
            tasks.append(call_kouzi_intelligence(session, match, sem))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            match = matches[i]
            match_id = match.get("match_id") or f"CT{match['issue']}_{match['num']}"

            if isinstance(result, Exception):
                print(f"  [FAIL] {match_id}: {result}")
                continue

            raw_text, error = result
            if error:
                print(f"  [WARN] {match_id}: {error}")
                continue

            if raw_text:
                intelligence_data, prediction_data = parse_kouzi_intelligence_response(raw_text)
                if intelligence_data:
                    if save_match_intelligence(match, intelligence_data):
                        kouzi_intelligence[match_id] = intelligence_data
                        print(f"  [OK] {match_id}: 情报已保存")

    print(f"\n[Phase 1 完成] 成功搜集 {len(kouzi_intelligence)}/{len(matches)} 场比赛情报")

    # ===== Phase 2: 其他6个AI基于情报预测 =====
    print(f"\n{'='*50}")
    print(f"[Phase 2] 其他6个AI基于情报预测")
    print(f"{'='*50}")

    other_ai_names = [name for name in AI_CONFIGS.keys() if name != "扣子"]

    total = 0
    for game_type in game_types:
        count = await predict_for_game_type_with_intel(game_type, matches, other_ai_names, kouzi_intelligence, args.force)
        total += count

    print(f"\n{'='*50}")
    print(f"[完成] 共生成 {total} 条预测（写入 predictions 表）")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())