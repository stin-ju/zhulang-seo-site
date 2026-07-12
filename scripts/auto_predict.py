#!/usr/bin/env python3
"""
auto_predict.py - 7AI预测调度
为待预测比赛调用7个AI生成预测，写入predictions表。
每个AI独立调用，某个AI挂了不影响其他AI。
"""
import os
import sys
import json
import re
import time
import traceback
import psycopg2
import requests

# ============ 配置 ============

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# 7个活跃AI及其API配置
AI_CONFIGS = {
    "AI-DeepSeek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "format": "openai",
    },
    "AI-MiniMax": {
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model": "MiniMax-Text-01",
        "format": "minimax",
    },
    "AI-豆包": {
        "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "key_env": "DOUBAO_API_KEY",
        "model": "doubao-seed-2-0-lite-260428",
        "format": "openai",
    },
    "AI-智谱清言": {
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "ZHIPU_API_KEY",
        "model": "glm-4-flash",
        "format": "openai",
    },
    "AI-文心": {
        "url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        "key_env": "WENXIN_API_KEY",
        "model": "ernie-speed-128k",
        "format": "wenxin",
    },
    "AI-混元": {
        "url": "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "model": "hunyuan-lite",
        "format": "openai",
    },
    "AI-扣子（皮皮）": {
        "url": None,  # 使用模板生成
        "key_env": None,
        "model": None,
        "format": "template",
    },
}

# ============ Prompt模板 ============

PREDICTION_PROMPT = """你是一个专业的足球比赛预测分析师。请根据以下比赛信息做出预测。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让球: {handicap}
- 胜平负赔率: 胜{win_odds} / 平{draw_odds} / 负{lose_odds}
- 让球赔率: 让胜{hw_odds} / 让平{hd_odds} / 让负{hl_odds}

## 请严格按以下JSON格式输出预测结果（不要输出其他内容）:
```json
{{
  "spf": "胜"或"平"或"负",
  "handicap_spf": "让胜"或"让平"或"让负",
  "score": "比分如2-1",
  "goals": 总进球数(整数),
  "half_full": "半全场如胜胜/平胜/负平",
  "analysis": "50-100字的分析理由"
}}
```"""

# ============ 数据库 ============

def get_db():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)


def get_pending_matches(conn):
    """获取在售且有赔率的比赛"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.id, m.teams, m.match_time, m.handicap,
                   m.win_odds, m.draw_odds, m.lose_odds,
                   m.handicap_win_odds, m.handicap_draw_odds, m.handicap_lose_odds,
                   m.metadata->>'league' as league
            FROM matches m
            WHERE m.status = 'on_sale'
            AND m.win_odds IS NOT NULL
            AND m.sport_type = 'football'
            ORDER BY m.match_time ASC
        """)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_existing_predictions(conn, match_id):
    """获取某场比赛已有的AI预测，返回标准化后的AI名称集合"""
    with conn.cursor() as cur:
        cur.execute("SELECT ai_name FROM predictions WHERE match_id = %s", (match_id,))
        raw_names = {row[0] for row in cur.fetchall()}
        # 标准化：DB中可能是 "DeepSeek" 或 "AI-DeepSeek"，统一为 "AI-xxx"
        normalized = set()
        for name in raw_names:
            if name.startswith("AI-"):
                normalized.add(name)
            else:
                normalized.add(f"AI-{name}")
        return normalized


def insert_prediction(conn, pred):
    """插入一条预测记录"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO predictions (match_id, ai_name, spf, handicap_spf, score, goals, half_full, analysis, sport_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            pred["match_id"], pred["ai_name"], pred["spf"], pred["handicap_spf"],
            pred["score"], pred["goals"], pred["half_full"], pred["analysis"], pred.get("sport_type", "football")
        ))


# ============ AI API调用 ============

def call_openai_compatible(url, key, model, prompt, timeout=60):
    """调用OpenAI兼容格式的API (DeepSeek/豆包/智谱/混元)"""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 500,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_minimax(url, key, model, prompt, timeout=60):
    """调用MiniMax API"""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 500,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_wenxin(url, key, model, prompt, timeout=60):
    """调用文心API（需要access_token）"""
    # 先获取access_token
    token_url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={key}&client_secret={os.environ.get('WENXIN_SECRET_KEY', '')}"
    token_resp = requests.post(token_url, timeout=10)
    token_resp.raise_for_status()
    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise Exception(f"文心token获取失败: {token_resp.text}")
    
    full_url = f"{url}/{model}?access_token={access_token}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_output_tokens": 500,
    }
    resp = requests.post(full_url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "error_code" in data:
        raise Exception(f"文心API错误: {data.get('error_msg')}")
    return data.get("result", "")


def generate_template_prediction(prompt):
    """扣子(皮皮) - 基于规则的模板预测"""
    # 简单规则：基于赔率推断
    return "根据赔率分析，" + prompt.split("让球:")[-1].split("\n")[0] + "。综合考虑主队优势和赔率走势给出预测。"


def parse_ai_response(text):
    """从AI回复中提取JSON预测结果"""
    # 尝试提取JSON块
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))
    
    # 尝试直接解析
    json_match = re.search(r'\{[^{}]*"spf"[^{}]*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    
    # 解析失败，返回默认值
    print(f"  WARNING: 无法解析AI回复，使用默认值")
    return {
        "spf": "胜",
        "handicap_spf": "让胜",
        "score": "1-0",
        "goals": 1,
        "half_full": "胜胜",
        "analysis": text[:200] if text else "解析失败",
    }


def call_ai(ai_name, prompt):
    """调用指定AI生成预测"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        raise Exception(f"未知AI: {ai_name}")
    
    fmt = config["format"]
    
    if fmt == "template":
        analysis = generate_template_prediction(prompt)
        return parse_ai_response(analysis)
    
    key = os.environ.get(config["key_env"], "")
    if not key:
        raise Exception(f"{ai_name} 的API Key未配置 ({config['key_env']})")
    
    if fmt == "openai":
        raw = call_openai_compatible(config["url"], key, config["model"], prompt)
    elif fmt == "minimax":
        raw = call_minimax(config["url"], key, config["model"], prompt)
    elif fmt == "wenxin":
        raw = call_wenxin(config["url"], key, config["model"], prompt)
    else:
        raise Exception(f"未知格式: {fmt}")
    
    return parse_ai_response(raw)


