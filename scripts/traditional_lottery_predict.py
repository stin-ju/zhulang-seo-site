#!/usr/bin/env python3
"""
traditional_lottery_predict.py - 传统足彩7AI预测
支持玩法：胜负彩(90)、任9(90)、半全场(98)、进球彩(94)
"""
import os
import sys
import json
import time
import traceback
import psycopg2
import requests
from datetime import datetime

# ============ 配置 ============

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# 体彩API配置
SPORTTERY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://www.sporttery.cn/",
    "Origin": "https://www.sporttery.cn",
    "Accept": "application/json, text/plain, */*",
}

# 玩法ID映射
GAME_TYPES = {
    "胜负彩": {"id": 90, "param": "90,0"},
    "任9": {"id": 90, "param": "90,0"},  # 任9使用胜负彩数据
    "半全场": {"id": 98, "param": "98,0"},
    "进球彩": {"id": 94, "param": "94,0"},
}

# 7个AI配置（与auto_predict.py相同）
AI_CONFIGS = {
    "扣子": {
        "url": None,
        "key_env": None,
        "model": None,
        "format": "template",
    },
    "豆包": {
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
    "文心": {
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "model": "ernie-4.0-8k-latest",
        "format": "openai",
    },
    "混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "model": "hy3-preview",
        "format": "openai",
    },
    "DeepSeek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "format": "openai",
    },
    "智谱清言": {
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "ZHIPU_API_KEY",
        "model": "glm-4-flash",
        "format": "openai",
    },
    "MiniMax": {
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model": "MiniMax-Text-01",
        "format": "minimax",
    },
}

# ============ Prompt模板 ============

PROMPT_TEMPLATE = """你是一个专业足球比赛预测模型，请严格按照以下规则输出纯JSON，不要任何分析。

【核心原则】
- 赔率越低=概率越高，让球方向看让球赔率最低方
- 强队主场让球多(1.5+)时，关注赢球输盘风险
- 同赔率组合下，优先选择概率更高的选项

【历史赔率分析要求】
在预测前，请联网搜索历史数据：
1. 搜索当前比赛双方相同/相似赔率的历史场次（至少30场）
2. 搜索当前大小球盘口的历史概率数据（至少50场）
3. 搜索当前让球盘口的历史赢盘率（至少30场）
4. 搜索相同半全场赔率结构的历史概率（如有）
5. 搜索相似比分赔率的历史数据（如有）

统计这些历史场次中各结果的实际出现概率。

【历史数据应用】
- 历史概率与赔率隐含概率一致时，按赔率预测
- 历史概率明显偏离赔率时（如历史主胜70%，赔率暗示50%），优先参考历史数据
- 任选9场优先选历史概率最稳定（方差最小）的场次

【半全场编码】
33=胜胜, 31=胜平, 30=胜负, 13=平胜, 11=平平, 10=平负, 03=负胜, 01=负平, 00=负负

【进球数编码】
0/1/2/3，其中3代表3球及以上

【输出格式】
{{
  "predictions": [
    {{"match": "场次编号", "spf": "3/1/0", "handicap": "3/1/0", "rq_number": 让球数, "bf": "比分如2:1", "zjq": "0/1/2/3", "bqc": "33/31/.../00"}},
    ...
  ],
  "ren9": ["场次编号1", "场次编号2", ...],
  "confidence": "高/中/低"
}}

【比赛数据】
{match_data}

【赔率数据】
{odds_data}

请输出14场比赛的完整预测，任9选择最有信心的9场。只输出JSON，不要其他内容。"""

# ============ 体彩API数据获取 ============

