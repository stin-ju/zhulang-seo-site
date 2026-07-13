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
import psycopg2
import requests
import math

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
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "model": "ernie-4.0-8k-latest",
        "format": "openai",
    },
    "AI-混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "model": "hy3-preview",
        "format": "openai",
    },
    "AI-扣子（皮皮）": {
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

## 请严格按以下JSON格式输出（不要输出其他内容）:
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

# ============ 数据库 ============

def get_db():
    if not DATABASE_URL:
        # 尝试从硬编码连接
        DATABASE_URL_FALLBACK = "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres"
        return psycopg2.connect(DATABASE_URL_FALLBACK)
    return psycopg2.connect(DATABASE_URL)


def get_pending_matches(conn, sport="football", include_settled=False):
    """获取待预测比赛（包含无赔率的pending比赛）。include_settled=True时包含已确认/已结算的比赛"""
    if sport == "basketball":
        if include_settled:
            status_filter = "m.status IN ('on_sale','未开赛','已确认','已结算')"
        else:
            status_filter = "m.status IN ('on_sale','未开赛')"
        query = f"""
            SELECT m.id, m.teams, m.match_time, m.handicap,
                   m.win_odds, m.lose_odds,
                   m.spread_line, m.total_line,
                   m.spread_odds, m.total_points_odds, m.score_diff_odds,
                   m.metadata->>'league' as league
            FROM matches m
            WHERE {status_filter}
            AND m.sport_type = 'basketball'
            ORDER BY m.match_time ASC
        """
    else:
        if include_settled:
            status_filter = "m.status IN ('on_sale','未开赛','已确认','已结算')"
        else:
            status_filter = "m.status IN ('on_sale','未开赛')"
        query = f"""
            SELECT m.id, m.teams, m.match_time, m.handicap,
                   m.win_odds, m.draw_odds, m.lose_odds,
                   m.handicap_win_odds, m.handicap_draw_odds, m.handicap_win_odds,
                   m.metadata->>'league' as league
            FROM matches m
            WHERE {status_filter}
            AND m.sport_type = 'football'
            ORDER BY m.match_time ASC
        """
    with conn.cursor() as cur:
        cur.execute(query)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_existing_predictions(conn, match_id):
    """获取某场比赛已有的AI预测，返回标准化后的AI名称集合"""
    with conn.cursor() as cur:
        cur.execute("SELECT ai_name FROM predictions WHERE match_id = %s", (match_id,))
        raw_names = {row[0] for row in cur.fetchall()}
        normalized = set()
        for name in raw_names:
            if name.startswith("AI-"):
                normalized.add(name)
            else:
                normalized.add(f"AI-{name}")
        return normalized


def insert_football_prediction(conn, pred):
    """插入足球预测"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO predictions (match_id, ai_name, spf, handicap_spf, score, goals, half_full, analysis, sport_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            pred["match_id"], pred["ai_name"], pred["spf"], pred["handicap_spf"],
            pred["score"], pred["goals"], pred["half_full"], pred["analysis"], "football"
        ))


def insert_basketball_prediction(conn, pred):
    """插入篮球预测"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO predictions (match_id, ai_name, win_loss, handicap_win_loss, 
                                     total_points, score_diff_range, half_win_loss, 
                                     analysis, sport_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            pred["match_id"], pred["ai_name"], pred["win_loss"], pred["handicap_win_loss"],
            pred["total_points"], pred["score_diff_range"], pred["half_win_loss"],
            pred["analysis"], "basketball"
        ))


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


def generate_template_prediction(prompt, sport="football"):
    """扣子(皮皮) - 基于规则的模板预测"""
    if sport == "basketball":
        return "根据赔率分析，篮球比赛综合考虑主队优势和赔率走势给出预测。"
    return "根据赔率分析，" + prompt.split("让球:")[-1].split("\n")[0] + "。综合考虑主队优势和赔率走势给出预测。"


