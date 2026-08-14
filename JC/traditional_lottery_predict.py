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
import psycopg2
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

## 比赛列表
{matches}

## 输出要求
为每场比赛输出：
- match: 场次编号(01-14)
- zjq: 总进球数预测(0/1/2/3/4/5/6/7+)
- analysis: 50字内分析

## 输出格式
输出JSON数组：
[{{"match": "01", "zjq": "2", "analysis": "..."}}, ...]
必须包含所有14场比赛。""",

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
              AND metadata->>'status' = 'on_sale'
            ORDER BY metadata->>'issue' DESC, (metadata->>'issue_num')::int
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
        
        try:
            cur.execute("""
                INSERT INTO traditional_predictions (game_type, ai_name, predictions, matches_info, issue, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (
                game_type,
                ai_name,
                json.dumps(predictions, ensure_ascii=False),
                json.dumps(matches_info, ensure_ascii=False),
                issue,
            ))
            conn.commit()
            total_saved += 1
            print(f"  [OK] {ai_name}: {len(predictions)}条预测")
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
    
    total = 0
    for game_type in game_types:
        count = await predict_for_game_type(game_type, matches, args.force)
        total += count
    
    print(f"\n=== 完成 ===")
    print(f"共生成 {total} 条预测")


if __name__ == "__main__":
    asyncio.run(main())
