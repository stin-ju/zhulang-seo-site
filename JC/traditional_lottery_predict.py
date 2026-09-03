#!/usr/bin/env python3
"""
传统彩票预测脚本 - 为胜负彩/半全场/进球彩/任9生成AI预测

数据源: matches表中match_type='ct'的比赛
输出: traditional_predictions表

用法:
  python3 traditional_lottery_predict.py              # 预测最新一期
  python3 traditional_lottery_predict.py --issue 26104  # 预测指定期号
  python3 traditional_lottery_predict.py --force      # 强制重新预测
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import aiohttp

# ====== psycopg2 自愈逻辑（FaaS容器不重启，依赖可能丢失） ======
import importlib, subprocess, shutil
try:
    import psycopg2
    psycopg2.__version__
    from psycopg2._psycopg import __file__ as _test  # noqa: F401
    del _test
except (ImportError, ModuleNotFoundError, AttributeError, OSError):
    _target = '/opt/bytefaas/site-packages' if os.path.exists('/opt/bytefaas/site-packages') else None
    _pip_cmd = [sys.executable, '-m', 'pip', 'install', 'psycopg2-binary', '--no-cache-dir', '--force-reinstall']
    if _target:
        for _p in [os.path.join(_target, 'psycopg2')]:
            if os.path.isdir(_p): shutil.rmtree(_p, ignore_errors=True)
        import glob as _glob
        for _d in _glob.glob(os.path.join(_target, 'psycopg2-*dist-info')):
            shutil.rmtree(_d, ignore_errors=True)
        _pip_cmd += ['--target', _target]
        if _target not in (os.environ.get('PYTHONPATH') or ''):
            os.environ['PYTHONPATH'] = _target + ':' + (os.environ.get('PYTHONPATH') or '')
            sys.path.insert(0, _target)
    subprocess.check_call(_pip_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _mod in list(sys.modules.keys()):
        if 'psycopg2' in _mod: del sys.modules[_mod]
    import psycopg2
# ====== psycopg2 自愈结束 ======

import json
import re
import time
from datetime import datetime

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres")

# AI配置 - 与multi_ai_predict.py保持一致
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

    "半全场": """你是专业传统足彩分析师，请为以下比赛生成半全场预测。

## 比赛列表
{matches}

## 输出要求
为每场比赛输出：
- match: 场次编号(01-14)
- bqc: 半全场预测(33=胜胜, 31=胜平, 30=胜负, 13=平胜, 11=平平, 10=平负, 03=负胜, 01=负平, 00=负负)
- analysis: 50字内分析

## 输出格式
输出JSON数组：
[{{"match": "01", "bqc": "33", "analysis": "..."}}, ...]
必须包含所有14场比赛。""",

    "进球彩": """你是专业传统足彩分析师，请为以下比赛生成进球数预测。

## 比赛规则
4场进球彩：对每场比赛的主队和客队分别预测全场90分钟进球数量。
每支球队进球数选项：0球、1球、2球、3+球（3球及以上）

## 重要：必须分别预测主队和客队进球数！
- zjq_home: 主队进球数（不是总进球！）
- zjq_away: 客队进球数（不是总进球！）
- 禁止使用 zjq 字段，必须用 zjq_home 和 zjq_away

## 示例
假设预测某场比赛主队进2球、客队进1球：
正确：{{"match": "01", "zjq_home": "2", "zjq_away": "1", "analysis": "..."}}
错误：{{"match": "01", "zjq": "3", "analysis": "..."}}  ← 禁止！

## 输出格式
输出JSON数组：
[{{"match": "01", "zjq_home": "1", "zjq_away": "2", "analysis": "主队进攻一般，客队防守较弱"}}, ...]
必须包含所有14场比赛，每场必须有 zjq_home 和 zjq_away 两个字段。""",

    "任9": """你是专业传统足彩分析师，请从以下14场比赛中选出9场最有把握的比赛，生成任9预测。

## 比赛列表
{matches}

