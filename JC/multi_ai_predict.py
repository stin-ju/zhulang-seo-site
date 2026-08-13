#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""
多AI预测生成脚本
调用6个AI API为指定比赛生成预测，写入predictions表。

AI列表: DeepSeek, MiniMax, 文心, 智谱清言, 混元, 豆包, 扣子
足球5维度: spf/handicap_spf/goals/score/half_full
篮球4维度: win_loss/handicap_result/total_points/score_diff

用法:
  python multi_ai_predict.py [result_mode] [match_ids] [db_url]
  result_mode: display_only | auto (默认 display_only)
  match_ids: 逗号分隔的比赛ID列表（为空则自动查on_sale比赛）
  db_url: 数据库连接串
"""
import asyncio
import sys
import time
import os
import json
import re
import psycopg2
import aiohttp
from datetime import datetime
from codeact_sdk import CodeActSDK

# ============================================================
# 参数区
# ============================================================
RESULT_MODE = sys.argv[1] if len(sys.argv) > 1 else "display_only"
MATCH_IDS_ARG = sys.argv[2] if len(sys.argv) > 2 else ""
DB_URL = sys.argv[3] if len(sys.argv) > 3 else os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres"
)

# ============================================================
# AI API 配置
# ============================================================
AI_CONFIGS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "REMOVED"),
        "model": "deepseek-chat",
        "max_tokens": 800,
    },
    "MiniMax": {
        "base_url": "https://api.minimaxi.com/v1/chat/completions",
        "api_key": os.environ.get("MINIMAX_API_KEY", "sk-api-taOJjMl9mnCFBuHWKkQ0_2mDhJpDV_ecQ4S6VEQvuBO180a10T7jIUDLxwsQUfHy4fpGy5Mk18sOVhWRyJBVGhfCsNXiwjAbFGgKIo_7oxFzzn1YoARPcHI"),
        "model": "MiniMax-Text-01",
        "max_tokens": 800,
    },
    "文心": {
        "base_url": "https://qianfan.baidubce.com/v2/chat/completions",
        "api_key": os.environ.get("WENXIN_API_KEY", "REMOVED"),
        "model": "ernie-4.0-8k-latest",
        "max_tokens": 800,
    },
    "智谱清言": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_key": os.environ.get("ZHIPU_API_KEY", "REMOVED"),
        "model": "glm-4-flash",
        "max_tokens": 800,
    },
    "混元": {
        "base_url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "api_key": os.environ.get("HUNYUAN_API_KEY", "REMOVED"),
        "model": "hy-mt2-lite",
        "max_tokens": 800,
    },
    "豆包": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key": os.environ.get("DOUBAO_API_KEY", "ark-e27a1337-a759-46fb-b30c-efe5ce5541bd-2a204"),
        "model": "ep-20260706041055-2mgpf",
        "max_tokens": 800,
        "timeout": 60,  # 豆包推理模型需要更长超时
    },
    "扣子": {
        "base_url": "https://7hsjv6c4cn.coze.site/stream_run",
        "api_key": os.environ.get("COZE_PROJECT_API_TOKEN", "REMOVED"),
        "model": None,
        "max_tokens": 800,
        "timeout": 120,
        "format": "coze_code",
        "project_id": 7667164681706078217,
    },
}

# ============================================================
# Prompt 模板
# ============================================================
FOOTBALL_PROMPT = """你是一个专业的足球比赛预测分析师。请根据以下比赛信息做出预测。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让球: {handicap}球
- 胜平负赔率: 胜{spf_win} / 平{spf_draw} / 负{spf_lose}
- 让球赔率: 让胜{hdc_win} / 让平{hdc_draw} / 让负{hdc_lose}

注意：如果赔率显示"暂无"或"?"，请根据球队实力、历史交锋等因素进行预测，不要受赔率缺失影响。

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
  "goals": 总进球数(0-7整数),
  "half_full": "半全场如胜胜/平胜/负平",
  "confidence": 把握度(0.3-0.95),
  "analysis": "50-100字的分析理由，需包含历史赔率分析结论"
}}
```"""

BASKETBALL_PROMPT = """你是专业的篮球比赛预测分析师。一次性给出所有维度的预测，必须逻辑自洽。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让分: {handicap_line}分（负数=主队让分，正数=客队让分）
- 总分线: {hilo_line}分

## 赔率数据
- 胜负: 主胜{mnl_win} / 客胜{mnl_lose}
- 让分: 让胜(主队覆盖){hdc_win} / 让负(客队覆盖){hdc_lose}
- 大小分: 大{hilo_over} / 小{hilo_under}（盘口{hilo_line}）

注意：如果赔率显示"暂无"或"?"，请根据球队实力、近期状态等因素进行预测，不要受赔率缺失影响。

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
  "win_loss": "主胜"或"客胜",
  "handicap_result": "让胜"或"让负",
  "total_points": "大"或"小",
  "score_diff": "分差区间如主6-10胜或客1-5负",
  "confidence": 把握度(0.3-0.95),
  "analysis": "50-100字分析理由，需包含历史赔率分析结论"
}}
```

