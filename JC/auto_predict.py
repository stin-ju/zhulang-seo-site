#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""
auto_predict.py - 两阶段AI预测调度

Phase 1 - 情报搜集：
  对每场待预测比赛，调用扣子预测智能体搜集情报数据
  （球队近况、交锋记录、赔率分析等），存入情报库

Phase 2 - 逐AI逐场预测：
  一场比赛一场比赛跑，每场比赛内逐个AI调用
  每完成一个AI的预测就立即入库，不等待全部完成
  AI调用顺序：DeepSeek→MiniMax→扣子→文心→智谱清言→混元→豆包

支持 --sport football|basketball 参数。
支持 --phase 1|2|all 参数（默认all，跑全部阶段）。
"""
import os
import sys
import json
import re
import time
import traceback
import requests
import math
from datetime import datetime
from supabase_db import (
    get_matches_by_sport, get_existing_ai_names, upsert_prediction,
    get_predictions_count, execute_query
)

# ============ 配置 ============

# AI调用间隔（秒），避免频率限制
AI_CALL_INTERVAL = 2

# 单个AI调用超时（秒）
AI_CALL_TIMEOUT = 90

# 情报搜集超时（秒）
INTEL_TIMEOUT = 180

# 7个活跃AI及其API配置（按调用顺序排列）
# 每个AI配置多个免费/低成本模型轮换，主模型失败自动切换备用
AI_CONFIGS = {
    "AI-DeepSeek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",            # DeepSeek-V3，最便宜稳定
        "format": "openai",
        "fallback_models": [
            "deepseek-v4-flash",              # V4 Flash 轻量版
            "deepseek-v3",                    # V3 备用
            "deepseek-reasoner",              # R1 推理版（较慢）
        ],
    },
    "AI-MiniMax": {
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model": "abab6.5s-chat",            # 性价比高，输入输出同价
        "format": "minimax",
        "fallback_models": [
            "abab6.5-chat",                   # 标准版
            "MiniMax-Text-01",                # Text-01
            "abab5.5s-chat",                  # 旧版兜底
        ],
    },
    "AI-扣子": {
        "url": "https://7hsjv6c4cn.coze.site/stream_run",
        "key_env": "COZE_PROJECT_API_TOKEN",
        "key_default": "REMOVED",
        "model": None,
        "format": "coze_code",
        "project_id": 7667164681706078217,
    },
    "AI-文心": {
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "key_default": "REMOVED",
        "model": "ernie-4.5-turbo-32k",       # ✅ 已验证可用，v2最新可用模型
        "format": "openai",
        "fallback_models": [
            "ernie-4.5-turbo-128k",           # 128K上下文版
            "ernie-5.0-thinking-preview",     # 思考模式，248K上下文
            "ernie-x1.1",                     # 121K上下文
            "ernie-4.5-turbo-20260402",       # 指定版本，138K上下文
        ],
    },
    "AI-智谱清言": {
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "ZHIPU_API_KEY",
        "model": "glm-4-flash",              # ✅ 永久免费，128K上下文
        "format": "openai",
        "fallback_models": [
            "glm-4.7-flash",                 # ✅ 永久免费，200K上下文，编程SOTA
            "glm-4-air",                     # 每月100万token免费
            "glm-4-flashx",                  # Flash加速版
        ],
    },
    "AI-混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "key_default": "REMOVED",
        "model": "hy3",                      # ✅ Hy3正式版(有额度)
        "format": "openai",
        "fallback_models": [
            "hy3-preview",                   # Hy3 预览版
        ],
    },
    "AI-豆包": {
        "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "key_env": "DOUBAO_API_KEY",
        "model": "doubao-lite-32k",          # ✅ 永久免费
        "format": "openai",
        "fallback_models": [
            "doubao-1.5-lite-32k",           # 1.5 Lite 版
            "doubao-seed-2-0-mini-260428",   # Seed 2.0 Mini
            "doubao-seed-2-0-lite-260515",   # Seed 2.0 Lite
            "doubao-seed-2-1-turbo-260628",  # Seed 2.1 Turbo
        ],
    },
}

# AI调用顺序（Phase 2使用）
AI_CALL_ORDER = [
    "AI-DeepSeek",
    "AI-MiniMax", 
    "AI-扣子",
    "AI-文心",
    "AI-智谱清言",
    "AI-混元",
    "AI-豆包",
]

# ============ Prompt模板 ============

# Phase 1: 情报搜集Prompt
INTEL_PROMPT_FOOTBALL = """你是足球比赛情报分析师。请搜集以下比赛的详细情报数据。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让球: {handicap}
- 胜平负赔率: 胜{win_odds} / 平{draw_odds} / 负{lose_odds}

## 需要搜集的情报

1. **球队近况**（近10场）
   - 主队近10场战绩（胜/平/负）
   - 客队近10场战绩
   - 双方近期进失球数据

2. **交锋记录**（近5次）
   - 历史交锋战绩
   - 主客场交锋特点

