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
        "key_default": "",
        "model": "hy-mt2-plus",               # ✅ TokenHub端点实测200
        "format": "openai",
        "fallback_models": [
            "hy-mt2-pro",                      # ✅ TokenHub实测200
            "hy4-preview",                     # ✅ TokenHub实测可用
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

# 混元专用Prompt（避免spf主客视角bug，改用winner队名+比分）
HUNYUAN_SYSTEM_PROMPT = """你是资深足球赛事分析师，基于赔率数据独立预测比赛结果。
赔率含义（严格遵守）：
- "胜"=主队赢，"平"=打平，"负"=客队赢。赔率数字越小=该结果概率越高。
- 让球数为负数（如-1）=主队让球（主队强）；正数（如+1）=主队受让（主队弱）。
- 让球后主队仍赢=让胜，打平=让平，主队输=让负。
你会收到主胜/平局/客胜的隐含概率（已由赔率换算好的客观数据）。请：
1. 结合概率与让球盘独立判断，可认同热门也可判冷门或平局，分析要具体。
2. 比分反映判断场面：实力悬殊可大比分，势均力敌可能1球小胜或平局。
3. 半场结果合理：强队可能半场领先，势均力敌半场平局常见。
4. 禁止套模板，每场分析针对这场比赛。
只输出JSON：
{"analysis":"具体分析40字以上","winner":"主队队名或客队队名或平局","home_goals":整数,"away_goals":整数,"half_leader":"半场领先队名或平局"}
比分必须与winner一致。"""

HUNYUAN_USER_TEMPLATE = """比赛：{league} {home}（主场） vs {away}（客场）
隐含概率：主胜{pw}% 平局{pd}% 客胜{pl}%
让球：{handicap_desc}
让球胜平负赔率：让胜{hw} 让平{hd} 让负{hl}
请独立分析并预测。"""

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
  "score_diff_range": "如主6-10胜或客1-5胜",
  "half_win_loss": "胜"或"负",
  "analysis": "50-100字分析理由"
}}
```

## 逻辑自洽规则:
1. 让分↔胜分差：选"让胜"→胜分差应为"主x胜"且分差>盘口
2. 让分↔胜负：选"让胜"→胜负应选"胜"
3. 胜分差格式: 主1-5胜/主6-10胜/主11-15胜/主16-20胜/主21+胜/客1-5胜/客6-10胜/客11-15胜/客16-20胜/客21+胜
4. **方向一致**: win_loss="胜"表示主队赢→score_diff_range必须是"主X胜"；win_loss="负"表示主队输→score_diff_range必须是"客X胜"。主/客前缀必须与win_loss同方向。"""

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
                normalized["score_diff_range"] = f"客{score_diff}胜"
            else:
                normalized["score_diff_range"] = score_diff
        else:
            normalized["score_diff_range"] = score_diff
    
    # === 解析容错：win_loss字段 ===
    # '客胜'→'负'、'主胜'→'胜'、'客负'→'胜'、'主负'→'负'
    wl = normalized.get("win_loss", "")
    wl_fix_map = {"客胜": "负", "主胜": "胜", "客负": "胜", "主负": "负"}
    if wl in wl_fix_map:
        normalized["win_loss"] = wl_fix_map[wl]
    
    # === 解析容错：handicap_win_loss字段 ===
    hwl = normalized.get("handicap_win_loss", "")
    hwl_fix_map = {"客胜": "让负", "主胜": "让胜", "客负": "让胜", "主负": "让负"}
    if hwl in hwl_fix_map:
        normalized["handicap_win_loss"] = hwl_fix_map[hwl]
    
    # 统一胜分差格式：将"主负/客负"转换为"主胜/客胜"
    sdr = normalized.get("score_diff_range", "")
    if sdr and isinstance(sdr, str):
        sdr = sdr.strip()
        # "主1-5负" → "主1-5胜", "客6-10负" → "客6-10胜"
        sdr = re.sub(r'^(主|客)(\d+[-+]\d*)负$', r'\1\2胜', sdr)
        # "主负1-5" → "客胜1-5", "客负6-10" → "主胜6-10"
        sdr = re.sub(r'^主负(\d+[-+]\d*|\d+\+?)$', r'客胜\1', sdr)
        sdr = re.sub(r'^客负(\d+[-+]\d*|\d+\+?)$', r'主胜\1', sdr)
        # 统一为"主X-Y胜"格式：将"主胜X-Y"转换为"主X-Y胜"
        sdr = re.sub(r'^(主|客)胜(\d+[-+]\d*|\d+\+?)$', r'\1\2胜', sdr)
        normalized["score_diff_range"] = sdr
    
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


def _normalize_hunyuan_format(data):
    """将混元的非标准JSON格式转换为标准预测格式"""
    if not isinstance(data, dict):
        return data
    # 混元格式: {"winner":"平局","home_goals":0,"away_goals":0,"half_leader":"平局","analysis":"..."}
    if "winner" in data and "spf" not in data:
        winner_map = {"胜": "胜", "平局": "平", "负": "负", "平": "平"}
        spf = winner_map.get(data.get("winner", ""), "")
        hg = data.get("home_goals", 0)
        ag = data.get("away_goals", 0)
        if isinstance(hg, (int, float)) and isinstance(ag, (int, float)):
            score = f"{int(hg)}-{int(ag)}"
        else:
            score = ""
        # half_leader → half_full 的第一位
        half_map = {"胜": "胜", "平局": "平", "负": "负", "平": "平"}
        half_result = half_map.get(data.get("half_leader", ""), "平")
        full_result = spf if spf else "平"
        half_full = f"{half_result}{full_result}"
        # 让球需要后续根据实际让球值计算，先设为空
        normalized = {
            "spf": spf,
            "handicap_spf": "",  # 由 validate_football_consistency 自动计算
            "score": score,
            "goals": int(hg) + int(ag),
            "half_full": half_full,
            "analysis": data.get("analysis", ""),
        }
        return normalized
    return data


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
            # 混元格式: 有 winner 字段但无 spf
            elif sport == "football" and "winner" in data:
                normalized = _normalize_hunyuan_format(data)
                if normalized and normalized.get("spf"):
                    return normalized
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
            # 尝试混元格式
            json_match = re.search(r'\{[^}]*"winner"[^}]*\}', text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                    normalized = _normalize_hunyuan_format(data)
                    if normalized and normalized.get("spf"):
                        return normalized
                except json.JSONDecodeError:
                    pass
                json_match = None
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
    
    # === 新增：win_loss ↔ score_diff_range方向一致性 ===
    # win_loss=胜 → sdr必须是"主X胜"；win_loss=负 → sdr必须是"客X胜"
    wl_fixed = corrected.get("win_loss", wl)
    sdr_fixed = corrected.get("score_diff_range", sdr)
    sdr_team_match = re.match(r'^(主|客)', sdr_fixed)
    if sdr_team_match:
        sdr_team = sdr_team_match.group(1)
        if wl_fixed == "胜" and sdr_team == "客":
            # win_loss=胜但sdr是客→以handicap方向为准修正sdr
            if hw == "让胜":
                corrected["score_diff_range"] = re.sub(r'^客', '主', sdr_fixed)
            else:
                corrected["win_loss"] = "负"
        elif wl_fixed == "负" and sdr_team == "主":
            # win_loss=负但sdr是主→以handicap方向为准修正sdr
            if hw == "让负":
                corrected["score_diff_range"] = re.sub(r'^主', '客', sdr_fixed)
            else:
                corrected["win_loss"] = "胜"
    
    return corrected


def _get_match_handicap(match):
    """从 match dict 中获取让球值（float），兼容 metadata 嵌套结构"""
    md = match.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except:
            md = {}
    raw = md.get("handicap") or match.get("handicap") or "0"
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


def validate_football_consistency(pred, match):
    """校验并修正足球预测的逻辑一致性：
    1. handicap_spf 必须与 score + 让球盘口 一致
    2. half_full 必须与 score 一致
    以比分为准，覆盖不一致的字段。
    """
    corrected = dict(pred)
    score_str = str(pred.get("score", ""))
    m = re.match(r'^(\d+)-(\d+)$', score_str)
    if not m:
        return corrected

    home_goals = int(m.group(1))
    away_goals = int(m.group(2))
    handicap = _get_match_handicap(match)

    # ---- 1. 校验 handicap_spf ----
    # 让球后净胜球 = 主进球 - 客进球 + 让球值
    net = home_goals - away_goals + handicap
    if net > 0.01:
        correct_handicap = "让胜"
    elif net < -0.01:
        correct_handicap = "让负"
    else:
        correct_handicap = "让平"

    current_handicap = pred.get("handicap_spf", "")
    if current_handicap != correct_handicap:
        print(f"  [修正] handicap_spf: {current_handicap} -> {correct_handicap} "
              f"(比分{score_str}, 盘口{handicap:+.1f}, 净胜{net:+.1f})")
        corrected["handicap_spf"] = correct_handicap

    # ---- 2. 校验 half_full ----
    current_hf = pred.get("half_full") or ""
    if len(current_hf) == 2:
        half_char = current_hf[0]   # 胜/平/负
        full_char = current_hf[1]   # 胜/平/负

        # 全场结果修正
        if home_goals > away_goals:
            correct_full = "胜"
        elif home_goals < away_goals:
            correct_full = "负"
        else:
            correct_full = "平"

        if full_char != correct_full:
            print(f"  [修正] half_full全场: {full_char} -> {correct_full} (比分{score_str})")
            full_char = correct_full

        # 半场结果修正：0-0 半场必须是 "平"
        if home_goals == 0 and away_goals == 0:
            correct_half = "平"
            if half_char != correct_half:
                print(f"  [修正] half_full半场: {half_char} -> {correct_half} (比分0-0)")
                half_char = correct_half

        corrected_hf = half_char + full_char
        if corrected_hf != current_hf:
            corrected["half_full"] = corrected_hf

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


def normalize_hunyuan_football(raw_pred, home_team, away_team, handicap_line):
    """
    混元足球预测归一化：将winner/home_goals/away_goals/half_leader转换为标准格式
    返回标准化后的prediction dict，如果无法归一化则返回None
    """
    if not raw_pred:
        return None
    
    try:
        winner = str(raw_pred.get("winner", "")).strip()
        home_goals = raw_pred.get("home_goals")
        away_goals = raw_pred.get("away_goals")
        half_leader = str(raw_pred.get("half_leader", "")).strip()
        analysis = str(raw_pred.get("analysis", "")).strip()
        
        # 1. 确定spf（胜平负）
        if not winner:
            return None
        
        # 判断winner是主队、客队还是平局
        home_keywords = [home_team, "主", "home"]
        away_keywords = [away_team, "客", "away"]
        draw_keywords = ["平", "draw", "平局"]
        
        winner_lower = winner.lower()
        if any(kw in winner for kw in home_keywords) or any(kw in winner_lower for kw in [k.lower() for k in home_keywords]):
            spf = "胜"
        elif any(kw in winner for kw in away_keywords) or any(kw in winner_lower for kw in [k.lower() for k in away_keywords]):
            spf = "负"
        elif any(kw in winner for kw in draw_keywords):
            spf = "平"
        else:
            # 无法判断，返回None
            return None
        
        # 2. 归一化比分
        try:
            hg = int(home_goals) if home_goals is not None else None
            ag = int(away_goals) if away_goals is not None else None
        except (ValueError, TypeError):
            return None
        
        if hg is None or ag is None:
            return None
        
        # 比分方向必须与winner一致
        if spf == "胜" and hg <= ag:
            # 修正：主队赢但比分不对，交换或调整
            if ag > hg:
                hg, ag = ag, hg  # 交换
            else:
                hg = ag + 1  # 调整
        elif spf == "负" and ag <= hg:
            if hg > ag:
                hg, ag = ag, hg
            else:
                ag = hg + 1
        elif spf == "平" and hg != ag:
            # 平局但比分不等，取平均
            avg = (hg + ag) // 2
            hg = ag = avg
        
        # 3. 计算goals和score
        goals = hg + ag
        score = f"{hg}-{ag}"
        
        # 4. 归一化half_leader为半场字（胜/平/负）
        if not half_leader:
            half_char = "平"  # 默认
        elif any(kw in half_leader for kw in home_keywords) or any(kw in half_leader.lower() for kw in [k.lower() for k in home_keywords]):
            half_char = "胜"
        elif any(kw in half_leader for kw in away_keywords) or any(kw in half_leader.lower() for kw in [k.lower() for k in away_keywords]):
            half_char = "负"
        elif any(kw in half_leader for kw in draw_keywords):
            half_char = "平"
        else:
            half_char = "平"
        
        # 5. 计算half_full = 半场字 + spf末字
        spf_char = spf  # 胜/平/负
        half_full = half_char + spf_char
        
        # 6. 计算让球胜平负
        try:
            handicap = float(handicap_line) if handicap_line else 0
        except (ValueError, TypeError):
            handicap = 0
        
        # 虚拟主队进球 = hg + handicap（handicap为负数表示主让）
        virtual_hg = hg + handicap
        if virtual_hg > ag + 0.01:
            handicap_spf = "让胜"
        elif abs(virtual_hg - ag) <= 0.01:
            handicap_spf = "让平"
        else:
            handicap_spf = "让负"
        
        # 7. 构建标准化结果
        result = {
            "spf": spf,
            "handicap_spf": handicap_spf,
            "score": score,
            "goals": goals,
            "half_full": half_full,
            "analysis": analysis[:500] if analysis else ""
        }
        
        return result
        
    except Exception as e:
        print(f"    [混元归一化失败] {e}")
        return None


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

def call_hunyuan_with_retry(match, intel_data, max_retries=3, retry_interval=5):
    """
    混元专用调用函数：使用特殊prompt + 归一化 + 重试机制
    返回标准化后的prediction dict，如果失败则返回None
    """
    home_team = match.get("home_team") or "主队"
    away_team = match.get("away_team") or "客队"
    odds = match.get("odds") or {}
    spf_odds = odds.get("spf") or {}
    handicap_spf_odds = odds.get("handicap_spf") or {}
    
    # 计算隐含概率
    try:
        w = float(spf_odds.get("win", 0))
        d = float(spf_odds.get("draw", 0))
        l = float(spf_odds.get("lose", 0))
        if w > 0 and d > 0 and l > 0:
            total = 1/w + 1/d + 1/l
            pw = round((1/w) / total * 100, 1)
            pd = round((1/d) / total * 100, 1)
            pl = round((1/l) / total * 100, 1)
        else:
            pw, pd, pl = 33.3, 33.3, 33.4
    except:
        pw, pd, pl = 33.3, 33.3, 33.4
    
    # 让球描述
    handicap_line = match.get("handicap") or "0"
    try:
        handicap_val = float(handicap_line)
        if handicap_val < 0:
            handicap_desc = f"主队让{-handicap_val}球"
        elif handicap_val > 0:
            handicap_desc = f"主队受让{handicap_val}球"
        else:
            handicap_desc = "平手盘"
    except:
        handicap_desc = "平手盘"
        handicap_val = 0
    
    # 构建混元专用prompt
    system_prompt = HUNYUAN_SYSTEM_PROMPT
    user_prompt = HUNYUAN_USER_TEMPLATE.format(
        league=match.get("league") or "未知联赛",
        home=home_team,
        away=away_team,
        pw=pw,
        pd=pd,
        pl=pl,
        handicap_desc=handicap_desc,
        hw=handicap_spf_odds.get("win", "暂无"),
        hd=handicap_spf_odds.get("draw", "暂无"),
        hl=handicap_spf_odds.get("lose", "暂无"),
    )
    
    # 组合prompt（system + user）
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    # 重试机制
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"[重试{attempt}/{max_retries}] ", end="", flush=True)
                time.sleep(retry_interval)
            
            # 调用混元API
            raw_result = call_ai("AI-混元", full_prompt, "football")
            
            if raw_result is None:
                continue
            
            # 归一化
            normalized = normalize_hunyuan_football(raw_result, home_team, away_team, handicap_val)
            
            if normalized:
                return normalized
            else:
                print(f"[归一化失败] ", end="", flush=True)
                continue
                
        except Exception as e:
            print(f"[异常: {str(e)[:30]}] ", end="", flush=True)
            continue
    
    # 所有重试都失败
    return None


def _call_ai_single(ai_name, match, sport, prompt, intel_data):
    """调用单个AI对单场比赛进行预测（含3次重试），返回 (result, retries, error_msg)"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            if ai_name == "AI-混元" and sport == "football":
                result = call_hunyuan_with_retry(match, intel_data)
            else:
                result = call_ai(ai_name, prompt, sport)
            elapsed = time.time() - t0
            
            if result is not None:
                return result, attempt, None
            else:
                err = "返回无法解析"
                if attempt < max_retries - 1:
                    print(f"    [重试{attempt+1}/{max_retries}] {err}，{AI_CALL_INTERVAL+5}s后重试...")
                    time.sleep(5)
                else:
                    return None, attempt, err
        except Exception as e:
            err = str(e)[:60]
            if attempt < max_retries - 1:
                print(f"    [重试{attempt+1}/{max_retries}] {err}，5s后重试...")
                time.sleep(5)
            else:
                return None, attempt, err
    return None, max_retries - 1, "max retries"


def _process_and_store(ai_name, result, match, sport):
    """处理AI返回结果并入库。返回 (success: bool, summary: str)"""
    match_id = match["id"]
    ai_short_name = ai_name.replace("AI-", "", 1) if ai_name.startswith("AI-") else ai_name
    
    try:
        if sport == "basketball":
            result = normalize_basketball_fields(result)
            result = validate_basketball_consistency(result, match.get("spread_line") or 0)
            
            wl_raw = result.get("win_loss", "")
            wl_map = {"主胜": "胜", "客胜": "负", "home": "胜", "away": "负"}
            wl = wl_map.get(wl_raw, wl_raw)
            if wl not in ("胜", "负"):
                return False, f"win_loss非法({wl_raw})"
            
            hwl_raw = result.get("handicap_win_loss", "")
            hwl_map = {"让球胜": "让胜", "让球负": "让负"}
            hwl = hwl_map.get(hwl_raw, hwl_raw)
            if hwl not in ("让胜", "让负"):
                return False, f"handicap非法({hwl_raw})"
            
            tp_raw = result.get("total_points", "")
            tp_map = {"大分": "大", "小分": "小", "over": "大", "under": "小"}
            tp = tp_map.get(tp_raw, tp_raw)
            if tp not in ("大", "小"):
                return False, f"total非法({tp_raw})"
            
            sdr = result.get("score_diff_range", "")
            sdr = str(sdr).strip()
            sdr = re.sub(r'^(主|客)(\d+[-+]\d*)负$', r'\1\2胜', sdr)
            sdr = re.sub(r'^主负(\d+[-+]\d*|\d+\+?)$', r'客胜\1', sdr)
            sdr = re.sub(r'^客负(\d+[-+]\d*|\d+\+?)$', r'主胜\1', sdr)
            sdr = re.sub(r'^(主|客)胜(\d+[-+]\d*|\d+\+?)$', r'\1\2胜', sdr)
            if not re.match(r'^(主|客)(\d+[-+]\d*|\d+\+?)胜$', sdr):
                return False, f"score_diff非法({sdr})"
            
            hwl_half = wl_map.get(result.get("half_win_loss", ""), result.get("half_win_loss", ""))
            if hwl_half not in ("胜", "负"):
                return False, f"half非法"
            
            pred = {
                "match_id": match_id, "ai_name": ai_short_name,
                "win_loss": wl, "handicap_win_loss": hwl,
                "total_points": tp, "score_diff_range": sdr,
                "half_win_loss": hwl_half,
                "analysis": result.get("analysis", "")[:500],
            }
            insert_basketball_prediction(pred)
            return True, f"{wl}/{hwl}/{tp}"
        
        else:  # football
            spf_raw = result.get("spf", "")
            spf_map = {"主胜": "胜", "主平": "平", "主负": "负", "平局": "平"}
            spf = spf_map.get(spf_raw, spf_raw)
            if spf not in ("胜", "平", "负"):
                return False, f"spf非法({spf_raw})"
            
            handicap_spf_raw = result.get("handicap_spf", "")
            handicap_map = {"让球胜": "让胜", "让球平": "让平", "让球负": "让负"}
            handicap_spf = handicap_map.get(handicap_spf_raw, handicap_spf_raw)
            if handicap_spf not in ("让胜", "让平", "让负"):
                return False, f"handicap非法({handicap_spf_raw})"
            
            score = result.get("score", "")
            if not re.match(r'^\d+-\d+$', str(score)):
                return False, f"score非法({score})"
            
            goals = int(result.get("goals", 1))
            half_full_raw = result.get("half_full", "")
            
            def normalize_half_full(raw):
                if not raw: return None
                raw = str(raw).strip()
                half_full_map = {
                    "主主": "胜胜", "主平": "胜平", "主负": "胜负",
                    "平主": "平胜", "平平": "平平", "平负": "平负",
                    "负主": "负胜", "负平": "负平", "负负": "负负",
                    "主/主": "胜胜", "主/平": "胜平", "主/负": "胜负",
                    "平/主": "平胜", "平/平": "平平", "平/负": "平负",
                    "负/主": "负胜", "负/平": "负平", "负/负": "负负",
                    "胜/胜": "胜胜", "胜/平": "胜平", "胜/负": "胜负",
                    "平/胜": "平胜", "平/平": "平平", "平/负": "平负",
                    "负/胜": "负胜", "负/平": "负平", "负/负": "负负",
                    "主-主": "胜胜", "主-平": "胜平", "主-负": "胜负",
                    "平-主": "平胜", "平-平": "平平", "平-负": "平负",
                    "负-主": "负胜", "负-平": "负平", "负-负": "负负",
                    "胜-胜": "胜胜", "胜-平": "胜平", "胜-负": "胜负",
                    "平-胜": "平胜", "平-平": "平平", "平-负": "平负",
                    "负-胜": "负胜", "负-平": "负平", "负-负": "负负",
                    "胜胜": "胜胜", "胜平": "胜平", "胜负": "胜负",
                    "平胜": "平胜", "平平": "平平", "平负": "平负",
                    "负胜": "负胜", "负平": "负平", "负负": "负负",
                }
                if raw in half_full_map: return half_full_map[raw]
                valid_values = ("胜胜", "胜平", "胜负", "平胜", "平平", "平负", "负胜", "负平", "负负")
                for val in valid_values:
                    if val in raw: return val
                m2 = re.search(r'([主平负胜])[/-]([主平负胜])', raw)
                if m2:
                    key = m2.group(1) + m2.group(2)
                    if key in half_full_map: return half_full_map[key]
                return None
            
            half_full = normalize_half_full(half_full_raw)
            if half_full is None and half_full_raw:
                half_full = None  # 降级为None，不阻断
            
            pred = {
                "match_id": match_id, "ai_name": ai_short_name,
                "spf": spf, "handicap_spf": handicap_spf,
                "score": score, "goals": goals, "half_full": half_full,
                "analysis": result.get("analysis", "")[:500],
            }
            pred = validate_football_consistency(pred, match)
            insert_football_prediction(pred)
            return True, f"{pred.get('spf')}/{pred.get('handicap_spf')}/{pred.get('score')}"
    
    except Exception as e:
        return False, f"入库异常: {str(e)[:50]}"


def phase2_predict(sport="football"):
    """Phase 2: 按AI轮转批次预测
    
    调度策略：每个AI每次处理5场比赛，跑完换下一个AI，依次轮转。
    失败重试：每次失败等5s后重试，最多3次。
    全部串行执行。
    """
    BATCH_SIZE = 5
    MAX_RETRY = 3
    RETRY_WAIT = 5  # 秒
    
    print(f"\n{'='*50}")
    print(f"Phase 2: AI预测 ({sport}) — 按AI轮转，批次{BATCH_SIZE}场")
    print(f"{'='*50}")
    
    matches = get_pending_matches(sport)
    if not matches:
        print(f"没有待预测的{sport}比赛")
        return {"matches": 0, "predictions": 0, "errors": 0}
    
    total_matches = len(matches)
    
    # 预计算：每场比赛需要哪些AI、prompt、intel
    match_tasks = []
    for i, match in enumerate(matches):
        match_id = match["id"]
        existing = get_existing_predictions(match_id)
        missing_ais = [ai for ai in AI_CALL_ORDER if ai not in existing]
        if not missing_ais:
            continue
        intel_data = get_intel(match_id)
        if sport == "basketball":
            prompt = build_basketball_prompt(match, intel_data)
        else:
            prompt = build_football_prompt(match, intel_data)
        match_tasks.append({
            "index": i, "match": match, "match_id": match_id,
            "home": match.get("home_team", "?"),
            "away": match.get("away_team", "?"),
            "missing_ais": set(missing_ais),
            "prompt": prompt, "intel_data": intel_data,
        })
    
    if not match_tasks:
        print("所有比赛已全部AI预测完成，无需补跑")
        return {"matches": 0, "predictions": 0, "errors": 0}
    
    print(f"待预测: {len(match_tasks)}场比赛 × {len(AI_CALL_ORDER)}个AI")
    
    # 按批次轮转：每个AI跑BATCH_SIZE场，换下一个AI
    total_predictions = 0
    total_errors = 0
    total_retries = 0
    log_entries = []
    
    # 将match_tasks分成批次
    num_batches = (len(match_tasks) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_idx in range(num_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, len(match_tasks))
        batch = match_tasks[batch_start:batch_end]
        batch_label = f"批次{batch_idx+1}/{num_batches}[场{batch_start+1}-{batch_end}]"
        
        for ai_name in AI_CALL_ORDER:
            # 检查本批次中哪些比赛还需要这个AI
            batch_need = [t for t in batch if ai_name in t["missing_ais"]]
            if not batch_need:
                continue
            
            ai_short = ai_name.replace("AI-", "", 1)
            print(f"\n--- {batch_label} | {ai_short} ---")
            
            for task in batch_need:
                match = task["match"]
                match_id = task["match_id"]
                home = task["home"]
                away = task["away"]
                prompt = task["prompt"]
                intel_data = task["intel_data"]
                
                start_time = datetime.now().strftime("%H:%M:%S")
                print(f"  [{task['index']+1}/{total_matches}] {home} vs {away} × {ai_short}...", end=" ", flush=True)
                
                result, retries, error = _call_ai_single(ai_name, match, sport, prompt, intel_data)
                total_retries += retries
                
                if result is not None:
                    success, summary = _process_and_store(ai_name, result, match, sport)
                    end_time = datetime.now().strftime("%H:%M:%S")
                    if success:
                        total_predictions += 1
                        retry_info = f" (重试{retries}次)" if retries > 0 else ""
                        print(f"OK -> {summary}{retry_info} [{start_time}→{end_time}]")
                        log_entries.append({
                            "match_id": match_id, "ai": ai_short,
                            "status": "ok", "retries": retries,
                            "start": start_time, "end": end_time,
                            "result": summary,
                        })
                        # 标记该AI已完成此场
                        task["missing_ais"].discard(ai_name)
                    else:
                        total_errors += 1
                        print(f"解析失败: {summary} [{start_time}→{datetime.now().strftime('%H:%M:%S')}]")
                        log_entries.append({
                            "match_id": match_id, "ai": ai_short,
                            "status": "parse_error", "retries": retries,
                            "start": start_time, "end": datetime.now().strftime("%H:%M:%S"),
                            "error": summary,
                        })
                else:
                    total_errors += 1
                    end_time = datetime.now().strftime("%H:%M:%S")
                    print(f"失败({retries+1}次尝试): {error} [{start_time}→{end_time}]")
                    log_entries.append({
                        "match_id": match_id, "ai": ai_short,
                        "status": "error", "retries": retries + 1,
                        "start": start_time, "end": end_time,
                        "error": error,
                    })
                
                # AI调用间隔
                time.sleep(AI_CALL_INTERVAL)
    
    # 汇总
    result = {
        "sport": sport,
        "predictions_created": total_predictions,
        "errors": total_errors,
        "total_retries": total_retries,
        "log": log_entries,
    }
    
    print(f"\n{'='*50}")
    print(f"Phase 2 完成")
    print(f"预测成功: {total_predictions}, 失败: {total_errors}, 重试总次数: {total_retries}")
    print(f"{'='*50}")
    
    return result


# ============ Phase 3: 质量检查与补预测 ============

def check_prediction_completeness(match_id, sport="football"):
    """检查单场比赛的预测完整性
    
    Returns:
        dict: {ai_name: {"complete": bool, "missing_fields": list}}
    """
    rows = execute_query("""
        SELECT ai_name, prediction
        FROM predictions
        WHERE match_id = %s
    """, (match_id,), fetch=True) or []
    
    # 定义关键字段
    if sport == "basketball":
        key_fields = ["win_loss", "handicap_win_loss", "total_points", "score_diff_range"]
    else:
        key_fields = ["spf", "handicap_spf", "score", "goals", "half_full"]
    
    result = {}
    existing_ais = set()
    
    for row in rows:
        ai_name = row.get("ai_name")
        prediction = row.get("prediction") or {}
        existing_ais.add(ai_name)
        missing = []
        
        for field in key_fields:
            val = prediction.get(field)
            if val is None or val == "" or val == []:
                missing.append(field)
        
        result[ai_name] = {
            "complete": len(missing) == 0,
            "missing_fields": missing,
        }
    
    # 检查缺失的AI（数据库存的是短名如"DeepSeek"，AI_CALL_ORDER是"AI-DeepSeek"）
    for ai in AI_CALL_ORDER:
        ai_short = ai.replace("AI-", "", 1) if ai.startswith("AI-") else ai
        if ai_short not in existing_ais and ai not in existing_ais:
            result[ai] = {
                "complete": False,
                "missing_fields": ["ALL"],
            }
    
    return result


def phase3_quality_check(sport="football", max_retries=1):
    """Phase 3: 质量检查与补预测（使用与Phase 2相同的重试+日志逻辑）"""
    BATCH_SIZE = 5
    
    print(f"\n{'='*50}")
    print(f"Phase 3: 质量检查与补预测 ({sport})")
    print(f"{'='*50}")
    
    # 获取今天及最近7天的比赛
    rows = execute_query("""
        SELECT m.id, m.home_team, m.away_team, m.sport_type, m.metadata,
               CASE WHEN (m.metadata->>'match_time')::date = CURRENT_DATE THEN 1 ELSE 0 END as is_today
        FROM matches m
        WHERE m.sport_type = %s
          AND m.id NOT LIKE 'CT%%'
          AND (m.metadata->>'match_time')::timestamp >= NOW() - INTERVAL '7 days'
        ORDER BY is_today DESC, (m.metadata->>'match_time')::timestamp DESC
    """, (sport,), fetch=True) or []
    
    matches = [{"id": row["id"], "home_team": row["home_team"], "away_team": row["away_team"],
                "metadata": row.get("metadata", {}), "sport_type": row.get("sport_type", sport)} 
               for row in rows]
    
    if not matches:
        print(f"没有需要检查的比赛")
        return {"matches_checked": 0, "retries": 0, "still_missing": 0}
    
    today_count = sum(1 for r in rows if r.get("is_today") == 1)
    print(f"检查范围: {len(matches)}场比赛 (今天{today_count}场)")
    
    # 扫描所有需要补预测的 (match, ai) 组合
    tasks = []
    for i, match in enumerate(matches):
        completeness = check_prediction_completeness(match["id"], sport)
        for ai_name, status in completeness.items():
            if not status["complete"]:
                full_ai = ai_name if ai_name.startswith("AI-") else f"AI-{ai_name}"
                tasks.append({
                    "index": i, "match": match, "match_id": match["id"],
                    "home": match.get("home_team", "?"),
                    "away": match.get("away_team", "?"),
                    "ai_name": full_ai,
                    "ai_short": ai_name.replace("AI-", "", 1) if ai_name.startswith("AI-") else ai_name,
                    "missing": status["missing_fields"],
                })
    
    if not tasks:
        print("所有比赛预测完整，无需补测")
        complete_count = len(matches)
        print(f"\n完整: {complete_count}场, 不完整: 0场")
        return {"matches_checked": len(matches), "today_matches": today_count,
                "retries": 0, "still_missing": 0, "complete": complete_count, "incomplete": 0}
    
    print(f"需补预测: {len(tasks)}条 (涉及{len(set(t['match_id'] for t in tasks))}场)")
    
    # 按批次轮转
    num_batches = (len(tasks) + BATCH_SIZE - 1) // BATCH_SIZE
    success_count = 0
    fail_count = 0
    total_retry_count = 0
    retry_log = []
    
    for batch_idx in range(num_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, len(tasks))
        batch = tasks[batch_start:batch_end]
        batch_label = f"补测{batch_idx+1}/{num_batches}[{batch_start+1}-{batch_end}]"
        
        for ai_name_full in AI_CALL_ORDER:
            batch_for_ai = [t for t in batch if t["ai_name"] == ai_name_full]
            if not batch_for_ai:
                continue
            
            ai_short = ai_name_full.replace("AI-", "", 1)
            print(f"\n--- {batch_label} | {ai_short} ---")
            
            for task in batch_for_ai:
                match = task["match"]
                match_id = task["match_id"]
                home = task["home"]
                away = task["away"]
                
                intel_data = get_intel(match_id)
                if sport == "basketball":
                    prompt = build_basketball_prompt(match, intel_data)
                else:
                    prompt = build_football_prompt(match, intel_data)
                
                start_time = datetime.now().strftime("%H:%M:%S")
                print(f"  [{task['index']+1}/{len(matches)}] {home} vs {away} × {ai_short} (缺:{','.join(task['missing'][:3])})...", end=" ", flush=True)
                
                result, retries, error = _call_ai_single(ai_name_full, match, sport, prompt, intel_data)
                total_retry_count += retries
                
                if result is not None:
                    ok, summary = _process_and_store(ai_name_full, result, match, sport)
                    end_time = datetime.now().strftime("%H:%M:%S")
                    if ok:
                        success_count += 1
                        retry_info = f" (重试{retries}次)" if retries > 0 else ""
                        print(f"OK -> {summary}{retry_info} [{start_time}→{end_time}]")
                        retry_log.append({"match_id": match_id, "ai_name": task["ai_short"],
                                          "status": "ok", "retries": retries,
                                          "start": start_time, "end": end_time})
                    else:
                        fail_count += 1
                        print(f"解析失败: {summary} [{start_time}→{datetime.now().strftime('%H:%M:%S')}]")
                        retry_log.append({"match_id": match_id, "ai_name": task["ai_short"],
                                          "status": "parse_error", "error": summary})
                else:
                    fail_count += 1
                    end_time = datetime.now().strftime("%H:%M:%S")
                    print(f"失败({retries+1}次尝试): {error} [{start_time}→{end_time}]")
                    retry_log.append({"match_id": match_id, "ai_name": task["ai_short"],
                                      "status": "error", "error": error, "retries": retries + 1})
                
                time.sleep(AI_CALL_INTERVAL)
    
    # 完整性摘要
    complete_count = 0
    incomplete_count = 0
    for match in matches:
        completeness = check_prediction_completeness(match["id"], sport)
        all_complete = all(status["complete"] for status in completeness.values())
        if all_complete:
            complete_count += 1
        else:
            incomplete_count += 1
    
    result = {
        "sport": sport,
        "matches_checked": len(matches),
        "today_matches": today_count,
        "retries": success_count,
        "still_missing": fail_count,
        "total_retries": total_retry_count,
        "complete": complete_count,
        "incomplete": incomplete_count,
        "retry_log": retry_log,
    }
    
    print(f"\n{'='*50}")
    print(f"Phase 3 完成")
    print(f"检查比赛: {len(matches)} (今天{today_count}场)")
    print(f"补预测成功: {success_count}, 失败: {fail_count}, 重试总次数: {total_retry_count}")
    print(f"完整预测: {complete_count}场, 不完整: {incomplete_count}场")
    
    if fail_count > 0 and retry_log:
        print(f"\n⚠️ 以下补预测失败，需人工检查:")
        for log in retry_log:
            if log.get("status") in ("error", "parse_error"):
                print(f"  - {log['match_id']} / {log['ai_name']}: {log['status']}")
    
    return result


# ============ 主入口 ============

def run_predict(sport="football", phase="all"):
    """主入口：三阶段预测
    
    Args:
        sport: football 或 basketball
        phase: "1"=只跑情报搜集, "2"=只跑预测, "3"=只跑质量检查, "all"=全部
    """
    start_time = time.time()
    
    print(f"\n{'#'*60}")
    print(f"# 三阶段AI预测系统")
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
    
    if phase in ("3", "all"):
        result["phase3"] = phase3_quality_check(sport)
    
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
        elif arg in ("1", "2", "3", "all"):
            phase = arg
        i += 1
    
    try:
        run_predict(sport, phase)
    except Exception as e:
        print(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