## ⚠️ 逻辑自洽规则（违反等于预测无效）:
1. **让分↔胜分差（最重要）**：
   - 让分盘口={handicap_line}分
   - 选"让胜"=看好主队赢超过盘口绝对值。如盘口-5.5选让胜→主队至少赢6分→胜分差只能选"主6-10胜""主11-15胜""主16-20胜""主21+胜"之一
   - 选"让负"=看好客队覆盖。如盘口-5.5选让负→客队赢或主队赢不到6分→胜分差应选"客x负"或"主1-5胜"
2. **让分↔胜负**：选"让胜"→胜负应选"主胜"；大让分盘口选"让负"→胜负倾向"客胜"
3. **胜分差↔大小分**：大胜分差（11+）→总分倾向"大"；小胜分差（1-5）→总分看情况

## 胜分差格式:
- "主x-y胜"=主队赢x到y分，"客x-y负"=客队赢x到y分
- 可选值: 主1-5胜/主6-10胜/主11-15胜/主16-20胜/主21+胜/客1-5负/客6-10负/客11-15负/客16-20负/客21+负"""


# ============================================================
# 情报搜集 Prompt 模板（扣子专用）
# ============================================================
INTELLIGENCE_PROMPT_FOOTBALL = """你是一个专业的足球比赛情报分析师。请联网搜索以下比赛的最新情报，然后结合情报和赔率给出预测。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让球: {handicap}球
- 胜平负赔率: 胜{spf_win} / 平{spf_draw} / 负{spf_lose}
- 让球赔率: 让胜{hdc_win} / 让平{hdc_draw} / 让负{hdc_lose}

## 情报搜集要求（必须联网搜索）

请依次搜索以下5个维度的情报：

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

### 4. 赔率走势（market_sentiment）
- 搜索本场比赛赔率变化趋势
- 是否有异常资金流入
- 初盘→即时盘的变化方向