3. **赔率分析**
   - 搜索相同/相似赔率的历史场次（至少30场）
   - 相同让球盘口的历史赢盘率
   - 相同大小球盘口的历史概率

4. **其他情报**
   - 伤停信息（如有）
   - 主客场战绩差异
   - 赛季目标/动力分析

## 输出格式（JSON）
```json
{{
  "home_form": "主队近况描述",
  "away_form": "客队近况描述",
  "h2h": "交锋记录描述",
  "odds_analysis": "赔率分析结论",
  "key_factors": ["关键因素1", "关键因素2", "关键因素3"],
  "intel_summary": "100字以内的情报总结"
}}
```"""

INTEL_PROMPT_BASKETBALL = """你是篮球比赛情报分析师。请搜集以下比赛的详细情报数据。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让分: {spread_desc}（盘口{spread_line}）
- 总分线: {total_line}

## 需要搜集的情报

1. **球队近况**（近10场）
   - 主队近10场战绩和得失分
   - 客队近10场战绩和得失分

2. **交锋记录**（近5次）
   - 历史交锋战绩和分差

3. **赔率分析**
   - 相同让分盘口的历史赢盘率
   - 相同大小分盘口的历史概率

4. **其他情报**
   - 伤停信息（如有）
   - 背靠背/赛程密度

## 输出格式（JSON）
```json
{{
  "home_form": "主队近况描述",
  "away_form": "客队近况描述",
  "h2h": "交锋记录描述",
  "odds_analysis": "赔率分析结论",
  "key_factors": ["关键因素1", "关键因素2"],
  "intel_summary": "100字以内的情报总结"
}}
```"""

# Phase 2: 预测Prompt（带情报）
PREDICTION_PROMPT = """你是一个专业的足球比赛预测分析师。请根据比赛信息和情报数据做出预测。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让球: {handicap}
- 胜平负赔率: 胜{win_odds} / 平{draw_odds} / 负{lose_odds}
- 让球赔率: 让胜{hw_odds} / 让平{hd_odds} / 让负{hl_odds}

## 情报数据
{intel_data}

## 请严格按以下JSON格式输出预测结果:
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

BASKETBALL_PROMPT = """你是专业的篮球比赛预测分析师。根据比赛信息和情报数据做出预测，必须逻辑自洽。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让分: {spread_desc}（盘口{spread_line}）
- 总分线: {total_line}

## 赔率数据
- 胜负: 主胜{win_odds} / 客胜{lose_odds}
- 让分: 让胜{spread_win_odds} / 让负{spread_lose_odds}
- 大小分: 大{total_over_odds} / 小{total_under_odds}
- 胜分差: 1-5分:{sdr_1_5} | 6-10分:{sdr_6_10} | 11-15分:{sdr_11_15} | 16-20分:{sdr_16_20} | 21-25分:{sdr_21_25} | 26+分:{sdr_26}

## 情报数据
{intel_data}

## 请严格按以下JSON格式输出:
```json
{{
  "win_loss": "胜"或"负",
  "handicap_win_loss": "让胜"或"让负",
  "total_points": "大"或"小",
  "score_diff_range": "如主6-10胜或客1-5负",
  "half_win_loss": "胜"或"负",
  "analysis": "50-100字分析理由"
}}
```

## 逻辑自洽规则:
1. 让分↔胜分差：选"让胜"→胜分差应为"主x胜"且分差>盘口
2. 让分↔胜负：选"让胜"→胜负应选"胜"
3. 胜分差格式: 主1-5胜/主6-10胜/主11-15胜/主16-20胜/主21+胜/客1-5负/客6-10负/客11-15负/客16-20负/客21+负"""

# ============ 数据库操作 ============

def get_pending_matches(sport="football"):
    """获取待预测比赛"""
    matches = get_matches_by_sport(sport, statuses=["on_sale", "pending"])
    return [m for m in matches if not m.get("id", "").startswith("CT")]


def get_existing_predictions(match_id):
    """获取某场比赛已有的AI预测"""
    return get_existing_ai_names(match_id)


def save_intel(match_id, intel_data):
    """保存情报到数据库（matches表的metadata字段）"""
    try:
        intel_json = json.dumps(intel_data, ensure_ascii=False)
        # 使用参数化查询避免SQL注入
        sql = """
            UPDATE matches 
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{intel}',
                %s::jsonb
            )
            WHERE id = %s
        """
        execute_query(sql, (intel_json, match_id), fetch=False)
        return True
    except Exception as e:
        print(f"  [ERROR] 保存情报失败: {e}")
        return False


def get_intel(match_id):
    """从数据库获取比赛情报"""
    try:
        sql = "SELECT metadata->>'intel' as intel FROM matches WHERE id = %s"
        result = execute_query(sql, (match_id,), fetch=True)
        if result and result[0].get('intel'):
            return json.loads(result[0]['intel'])
    except Exception as e:
        print(f"  [WARN] 获取情报失败: {e}")
    return None