def fetch_sporttery_data(game_type):
    """从体彩API获取比赛数据 - 使用getMatchCalculatorV1接口"""
    # 使用竞彩足球接口，该接口不会被WAF拦截
    url = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode=HAD,HHAD&channel=c"
    
    try:
        resp = requests.get(url, headers=SPORTTERY_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("value") and data["value"].get("matchInfoList"):
            return data["value"]["matchInfoList"]
        return None
    except Exception as e:
        print(f"获取体彩API失败: {e}")
        return None


def parse_match_data(api_data, game_type):
    """解析API返回的比赛数据"""
    if not api_data:
        return [], []
    
    matches = []
    odds_list = []
    
    # api_data 是包含 subMatchList 的对象列表
    all_matches = []
    if isinstance(api_data, list):
        for item in api_data:
            if isinstance(item, dict) and 'subMatchList' in item:
                all_matches.extend(item['subMatchList'])
            elif isinstance(item, dict):
                all_matches.append(item)
    
    for i, match in enumerate(all_matches[:14]):  # 最多14场
        match_num = str(i + 1)
        
        # 提取比赛信息
        home_team = match.get("homeTeamAbbName", match.get("homeTeamName", f"主队{i+1}"))
        away_team = match.get("awayTeamAbbName", match.get("awayTeamName", f"客队{i+1}"))
        league = match.get("leagueName", match.get("groupName", "未知联赛"))
        match_time = match.get("matchDate", "")
        
        matches.append({
            "num": match_num,
            "league": league,
            "home": home_team,
            "away": away_team,
            "time": match_time,
            "id": f"match_{match_num}",
            "issue": match.get("matchNum", ""),
        })
        
        # 提取赔率 - 从had/hhad字段或poolList中获取
        spf_odds = {}
        handicap_odds = {}
        handicap_num = 0
        
        # 尝试从had字段获取胜平负赔率
        had = match.get("had", {})
        if had:
            spf_odds["win"] = float(had.get("h", 0))
            spf_odds["draw"] = float(had.get("d", 0))
            spf_odds["lose"] = float(had.get("a", 0))
        
        # 尝试从hhad字段获取让球赔率
        hhad = match.get("hhad", {})
        if hhad:
            try:
                handicap_num = int(float(hhad.get("goalLineValue", 0)))
            except (ValueError, TypeError):
                handicap_num = 0
            handicap_odds["win"] = float(hhad.get("h", 0))
            handicap_odds["draw"] = float(hhad.get("d", 0))
            handicap_odds["lose"] = float(hhad.get("a", 0))
        
        # 如果上面没有获取到，尝试从poolList获取
        pool_list = match.get("poolList", [])
        for pool in pool_list:
            pool_code = pool.get("poolCode", "")
            if pool_code == "HAD" and not spf_odds:  # 胜平负
                odds_data = pool.get("oddsList", [])
                for odds in odds_data:
                    if odds.get("code") == "H":
                        spf_odds["win"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "D":
                        spf_odds["draw"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "A":
                        spf_odds["lose"] = float(odds.get("odds", 0))
            elif pool_code == "HHAD" and not handicap_odds:  # 让球胜平负
                handicap_num = int(pool.get("fixedOdds", 0))
                odds_data = pool.get("oddsList", [])
                for odds in odds_data:
                    if odds.get("code") == "H":
                        handicap_odds["win"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "D":
                        handicap_odds["draw"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "A":
                        handicap_odds["lose"] = float(odds.get("odds", 0))
        
        odds = {
            "num": match_num,
            "spf": spf_odds,
            "handicap": handicap_odds,
            "handicap_num": handicap_num,
        }
        odds_list.append(odds)
    
    return matches, odds_list


def build_prompt(matches, odds_list, game_type):
    """构建AI prompt"""
    # 构建MATCH_DATA
    match_lines = []
    for m in matches:
        match_lines.append(f"{m['num']}. [{m['league']}] {m['home']} vs {m['away']} ({m['time']})")
    match_data = "\n".join(match_lines)
    
    # 构建ODDS_DATA
    odds_lines = []
    for o in odds_list:
        spf = o.get("spf", {})
        handicap = o.get("handicap", {})
        handicap_num = o.get("handicap_num", 0)
        
        spf_str = f"胜{spf.get('win', '-')} 平{spf.get('draw', '-')} 负{spf.get('lose', '-')}"
        handicap_str = f"让{handicap_num}球 胜{handicap.get('win', '-')} 平{handicap.get('draw', '-')} 负{handicap.get('lose', '-')}"
        
        odds_lines.append(f"{o['num']}. {spf_str} | {handicap_str}")
    odds_data = "\n".join(odds_lines)
    
    # 填充模板
    prompt = PROMPT_TEMPLATE.format(match_data=match_data, odds_data=odds_data)
    return prompt


# ============ AI调用 ============

def call_ai(ai_name, prompt):
    """调用指定AI生成预测"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        raise Exception(f"未知AI: {ai_name}")
    
    fmt = config["format"]
    
    if fmt == "template":
        # 使用模板生成预测
        return generate_template_prediction(prompt)
    
    key = os.environ.get(config["key_env"], "")
    if not key:
        raise Exception(f"{ai_name} 的API Key未配置 ({config['key_env']})")
    
    # 限流相关错误关键词
    rate_limit_keywords = [
        "Arrearage", "Overdue", "quota", "QuotaExceeded", "insufficient",
        "SetLimitExceeded", "LimitExceeded", "ServerOverloaded",
        "RequestBurstTooFast", "RateLimitExceeded", "TooManyRequests", "429"
    ]
    
    # 构建模型列表（主模型 + fallback模型）
    models_to_try = [config["model"]]
    if config.get("fallback_models"):
        models_to_try.extend(config["fallback_models"])
    
    last_error = None
    for i, model in enumerate(models_to_try):
        try:
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            }
            
            if fmt == "openai":
                payload["model"] = model
                resp = requests.post(
                    config["url"],
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=60,
                )
            elif fmt == "minimax":
                payload["model"] = model
                resp = requests.post(
                    config["url"],
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=60,
                )
            else:
                raise Exception(f"未知格式: {fmt}")
            
            resp.raise_for_status()
            result = resp.json()
            
            if fmt == "openai":
                content = result["choices"][0]["message"]["content"]
            elif fmt == "minimax":
                content = result["reply"]["choices"][0]["message"]["content"]
            else:
                content = str(result)
            
            return parse_ai_response(content)
            
        except Exception as e:
            last_error = e
            err_msg = str(e)
            
            # 检查是否限流
            is_rate_limit = any(kw in err_msg for kw in rate_limit_keywords)
            
            if is_rate_limit and i < len(models_to_try) - 1:
                next_model = models_to_try[i + 1]
                print(f"  {ai_name} 模型 {model} 被限流，切换到 {next_model}")
                continue
            else:
                raise Exception(f"{ai_name} 调用失败: {last_error}")
    
    raise Exception(f"{ai_name} 所有模型都失败: {last_error}")


def generate_template_prediction(prompt):
    """使用模板生成预测（扣子使用）"""
    # 简单的基于赔率的预测逻辑
    import re
    
    # 从prompt中提取赔率数据
    odds_pattern = r"(\d+)\.\s*胜([\d.]+)\s*平([\d.]+)\s*负([\d.]+)"
    matches = re.findall(odds_pattern, prompt)
    
    predictions = []
    for m in matches:
        num, win, draw, lose = m
        win, draw, lose = float(win), float(draw), float(lose)
        
        # 基于赔率预测
        min_odds = min(win, draw, lose)
        if min_odds == win:
            spf = "3"
        elif min_odds == draw:
            spf = "1"
        else:
            spf = "0"
        
        predictions.append({
            "match": num,
            "spf": spf,
            "handicap": spf,
            "rq_number": 0,
            "bf": "1:0" if spf == "3" else "0:0" if spf == "1" else "0:1",
            "zjq": "1" if spf == "3" else "0" if spf == "1" else "1",
            "bqc": "33" if spf == "3" else "11" if spf == "1" else "00",
        })
    
    # 任9选择前9场
    ren9 = [p["match"] for p in predictions[:9]]
    
    return {
        "predictions": predictions,
        "ren9": ren9,
        "confidence": "中",
    }


def parse_ai_response(content):
    """解析AI返回的JSON"""
    import re
    
    # 尝试提取JSON
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # 如果解析失败，返回空结构
    return {
        "predictions": [],
        "ren9": [],
        "confidence": "低",
    }


# ============ 数据库操作 ============

def save_predictions(game_type, ai_name, predictions_data, matches_info=None):
    """保存预测结果到数据库"""
    if not DATABASE_URL:
        print("DATABASE_URL 未配置，跳过数据库保存")
        return
    
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # 创建传统彩预测表（如果不存在）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS traditional_predictions (
                    id SERIAL PRIMARY KEY,
                    game_type VARCHAR(20) NOT NULL,
                    ai_name VARCHAR(50) NOT NULL,
                    predictions JSONB,
                    ren9 JSONB,
                    confidence VARCHAR(10),
                    matches_info JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(game_type, ai_name)
                )
            """)
            
            # 插入或更新预测
            cur.execute("""
                INSERT INTO traditional_predictions (game_type, ai_name, predictions, ren9, confidence, matches_info)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_type, ai_name)
                DO UPDATE SET
                    predictions = EXCLUDED.predictions,
                    ren9 = EXCLUDED.ren9,
                    confidence = EXCLUDED.confidence,
                    matches_info = EXCLUDED.matches_info,
                    created_at = CURRENT_TIMESTAMP
            """, (
                game_type,
                ai_name,
                json.dumps(predictions_data.get("predictions", [])),
                json.dumps(predictions_data.get("ren9", [])),
                predictions_data.get("confidence", "低"),
                json.dumps(matches_info) if matches_info else None,
            ))
            
        conn.commit()
        print(f"  ✓ {ai_name} 预测已保存")
    except Exception as e:
        print(f"  ✗ {ai_name} 保存失败: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_predictions(game_type):
    """获取指定玩法的所有AI预测，返回前端期望的格式"""
    if not DATABASE_URL:
        return []
    
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # 获取最新的预测数据
            cur.execute("""
                SELECT ai_name, predictions, ren9, confidence, created_at, matches_info
                FROM traditional_predictions
                WHERE game_type = %s
                ORDER BY created_at DESC
                LIMIT 7
            """, (game_type,))
            
            rows = cur.fetchall()
            if not rows:
                return []
            
            # 获取比赛信息（从第一条记录的matches_info）
            matches_info = rows[0][5] if rows[0][5] else []
            if isinstance(matches_info, str):
                matches_info = json.loads(matches_info)
            
            # 根据游戏类型确定提取哪个字段
            field_map = {
                "胜负彩": "spf",
                "任9": "spf",
                "半全场": "bqc",
                "进球彩": "zjq"
            }
            field_key = field_map.get(game_type, "spf")
            
            # 转换为前端期望的格式：按比赛分组
            results = []
            for idx, match in enumerate(matches_info):
                match_id = match.get("id", f"match_{idx+1}")
                home_team = match.get("home", "未知")
                away_team = match.get("away", "未知")
                league = match.get("league", "")
                match_time = match.get("time", "")
                
                # 为每个AI创建一个预测项
                for row in rows:
                    ai_name = row[0]
                    predictions = row[1] if isinstance(row[1], list) else json.loads(row[1]) if row[1] else []
                    
                    # 获取该AI对该比赛的预测
                    prediction_obj = predictions[idx] if idx < len(predictions) else {}
                    
                    # 将预测对象转换为字符串
                    if isinstance(prediction_obj, dict):
                        prediction = prediction_obj.get(field_key, "")
                    else:
                        prediction = str(prediction_obj)
                    
                    results.append({
                        "match_id": match_id,
                        "home_team": home_team,
                        "away_team": away_team,
                        "league": league,
                        "match_time": match_time,
                        "ai_name": ai_name,
                        "prediction": prediction,
                        "issue": match.get("issue", "")
                    })
            
            return results
    except Exception as e:
        print(f"获取预测失败: {e}")
        return []
    finally:
        conn.close()


# ============ 主流程 ============

def predict(game_type, force=False):
    """为指定玩法生成7AI预测"""
    print(f"\n=== 传统彩预测: {game_type} ===")
    
    # 检查是否已有预测
    if not force:
        existing = get_predictions(game_type)
        if existing and len(existing) >= 7:
            print(f"已有 {len(existing)} 个AI的预测，使用 --force 强制刷新")
            return {"status": "skipped", "message": "已有预测", "data": existing}
    
    # 获取体彩API数据
    print(f"获取体彩API数据...")
    api_data = fetch_sporttery_data(game_type)
    if not api_data:
        return {"status": "error", "message": "获取体彩API数据失败"}
    
    # 解析比赛数据
    matches, odds_list = parse_match_data(api_data, game_type)
    if not matches:
        return {"status": "error", "message": "没有可用的比赛数据"}
    
    print(f"获取到 {len(matches)} 场比赛")
    
    # 构建prompt
    prompt = build_prompt(matches, odds_list, game_type)
    
    # 调用7个AI
    results = []
    for ai_name in AI_CONFIGS.keys():
        print(f"调用 {ai_name}...")
        try:
            predictions = call_ai(ai_name, prompt)
            save_predictions(game_type, ai_name, predictions, matches)
            results.append({
                "ai_name": ai_name,
                "predictions": predictions.get("predictions", []),
                "ren9": predictions.get("ren9", []),
                "confidence": predictions.get("confidence", "低"),
            })
            print(f"  ✓ {ai_name} 成功")
        except Exception as e:
            print(f"  ✗ {ai_name} 失败: {e}")
            results.append({
                "ai_name": ai_name,
                "error": str(e),
            })
    
    return {
        "status": "success",
        "game_type": game_type,
        "matches": matches,
        "predictions": results,
    }


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="传统足彩7AI预测")
    parser.add_argument("--game", choices=["胜负彩", "任9", "半全场", "进球彩"], default="胜负彩",
                        help="玩法类型")
    parser.add_argument("--force", action="store_true", help="强制刷新预测")
    parser.add_argument("--get", action="store_true", help="获取已有预测")
    
    args = parser.parse_args()
    
    if args.get:
        results = get_predictions(args.game)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        result = predict(args.game, force=args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