## 输出要求
- 从14场中选出9场最有把握的比赛
- 为每场选出的比赛输出胜平负预测(3=主胜, 1=平, 0=客胜)
- 分析为什么选择这9场

## 输出格式
输出JSON数组（只包含9场）：
[{{"match": "01", "spf": "3", "analysis": "选择理由..."}}, ...]
必须恰好9场比赛。"""
}

# CT彩情报搜集Prompt（扣子专用）
CT_INTELLIGENCE_PROMPT = """你是一个专业的传统足彩情报分析师。请联网搜索以下比赛的最新情报，然后结合情报给出预测。

## 比赛信息
- 期号: {issue}
- 场次: 第{num}场
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}

## 情报搜集要求（必须联网搜索）

请依次搜索以下4个维度的情报：

### 1. 双方近况（basic_data）
- 搜索两队最近5场比赛的战绩（胜平负、进失球）
- 搜索主队主场战绩、客队客场战绩
- 搜索两队近期状态趋势（连胜/连败）

### 2. 伤停信息（basic_data）
- 搜索两队最新伤停名单
- 重点关注核心球员是否缺阵

### 3. 历史交锋（basic_data）
- 搜索两队近5次交锋记录
- 注意主客场因素

### 4. 专家分析（expert_opinions）
- 搜索主流媒体的赛前分析文章
- 搜索知名分析师的预测观点

## 请严格按以下JSON格式输出（不要输出其他内容）:
```json
{{
  "intelligence": {{
    "basic_data": {{
      "home_form": "主队近5场战绩描述",
      "away_form": "客队近5场战绩描述",
      "home_injuries": "主队伤停信息",
      "away_injuries": "客队伤停信息",
      "h2h": "历史交锋记录"
    }},
    "expert_opinions": {{
      "consensus": "专家主流观点",
      "key_points": ["分析要点1", "分析要点2", "分析要点3"]
    }},
    "market_sentiment": {{
      "odds_trend": "赔率变化趋势（如有）",
      "money_flow": "资金流向分析（如有）"
    }},
    "summary": "情报总结，100字以内"
  }},
  "prediction": {{
    "spf": "胜平负预测(3=主胜, 1=平, 0=客胜)",
    "bqc": "半全场预测(如胜胜/平胜/负平)",
    "zjq": "总进球数(0-7)",
    "r9_recommended": true或false,
    "confidence": 把握度(0.3-0.95),
    "analysis": "50-100字分析理由，需结合情报"
  }}
}}
```"""


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
        # 获取最新一期（不限制状态，所有抓取到的CT彩比赛都跑预测）
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
    
    # 获取期号
    first_meta = rows[0][3] if isinstance(rows[0][3], dict) else json.loads(rows[0][3]) if rows[0][3] else {}
    current_issue = first_meta.get('issue')
    
    matches = []
    for row in rows:
        meta = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}
        matches.append({
            "id": row[0],
            "num": str(meta.get('issue_num', '')).zfill(2),
            "home": row[1] or meta.get('home_team', '待定'),
            "away": row[2] or meta.get('away_team', '待定'),
            "league": meta.get('league', ''),
            "time": meta.get('match_time', ''),
            "issue": current_issue,
        })
    
    return current_issue, matches


# ============================================================
# 情报库操作
# ============================================================
def save_match_intelligence(match, intelligence_data):
    """将情报告写入 match_intelligence 表（upsert）
    
    Args:
        match: dict，包含 id, home, away, time, league, issue, num
        intelligence_data: dict，包含 basic_data, expert_opinions, market_sentiment, summary
    
    Returns:
        bool: 成功返回 True，失败返回 False
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        # CT比赛使用 CT{issue}_{num} 格式的 match_id
        match_id = f"CT{match['issue']}_{match['num']}"
        
        # 检查是否已存在
        cur.execute("SELECT id FROM match_intelligence WHERE match_id = %s", (match_id,))
        existing = cur.fetchone()
        
        # 序列化 jsonb 字段
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
            # UPDATE
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
            # INSERT
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
    """从 match_intelligence 表读取情报
    
    Args:
        match_id: str，比赛ID（CT格式: CT{issue}_{num}）
    
    Returns:
        dict or None: 包含 basic_data, expert_opinions, market_sentiment, summary
                      如果不存在返回 None
    """
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
        
        # 反序列化 jsonb 字段
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
    """将情报数据格式化为prompt中的情报段落
    
    Args:
        intelligence: dict，包含 basic_data, expert_opinions, market_sentiment, summary
    
    Returns:
        str: 格式化后的情报文本
    """
    if not intelligence:
        return ""
    
    lines = ["\n## 已搜集情报（来自联网搜索）"]
    
    basic = intelligence.get("basic_data", {})
    if basic:
        lines.append("\n### 基本面")
        if basic.get("home_form"):
            lines.append(f"- 主队近况: {basic['home_form']}")
        if basic.get("away_form"):
            lines.append(f"- 客队近况: {basic['away_form']}")
        if basic.get("home_injuries"):
            lines.append(f"- 主队伤停: {basic['home_injuries']}")
        if basic.get("away_injuries"):
            lines.append(f"- 客队伤停: {basic['away_injuries']}")
        if basic.get("h2h"):
            lines.append(f"- 历史交锋: {basic['h2h']}")
    
    expert = intelligence.get("expert_opinions", {})
    if expert:
        lines.append("\n### 专家观点")
        if expert.get("consensus"):
            lines.append(f"- 主流观点: {expert['consensus']}")
        if expert.get("key_points"):
            for point in expert["key_points"][:3]:
                lines.append(f"- {point}")
    
    market = intelligence.get("market_sentiment", {})
    if market:
        lines.append("\n### 市场情绪")
        if market.get("odds_trend"):
            lines.append(f"- 赔率走势: {market['odds_trend']}")
        if market.get("money_flow"):
            lines.append(f"- 资金流向: {market['money_flow']}")
    
    if intelligence.get("summary"):
        lines.append(f"\n### 情报总结\n{intelligence['summary']}")
    
    return "\n".join(lines)