def insert_football_prediction(pred):
    """插入足球预测（立即入库）"""
    prediction_json = {
        "spf": pred.get("spf"),
        "handicap_spf": pred.get("handicap_spf"),
        "score": pred.get("score"),
        "goals": pred.get("goals"),
        "half_full": pred.get("half_full")
    }
    upsert_prediction({
        "match_id": pred["match_id"],
        "ai_name": pred["ai_name"],
        "prediction": prediction_json,
        "analysis": pred.get("analysis", ""),
        "sport_type": "football"
    })
    
    # 同时更新单独的足球列（upsert_prediction只更新prediction JSONB）
    try:
        execute_query("""
            UPDATE predictions 
            SET spf = %s,
                handicap_spf = %s,
                score = %s,
                goals = %s,
                half_full = %s,
                raw_response = %s
            WHERE match_id = %s AND ai_name = %s
        """, (
            pred.get("spf"),
            pred.get("handicap_spf"),
            pred.get("score"),
            pred.get("goals"),
            pred.get("half_full"),
            json.dumps(prediction_json, ensure_ascii=False),
            pred["match_id"],
            pred["ai_name"]
        ), fetch=False)
    except Exception as e:
        print(f"  [WARN] 更新足球顶层列失败: {e}")


def normalize_basketball_fields(pred):
    """规范化篮球预测字段名"""
    normalized = dict(pred)
    
    if "handicap_result" in normalized and "handicap_win_loss" not in normalized:
        normalized["handicap_win_loss"] = normalized.pop("handicap_result")
    
    if "score_diff" in normalized and "score_diff_range" not in normalized:
        score_diff = normalized.pop("score_diff")
        if score_diff and not any(score_diff.startswith(p) for p in ["主", "客"]):
            win_loss = normalized.get("win_loss", "")
            if "主胜" in win_loss or win_loss == "胜":
                normalized["score_diff_range"] = f"主{score_diff}胜"
            elif "客胜" in win_loss or win_loss == "负":
                normalized["score_diff_range"] = f"客{score_diff}负"
            else:
                normalized["score_diff_range"] = score_diff
        else:
            normalized["score_diff_range"] = score_diff
    
    return normalized


def insert_basketball_prediction(pred):
    """插入篮球预测（立即入库，同时更新单独列）"""
    pred = normalize_basketball_fields(pred)
    
    prediction_json = {
        "win_loss": pred.get("win_loss"),
        "handicap_win_loss": pred.get("handicap_win_loss"),
        "total_points": pred.get("total_points"),
        "score_diff_range": pred.get("score_diff_range"),
        "half_win_loss": pred.get("half_win_loss")
    }
    upsert_prediction({
        "match_id": pred["match_id"],
        "ai_name": pred["ai_name"],
        "sport_type": "basketball",
        "prediction": prediction_json,
        "analysis": pred.get("analysis", "")
    })
    
    # 同时更新单独的篮球列（upsert_prediction只更新prediction JSONB）
    try:
        execute_query("""
            UPDATE predictions 
            SET win_loss = %s,
                handicap_win_loss = %s,
                total_points = %s,
                score_diff_range = %s,
                half_win_loss = %s
            WHERE match_id = %s AND ai_name = %s
        """, (
            pred.get("win_loss"),
            pred.get("handicap_win_loss"),
            pred.get("total_points"),
            pred.get("score_diff_range"),
            pred.get("half_win_loss"),
            pred["match_id"],
            pred["ai_name"]
        ))
    except Exception as e:
        print(f"[WARN] 更新篮球单独列失败: {e}")


# ============ AI API调用 ============

def call_openai_compatible(url, key, model, prompt, timeout=AI_CALL_TIMEOUT):
    """调用OpenAI兼容API"""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 800,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_minimax(url, key, model, prompt, timeout=AI_CALL_TIMEOUT):
    """调用MiniMax API"""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 800,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def parse_ai_response(text, sport="football"):
    """从AI回复中提取JSON预测结果"""
    if not text:
        return None
    
    # 方法1: 提取```json代码块
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 方法2: 尝试提取所有JSON对象
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_matches = re.findall(json_pattern, text, re.DOTALL)
    
    for match in json_matches:
        try:
            data = json.loads(match)
            if sport == "basketball" and "win_loss" in data:
                return data
            elif sport == "football" and "spf" in data:
                return data
            # 情报格式
            if "intel_summary" in data or "home_form" in data:
                return data
        except json.JSONDecodeError:
            continue
    
    # 方法3: 宽松匹配
    if sport == "basketball":
        json_match = re.search(r'\{[^}]*"win_loss"[^}]*\}', text, re.DOTALL)
    else:
        json_match = re.search(r'\{[^}]*"spf"[^}]*\}', text, re.DOTALL)
        if not json_match:
            # 尝试匹配情报格式
            json_match = re.search(r'\{[^}]*"intel_summary"[^}]*\}', text, re.DOTALL)
    
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    print(f"  WARNING: AI回复无法解析为JSON，原始内容: {(text or '')[:300]}")
    return None