def parse_ai_response(text, sport="football"):
    """从AI回复中提取JSON预测结果"""
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))
    
    if sport == "basketball":
        json_match = re.search(r'\{[^{}]*"win_loss"[^{}]*\}', text, re.DOTALL)
    else:
        json_match = re.search(r'\{[^{}]*"spf"[^{}]*\}', text, re.DOTALL)
    
    if json_match:
        return json.loads(json_match.group(0))
    
    print(f"  WARNING: 无法解析AI回复，使用默认值")
    if sport == "basketball":
        return {
            "win_loss": "胜",
            "handicap_win_loss": "让胜",
            "total_points": "大",
            "score_diff_range": "主6-10胜",
            "half_win_loss": "胜",
            "analysis": text[:200] if text else "解析失败",
        }
    return {
        "spf": "胜",
        "handicap_spf": "让胜",
        "score": "1-0",
        "goals": 1,
        "half_full": "胜胜",
        "analysis": text[:200] if text else "解析失败",
    }


def call_ai(ai_name, prompt, sport="football"):
    """调用指定AI生成预测"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        raise Exception(f"未知AI: {ai_name}")
    
    fmt = config["format"]
    
    if fmt == "template":
        analysis = generate_template_prediction(prompt, sport)
        return parse_ai_response(analysis, sport)
    
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
    teams = (match.get("teams") or "").split(" VS ")
    home_team = teams[0] if len(teams) > 0 else "主队"
    away_team = teams[1] if len(teams) > 1 else "客队"
    
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
        win_odds=fmt_odds(match.get("win_odds")),
        draw_odds=fmt_odds(match.get("draw_odds")),
        lose_odds=fmt_odds(match.get("lose_odds")),
        hw_odds=fmt_odds(match.get("handicap_win_odds")),
        hd_odds=fmt_odds(match.get("handicap_draw_odds")),
        hl_odds=fmt_odds(match.get("handicap_lose_odds")),
    )


def build_basketball_prompt(match):
    """构建篮球预测prompt"""
    teams_str = match.get("teams") or ""
    # 支持多种分隔符
    for sep in [" VS ", "VS", " vs ", "—"]:
        parts = teams_str.split(sep)
        if len(parts) == 2:
            home_team, away_team = parts[0].strip(), parts[1].strip()
            break
    else:
        home_team, away_team = "主队", "客队"
    
    # 解析让分赔率
    spread_odds = match.get("spread_odds") or {}
    if isinstance(spread_odds, str):
        try:
            spread_odds = json.loads(spread_odds)
        except:
            spread_odds = {}
    
    # 解析大小分赔率
    total_odds = match.get("total_points_odds") or {}
    if isinstance(total_odds, str):
        try:
            total_odds = json.loads(total_odds)
        except:
            # 可能是纯数字（线值），不是赔率
            total_odds = {}
    
    # 解析胜分差赔率
    sdr_odds = match.get("score_diff_odds") or {}
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
    conn = get_db()
    matches = get_pending_matches(conn, sport)
    
    if not matches:
        print(json.dumps({"message": f"没有待预测的{('篮球' if sport=='basketball' else '足球')}比赛", "matches": 0, "predictions": 0}))
        conn.close()
        return
    
    total_predictions = 0
    total_errors = 0
    total_corrections = 0
    match_results = []
    
    for match in matches:
        match_id = match["id"]
        existing = get_existing_predictions(conn, match_id)
        
        if sport == "basketball":
            prompt = build_basketball_prompt(match)
        else:
            prompt = build_football_prompt(match)
        
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
                        "ai_name": ai_name,
                        "win_loss": wl,
                        "handicap_win_loss": hwl,
                        "total_points": tp,
                        "score_diff_range": sdr,
                        "half_win_loss": hwl_half,
                        "analysis": analysis,
                    }
                    
                    insert_basketball_prediction(conn, pred)
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
                        "ai_name": ai_name,
                        "spf": spf,
                        "handicap_spf": handicap_spf,
                        "score": score,
                        "goals": goals,
                        "half_full": half_full,
                        "analysis": analysis,
                    }
                    
                    insert_football_prediction(conn, pred)
                    match_pred_count += 1
                    print(f"  OK: {match_id} {ai_name} -> {spf}/{handicap_spf}/{score}")
                
            except Exception as e:
                error_msg = f"{ai_name}: {str(e)[:100]}"
                match_errors.append(error_msg)
                print(f"  FAIL: {match_id} {ai_name} - {e}")
                total_errors += 1
            
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