def build_matches_text(matches):
    """构建比赛列表文本"""
    lines = []
    for m in matches:
        lines.append(f"{m['num']}. [{m['league']}] {m['home']} vs {m['away']} ({m['time']})")
    return "\n".join(lines)


def build_matches_info(matches):
    """构建matches_info JSON"""
    return [{
        "id": m["id"],
        "num": m["num"],
        "home": m["home"],
        "away": m["away"],
        "league": m["league"],
        "time": m["time"],
        "issue": m["issue"],
    } for m in matches]


async def call_ai_api(session, ai_name, prompt, sem):
    """调用单个AI API"""
    config = AI_CONFIGS[ai_name]
    
    async with sem:
        try:
            # 扣子专用逻辑
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
                    
                    # JSON响应
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
                    
                    # 回退：返回原始文本
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
    """标准化半全场bqc字段，将混合格式转为两位数字代码
    
    混元可能返回 "1平"、"0负"、"3胜" 等混合格式，需要转为 "11"、"00"、"33"
    
    规则：第一位是半场结果(3=胜,1=平,0=负)，第二位是全场结果(3=胜,1=平,0=负)
    """
    if not value:
        return value
    
    value = str(value).strip()
    
    # 如果已经是两位数字，直接返回
    if re.match(r'^[013][013]$', value):
        return value
    
    # 结果映射
    result_map = {'胜': '3', '平': '1', '负': '0'}
    
    # 处理混合格式：如 "1平"、"3胜"、"0负"
    match = re.match(r'^([013])([胜平负])$', value)
    if match:
        first = match.group(1)
        second_char = match.group(2)
        second = result_map.get(second_char, '')
        if second:
            return first + second
    
    # 处理中文格式：如 "平胜"、"平平"、"负负"
    match = re.match(r'^([胜平负])([胜平负])$', value)
    if match:
        first_char = match.group(1)
        second_char = match.group(2)
        first = result_map.get(first_char, '')
        second = result_map.get(second_char, '')
        if first and second:
            return first + second
    
    # 无法识别，返回原值
    return value