def call_coze_code(url, token, prompt, project_id=None, timeout=INTEL_TIMEOUT):
    """调用扣子编程API"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "content": {
            "query": {
                "prompt": [{"type": "text", "content": {"text": prompt}}],
            },
        },
        "type": "query",
        "session_id": f"predict_{int(time.time())}",
    }
    if project_id:
        payload["project_id"] = project_id

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    
    if resp.status_code != 200:
        print(f"  [扣子API] HTTP {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")

    # JSON响应
    if "json" in content_type:
        data = resp.json()
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], dict):
                messages = data["data"].get("messages", [])
                for msg in reversed(messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        return msg["content"]
            if "result" in data:
                return str(data["result"])
            if "text" in data:
                return str(data["text"])
        return json.dumps(data, ensure_ascii=False)

    # SSE流式响应
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
                if isinstance(evt, dict) and evt.get("type") == "answer":
                    chunk = evt.get("content", {}).get("answer")
                    if chunk:
                        answer_chunks.append(chunk)
            except json.JSONDecodeError:
                pass
    
    if answer_chunks:
        return "".join(answer_chunks)

    return resp.text


def call_ai(ai_name, prompt, sport="football"):
    """调用指定AI，支持fallback模型"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        raise Exception(f"未知AI: {ai_name}")
    
    fmt = config["format"]
    
    if fmt == "coze_code":
        token = os.environ.get(config.get("key_env", ""), "") or config.get("key_default", "")
        if not token:
            raise Exception(f"{ai_name} Token未配置")
        raw = call_coze_code(config["url"], token, prompt, config.get("project_id"))
        return parse_ai_response(raw, sport)
    
    key = os.environ.get(config["key_env"], "")
    if not key:
        raise Exception(f"{ai_name} API Key未配置")
    
    models_to_try = [config["model"]]
    if config.get("fallback_models"):
        models_to_try.extend(config["fallback_models"])
    
    last_error = None
    for i, model in enumerate(models_to_try):
        try:
            if fmt == "openai":
                raw = call_openai_compatible(config["url"], key, model, prompt)
            elif fmt == "minimax":
                raw = call_minimax(config["url"], key, model, prompt)
            else:
                raise Exception(f"未知格式: {fmt}")
            
            # 检查返回内容是否为空或明显异常
            if not raw or len(raw.strip()) < 1:
                raise Exception(f"模型 {model} 返回空内容")
            
            result = parse_ai_response(raw, sport)
            if result is None and i < len(models_to_try) - 1:
                # 解析失败也算失败，触发fallback
                print(f"    [fallback] {model} 返回内容无法解析为有效JSON，尝试备用...")
                last_error = Exception(f"{model} 返回内容无法解析")
                continue
            
            if i > 0:
                print(f"    [fallback] 已切换到 {model}")
            return result
            
        except Exception as e:
            error_str = str(e)
            last_error = e
            
            if i < len(models_to_try) - 1:
                # 任何错误都触发fallback：403/限流/超时/解析失败等
                print(f"    [fallback] {model} 失败({error_str[:60]})，尝试备用...")
                continue
            else:
                # 最后一个模型也失败了
                raise e
    
    if last_error:
        raise last_error


# ============ 逻辑校验 ============

def validate_basketball_consistency(pred, spread_line):
    """校验篮球预测的逻辑一致性"""
    try:
        spread = float(spread_line) if spread_line else 0
    except (ValueError, TypeError):
        spread = 0
    
    hw = pred.get("handicap_win_loss", "让胜")
    sdr = pred.get("score_diff_range", "")
    wl = pred.get("win_loss", "胜")
    
    sdr_match = re.match(r'(主|客)(\d+)[-](\d+)(胜|负)', sdr)
    if not sdr_match:
        sdr_match2 = re.match(r'(主|客)(\d+)\+(胜|负)', sdr)
        if sdr_match2:
            team = sdr_match2.group(1)
            low = int(sdr_match2.group(2))
            high = 99
        else:
            return pred
    else:
        team = sdr_match.group(1)
        low = int(sdr_match.group(2))
        high = int(sdr_match.group(3))
    
    abs_spread = abs(spread)
    min_cover = math.floor(abs_spread) + 1
    
    corrected = dict(pred)
    
    # 让分↔胜负一致性
    if hw == "让胜" and wl == "负" and spread < 0:
        corrected["win_loss"] = "胜"
    elif hw == "让负" and wl == "胜" and spread < 0 and abs_spread >= 8:
        corrected["win_loss"] = "负"
    
    return corrected


# ============ Prompt构建 ============

