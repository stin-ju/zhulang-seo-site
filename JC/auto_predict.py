#!/usr/bin/env python3
"""
auto_predict.py - 7AI预测调度
为待预测比赛调用7个AI生成预测，写入predictions表。
每个AI独立调用，某个AI挂了不影响其他AI。
支持 --sport football|basketball 参数。
"""
import os
import sys
import json
import re
import time
import traceback
import requests
import math
from supabase_db import (
    get_matches_by_sport, get_existing_ai_names, upsert_prediction,
    get_predictions_count
)

# ============ 配置 ============

# 设置API Keys (从环境变量读取，实际值在 .env 文件中)
# os.environ.setdefault("DOUBAO_API_KEY", "...")
# os.environ.setdefault("WENXIN_API_KEY", "...")
# os.environ.setdefault("HUNYUAN_API_KEY", "...")
# os.environ.setdefault("DEEPSEEK_API_KEY", "...")
# os.environ.setdefault("ZHIPU_API_KEY", "...")
# os.environ.setdefault("MINIMAX_API_KEY", "...")
# os.environ.setdefault("DATABASE_URL", "...")

# 7个活跃AI及其API配置
AI_CONFIGS = {
    "AI-DeepSeek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "format": "openai",
        "fallback_models": ["deepseek-v4-pro", "deepseek-v3", "deepseek-chat"],
    },
    "AI-MiniMax": {
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model": "MiniMax-Text-01",
        "format": "minimax",
        "fallback_models": ["abab6.5s-chat", "abab6.5-chat", "MiniMax-Text-01"],
    },
    "AI-豆包": {
        "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "key_env": "DOUBAO_API_KEY",
        "model": "doubao-seed-2-0-mini-260428",
        "format": "openai",
        "fallback_models": [
            "doubao-seed-2-1-turbo-260628",
            "doubao-seed-2-0-mini-260215",
            "doubao-seed-2-0-pro-260215",
        ],
    },
    "AI-智谱清言": {
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "ZHIPU_API_KEY",
        "model": "glm-4-flash",
        "format": "openai",
        "fallback_models": ["glm-4-plus", "glm-4-air", "glm-4-flashx"],
    },
    "AI-文心": {
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "model": "ernie-4.0-8k-latest",
        "format": "openai",
        "fallback_models": ["ernie-4.0-turbo-8k", "ernie-3.5-8k", "ernie-speed-128k"],
    },
    "AI-混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "model": "hy3-preview",
        "format": "openai",
        "fallback_models": ["hy-mt2-lite"],
    },
    "AI-扣子": {
        "url": None,
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

注意：如果赔率显示"暂无"，请根据球队实力、历史交锋等因素进行预测，不要受赔率缺失影响。

## 历史赔率分析要求

在预测前，请先联网搜索历史数据：

1. 搜索当前比赛双方相同/相似赔率的历史场次（至少30场）
   - 数据源：oddsportal.com、betexplorer.com、flashscore.com
   - 重点关注主胜赔率±0.1区间的历史场次

2. 搜索当前大小球盘口的历史概率数据（至少50场）
   - 如2.5球盘口的历史大/小球概率

3. 搜索当前让球盘口的历史赢盘率（至少30场）
   - 如主让0.5的历史赢盘/输盘概率

4. 搜索相同半全场赔率结构的历史概率（如有）

5. 搜索相似比分赔率的历史数据（如有）

统计这些历史场次中各结果的实际出现概率。

## 历史数据应用规则

- 历史概率与赔率隐含概率一致时，按赔率预测
- 历史概率明显偏离赔率时（如历史主胜70%，赔率暗示50%），优先参考历史数据（说明有信息差）
- 在analysis字段中简要说明历史数据分析结论

## 请严格按以下JSON格式输出预测结果（不要输出其他内容）:
```json
{{
  "spf": "胜"或"平"或"负",
  "handicap_spf": "让胜"或"让平"或"让负",
  "score": "比分如2-1",
  "goals": 总进球数(整数),
  "half_full": "半全场如胜胜/平胜/负平",
  "analysis": "50-100字的分析理由，需包含历史赔率分析结论"
}}
```"""

BASKETBALL_PROMPT = """你是专业的篮球比赛预测分析师。一次性给出所有维度的预测，必须逻辑自洽。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让分: {spread_desc}（盘口{spread_line}，负数=主队让分，正数=客队让分）
- 总分线: {total_line}

## 赔率数据
- 胜负: 主胜{win_odds} / 客胜{lose_odds}
- 让分: 让胜(主队覆盖){spread_win_odds} / 让负(客队覆盖){spread_lose_odds}
- 大小分: 大{total_over_odds} / 小{total_under_odds}（盘口{total_line}）
- 胜分差赔率（不分主客，分差区间统一）:
  1-5分: {sdr_1_5} | 6-10分: {sdr_6_10} | 11-15分: {sdr_11_15} | 16-20分: {sdr_16_20} | 21-25分: {sdr_21_25} | 26+分: {sdr_26}

注意：如果赔率显示"暂无"，请根据球队实力、近期状态等因素进行预测，不要受赔率缺失影响。

## 历史赔率分析要求

在预测前，请先联网搜索历史数据：

1. 搜索当前比赛双方相同/相似赔率的历史场次（至少30场）
   - 数据源：oddsportal.com、betexplorer.com、flashscore.com
   - 重点关注主胜赔率±0.1区间的历史场次

2. 搜索当前让分盘口的历史赢盘率（至少30场）
   - 如主队让5.5分的历史赢盘/输盘概率

3. 搜索当前大小分盘口的历史概率数据（至少50场）
   - 如总分210.5的历史大/小概率

4. 搜索相同胜分差赔率结构的历史概率（如有）

统计这些历史场次中各结果的实际出现概率。

## 历史数据应用规则

- 历史概率与赔率隐含概率一致时，按赔率预测
- 历史概率明显偏离赔率时（如历史主胜70%，赔率暗示50%），优先参考历史数据（说明有信息差）
- 在analysis字段中简要说明历史数据分析结论

## 请严格按以下JSON格式输出（不要输出其他内容）:
```json
{{
  "win_loss": "胜"或"负",
  "handicap_win_loss": "让胜"或"让负",
  "total_points": "大"或"小",
  "score_diff_range": "如主6-10胜或客1-5负",
  "half_win_loss": "胜"或"负",
  "analysis": "50-100字分析理由，需包含历史赔率分析结论"
}}
```

## ⚠️ 逻辑自洽规则（违反等于预测无效）:
1. **让分↔胜分差（最重要）**：
   - 让分盘口={spread_line}（{spread_desc}）
   - 选"让胜"=看好主队赢超过盘口绝对值。如盘口-5.5选让胜→主队至少赢6分→胜分差只能选"主6-10胜""主11-15胜""主16-20胜""主21+胜"之一
   - 选"让负"=看好客队覆盖。如盘口-5.5选让负→客队赢或主队赢不到6分→胜分差应选"客x负"或"主1-5胜"
2. **让分↔胜负**：选"让胜"→胜负应选"胜"；大让分盘口选"让负"→胜负倾向"负"
3. **胜分差↔大小分**：大胜分差（11+）→总分倾向"大"；小胜分差（1-5）→总分倾向看情况

## 胜分差格式:
- "主x-y胜"=主队赢x到y分，"客x-y负"=客队赢x到y分
- 可选值: 主1-5胜/主6-10胜/主11-15胜/主16-20胜/主21+胜/客1-5负/客6-10负/客11-15负/客16-20负/客21+负"""

# ============ 数据库（Supabase） ============

def get_pending_matches(sport="football", include_settled=False):
    """获取待预测比赛（新schema适配）"""
    from supabase_db import get_matches_by_sport
    # 获取在售和待处理的比赛
    return get_matches_by_sport(sport, statuses=["on_sale", "pending"])


def get_existing_predictions(match_id):
    """获取某场比赛已有的AI预测，返回标准化后的AI名称集合"""
    return get_existing_ai_names(match_id)


def insert_football_prediction(pred):
    """插入足球预测"""
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


def insert_basketball_prediction(pred):
    """插入篮球预测"""
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
        "prediction": prediction_json,
        "analysis": pred.get("analysis", ""),
        "sport_type": "basketball"
    })


# ============ AI API调用 ============

def call_openai_compatible(url, key, model, prompt, timeout=60):
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
    """文心一言 - v2 OpenAI兼容格式"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
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


def extract_odds_from_prompt(prompt, sport="football"):
    """从prompt中提取赔率数据，返回结构化字典。如果没有赔率数据，使用基于prompt哈希的随机值。"""
    import re
    import hashlib
    result = {}
    
    # 使用prompt的哈希作为随机种子，确保同一场比赛总是得到相同的"随机"值
    prompt_hash = int(hashlib.md5(prompt.encode()).hexdigest(), 16)
    
    def hash_random(min_val, max_val, offset=0):
        """基于哈希生成min_val到max_val之间的伪随机值"""
        return min_val + ((prompt_hash + offset) % 1000) / 1000 * (max_val - min_val)
    
    if sport == "basketball":
        # 篮球prompt格式:
        # - 让分盘口: -5.5分 (主队让5.5分)
        # - 总分盘口: 165.5分
        # - 胜负赔率: 主胜1.65 / 客胜2.25
        # - 让分赔率: 让胜1.90 / 让负1.90
        # - 大小分赔率: 大1.90 / 小1.90
        
        # 提取让分盘口
        spread_match = re.search(r'让分盘口[:：]\s*([+-]?\d+\.?\d*)', prompt)
        result['spread_line'] = float(spread_match.group(1)) if spread_match else 0
        
        # 提取总分盘口
        total_match = re.search(r'总分盘口[:：]\s*(\d+\.?\d*)', prompt)
        result['total_line'] = float(total_match.group(1)) if total_match else 165.5
        
        # 提取胜负赔率 (主胜/客胜)
        ml_match = re.search(r'胜负赔率[:：].*?主胜(\d+\.?\d*)\s*[\/\\]\s*客胜(\d+\.?\d*)', prompt)
        if ml_match:
            result['home_ml'] = float(ml_match.group(1))
            result['away_ml'] = float(ml_match.group(2))
        else:
            result['home_ml'] = 1.80
            result['away_ml'] = 2.00
        
        # 提取让分赔率
        spread_odds_match = re.search(r'让分赔率[:：].*?让胜(\d+\.?\d*)\s*[\/\\]\s*让负(\d+\.?\d*)', prompt)
        if spread_odds_match:
            result['spread_win_odds'] = float(spread_odds_match.group(1))
            result['spread_lose_odds'] = float(spread_odds_match.group(2))
        else:
            result['spread_win_odds'] = 1.90
            result['spread_lose_odds'] = 1.90
        
        # 提取大小分赔率
        total_odds_match = re.search(r'大小分赔率[:：].*?大(\d+\.?\d*)\s*[\/\\]\s*小(\d+\.?\d*)', prompt)
        if total_odds_match:
            result['over_odds'] = float(total_odds_match.group(1))
            result['under_odds'] = float(total_odds_match.group(2))
        else:
            result['over_odds'] = 1.90
            result['under_odds'] = 1.90
    
    else:  # football
        # 足球prompt格式:
        # - 让球: 0.5
        # - 胜平负赔率: 胜2.10 / 平3.20 / 负3.50
        # - 让球赔率: 让胜1.85 / 让平3.40 / 让负4.20
        
        # 提取让球
        handicap_match = re.search(r'让球[:：]\s*([+-]?\d+\.?\d*)', prompt)
        result['handicap'] = float(handicap_match.group(1)) if handicap_match else 0
        
        # 提取胜平负赔率
        spf_match = re.search(r'胜平负赔率[:：].*?胜(\d+\.?\d*)\s*[\/\\]\s*平(\d+\.?\d*)\s*[\/\\]\s*负(\d+\.?\d*)', prompt)
        if spf_match:
            result['win_odds'] = float(spf_match.group(1))
            result['draw_odds'] = float(spf_match.group(2))
            result['lose_odds'] = float(spf_match.group(3))
        else:
            result['win_odds'] = 2.10
            result['draw_odds'] = 3.20
            result['lose_odds'] = 3.50
        
        # 提取让球赔率
        hspf_match = re.search(r'让球赔率[:：].*?让胜(\d+\.?\d*)\s*[\/\\]\s*让平(\d+\.?\d*)\s*[\/\\]\s*让负(\d+\.?\d*)', prompt)
        if hspf_match:
            result['hw_odds'] = float(hspf_match.group(1))
            result['hd_odds'] = float(hspf_match.group(2))
            result['hl_odds'] = float(hspf_match.group(3))
        else:
            result['hw_odds'] = 1.85
            result['hd_odds'] = 3.40
            result['hl_odds'] = 4.20
    
    return result


def generate_template_prediction(prompt, sport="football"):
    """扣子 - 基于赔率数据的规则预测"""
    odds = extract_odds_from_prompt(prompt, sport)
    
    if sport == "basketball":
        home_ml = odds.get('home_ml', 1.80)
        away_ml = odds.get('away_ml', 2.00)
        spread_line = odds.get('spread_line', 0)
        total_line = odds.get('total_line', 165.5)
        over_odds = odds.get('over_odds', 1.90)
        under_odds = odds.get('under_odds', 1.90)
        spread_win_odds = odds.get('spread_win_odds', 1.90)
        spread_lose_odds = odds.get('spread_lose_odds', 1.90)
        
        # 胜负：赔率低的一方更可能赢
        win_loss = "胜" if home_ml < away_ml else "负"
        
        # 让球：根据让分盘口和赔率判断
        # spread_line < 0 表示主队让分，> 0 表示客队让分
        if spread_line < 0:  # 主队让分
            handicap_win_loss = "让胜" if spread_win_odds <= spread_lose_odds else "让负"
        else:  # 客队让分
            handicap_win_loss = "让负" if spread_lose_odds <= spread_win_odds else "让胜"
        
        # 大小分：赔率低的一方更可能
        total_points = "大" if over_odds < under_odds else "小"
        
        # 胜分差：根据胜负预测和让分盘口生成合理范围
        if win_loss == "胜":
            if spread_line < -10:
                score_diff_range = "主11-15胜"
            elif spread_line < -5:
                score_diff_range = "主6-10胜"
            else:
                score_diff_range = "主1-5胜"
        else:
            if spread_line > 10:
                score_diff_range = "主11-15负"
            elif spread_line > 5:
                score_diff_range = "主6-10负"
            else:
                score_diff_range = "主1-5负"
        
        # 半场胜负：根据全场结果推导，强队半场领先概率高
        half_win_loss = win_loss
        
        return {
            "win_loss": win_loss,
            "handicap_win_loss": handicap_win_loss,
            "total_points": total_points,
            "score_diff_range": score_diff_range,
            "half_win_loss": half_win_loss,
            "analysis": f"基于赔率分析：主胜{home_ml}/客胜{away_ml}，让分{spread_line}，大小分线{total_line}。"
        }
    
    # 足球预测
    handicap = odds.get('handicap', 0)
    win_odds = odds.get('win_odds', 2.10)
    draw_odds = odds.get('draw_odds', 3.20)
    lose_odds = odds.get('lose_odds', 3.50)
    hw_odds = odds.get('hw_odds', 1.85)
    hd_odds = odds.get('hd_odds', 3.40)
    hl_odds = odds.get('hl_odds', 4.20)
    
    # 胜平负：赔率最低的结果最可能
    min_odds = min(win_odds, draw_odds, lose_odds)
    if min_odds == win_odds:
        spf = "胜"
    elif min_odds == lose_odds:
        spf = "负"
    else:
        spf = "平"
    
    # 让球胜平负：根据让球赔率判断
    min_h_odds = min(hw_odds, hd_odds, hl_odds)
    if min_h_odds == hw_odds:
        handicap_spf = "让胜"
    elif min_h_odds == hl_odds:
        handicap_spf = "让负"
    else:
        handicap_spf = "让平"
    
    # 比分：根据胜平负结果推导
    if spf == "胜":
        score = "1-0" if handicap >= 0 else "2-1"
    elif spf == "负":
        score = "0-1" if handicap <= 0 else "1-2"
    else:
        score = "1-1"
    
    # 进球数：根据比分推导
    goals = str(sum(int(x) for x in score.split('-')))
    
    # 半全场：根据全场结果推导
    if spf == "胜":
        half_full = "胜-胜"
    elif spf == "负":
        half_full = "负-负"
    else:
        half_full = "平-平"
    
    return {
        "spf": spf,
        "handicap_spf": handicap_spf,
        "score": score,
        "goals": goals,
        "half_full": half_full,
        "analysis": f"基于赔率分析：胜{win_odds}/平{draw_odds}/负{lose_odds}，让球{handicap}。"
    }


def parse_ai_response(text, sport="football"):
    """从AI回复中提取JSON预测结果"""
    # 方法1: 提取```json代码块
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 方法2: 尝试提取所有JSON对象（处理嵌套花括号）
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_matches = re.findall(json_pattern, text, re.DOTALL)
    
    for match in json_matches:
        try:
            data = json.loads(match)
            # 检查是否是有效的预测结果
            if sport == "basketball" and "win_loss" in data:
                return data
            elif sport == "football" and "spf" in data:
                return data
        except json.JSONDecodeError:
            continue
    
    # 方法3: 宽松匹配，提取包含关键字段的JSON
    if sport == "basketball":
        json_match = re.search(r'\{[^}]*"win_loss"[^}]*\}', text, re.DOTALL)
    else:
        json_match = re.search(r'\{[^}]*"spf"[^}]*\}', text, re.DOTALL)
    
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    print(f"  WARNING: 无法解析AI回复，使用赔率分析")
    # 使用赔率分析生成预测，而不是硬编码默认值
    return generate_template_prediction(text, sport)


def call_ai(ai_name, prompt, sport="football"):
    """调用指定AI生成预测，支持fallback模型自动降级"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        raise Exception(f"未知AI: {ai_name}")
    
    fmt = config["format"]
    
    if fmt == "template":
        # generate_template_prediction 直接返回 dict，无需解析
        return generate_template_prediction(prompt, sport)
    
    key = os.environ.get(config["key_env"], "")
    if not key:
        raise Exception(f"{ai_name} 的API Key未配置 ({config['key_env']})")
    
    # 限流/额度相关错误关键词
    rate_limit_keywords = [
        "Arrearage", "Overdue", "quota", "QuotaExceeded", "insufficient",
        "SetLimitExceeded", "LimitExceeded", "ServerOverloaded", 
        "RequestBurstTooFast", "RateLimitExceeded", "TooManyRequests", "429",
        "402", "balance", "Payment Required", "quota exceeded", "no quota",
    ]
    
    # 构建模型列表（主模型 + fallback模型）
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
            elif fmt == "wenxin":
                raw = call_wenxin(config["url"], key, model, prompt)
            else:
                raise Exception(f"未知格式: {fmt}")
            
            if i > 0:
                print(f"  [fallback] {ai_name} 主模型额度耗尽/限流，自动切换到 {model}")
            return parse_ai_response(raw, sport)
            
        except Exception as e:
            error_str = str(e)
            # 检查是否是限流错误
            is_rate_limit = any(kw in error_str for kw in rate_limit_keywords)
            
            if is_rate_limit and i < len(models_to_try) - 1:
                print(f"  [fallback] {ai_name} 模型 {model} 额度耗尽或限流，尝试备用模型...")
                last_error = e
                continue
            else:
                # 非限流错误或已是最后一个模型，直接抛出
                raise e
    
    if last_error:
        raise last_error
    
    return parse_ai_response(raw, sport)


# ============ 逻辑校验 ============

def validate_basketball_consistency(pred, spread_line):
    """校验篮球预测的逻辑一致性，返回修正后的预测。
    spread_line规则：负数=主队让分，正数=客队让分。
    让胜=主队覆盖，让负=客队覆盖。
    """
    try:
        spread = float(spread_line) if spread_line else 0
    except (ValueError, TypeError):
        spread = 0
    
    hw = pred.get("handicap_win_loss", "让胜")
    sdr = pred.get("score_diff_range", "")
    wl = pred.get("win_loss", "胜")
    
    # 解析胜分差
    sdr_match = re.match(r'(主|客)(\d+)[-](\d+)(胜|负)', sdr)
    if not sdr_match:
        sdr_match2 = re.match(r'(主|客)(\d+)\+(胜|负)', sdr)
        if sdr_match2:
            team = sdr_match2.group(1)
            low = int(sdr_match2.group(2))
            high = 99
            direction = sdr_match2.group(3)
        else:
            return pred
    else:
        team = sdr_match.group(1)
        low = int(sdr_match.group(2))
        high = int(sdr_match.group(3))
        direction = sdr_match.group(4)
    
    abs_spread = abs(spread)
    min_cover = math.floor(abs_spread) + 1  # 覆盖所需最小净胜分
    
    corrected = dict(pred)
    fix_reason = ""
    
    # 确定让胜/让负的含义
    if spread < 0:
        # 主队让分：让胜=主队赢min_cover+分
        home_covers_margin = min_cover
    else:
        # 客队让分：让胜=主队赢或输不到min_cover分
        home_covers_margin = min_cover
    
    if hw == "让胜":
        if spread < 0:
            # 主队让分，让胜=主队赢超过|让分值|
            if team == "客":
                fix_reason = f"让胜(主让{abs_spread})但胜分差={sdr}(客赢)"
                if home_covers_margin <= 5:
                    corrected["score_diff_range"] = "主6-10胜"
                elif home_covers_margin <= 10:
                    corrected["score_diff_range"] = "主11-15胜"
                elif home_covers_margin <= 15:
                    corrected["score_diff_range"] = "主16-20胜"
                else:
                    corrected["score_diff_range"] = "主21+胜"
            elif team == "主" and high < min_cover:
                fix_reason = f"让胜(需赢{min_cover}+)但胜分差={sdr}(最多赢{high})"
                if min_cover <= 5:
                    corrected["score_diff_range"] = "主6-10胜"
                elif min_cover <= 10:
                    corrected["score_diff_range"] = "主11-15胜"
                elif min_cover <= 15:
                    corrected["score_diff_range"] = "主16-20胜"
                else:
                    corrected["score_diff_range"] = "主21+胜"
        else:
            # 客队让分，让胜=主队赢或输不到|让分值|
            if team == "客" and low >= min_cover:
                fix_reason = f"让胜(客让{abs_spread},主不能输{min_cover}+)但胜分差={sdr}(客赢{low}+)"
                corrected["score_diff_range"] = "客1-5负" if min_cover > 5 else "主1-5胜"
    
    elif hw == "让负":
        if spread < 0:
            # 主队让分，让负=客队覆盖（客赢或主赢不到|让分值|）
            if team == "主" and low >= min_cover:
                fix_reason = f"让负(主让{abs_spread},主不能赢{min_cover}+)但胜分差={sdr}(主赢{low}+)"
                corrected["score_diff_range"] = "主1-5胜"
        else:
            # 客队让分，让负=客队赢超过|让分值|
            if team == "主":
                fix_reason = f"让负(客让{abs_spread})但胜分差={sdr}(主赢)"
                corrected["score_diff_range"] = "客6-10负" if min_cover <= 5 else "客11-15负"
            elif team == "客" and high < min_cover:
                fix_reason = f"让负(客需赢{min_cover}+)但胜分差={sdr}(最多赢{high})"
                if min_cover <= 5:
                    corrected["score_diff_range"] = "客6-10负"
                elif min_cover <= 10:
                    corrected["score_diff_range"] = "客11-15负"
                else:
                    corrected["score_diff_range"] = "客16-20负"
    
    # 让分↔胜负一致性
    if hw == "让胜" and wl == "负":
        if spread < 0:
            # 主队让分选让胜，但选客队赢？矛盾
            corrected["win_loss"] = "胜"
            fix_reason += "；让胜→胜负修正为胜"
    elif hw == "让负" and wl == "胜":
        if spread < 0 and abs_spread >= 8:
            # 大让分选让负，但选主队赢？矛盾
            corrected["win_loss"] = "负"
            fix_reason += "；大让分让负→胜负修正为负"
    
    if fix_reason:
        print(f"  校验修正: {fix_reason}")
    
    return corrected

# ============ Prompt构建 ============

def build_football_prompt(match):
    """构建足球预测prompt"""
    # 从新结构读取数据
    home_team = match.get("home_team") or "主队"
    away_team = match.get("away_team") or "客队"
    odds = match.get("odds") or {}
    spf_odds = odds.get("spf") or {}
    handicap_spf_odds = odds.get("handicap_spf") or {}
    
    # 处理赔率：无赔率时显示"暂无"
    def fmt_odds(val):
        if val is None or val == 0 or val == "":
            return "暂无"
        return str(val)
    
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
    )


def build_basketball_prompt(match):
    """构建篮球预测prompt"""
    # 从新结构读取数据
    home_team = match.get("home_team") or "主队"
    away_team = match.get("away_team") or "客队"
    odds = match.get("odds") or {}
    
    # 解析让分赔率
    spread_odds = odds.get("spread") or {}
    if isinstance(spread_odds, str):
        try:
            spread_odds = json.loads(spread_odds)
        except:
            spread_odds = {}
    
    # 解析大小分赔率
    total_odds = odds.get("total_points") or {}
    if isinstance(total_odds, str):
        try:
            total_odds = json.loads(total_odds)
        except:
            # 可能是纯数字（线值），不是赔率
            total_odds = {}
    
    # 解析胜分差赔率
    sdr_odds = odds.get("score_diff") or {}
    if isinstance(sdr_odds, str):
        try:
            sdr_odds = json.loads(sdr_odds)
        except:
            sdr_odds = {}
    
    # 让分线值（负数=主队让分，正数=客队让分）
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
    
    # 让分赔率映射（支持 home/away 和 胜/负 key）
    spread_win = spread_odds.get("home", spread_odds.get("胜", spread_odds.get("win", "-")))
    spread_lose = spread_odds.get("away", spread_odds.get("负", spread_odds.get("lose", "-")))
    
    # 大小分赔率映射
    total_over = total_odds.get("over", total_odds.get("大", "-"))
    total_under = total_odds.get("under", total_odds.get("小", "-"))
    
    # 胜分差赔率映射（支持两种格式）
    # 格式1: l1-l6（无方向）
    # 格式2: 主胜_1~主胜_6 + 主负_1~主负_6（有方向）
    sdr_ranges = ["1-5", "6-10", "11-15", "16-20", "21-25", "26+"]
    sdr_vals = {}
    for i, rng in enumerate(sdr_ranges):
        idx = str(i + 1)
        # 尝试 l1-l6 格式
        val = sdr_odds.get(f"l{idx}", None)
        if val is None:
            # 尝试 主胜_1 / 主负_1 格式（取两者中赔率更低的 = 更可能的方向）
            home_val = sdr_odds.get(f"主胜_{idx}", None)
            away_val = sdr_odds.get(f"主负_{idx}", None)
            if home_val is not None and away_val is not None:
                val = min(home_val, away_val)  # 取概率更高的
            elif home_val is not None:
                val = home_val
            elif away_val is not None:
                val = away_val
        sdr_vals[rng] = val if val is not None else "-"
    
    # 让分描述
    if spread_line < 0:
        spread_desc = f"主队让{-spread_line}分"
    elif spread_line > 0:
        spread_desc = f"客队让{spread_line}分"
    else:
        spread_desc = "平手盘"
    
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
        total_under_odds=total_under,
        sdr_1_5=sdr_vals["1-5"],
        sdr_6_10=sdr_vals["6-10"],
        sdr_11_15=sdr_vals["11-15"],
        sdr_16_20=sdr_vals["16-20"],
        sdr_21_25=sdr_vals["21-25"],
        sdr_26=sdr_vals["26+"],
    )
def run_predict(sport="football"):
    """主入口：为所有待预测比赛生成AI预测"""
    matches = get_pending_matches(sport)
    
    if not matches:
        print(json.dumps({"message": f"没有待预测的{('篮球' if sport=='basketball' else '足球')}比赛", "matches": 0, "predictions": 0}))
        return
    
    total_predictions = 0
    total_errors = 0
    total_corrections = 0
    match_results = []
    
    for match in matches:
        match_id = match["id"]
        existing = get_existing_predictions(match_id)
        
        if sport == "basketball":
            prompt = build_basketball_prompt(match)
        else:
            prompt = build_football_prompt(match)
        
        # get_existing_ai_names 现在返回带 "AI-" 前缀的名称，与 AI_CONFIGS 的 key 格式一致
        missing_ais = [ai for ai in AI_CONFIGS if ai not in existing]
        if not missing_ais:
            continue
        
        match_pred_count = 0
        match_errors = []
        
        for ai_name in missing_ais:
            try:
                result = call_ai(ai_name, prompt, sport)
                
                if sport == "basketball":
                    # 校验逻辑一致性
                    spread_line = match.get("spread_line") or match.get("handicap") or 0
                    result = validate_basketball_consistency(result, spread_line)
                    
                    # 验证字段
                    wl = result.get("win_loss", "胜")
                    if wl not in ("胜", "负"):
                        wl = "胜"
                    
                    hwl = result.get("handicap_win_loss", "让胜")
                    if hwl not in ("让胜", "让负"):
                        hwl = "让胜"
                    
                    tp = result.get("total_points", "大")
                    if tp not in ("大", "小"):
                        tp = "大"
                    
                    sdr = result.get("score_diff_range", "主6-10胜")
                    # 验证胜分差格式
                    sdr_valid = re.match(r'^(主|客)\d+[-+]\d*(胜|负)$', sdr)
                    if not sdr_valid:
                        sdr = "主6-10胜"
                    
                    hwl_half = result.get("half_win_loss", "胜")
                    if hwl_half not in ("胜", "负"):
                        hwl_half = "胜"
                    
                    analysis = result.get("analysis", "")[:500]
                    
                    pred = {
                        "match_id": match_id,
                        "match_uid": match.get("match_uid", match_id),
                        "ai_name": ai_name.replace("AI-", "", 1) if ai_name.startswith("AI-") else ai_name,
                        "win_loss": wl,
                        "handicap_win_loss": hwl,
                        "total_points": tp,
                        "score_diff_range": sdr,
                        "half_win_loss": hwl_half,
                        "analysis": analysis,
                    }
                    
                    insert_basketball_prediction(pred)
                    match_pred_count += 1
                    print(f"  OK: {match_id} {ai_name} -> {wl}/{hwl}/{tp}/{sdr}")
                    
                else:
                    # 足球处理（原逻辑）
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
                        "match_uid": match.get("match_uid", match_id),
                        "ai_name": ai_name.replace("AI-", "", 1) if ai_name.startswith("AI-") else ai_name,
                        "spf": spf,
                        "handicap_spf": handicap_spf,
                        "score": score,
                        "goals": goals,
                        "half_full": half_full,
                        "analysis": analysis,
                    }
                    
                    insert_football_prediction(pred)
                    match_pred_count += 1
                    print(f"  OK: {match_id} {ai_name} -> {spf}/{handicap_spf}/{score}")
                
            except Exception as e:
                error_msg = f"{ai_name}: {str(e)[:100]}"
                match_errors.append(error_msg)
                print(f"  FAIL: {match_id} {ai_name} - {e}")
                total_errors += 1
            
            time.sleep(1)
        
        total_predictions += match_pred_count
        match_results.append({
            "match_id": match_id,
            "predicted": match_pred_count,
            "errors": len(match_errors),
        })
    
    result = {
        "sport": sport,
        "matches_processed": len(match_results),
        "predictions_created": total_predictions,
        "errors": total_errors,
        "details": match_results,
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    sport = "football"
    if len(sys.argv) > 1:
        if sys.argv[1] in ("football", "basketball"):
            sport = sys.argv[1]
        elif sys.argv[1] == "--sport" and len(sys.argv) > 2:
            sport = sys.argv[2]
    
    try:
        run_predict(sport)
    except Exception as e:
        print(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