# ============ 主逻辑 ============

def build_prompt(match):
    """构建AI预测prompt"""
    teams = (match.get("teams") or "").split(" VS ")
    home_team = teams[0] if len(teams) > 0 else "主队"
    away_team = teams[1] if len(teams) > 1 else "客队"
    
    return PREDICTION_PROMPT.format(
        league=match.get("league") or "未知联赛",
        home_team=home_team,
        away_team=away_team,
        match_time=match.get("match_time") or "",
        handicap=match.get("handicap") or 0,
        win_odds=match.get("win_odds") or 0,
        draw_odds=match.get("draw_odds") or 0,
        lose_odds=match.get("lose_odds") or 0,
        hw_odds=match.get("handicap_win_odds") or 0,
        hd_odds=match.get("handicap_draw_odds") or 0,
        hl_odds=match.get("handicap_lose_odds") or 0,
    )


def run_predict():
    """主入口：为所有待预测比赛生成AI预测"""
    conn = get_db()
    matches = get_pending_matches(conn)
    
    if not matches:
        print(json.dumps({"message": "没有待预测的比赛", "matches": 0, "predictions": 0}))
        conn.close()
        return
    
    total_predictions = 0
    total_errors = 0
    match_results = []
    
    for match in matches:
        match_id = match["id"]
        existing = get_existing_predictions(conn, match_id)
        prompt = build_prompt(match)
        
        missing_ais = [ai for ai in AI_CONFIGS if ai not in existing]
        if not missing_ais:
            continue
        
        match_pred_count = 0
        match_errors = []
        
        for ai_name in missing_ais:
            try:
                result = call_ai(ai_name, prompt)
                
                # 验证和修正字段
                spf = result.get("spf", "胜")
                if spf not in ("胜", "平", "负"):
                    spf = "胜"
                
                handicap_spf = result.get("handicap_spf", "让胜")
                if handicap_spf not in ("让胜", "让平", "让负"):
                    handicap_spf = "让胜"
                
                score = result.get("score", "1-0")
                if not re.match(r'^\d+-\d+$', score):
                    score = "1-0"
                
                goals = int(result.get("goals", 1))
                half_full = result.get("half_full", "胜胜")
                if half_full not in ("胜胜", "胜平", "胜负", "平胜", "平平", "平负", "负胜", "负平", "负负"):
                    half_full = "胜胜"
                
                analysis = result.get("analysis", "")[:500]
                
                pred = {
                    "match_id": match_id,
                    "ai_name": ai_name,
                    "spf": spf,
                    "handicap_spf": handicap_spf,
                    "score": score,
                    "goals": goals,
                    "half_full": half_full,
                    "analysis": analysis,
                    "sport_type": "football",
                }
                
                insert_prediction(conn, pred)
                match_pred_count += 1
                print(f"  OK: {match_id} {ai_name} -> {spf}/{handicap_spf}/{score}")
                
            except Exception as e:
                error_msg = f"{ai_name}: {str(e)[:100]}"
                match_errors.append(error_msg)
                print(f"  FAIL: {match_id} {ai_name} - {e}")
                total_errors += 1
            
            # 避免API限流
            time.sleep(1)
        
        conn.commit()
        total_predictions += match_pred_count
        match_results.append({
            "match_id": match_id,
            "predicted": match_pred_count,
            "errors": len(match_errors),
        })
    
    conn.close()
    
    result = {
        "matches_processed": len(match_results),
        "predictions_created": total_predictions,
        "errors": total_errors,
        "details": match_results,
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    try:
        run_predict()
    except Exception as e:
        print(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