def build_intel_prompt(match, sport="football"):
    """构建情报搜集Prompt"""
    home_team = match.get("home_team") or "主队"
    away_team = match.get("away_team") or "客队"
    odds = match.get("odds") or {}
    
    def fmt_odds(val):
        if val is None or val == 0 or val == "":
            return "暂无"
        return str(val)
    
    if sport == "basketball":
        spread_line = match.get("spread_line") or 0
        try:
            spread_line = float(spread_line)
        except:
            spread_line = 0
        
        if spread_line < 0:
            spread_desc = f"主队让{-spread_line}分"
        elif spread_line > 0:
            spread_desc = f"客队让{spread_line}分"
        else:
            spread_desc = "平手盘"
        
        return INTEL_PROMPT_BASKETBALL.format(
            league=match.get("league") or "未知联赛",
            home_team=home_team,
            away_team=away_team,
            match_time=match.get("match_time") or "",
            spread_line=spread_line,
            spread_desc=spread_desc,
            total_line=match.get("total_line") or 0,
        )
    else:
        spf_odds = odds.get("spf") or {}
        return INTEL_PROMPT_FOOTBALL.format(
            league=match.get("league") or "未知联赛",
            home_team=home_team,
            away_team=away_team,
            match_time=match.get("match_time") or "",
            handicap=match.get("handicap") or "暂无",
            win_odds=fmt_odds(spf_odds.get("win")),
            draw_odds=fmt_odds(spf_odds.get("draw")),
            lose_odds=fmt_odds(spf_odds.get("lose")),
        )


def build_football_prompt(match, intel_data=None):
    """构建足球预测Prompt"""
    home_team = match.get("home_team") or "主队"
    away_team = match.get("away_team") or "客队"
    odds = match.get("odds") or {}
    spf_odds = odds.get("spf") or {}
    handicap_spf_odds = odds.get("handicap_spf") or {}
    
    def fmt_odds(val):
        if val is None or val == 0 or val == "":
            return "暂无"
        return str(val)
    
    # 格式化情报数据
    intel_text = "暂无情报数据"
    if intel_data:
        parts = []
        if intel_data.get("home_form"):
            parts.append(f"- 主队近况: {intel_data['home_form']}")
        if intel_data.get("away_form"):
            parts.append(f"- 客队近况: {intel_data['away_form']}")
        if intel_data.get("h2h"):
            parts.append(f"- 交锋记录: {intel_data['h2h']}")
        if intel_data.get("odds_analysis"):
            parts.append(f"- 赔率分析: {intel_data['odds_analysis']}")
        if intel_data.get("key_factors"):
            parts.append(f"- 关键因素: {', '.join(intel_data['key_factors'])}")
        if intel_data.get("intel_summary"):
            parts.append(f"- 情报总结: {intel_data['intel_summary']}")
        if parts:
            intel_text = "\n".join(parts)
    
    return PREDICTION_PROMPT.format(
        league=match.get("league") or "未知联赛",
        home_team=home_team,
        away_team=away_team,
        match_time=match.get("match_time") or "",
        handicap=match.get("handicap") or "暂无",
        win_odds=fmt_odds(spf_odds.get("win")),
        draw_odds=fmt_odds(spf_odds.get("draw")),
        lose_odds=fmt_odds(spf_odds.get("lose")),
        hw_odds=fmt_odds(handicap_spf_odds.get("win")),
        hd_odds=fmt_odds(handicap_spf_odds.get("draw")),
        hl_odds=fmt_odds(handicap_spf_odds.get("lose")),
        intel_data=intel_text,
    )


def build_basketball_prompt(match, intel_data=None):
    """构建篮球预测Prompt"""
    home_team = match.get("home_team") or "主队"
    away_team = match.get("away_team") or "客队"
    odds = match.get("odds") or {}
    
    spread_odds = odds.get("spread") or {}
    if isinstance(spread_odds, str):
        try:
            spread_odds = json.loads(spread_odds)
        except:
            spread_odds = {}
    
    total_odds = odds.get("total_points") or {}
    if isinstance(total_odds, str):
        try:
            total_odds = json.loads(total_odds)
        except:
            total_odds = {}
    
    sdr_odds = odds.get("score_diff") or {}
    if isinstance(sdr_odds, str):
        try:
            sdr_odds = json.loads(sdr_odds)
        except:
            sdr_odds = {}
    
    spread_line = match.get("spread_line") or 0
    try:
        spread_line = float(spread_line)
    except:
        spread_line = 0
    
    total_line = match.get("total_line") or 0
    try:
        total_line = float(total_line)
    except:
        total_line = 0
    
    spread_win = spread_odds.get("home", spread_odds.get("胜", spread_odds.get("win", "-")))
    spread_lose = spread_odds.get("away", spread_odds.get("负", spread_odds.get("lose", "-")))
    total_over = total_odds.get("over", total_odds.get("大", "-"))
    total_under = total_odds.get("under", total_odds.get("小", "-"))
    
    sdr_ranges = ["1-5", "6-10", "11-15", "16-20", "21-25", "26+"]
    sdr_vals = {}
    for i, rng in enumerate(sdr_ranges):
        idx = str(i + 1)
        val = sdr_odds.get(f"l{idx}", None)
        if val is None:
            home_val = sdr_odds.get(f"主胜_{idx}", None)
            away_val = sdr_odds.get(f"主负_{idx}", None)
            if home_val is not None and away_val is not None:
                val = min(home_val, away_val)
            elif home_val is not None:
                val = home_val
            elif away_val is not None:
                val = away_val
        sdr_vals[rng] = val if val is not None else "-"
    
    if spread_line < 0:
        spread_desc = f"主队让{-spread_line}分"
    elif spread_line > 0:
        spread_desc = f"客队让{spread_line}分"
    else:
        spread_desc = "平手盘"
    
    # 格式化情报数据
    intel_text = "暂无情报数据"
    if intel_data:
        parts = []
        if intel_data.get("home_form"):
            parts.append(f"- 主队近况: {intel_data['home_form']}")
        if intel_data.get("away_form"):
            parts.append(f"- 客队近况: {intel_data['away_form']}")
        if intel_data.get("h2h"):
            parts.append(f"- 交锋记录: {intel_data['h2h']}")
        if intel_data.get("odds_analysis"):
            parts.append(f"- 赔率分析: {intel_data['odds_analysis']}")
        if intel_data.get("intel_summary"):
            parts.append(f"- 情报总结: {intel_data['intel_summary']}")
        if parts:
            intel_text = "\n".join(parts)
    
    return BASKETBALL_PROMPT.format(
        league=match.get("league") or "未知联赛",
        home_team=home_team,
        away_team=away_team,
        match_time=match.get("match_time") or "",
        spread_line=spread_line,
        spread_desc=spread_desc,
        total_line=total_line,
        win_odds=match.get("win_odds") or "暂无",
        lose_odds=match.get("lose_odds") or "暂无",
        spread_win_odds=spread_win or "暂无",
        spread_lose_odds=spread_lose or "暂无",
        total_over_odds=total_over or "暂无",
        total_under_odds=total_under or "-",
        sdr_1_5=sdr_vals["1-5"],
        sdr_6_10=sdr_vals["6-10"],
        sdr_11_15=sdr_vals["11-15"],
        sdr_16_20=sdr_vals["16-20"],
        sdr_21_25=sdr_vals["21-25"],
        sdr_26=sdr_vals["26+"],
        intel_data=intel_text,
    )