### 5. 专家分析（expert_opinions）
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
      "odds_trend": "赔率变化趋势",
      "money_flow": "资金流向分析",
      "anomaly": "是否有异常"
    }},
    "summary": "情报总结，100字以内"
  }},
  "prediction": {{
    "spf": "胜"或"平"或"负",
    "handicap_spf": "让胜"或"让平"或"让负",
    "score": "比分如2-1",
    "goals": 总进球数(0-7整数),
    "half_full": "半全场如胜胜/平胜/负平",
    "confidence": 把握度(0.3-0.95),
    "analysis": "50-100字分析理由，需结合情报和赔率"
  }}
}}
```"""

INTELLIGENCE_PROMPT_BASKETBALL = """你是一个专业的篮球比赛情报分析师。请联网搜索以下比赛的最新情报，然后结合情报和赔率给出预测。

## 比赛信息
- 联赛: {league}
- 主队: {home_team}
- 客队: {away_team}
- 比赛时间: {match_time}
- 让分: {handicap_line}分（负数=主队让分，正数=客队让分）
- 总分线: {hilo_line}分
- 胜负赔率: 主胜{mnl_win} / 客胜{mnl_lose}
- 让分赔率: 让胜{hdc_win} / 让负{hdc_lose}
- 大小分赔率: 大{hilo_over} / 小{hilo_under}

## 情报搜集要求（必须联网搜索）

请依次搜索以下5个维度的情报：

### 1. 双方近况（basic_data）
- 搜索两队最近5场比赛的战绩（胜负、得失分）
- 搜索主队主场战绩、客队客场战绩
- 搜索两队近期状态趋势

### 2. 伤停/轮休信息（basic_data）
- 搜索两队最新伤停和轮休名单
- 重点关注明星球员是否出战

### 3. 历史交锋（basic_data）
- 搜索两队近5次交锋记录
- 注意主客场因素

### 4. 赔率走势（market_sentiment）
- 搜索本场比赛赔率变化趋势
- 是否有异常资金流入
- 初盘→即时盘的变化方向

### 5. 专家分析（expert_opinions）
- 搜索主流媒体的赛前分析文章
- 搜索知名分析师的预测观点

## 请严格按以下JSON格式输出（不要输出其他内容）:
```json
{{
  "intelligence": {{
    "basic_data": {{
      "home_form": "主队近5场战绩描述",
      "away_form": "客队近5场战绩描述",
      "home_injuries": "主队伤停/轮休信息",
      "away_injuries": "客队伤停/轮休信息",
      "h2h": "历史交锋记录"
    }},
    "expert_opinions": {{
      "consensus": "专家主流观点",
      "key_points": ["分析要点1", "分析要点2", "分析要点3"]
    }},
    "market_sentiment": {{
      "odds_trend": "赔率变化趋势",
      "money_flow": "资金流向分析",
      "anomaly": "是否有异常"
    }},
    "summary": "情报总结，100字以内"
  }},
  "prediction": {{
    "win_loss": "主胜"或"客胜",
    "handicap_result": "让胜"或"让负",
    "total_points": "大"或"小",
    "score_diff": "分差区间如主6-10胜或客1-5负",
    "confidence": 把握度(0.3-0.95),
    "analysis": "50-100字分析理由，需结合情报和赔率"
  }}
}}
```"""

# 情报展示模板（用于将已有情报注入到普通预测prompt中）
INTELLIGENCE_SECTION = """
## 已搜集的情报

### 基本面数据
{basic_data}

### 专家观点
{expert_opinions}

### 市场情绪
{market_sentiment}

### 情报总结
{summary}

请结合以上情报和赔率数据，给出你的预测。"""


def format_intelligence_section(intelligence):
    """将intelligence dict格式化为INTELLIGENCE_SECTION文本
    
    Args:
        intelligence: dict，包含 basic_data, expert_opinions, market_sentiment, summary
    
    Returns:
        str: 格式化后的文本，如果intelligence为None返回空字符串
    """
    if not intelligence:
        return ""
    
    def format_value(val):
        if val is None:
            return "暂无"
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False, indent=2)
        return str(val)
    
    return INTELLIGENCE_SECTION.format(
        basic_data=format_value(intelligence.get("basic_data")),
        expert_opinions=format_value(intelligence.get("expert_opinions")),
        market_sentiment=format_value(intelligence.get("market_sentiment")),
        summary=format_value(intelligence.get("summary")),
    )


# ============================================================
# 数据库操作
# ============================================================
def get_db_conn():
    return psycopg2.connect(DB_URL)


def fetch_matches(match_ids=None):
    """从matches表读取比赛信息"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        if match_ids:
            placeholders = ",".join(["%s"] * len(match_ids))
            cur.execute(f"""
                SELECT id, sport_type, home_team, away_team, metadata
                FROM matches
                WHERE id IN ({placeholders})
                ORDER BY id ASC
            """, match_ids)
        else:
            # 查询今天和明天的在售比赛
            cur.execute("""
                SELECT id, sport_type, home_team, away_team, metadata
                FROM matches
                WHERE metadata->>'status' = 'on_sale'
                  AND metadata->>'match_date' >= CURRENT_DATE::text
                  AND metadata->>'match_date' <= (CURRENT_DATE + INTERVAL '1 day')::text
                ORDER BY id ASC
            """)
        rows = cur.fetchall()
        matches = []
        for row in rows:
            meta = row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {}
            matches.append({
                "id": row[0],
                "sport_type": row[1],
                "home_team": row[2],
                "away_team": row[3],
                "league": meta.get("league", ""),
                "match_date": meta.get("match_date", ""),
                "match_time": meta.get("match_time", ""),
                "odds": meta.get("odds", {}),
                "metadata": meta,
            })
        return matches
    finally:
        conn.close()


def fetch_existing_predictions(match_ids, ai_name):
    """检查哪些比赛已有该AI的预测"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(match_ids))
        cur.execute(f"""
            SELECT match_id FROM predictions
            WHERE match_id IN ({placeholders}) AND ai_name = %s
        """, match_ids + [ai_name])
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def get_next_prediction_id():
    """获取predictions表下一个id"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM predictions")
        return cur.fetchone()[0]
    finally:
        conn.close()


def delete_existing_predictions(match_ids, ai_name):
    """删除已有预测（用于重新生成）"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(match_ids))
        cur.execute(f"""
            DELETE FROM predictions
            WHERE match_id IN ({placeholders}) AND ai_name = %s
        """, match_ids + [ai_name])
        deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def write_prediction(pred_data):
    """写入单条预测到predictions表"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        next_id = get_next_prediction_id()

        sport_type = pred_data["sport_type"]

        if sport_type == "football":
            cur.execute("""
                INSERT INTO predictions (
                    id, match_id, ai_name, prediction, analysis,
                    sport_type, confidence, match_date,
                    spf, handicap_spf, goals, score, half_full,
                    raw_response
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                next_id,
                pred_data["match_id"],
                pred_data["ai_name"],
                json.dumps(pred_data["prediction"], ensure_ascii=False),
                pred_data.get("analysis", ""),
                "football",
                str(pred_data.get("confidence", "")),
                pred_data.get("match_date"),
                pred_data.get("spf_pred"),
                pred_data.get("handicap_spf_pred"),
                pred_data.get("goals_pred"),
                pred_data.get("score_pred"),
                pred_data.get("half_full_pred"),
                pred_data.get("raw_response", ""),
            ))
        else:  # basketball
            cur.execute("""
                INSERT INTO predictions (
                    id, match_id, ai_name, prediction, analysis,
                    sport_type, confidence, match_date,
                    win_loss_pred, handicap_win_loss_pred, total_points_pred, score_diff_range_pred,
                    raw_response
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                next_id,
                pred_data["match_id"],
                pred_data["ai_name"],
                json.dumps(pred_data["prediction"], ensure_ascii=False),
                pred_data.get("analysis", ""),
                "basketball",
                str(pred_data.get("confidence", "")),
                pred_data.get("match_date"),
                pred_data.get("win_loss_pred"),
                pred_data.get("handicap_win_loss_pred"),
                pred_data.get("total_points_pred"),
                pred_data.get("score_diff_range_pred"),
                pred_data.get("raw_response", ""),
            ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 写入预测失败 match={pred_data['match_id']} ai={pred_data['ai_name']}: {e}")
        return False
    finally:
        conn.close()


def save_match_intelligence(match, intelligence_data):
    """将情报告写入 match_intelligence 表（upsert）
    
    Args:
        match: dict，包含 id, home_team, away_team, match_time, league
        intelligence_data: dict，包含 basic_data, expert_opinions, media_analysis, market_sentiment, summary
    
    Returns:
        bool: 成功返回 True，失败返回 False
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        match_id = match["id"]
        
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
        
        media_analysis = intelligence_data.get("media_analysis")
        if isinstance(media_analysis, dict):
            media_analysis = json.dumps(media_analysis, ensure_ascii=False)
        
        market_sentiment = intelligence_data.get("market_sentiment")
        if isinstance(market_sentiment, dict):
            market_sentiment = json.dumps(market_sentiment, ensure_ascii=False)
        
        summary = intelligence_data.get("summary", "")
        match_time = match.get("match_time")
        home_team = match.get("home_team", "")
        away_team = match.get("away_team", "")
        league = match.get("league", "")
        
        if existing:
            # UPDATE
            cur.execute("""
                UPDATE match_intelligence 
                SET home_team = %s, away_team = %s, match_time = %s, league = %s,
                    basic_data = %s::jsonb, expert_opinions = %s::jsonb,
                    media_analysis = %s::jsonb, market_sentiment = %s::jsonb,
                    summary = %s, updated_at = NOW()
                WHERE match_id = %s
            """, (home_team, away_team, match_time, league,
                  basic_data, expert_opinions, media_analysis, market_sentiment,
                  summary, match_id))
        else:
            # INSERT
            cur.execute("""
                INSERT INTO match_intelligence 
                (match_id, home_team, away_team, match_time, league,
                 basic_data, expert_opinions, media_analysis, market_sentiment, summary)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            """, (match_id, home_team, away_team, match_time, league,
                  basic_data, expert_opinions, media_analysis, market_sentiment, summary))
        
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
        match_id: str，比赛ID
    
    Returns:
        dict or None: 包含 basic_data, expert_opinions, media_analysis, market_sentiment, summary
                      如果不存在返回 None
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT basic_data, expert_opinions, media_analysis, market_sentiment, summary
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
            "media_analysis": parse_jsonb(row[2]),
            "market_sentiment": parse_jsonb(row[3]),
            "summary": row[4] or "",
        }
    except Exception as e:
        print(f"[ERROR] 读取情报告失败 match={match_id}: {e}")
        return None
    finally:
        conn.close()


# ============================================================
# AI API 调用
# ============================================================
def build_prompt(match):
    """根据比赛类型构建prompt"""
    odds = match.get("odds", {})

    if match["sport_type"] == "football":
        spf = odds.get("spf", {})
        hdc = odds.get("handicap_spf", {})
        return FOOTBALL_PROMPT.format(
            home_team=match["home_team"],
            away_team=match["away_team"],
            league=match["league"],
            match_time=match["match_time"],
            spf_win=spf.get("win", "?"),
            spf_draw=spf.get("draw", "?"),
            spf_lose=spf.get("lose", "?"),
            handicap=hdc.get("handicap", "?"),
            hdc_win=hdc.get("win", "?"),
            hdc_draw=hdc.get("draw", "?"),
            hdc_lose=hdc.get("lose", "?"),
        )
    else:  # basketball
        mnl = odds.get("mnl", odds.get("spf", {}))
        hdc = odds.get("hdc", {})
        hilo = odds.get("hilo", {})
        return BASKETBALL_PROMPT.format(
            home_team=match["home_team"],
            away_team=match["away_team"],
            league=match["league"],
            match_time=match["match_time"],
            mnl_win=mnl.get("win", "?"),
            mnl_lose=mnl.get("lose", "?"),
            handicap_line=hdc.get("line", "?"),
            hdc_win=hdc.get("win", "?"),
            hdc_lose=hdc.get("lose", "?"),
            hilo_line=hilo.get("line", "?"),
            hilo_over=hilo.get("over", "?"),
            hilo_under=hilo.get("under", "?"),
        )


async def call_ai_api(session, ai_name, match, sem):
    """调用单个AI API获取预测，失败自动重试1次"""
    result, error = await _call_ai_api_once(session, ai_name, match, sem)
    if error and "超时" in error:
        print(f"[RETRY] {ai_name} 超时重试 match={match['id']}")
        result, error = await _call_ai_api_once(session, ai_name, match, sem)
    return result, error


async def _call_ai_api_once(session, ai_name, match, sem):
    """单次调用AI API"""
    config = AI_CONFIGS[ai_name]
    prompt = build_prompt(match)

    async with sem:
        try:
            timeout_sec = config.get("timeout", 30)
            timeout = aiohttp.ClientTimeout(total=timeout_sec)

            # 扣子专用调用逻辑（coze_code格式）
            if config.get("format") == "coze_code":
                headers = {
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "content": {
                        "query": {
                            "prompt": [
                                {
                                    "type": "text",
                                    "content": {"text": prompt},
                                }
                            ],
                        },
                    },
                    "type": "query",
                    "session_id": f"predict_{int(time.time())}",
                }
                if config.get("project_id"):
                    payload["project_id"] = config["project_id"]

                async with session.post(
                    config["base_url"],
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        print(f"[WARN] {ai_name} API返回 {resp.status}: {text[:200]}")
                        return None, f"HTTP {resp.status}"

                    content_type = resp.headers.get("Content-Type", "")

                    # JSON响应
                    if "json" in content_type:
                        data = await resp.json()
                        if isinstance(data, dict):
                            if "data" in data and isinstance(data["data"], dict):
                                messages = data["data"].get("messages", [])
                                for msg in reversed(messages):
                                    if msg.get("role") == "assistant" and msg.get("content"):
                                        return msg["content"], None
                            if "messages" in data:
                                for msg in reversed(data["messages"]):
                                    if msg.get("role") == "assistant" and msg.get("content"):
                                        return msg["content"], None
                            if "result" in data:
                                return str(data["result"]), None
                            if "text" in data:
                                return str(data["text"]), None
                        return json.dumps(data, ensure_ascii=False), None

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

                    # 回退：返回原始文本
                    text = await resp.text()
                    if text:
                        return text, None
                    print(f"[WARN] {ai_name} 返回空内容 match={match['id']}")
                    return None, "空响应"

            # 标准OpenAI格式调用
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

            async with session.post(
                config["base_url"],
                headers=headers,
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"[WARN] {ai_name} API返回 {resp.status}: {text[:200]}")
                    return None, f"HTTP {resp.status}"

                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    print(f"[WARN] {ai_name} 返回空内容 match={match['id']}")
                    return None, "空响应"

                return content, None

        except asyncio.TimeoutError:
            print(f"[WARN] {ai_name} 超时 match={match['id']}")
            return None, "超时"
        except Exception as e:
            print(f"[WARN] {ai_name} 异常 match={match['id']}: {e}")
            return None, str(e)


def parse_football_prediction(raw_text, ai_name):
    """解析足球预测JSON"""
    # 预处理：修复常见的JSON格式问题
    # 1. 修复 goals 字段为 "2-3" 这种非法格式（取第一个数字）
    cleaned = re.sub(r'"goals"\s*:\s*(\d+)\s*-\s*(\d+)', r'"goals": \1', raw_text)
    # 2. 修复 goals 字段为字符串 "3" 的情况
    cleaned = re.sub(r'"goals"\s*:\s*"(\d+)"', r'"goals": \1', cleaned)
    # 3. 如果JSON被截断，尝试补全闭合大括号
    open_braces = cleaned.count('{') - cleaned.count('}')
    if open_braces > 0:
        cleaned += '}' * open_braces
    # 4. 移除尾部逗号
    cleaned = re.sub(r',\s*}', '}', cleaned)
    cleaned = re.sub(r',\s*]', ']', cleaned)

    # 尝试从文本中提取JSON
    json_match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
    if not json_match:
        # 尝试更宽松的匹配（包含嵌套大括号）
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)

    if json_match:
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            print(f"[WARN] {ai_name} JSON解析失败: {raw_text[:100]}")
            return None
    else:
        print(f"[WARN] {ai_name} 未找到JSON: {raw_text[:100]}")
        return None

    # 验证字段
    valid_spf = ["胜", "平", "负"]
    valid_hf = ["胜胜", "胜平", "胜负", "平胜", "平平", "平负", "负胜", "负平", "负负"]
    valid_hdc = ["让胜", "让平", "让负"]

    spf = data.get("spf", "")
    if spf not in valid_spf:
        # 尝试模糊匹配
        if "胜" in str(spf) and "平" not in str(spf):
            spf = "胜"
        elif "平" in str(spf):
            spf = "平"
        elif "负" in str(spf):
            spf = "负"
        else:
            spf = "平"  # 默认

    handicap_spf = data.get("handicap_spf", "")
    if handicap_spf not in valid_hdc:
        if "让胜" in str(handicap_spf):
            handicap_spf = "让胜"
        elif "让负" in str(handicap_spf):
            handicap_spf = "让负"
        elif "让平" in str(handicap_spf):
            handicap_spf = "让平"
        else:
            handicap_spf = "让负"  # 默认

    goals = data.get("goals", 2)
    try:
        goals = int(goals)
        goals = max(0, min(7, goals))
    except (ValueError, TypeError):
        goals = 2

    score = data.get("score", "1-1")
    if not re.match(r'\d+-\d+', str(score)):
        score = "1-1"

    half_full = data.get("half_full", "")
    if half_full not in valid_hf:
        half_full = "平平"  # 默认

    confidence = data.get("confidence", 0.5)
    try:
        confidence = float(confidence)
        confidence = max(0.3, min(0.95, confidence))
    except (ValueError, TypeError):
        confidence = 0.5

    analysis = data.get("analysis", "")

    return {
        "spf": spf,
        "handicap_spf": handicap_spf,
        "goals": goals,
        "score": score,
        "half_full": half_full,
        "confidence": confidence,
        "analysis": analysis,
    }


def parse_basketball_prediction(raw_text, ai_name):
    """解析篮球预测JSON"""
    # 预处理：修复常见的JSON格式问题
    cleaned = raw_text
    open_braces = cleaned.count('{') - cleaned.count('}')
    if open_braces > 0:
        cleaned += '}' * open_braces
    cleaned = re.sub(r',\s*}', '}', cleaned)
    cleaned = re.sub(r',\s*]', ']', cleaned)

    json_match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
    if not json_match:
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)

    if json_match:
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            print(f"[WARN] {ai_name} JSON解析失败: {raw_text[:100]}")
            return None
    else:
        print(f"[WARN] {ai_name} 未找到JSON: {raw_text[:100]}")
        return None

    valid_wl = ["主胜", "客胜"]
    valid_hr = ["让胜", "让负"]
    valid_tp = ["大", "小"]
    valid_diff = ["1-5", "6-10", "11-15", "16-20", "21-25", "26+"]

    win_loss = data.get("win_loss", "")
    if win_loss not in valid_wl:
        if "主" in str(win_loss):
            win_loss = "主胜"
        else:
            win_loss = "客胜"

    handicap_result = data.get("handicap_result", "")
    if handicap_result not in valid_hr:
        if "让胜" in str(handicap_result):
            handicap_result = "让胜"
        elif "让负" in str(handicap_result):
            handicap_result = "让负"
        else:
            handicap_result = "让负"

    total_points = data.get("total_points", "")
    if total_points not in valid_tp:
        if "大" in str(total_points):
            total_points = "大"
        else:
            total_points = "小"

    score_diff = data.get("score_diff", "")
    matched_diff = False
    for d in valid_diff:
        if d in str(score_diff):
            score_diff = d
            matched_diff = True
            break
    if not matched_diff:
        # 尝试数字匹配
        diff_num = re.search(r'(\d+)', str(score_diff))
        if diff_num:
            n = int(diff_num.group(1))
            if n <= 5: score_diff = "1-5"
            elif n <= 10: score_diff = "6-10"
            elif n <= 15: score_diff = "11-15"
            elif n <= 20: score_diff = "16-20"
            elif n <= 25: score_diff = "21-25"
            else: score_diff = "26+"
        else:
            score_diff = "6-10"

    confidence = data.get("confidence", 0.5)
    try:
        confidence = float(confidence)
        confidence = max(0.3, min(0.95, confidence))
    except (ValueError, TypeError):
        confidence = 0.5

    analysis = data.get("analysis", "")

    return {
        "win_loss": win_loss,
        "handicap_result": handicap_result,
        "total_points": total_points,
        "score_diff": score_diff,
        "confidence": confidence,
        "analysis": analysis,
    }


def build_prediction_record(match, ai_name, parsed, raw_text):
    """组装写入predictions表的记录"""
    sport_type = match["sport_type"]

    if sport_type == "football":
        prediction_json = {
            "spf": parsed["spf"],
            "handicap_spf": parsed["handicap_spf"],
            "goals": parsed["goals"],
            "score": parsed["score"],
            "half_full": parsed["half_full"],
            "confidence": parsed["confidence"],
        }
        return {
            "match_id": match["id"],
            "ai_name": ai_name,
            "prediction": prediction_json,
            "analysis": parsed.get("analysis", ""),
            "sport_type": "football",
            "confidence": parsed["confidence"],
            "match_date": match.get("match_date"),
            "spf_pred": parsed["spf"],
            "handicap_spf_pred": parsed["handicap_spf"],
            "goals_pred": parsed["goals"],
            "score_pred": parsed["score"],
            "half_full_pred": parsed["half_full"],
            "raw_response": raw_text[:2000] if raw_text else "",
        }
    else:  # basketball
        prediction_json = {
            "win_loss": parsed["win_loss"],
            "handicap_result": parsed["handicap_result"],
            "total_points": parsed["total_points"],
            "score_diff": parsed["score_diff"],
            "confidence": parsed["confidence"],
        }
        return {
            "match_id": match["id"],
            "ai_name": ai_name,
            "prediction": prediction_json,
            "analysis": parsed.get("analysis", ""),
            "sport_type": "basketball",
            "confidence": parsed["confidence"],
            "match_date": match.get("match_date"),
            "win_loss_pred": parsed["win_loss"],
            "handicap_win_loss_pred": parsed["handicap_result"],
            "total_points_pred": parsed["total_points"],
            "score_diff_range_pred": parsed["score_diff"],
            "raw_response": raw_text[:2000] if raw_text else "",
        }


# ============================================================
# 主流程
# ============================================================
async def main():
    print(f"[参数] result_mode={RESULT_MODE}, match_ids={MATCH_IDS_ARG}")
    sdk = CodeActSDK()

    try:
        # 1. 获取比赛列表
        if MATCH_IDS_ARG:
            target_match_ids = [m.strip() for m in MATCH_IDS_ARG.split(",") if m.strip()]
        else:
            target_match_ids = None

        matches = fetch_matches(target_match_ids)
        if target_match_ids is None:
            target_match_ids = [m["id"] for m in matches]
        print(f"[步骤1] 查询到 {len(matches)} 场比赛...")
        if not matches:
            actual_mode = RESULT_MODE if RESULT_MODE != "auto" else "display_only"
            await sdk.submit_result(
                result_mode=actual_mode,
                status="success",
                message=f"未找到指定比赛（{len(target_match_ids)}场），可能已不在售。",
            )
            return

        # 按 match_id 排序保持与指定顺序一致
        match_map = {m["id"]: m for m in matches}
        ordered_matches = [match_map[mid] for mid in target_match_ids if mid in match_map]
        missing = [mid for mid in target_match_ids if mid not in match_map]

        print(f"  找到 {len(ordered_matches)} 场比赛")
        if missing:
            print(f"  未找到: {missing}")
        for m in ordered_matches:
            print(f"  {m['id']}: {m['home_team']} vs {m['away_team']} ({m['sport_type']}/{m['league']})")

        match_ids = [m["id"] for m in ordered_matches]
        ai_names = list(AI_CONFIGS.keys())

        # 2. 删除已有预测（重新生成）
        for ai_name in ai_names:
            existing = fetch_existing_predictions(match_ids, ai_name)
            if existing:
                deleted = delete_existing_predictions(match_ids, ai_name)
                print(f"  删除 {ai_name} 旧预测 {deleted} 条")

        # 3. 并发调用6个AI × N场比赛
        print(f"\n[步骤3] 开始调用 {len(ai_names)} 个AI为 {len(ordered_matches)} 场比赛生成预测...")
        sem = asyncio.Semaphore(6)  # 最多6个并发API请求

        async with aiohttp.ClientSession() as session:
            tasks = []
            task_info = []  # (ai_name, match) for each task

            for match in ordered_matches:
                for ai_name in ai_names:
                    tasks.append(call_ai_api(session, ai_name, match, sem))
                    task_info.append((ai_name, match))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. 解析结果并写入数据库
        print(f"\n[步骤4] 解析预测结果并写入数据库...")
        success_count = 0
        fail_count = 0
        fail_details = []
        predictions_summary = {}  # {match_id: {ai_name: parsed_summary}}

        for i, result in enumerate(results):
            ai_name, match = task_info[i]

            if isinstance(result, Exception):
                print(f"  [FAIL] {ai_name} × {match['id']}: {result}")
                fail_count += 1
                fail_details.append(f"{ai_name}/{match['id']}")
                continue

            raw_text, error = result
            if error:
                print(f"  [FAIL] {ai_name} × {match['id']}: {error}")
                fail_count += 1
                fail_details.append(f"{ai_name}/{match['id']}")
                continue

            # 解析预测
            if match["sport_type"] == "football":
                parsed = parse_football_prediction(raw_text, ai_name)
            else:
                parsed = parse_basketball_prediction(raw_text, ai_name)

            if not parsed:
                print(f"  [FAIL] {ai_name} × {match['id']}: 解析失败")
                fail_count += 1
                fail_details.append(f"{ai_name}/{match['id']}(解析失败)")
                continue

            # 组装记录
            record = build_prediction_record(match, ai_name, parsed, raw_text)
            if write_prediction(record):
                success_count += 1
                # 记录摘要
                mid = match["id"]
                if mid not in predictions_summary:
                    predictions_summary[mid] = {}
                if match["sport_type"] == "football":
                    predictions_summary[mid][ai_name] = f"spf={parsed['spf']} score={parsed['score']}"
                else:
                    predictions_summary[mid][ai_name] = f"wl={parsed['win_loss']} diff={parsed['score_diff']}"
                print(f"  [OK] {ai_name} × {match['id']}")
            else:
                fail_count += 1
                fail_details.append(f"{ai_name}/{match['id']}(写入失败)")

        total = len(ai_names) * len(ordered_matches)
        print(f"\n  完成: 成功{success_count}/{total}, 失败{fail_count}")
        if fail_details:
            print(f"  失败明细: {fail_details}")

        # 5. 生成报告
        print(f"\n[步骤5] 生成预测报告...")
        report_lines = [
            f"# 多AI竞彩预测报告",
            f"",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"AI数量: {len(ai_names)} ({', '.join(ai_names)})",
            f"比赛场次: {len(ordered_matches)}场",
            f"预测总数: {success_count}/{total}",
            f"",
        ]

        # 按比赛分组
        for match in ordered_matches:
            mid = match["id"]
            sport = match["sport_type"]
            report_lines.append(f"## {mid} {match['home_team']} vs {match['away_team']} ({match['league']})")
            report_lines.append("")

            if sport == "football":
                report_lines.append("| AI | 胜平负 | 让球 | 比分 | 进球 | 半全场 | 把握度 |")
                report_lines.append("|----|--------|------|------|------|--------|--------|")
            else:
                report_lines.append("| AI | 胜负 | 让分 | 大小 | 分差 | 把握度 |")
                report_lines.append("|----|------|------|------|------|--------|")

            ai_preds = predictions_summary.get(mid, {})
            # 需要重新获取预测数据来生成表格（因为之前只存了摘要字符串）
            # 从数据库读取刚写入的预测
            conn = get_db_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT ai_name, prediction, confidence, analysis
                    FROM predictions
                    WHERE match_id = %s
                    ORDER BY ai_name
                """, (mid,))
                preds = cur.fetchall()
                for pred_row in preds:
                    a_name = pred_row[0]
                    pred_json = pred_row[1] if isinstance(pred_row[1], dict) else json.loads(pred_row[1]) if pred_row[1] else {}
                    conf = pred_row[2] or ""
                    if sport == "football":
                        report_lines.append(
                            f"| {a_name} | {pred_json.get('spf','')} | {pred_json.get('handicap_spf','')} "
                            f"| {pred_json.get('score','')} | {pred_json.get('goals','')} "
                            f"| {pred_json.get('half_full','')} | {conf} |"
                        )
                    else:
                        report_lines.append(
                            f"| {a_name} | {pred_json.get('win_loss','')} | {pred_json.get('handicap_result','')} "
                            f"| {pred_json.get('total_points','')} | {pred_json.get('score_diff','')} | {conf} |"
                        )
            finally:
                conn.close()
            report_lines.append("")

        report_text = "\n".join(report_lines)

        # 写入报告文件
        report_path = f"./codeact/output/multi_ai_predict_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        os.makedirs("./codeact/output", exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"  报告已写入: {report_path}")

        # 6. 提交结果
        fb_count = sum(1 for m in ordered_matches if m["sport_type"] == "football")
        bb_count = sum(1 for m in ordered_matches if m["sport_type"] == "basketball")

        message_lines = [
            f"多AI预测完成: {success_count}/{total} 条成功",
            f"",
            f"比赛: {len(ordered_matches)}场 (足球{fb_count}/篮球{bb_count})",
            f"AI: {', '.join(ai_names)}",
        ]
        if fail_count > 0:
            message_lines.append(f"失败: {fail_count}条 ({', '.join(fail_details[:5])}{'...' if len(fail_details)>5 else ''})")
        message_lines.append(f"")
        message_lines.append(f"完整报告: [multi_ai_predict_{datetime.now().strftime('%Y%m%d_%H%M')}.md](computer://{os.path.abspath(report_path)})")

        message = "\n".join(message_lines)
        actual_mode = RESULT_MODE if RESULT_MODE != "auto" else "display_only"

        await sdk.submit_result(
            result_mode=actual_mode,
            status="success" if fail_count < total else "error",
            message=message,
            data={
                "total": total,
                "success": success_count,
                "failed": fail_count,
                "football_matches": fb_count,
                "basketball_matches": bb_count,
                "ai_count": len(ai_names),
                "fail_details": fail_details[:10],
                "report_path": report_path,
            },
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"多AI预测脚本执行失败: {e}",
            data={"error_type": type(e).__name__},
        )


asyncio.run(main())