def parse_prediction(content, game_type, match_count):
    """解析AI返回的预测"""
    if not content:
        return None
    
    # 清理markdown代码块
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    content = content.strip()
    
    # 尝试提取JSON数组
    json_match = re.search(r'\[[\s\S]*?\](?=\s*[^\[\{]|\s*$)', content)
    if json_match:
        try:
            predictions = json.loads(json_match.group())
            if isinstance(predictions, list) and len(predictions) > 0:
                return predictions
        except json.JSONDecodeError:
            pass
    
    # 尝试提取JSON对象
    json_match = re.search(r'\{[\s\S]*?\}(?=\s*[^\[\{]|\s*$)', content)
    if json_match:
        try:
            obj = json.loads(json_match.group())
            if isinstance(obj, dict):
                return [obj]
        except json.JSONDecodeError:
            pass
    
    # 尝试直接解析整个内容
    try:
        data = json.loads(content)
        if isinstance(data, list) and len(data) > 0:
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass
    
    # 调试输出
    print(f"  [DEBUG] 解析失败，原始内容前200字符: {content[:200]}")
    return None


async def predict_for_game_type(game_type, matches, force=False):
    """为单个维度生成预测"""
    print(f"\n=== {game_type} ===")
    
    conn = get_db()
    issue = matches[0]["issue"] if matches else None
    
    if not issue:
        print("无比赛数据")
        conn.close()
        return 0
    
    # 检查是否已有预测
    cur = conn.cursor()
    cur.execute("""
        SELECT ai_name FROM traditional_predictions 
        WHERE issue = %s AND game_type = %s
    """, (issue, game_type))
    existing = set(row[0] for row in cur.fetchall())
    conn.commit()
    
    if existing and not force:
        print(f"期号{issue}的{game_type}已有预测: {existing}")
        conn.close()
        return 0
    
    # force模式：先删除旧记录
    if force and existing:
        cur.execute("""
            DELETE FROM traditional_predictions 
            WHERE issue = %s AND game_type = %s
        """, (issue, game_type))
        conn.commit()
        print(f"已删除旧预测记录")
        existing = set()
    
    # 构建prompt
    matches_text = build_matches_text(matches)
    matches_info = build_matches_info(matches)
    prompt_template = PROMPTS.get(game_type, PROMPTS["胜负彩"])
    prompt = prompt_template.format(matches=matches_text)
    
    print(f"期号: {issue}, 比赛数: {len(matches)}")
    
    # 调用所有AI
    sem = asyncio.Semaphore(3)
    timeout = aiohttp.ClientTimeout(total=180)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for ai_name in AI_CONFIGS.keys():
            if ai_name not in existing or force:
                tasks.append((ai_name, call_ai_api(session, ai_name, prompt, sem)))
        
        results = {}
        for ai_name, task in tasks:
            try:
                result = await task
                results[ai_name] = result
            except Exception as e:
                print(f"  [FAIL] {ai_name}: {e}")
    
    # 保存结果
    total_saved = 0
    for ai_name, content in results.items():
        if not content:
            continue
        
        predictions = parse_prediction(content, game_type, len(matches))
        if not predictions:
            print(f"  [WARN] {ai_name} 解析失败")
            continue
        
        # 半全场维度：标准化bqc字段（修复混元返回的混合格式如"1平"、"0负"）
        if game_type == "半全场" and predictions:
            for pred in predictions:
                if 'bqc' in pred:
                    pred['bqc'] = normalize_bqc(pred['bqc'])
        
        # 任9维度：提取推荐的场次号列表
        ren9_list = None
        if game_type == "任9" and predictions:
            ren9_list = [str(p.get("match", "")).zfill(2) for p in predictions if p.get("match")]
        
        try:
            cur.execute("""
                INSERT INTO traditional_predictions (game_type, ai_name, predictions, matches_info, issue, ren9, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (
                game_type,
                ai_name,
                json.dumps(predictions, ensure_ascii=False),
                json.dumps(matches_info, ensure_ascii=False),
                issue,
                json.dumps(ren9_list, ensure_ascii=False) if ren9_list else None,
            ))
            conn.commit()
            total_saved += 1
            r9_info = f" (任9推荐: {ren9_list})" if ren9_list else ""
            print(f"  [OK] {ai_name}: {len(predictions)}条预测{r9_info}")
        except Exception as e:
            print(f"  [FAIL] {ai_name}: {e}")
            conn.rollback()
    
    conn.close()
    return total_saved


# ============================================================
# 两阶段模式辅助函数
# ============================================================
async def call_kouzi_intelligence(session, match, sem):
    """扣子专用：搜集单场比赛情报
    
    Returns:
        (raw_text, error): raw_text 为扣子返回的原始文本，error 为错误信息
    """
    config = AI_CONFIGS["扣子"]
    
    # 构建情报搜集prompt
    prompt = CT_INTELLIGENCE_PROMPT.format(
        issue=match.get("issue", ""),
        num=match.get("num", ""),
        league=match.get("league", ""),
        home_team=match.get("home", ""),
        away_team=match.get("away", ""),
        match_time=match.get("time", ""),
    )
    
    match_id = f"CT{match['issue']}_{match['num']}"
    
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
                    return "".join(answer_chunks), None
                
                # JSON响应回退
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
    """解析扣子返回的情报+预测JSON
    
    Returns:
        (intelligence_data, prediction_data): 情报和预测数据，解析失败返回 (None, None)
    """
    if not raw_text:
        return None, None
    
    # 清理markdown代码块
    content = re.sub(r'```json\s*', '', raw_text)
    content = re.sub(r'```\s*', '', content)
    content = content.strip()
    
    # 尝试提取JSON对象
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
    
    # 尝试直接解析
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data.get("intelligence"), data.get("prediction")
    except json.JSONDecodeError:
        pass
    
    print(f"  [DEBUG] 情报解析失败，原始内容前200字符: {content[:200]}")
    return None, None


async def predict_for_game_type_with_intel(game_type, matches, ai_names, intelligence_cache, force=False):
    """为单个维度生成预测（带情报增强）
    
    Args:
        game_type: 维度名称（胜负彩/半全场/进球彩/任9）
        matches: 比赛列表
        ai_names: AI名称列表（排除扣子）
        intelligence_cache: 情报缓存 {match_id: intelligence_data}
        force: 是否强制重新预测
    
    Returns:
        int: 成功保存的预测数量
    """
    print(f"\n--- {game_type} ---")
    
    conn = get_db()
    issue = matches[0]["issue"] if matches else None
    
    if not issue:
        print("无比赛数据")
        conn.close()
        return 0
    
    # 检查是否已有预测
    cur = conn.cursor()
    cur.execute("""
        SELECT ai_name FROM traditional_predictions 
        WHERE issue = %s AND game_type = %s
    """, (issue, game_type))
    existing = set(row[0] for row in cur.fetchall())
    conn.commit()
    
    if existing and not force:
        print(f"期号{issue}的{game_type}已有预测: {existing}")
        conn.close()
        return 0
    
    # force模式：先删除旧记录
    if force and existing:
        cur.execute("""
            DELETE FROM traditional_predictions 
            WHERE issue = %s AND game_type = %s
        """, (issue, game_type))
        conn.commit()
        print(f"已删除旧预测记录")
        existing = set()
    
    # 构建基础prompt（包含所有比赛）
    matches_text = build_matches_text(matches)
    matches_info = build_matches_info(matches)
    prompt_template = PROMPTS.get(game_type, PROMPTS["胜负彩"])
    base_prompt = prompt_template.format(matches=matches_text)
    
    # 如果有情报，插入到prompt中
    if intelligence_cache:
        intel_lines = ["\n\n## 已搜集情报（来自联网搜索）"]
        for match in matches:
            match_id = f"CT{match['issue']}_{match['num']}"
            intel = intelligence_cache.get(match_id)
            if intel:
                intel_section = format_intelligence_section(intel)
                if intel_section:
                    intel_lines.append(f"\n### 第{match['num']}场 {match['home']} vs {match['away']}")
                    intel_lines.append(intel_section)
        
        if len(intel_lines) > 1:
            # 在输出格式要求之前插入情报
            insert_marker = "## 输出格式"
            if insert_marker in base_prompt:
                idx = base_prompt.index(insert_marker)
                base_prompt = base_prompt[:idx] + "\n".join(intel_lines) + "\n\n" + base_prompt[idx:]
            else:
                base_prompt += "\n".join(intel_lines)
    
    print(f"期号: {issue}, 比赛数: {len(matches)}, 情报数: {len(intelligence_cache)}")
    
    # 调用其他AI（每个AI完成后立即入库）
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
                
                # 任9维度：提取推荐的场次号列表
                ren9_list = None
                if game_type == "任9" and predictions:
                    ren9_list = [str(p.get("match", "")).zfill(2) for p in predictions if p.get("match")]
                
                # 立即入库
                cur.execute("""
                    INSERT INTO traditional_predictions (game_type, ai_name, predictions, matches_info, issue, ren9, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (
                    game_type,
                    ai_name,
                    json.dumps(predictions, ensure_ascii=False),
                    json.dumps(matches_info, ensure_ascii=False),
                    issue,
                    json.dumps(ren9_list, ensure_ascii=False) if ren9_list else None,
                ))
                conn.commit()
                total_saved += 1
                r9_info = f" (任9推荐: {ren9_list})" if ren9_list else ""
                print(f"  [OK] {ai_name}: {len(predictions)}条预测{r9_info}")
                
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
    
    conn = get_db()
    issue, matches = get_ct_matches(conn, args.issue)
    conn.close()
    
    if not matches:
        print("没有找到CT比赛")
        return
    
    print(f"期号: {issue}, 比赛数: {len(matches)}")
    for m in matches[:3]:
        print(f"  {m['num']}. {m['home']} vs {m['away']}")
    if len(matches) > 3:
        print(f"  ... 共{len(matches)}场")
    
    # 确定要处理的维度
    game_types = [args.game] if args.game else ["胜负彩", "半全场", "进球彩", "任9"]
    
    # ============================================================
    # 两阶段模式：Phase 1 情报搜集 + Phase 2 预测
    # ============================================================
    
    # Phase 1: 扣子情报搜集
    print(f"\n{'='*50}")
    print(f"[Phase 1] 扣子情报搜集 ({len(matches)} 场比赛)")
    print(f"{'='*50}")
    
    kouzi_intelligence = {}  # match_id -> intelligence_data
    sem = asyncio.Semaphore(3)
    timeout = aiohttp.ClientTimeout(total=120)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for match in matches:
            tasks.append(call_kouzi_intelligence(session, match, sem))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            match = matches[i]
            match_id = f"CT{match['issue']}_{match['num']}"
            
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
                    # 写入情报库
                    if save_match_intelligence(match, intelligence_data):
                        kouzi_intelligence[match_id] = intelligence_data
                        print(f"  [OK] {match_id}: 情报已保存")
    
    print(f"\n[Phase 1 完成] 成功搜集 {len(kouzi_intelligence)}/{len(matches)} 场比赛情报")
    
    # Phase 2: 其他6个AI基于情报预测
    print(f"\n{'='*50}")
    print(f"[Phase 2] 其他6个AI基于情报预测")
    print(f"{'='*50}")
    
    # 其他AI列表（排除扣子）
    other_ai_names = [name for name in AI_CONFIGS.keys() if name != "扣子"]
    
    total = 0
    for game_type in game_types:
        count = await predict_for_game_type_with_intel(game_type, matches, other_ai_names, kouzi_intelligence, args.force)
        total += count
    
    print(f"\n{'='*50}")
    print(f"[完成] 共生成 {total} 条预测")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