# ============ Phase 1: 情报搜集 ============

def phase1_collect_intel(sport="football"):
    """Phase 1: 为所有待预测比赛搜集情报"""
    print(f"\n{'='*50}")
    print(f"Phase 1: 情报搜集 ({sport})")
    print(f"{'='*50}")
    
    matches = get_pending_matches(sport)
    if not matches:
        print(f"没有待预测的{sport}比赛")
        return {"collected": 0, "failed": 0}
    
    collected = 0
    failed = 0
    
    for i, match in enumerate(matches):
        match_id = match["id"]
        home = match.get("home_team", "?")
        away = match.get("away_team", "?")
        
        print(f"\n[{i+1}/{len(matches)}] {home} vs {away}")
        
        # 检查是否已有情报
        existing_intel = get_intel(match_id)
        if existing_intel:
            print(f"  已有情报，跳过")
            collected += 1
            continue
        
        # 构建情报搜集Prompt
        prompt = build_intel_prompt(match, sport)
        
        # 调用扣子智能体搜集情报
        try:
            print(f"  调用扣子情报智能体...")
            result = call_coze_code(
                AI_CONFIGS["AI-扣子"]["url"],
                os.environ.get("COZE_PROJECT_API_TOKEN", "") or AI_CONFIGS["AI-扣子"]["key_default"],
                prompt,
                AI_CONFIGS["AI-扣子"].get("project_id"),
                timeout=INTEL_TIMEOUT
            )
            
            intel_data = parse_ai_response(result, "intel")
            if intel_data and (intel_data.get("intel_summary") or intel_data.get("home_form")):
                save_intel(match_id, intel_data)
                print(f"  情报已保存: {intel_data.get('intel_summary', '')[:50]}...")
                collected += 1
            else:
                print(f"  情报解析失败")
                failed += 1
                
        except Exception as e:
            print(f"  情报搜集失败: {str(e)[:100]}")
            failed += 1
        
        # 间隔避免限流
        time.sleep(AI_CALL_INTERVAL)
    
    print(f"\nPhase 1 完成: 成功{collected}, 失败{failed}")
    return {"collected": collected, "failed": failed}


# ============ Phase 2: 逐AI逐场预测 ============

def phase2_predict(sport="football"):
    """Phase 2: 逐场比赛、逐AI预测，每个预测立即入库"""
    print(f"\n{'='*50}")
    print(f"Phase 2: AI预测 ({sport})")
    print(f"{'='*50}")
    
    matches = get_pending_matches(sport)
    if not matches:
        print(f"没有待预测的{sport}比赛")
        return {"matches": 0, "predictions": 0, "errors": 0}
    
    total_predictions = 0
    total_errors = 0
    match_results = []
    
    for i, match in enumerate(matches):
        match_id = match["id"]
        home = match.get("home_team", "?")
        away = match.get("away_team", "?")
        
        # 获取已有预测
        existing = get_existing_predictions(match_id)
        
        # 按顺序找出需要预测的AI
        missing_ais = [ai for ai in AI_CALL_ORDER if ai not in existing]
        if not missing_ais:
            print(f"\n[{i+1}/{len(matches)}] {home} vs {away} - 全部AI已完成")
            continue
        
        print(f"\n[{i+1}/{len(matches)}] {home} vs {away}")
        print(f"  待预测AI: {', '.join(missing_ais)}")
        
        # 获取情报数据
        intel_data = get_intel(match_id)
        if intel_data:
            print(f"  情报: {intel_data.get('intel_summary', '')[:50]}...")
        else:
            print(f"  无情报数据")
        
        # 构建Prompt
        if sport == "basketball":
            prompt = build_basketball_prompt(match, intel_data)
        else:
            prompt = build_football_prompt(match, intel_data)
        
        match_pred_count = 0
        match_errors = 0
        
        # 逐个AI调用
        for ai_name in missing_ais:
            try:
                print(f"  调用 {ai_name}...", end=" ", flush=True)
                result = call_ai(ai_name, prompt, sport)
                
                if result is None:
                    print("返回无法解析")
                    match_errors += 1
                    continue
                
                # 处理预测结果
                ai_short_name = ai_name.replace("AI-", "", 1) if ai_name.startswith("AI-") else ai_name
                
                if sport == "basketball":
                    # 篮球处理
                    result = validate_basketball_consistency(result, match.get("spread_line") or 0)
                    
                    wl_raw = result.get("win_loss", "")
                    wl_map = {"主胜": "胜", "客胜": "负", "home": "胜", "away": "负"}
                    wl = wl_map.get(wl_raw, wl_raw)
                    if wl not in ("胜", "负"):
                        print(f"win_loss非法")
                        match_errors += 1
                        continue
                    
                    hwl_raw = result.get("handicap_win_loss", "")
                    hwl_map = {"让球胜": "让胜", "让球负": "让负"}
                    hwl = hwl_map.get(hwl_raw, hwl_raw)
                    if hwl not in ("让胜", "让负"):
                        print(f"handicap非法")
                        match_errors += 1
                        continue
                    
                    tp_raw = result.get("total_points", "")
                    tp_map = {"大分": "大", "小分": "小", "over": "大", "under": "小"}
                    tp = tp_map.get(tp_raw, tp_raw)
                    if tp not in ("大", "小"):
                        print(f"total非法")
                        match_errors += 1
                        continue
                    
                    sdr = result.get("score_diff_range", "")
                    if not re.match(r'^(主|客)\d+[-+]\d*(胜|负)$', str(sdr)):
                        print(f"score_diff非法")
                        match_errors += 1
                        continue
                    
                    hwl_half = wl_map.get(result.get("half_win_loss", ""), result.get("half_win_loss", ""))
                    if hwl_half not in ("胜", "负"):
                        print(f"half非法")
                        match_errors += 1
                        continue
                    
                    pred = {
                        "match_id": match_id,
                        "ai_name": ai_short_name,
                        "win_loss": wl,
                        "handicap_win_loss": hwl,
                        "total_points": tp,
                        "score_diff_range": sdr,
                        "half_win_loss": hwl_half,
                        "analysis": result.get("analysis", "")[:500],
                    }
                    
                    # 立即入库
                    insert_basketball_prediction(pred)
                    match_pred_count += 1
                    print(f"OK -> {wl}/{hwl}/{tp}")
                    
                else:
                    # 足球处理
                    spf_raw = result.get("spf", "")
                    spf_map = {"主胜": "胜", "主平": "平", "主负": "负", "平局": "平"}
                    spf = spf_map.get(spf_raw, spf_raw)
                    if spf not in ("胜", "平", "负"):
                        print(f"spf非法")
                        match_errors += 1
                        continue
                    
                    handicap_spf_raw = result.get("handicap_spf", "")
                    handicap_map = {"让球胜": "让胜", "让球平": "让平", "让球负": "让负"}
                    handicap_spf = handicap_map.get(handicap_spf_raw, handicap_spf_raw)
                    if handicap_spf not in ("让胜", "让平", "让负"):
                        print(f"handicap非法")
                        match_errors += 1
                        continue
                    
                    score = result.get("score", "")
                    if not re.match(r'^\d+-\d+$', str(score)):
                        print(f"score非法")
                        match_errors += 1
                        continue
                    
                    goals = int(result.get("goals", 1))
                    half_full_raw = result.get("half_full", "")
                    
                    # 半全场值规范化函数
                    def normalize_half_full(raw):
                        if not raw:
                            return None
                        
                        raw = str(raw).strip()
                        
                        # 标准映射表
                        half_full_map = {
                            # 标准映射（主/平/负 -> 胜/平/负）
                            "主主": "胜胜", "主平": "胜平", "主负": "胜负",
                            "平主": "平胜", "平平": "平平", "平负": "平负",
                            "负主": "负胜", "负平": "负平", "负负": "负负",
                            # 带斜杠格式
                            "主/主": "胜胜", "主/平": "胜平", "主/负": "胜负",
                            "平/主": "平胜", "平/平": "平平", "平/负": "平负",
                            "负/主": "负胜", "负/平": "负平", "负/负": "负负",
                            "胜/胜": "胜胜", "胜/平": "胜平", "胜/负": "胜负",
                            "平/胜": "平胜", "平/平": "平平", "平/负": "平负",
                            "负/胜": "负胜", "负/平": "负平", "负/负": "负负",
                            # 带横线格式（主/平/负）
                            "主-主": "胜胜", "主-平": "胜平", "主-负": "胜负",
                            "平-主": "平胜", "平-平": "平平", "平-负": "平负",
                            "负-主": "负胜", "负-平": "负平", "负-负": "负负",
                            # 带横线格式（胜/平/负）- 新增
                            "胜-胜": "胜胜", "胜-平": "胜平", "胜-负": "胜负",
                            "平-胜": "平胜", "平-平": "平平", "平-负": "平负",
                            "负-胜": "负胜", "负-平": "负平", "负-负": "负负",
                            # 标准胜平负格式
                            "胜胜": "胜胜", "胜平": "胜平", "胜负": "胜负",
                            "平胜": "平胜", "平平": "平平", "平负": "平负",
                            "负胜": "负胜", "负平": "负平", "负负": "负负",
                        }
                        
                        # 直接匹配
                        if raw in half_full_map:
                            return half_full_map[raw]
                        
                        # 正则提取：处理带前缀/后缀的情况
                        # 例如："半全场平胜", "平胜(半全场)", "半场平/全场胜"
                        valid_values = ("胜胜", "胜平", "胜负", "平胜", "平平", "平负", "负胜", "负平", "负负")
                        
                        # 尝试从字符串中提取有效的半全场值
                        for val in valid_values:
                            if val in raw:
                                return val
                        
                        # 尝试提取"X/Y"或"X-Y"格式
                        match = re.search(r'([主平负胜])[/-]([主平负胜])', raw)
                        if match:
                            key = match.group(1) + match.group(2)
                            if key in half_full_map:
                                return half_full_map[key]
                        
                        # 无法解析
                        return None
                    
                    half_full = normalize_half_full(half_full_raw)
                    if half_full is None and half_full_raw:
                        print(f"half_full非法({half_full_raw})，降级为None")
                    
                    pred = {
                        "match_id": match_id,
                        "ai_name": ai_short_name,
                        "spf": spf,
                        "handicap_spf": handicap_spf,
                        "score": score,
                        "goals": goals,
                        "half_full": half_full,
                        "analysis": result.get("analysis", "")[:500],
                    }
                    
                    # 立即入库
                    insert_football_prediction(pred)
                    match_pred_count += 1
                    print(f"OK -> {spf}/{handicap_spf}/{score}")
                
            except Exception as e:
                print(f"失败: {str(e)[:50]}")
                match_errors += 1
            
            # AI调用间隔
            time.sleep(AI_CALL_INTERVAL)
        
        total_predictions += match_pred_count
        total_errors += match_errors
        match_results.append({
            "match_id": match_id,
            "home": home,
            "away": away,
            "predicted": match_pred_count,
            "errors": match_errors,
        })
    
    result = {
        "sport": sport,
        "matches_processed": len(match_results),
        "predictions_created": total_predictions,
        "errors": total_errors,
        "details": match_results,
    }
    
    print(f"\n{'='*50}")
    print(f"Phase 2 完成")
    print(f"比赛: {len(match_results)}, 预测: {total_predictions}, 错误: {total_errors}")
    print(f"{'='*50}")
    
    return result


# ============ 主入口 ============

def run_predict(sport="football", phase="all"):
    """主入口：两阶段预测
    
    Args:
        sport: football 或 basketball
        phase: "1"=只跑情报搜集, "2"=只跑预测, "all"=全部
    """
    start_time = time.time()
    
    print(f"\n{'#'*60}")
    print(f"# 两阶段AI预测系统")
    print(f"# 运动: {sport}, 阶段: {phase}")
    print(f"# 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")
    
    result = {
        "sport": sport,
        "phase": phase,
        "start_time": datetime.now().isoformat(),
    }
    
    if phase in ("1", "all"):
        result["phase1"] = phase1_collect_intel(sport)
    
    if phase in ("2", "all"):
        result["phase2"] = phase2_predict(sport)
    
    elapsed = time.time() - start_time
    result["elapsed_seconds"] = round(elapsed, 1)
    result["end_time"] = datetime.now().isoformat()
    
    print(f"\n总耗时: {elapsed:.1f}秒")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result


if __name__ == "__main__":
    sport = "football"
    phase = "all"
    
    # 解析参数
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ("football", "basketball"):
            sport = arg
        elif arg == "--sport" and i + 1 < len(sys.argv):
            sport = sys.argv[i + 1]
            i += 1
        elif arg == "--phase" and i + 1 < len(sys.argv):
            phase = sys.argv[i + 1]
            i += 1
        elif arg in ("1", "2", "all"):
            phase = arg
        i += 1
    
    try:
        run_predict(sport, phase)
    except Exception as e:
        print(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
