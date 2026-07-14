#!/usr/bin/env python3
"""
traditional_lottery_predict.py - 传统足彩7AI预测
支持玩法：胜负彩(gameNum=90)、半全场(gameNum=98)、进球彩(gameNum=94)
API: getFootBallDrawInfoV2.qry
"""
import os, sys, json, time, re, traceback
import psycopg2
import requests
from datetime import datetime

# ============ 配置 ============

DATABASE_URL = os.environ.get("DATABASE_URL", "")

SPORTTERY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://www.sporttery.cn/ctzc/kjgg/index.html",
    "Origin": "https://www.sporttery.cn",
    "Accept": "application/json, text/plain, */*",
}

# 玩法 -> gameNum 映射
GAME_NUM_MAP = {
    "胜负彩": 90,
    "任9": 90,
    "半全场": 98,
    "进球彩": 94,
}

# 7个AI配置
AI_CONFIGS = {
    "扣子": {"format": "template"},
    "豆包": {
        "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "key_env": "DOUBAO_API_KEY",
        "model": "doubao-seed-2-0-mini-260428",
        "format": "openai",
        "fallback_models": [
            "doubao-seed-2-1-turbo-260628",
            "doubao-seed-2-0-pro-251215",
            "doubao-seed-1-12-32k-251015-pro",
            "doubao-1-5-pro-256k-250115",
            "doubao-1-5-pro-32k-250115",
            "doubao-seed-2-0-lite-260428",
            "doubao-seed-2-0-lite-251215",
            "doubao-seed-2-0-lite-260215",
            "doubao-seed-2-0-mini-251215",
            "doubao-seed-2-0-mini-260215",
            "doubao-1-5-lite-32k-250115",
            "doubao-1-5-lite-96k-250328",
        ],
    },
    "文心": {
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "model": "ernie-4.0-8k-latest",
        "format": "openai",
        "max_tokens": 2048,
        "fallback_models": ["ernie-3.5-8k", "ernie-speed-128k", "ernie-4.0-8k"],
    },
    "混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "model": "hy3-preview",
        "format": "openai",
        "fallback_models": ["hy3", "hy-mt2-pro", "hy-mt2-plus", "hy-mt2-lite", "hy-role"],
    },
    "DeepSeek": {
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "format": "openai",
        "fallback_models": ["deepseek-reasoner"],
    },
    "智谱清言": {
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "ZHIPU_API_KEY",
        "model": "glm-4-flash",
        "format": "openai",
        "fallback_models": ["glm-4.7", "glm-4-plus", "glm-4-air"],
    },
    "MiniMax": {
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model": "MiniMax-Text-01",
        "format": "minimax",
        "fallback_models": ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "abab6.5s-chat", "abab6.5-chat"],
    },
}

# ============ Prompt模板（含详细分析指导） ============

PROMPT_TEMPLATE = """你是一位资深足球赛事分析师。请严格按以下步骤完成分析后输出JSON。

## 第一步：联网搜索分析（必须执行）

对每场比赛，请联网搜索以下信息：
1. **双方近期战绩**：近10场正式比赛的胜平负记录
2. **交锋记录**：双方近5次直接交锋结果
3. **主客场表现**：主队主场胜率、客队客场胜率
4. **伤停情报**：关键球员缺阵情况

## 第二步：赔率深度分析

基于提供的赔率数据：
1. **相同赔率历史统计**：搜索与当前胜平负赔率组合（误差±0.10）相似的历史场次至少30场，统计主胜/平/客胜的实际出现比例
2. **让球盘口分析**：搜索相同让球盘口的历史赢盘率（至少30场），判断上盘/下盘哪个更值得关注
3. **大小球分析**：搜索相同大小球盘口的历史概率（至少50场），判断进球数倾向
4. **赔率异动**：如能查到初盘与即时盘的差异，分析资金流向

## 第三步：综合判断

结合基本面和赔率数据：
- 当历史统计与赔率隐含概率一致时，按赔率方向判断
- 当历史统计明显偏离赔率时（如历史主胜65%但赔率暗示45%），优先参考历史数据
- 强队客场让球浅（0.5以下）时，警惕冷门
- **任9选择**：从所有比赛中，独立选出你认为最有把握、最稳定的9场比赛（不是共识，是你自己的判断）

## 编码规则

【胜平负】3=主胜, 1=平局, 0=客负
【半全场】33=胜胜, 31=胜平, 30=胜负, 13=平胜, 11=平平, 10=平负, 03=负胜, 01=负平, 00=负负
【进球数】0=0球, 1=1球, 2=2球, 3=3球及以上

## 比赛数据

{match_data}

## 赔率数据

{odds_data}

## 输出要求

只输出以下JSON，不要任何分析过程或其他文字：
```json
{{
  "predictions": [
    {{"match": "1", "spf": "3", "handicap": "3", "rq_number": -1, "bf": "2:1", "zjq": "2", "bqc": "33"}},
    {{"match": "2", "spf": "1", "handicap": "0", "rq_number": -1, "bf": "1:1", "zjq": "2", "bqc": "11"}}
  ],
  "ren9": ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
  "confidence": "高"
}}
```

**重要说明**：
- predictions数组必须包含所有{match_count}场比赛的预测
- spf/handicap只选一个值(3/1/0)
- bf为精确比分（如2:1）
- zjq为总进球数(0/1/2/3)
- bqc为半全场编码（如33=胜胜）
- **ren9：你必须独立选出你认为最有把握的9场比赛编号**（从1到{match_count}中选9个，代表你最看好的9场）
- confidence为整体信心度(高/中/低)"""

# ============ 体彩API数据获取 ============

def fetch_sporttery_data(game_type):
    """从体彩API获取比赛数据
    使用 getMatchCalculatorV1 获取当前在售赛事（含赔率）
    使用 getFootBallDrawInfoV2 获取期次信息
    """
    game_num = GAME_NUM_MAP.get(game_type, 90)
    
    # 1. 获取期次信息
    issue_num = None
    try:
        url1 = f"https://webapi.sporttery.cn/gateway/lottery/getFootBallDrawInfoV2.qry?isVerify=1&param={game_num},0"
        resp1 = requests.get(url1, headers=SPORTTERY_HEADERS, timeout=15)
        resp1.raise_for_status()
        data1 = resp1.json()
        val1 = data1.get("value", {})
        
        # 从列表中找到当前在售期次
        key_map = {"胜负彩": "sfclist", "任9": "sfclist", "半全场": "bqclist", "进球彩": "jqclist"}
        list_key = key_map.get(game_type, "sfclist")
        sale_list = val1.get(list_key, [])
        for item in sale_list:
            if item.get("onSale") == 1:
                issue_num = item.get("lotteryDrawNum")
                break
        
        # 也从detail中获取
        detail_key = list_key.replace("list", "Detail")
        detail = val1.get(detail_key, {})
        if not issue_num and detail.get("lotteryDrawNum"):
            issue_num = detail.get("lotteryDrawNum")
            
        print(f"期次信息: {issue_num or '未知'}")
    except Exception as e:
        print(f"获取期次信息失败: {e}")
    
    # 2. 获取当前在售赛事（含赔率）- 使用竞彩足球接口
    try:
        url2 = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode=HAD,HHAD&channel=c"
        resp2 = requests.get(url2, headers=SPORTTERY_HEADERS, timeout=15)
        resp2.raise_for_status()
        data2 = resp2.json()
        
        if data2.get("value") and data2["value"].get("matchInfoList"):
            match_list = data2["value"]["matchInfoList"]
            # 附加期次信息到每个match
            if issue_num:
                for group in match_list:
                    for m in group.get("subMatchList", []):
                        m["_issue"] = issue_num
            return match_list
        return None
    except Exception as e:
        print(f"获取赛事数据失败: {e}")
        traceback.print_exc()
        return None


def parse_match_data(api_data, game_type):
    """解析API返回的比赛数据"""
    if not api_data:
        return [], []

    matches = []
    odds_list = []

    # 展开 subMatchList
    all_matches = []
    if isinstance(api_data, list):
        for item in api_data:
            if isinstance(item, dict) and 'subMatchList' in item:
                all_matches.extend(item['subMatchList'])
            elif isinstance(item, dict):
                all_matches.append(item)

    max_matches = 14 if game_type in ("胜负彩", "任9") else 6 if game_type == "半全场" else 4

    for i, match in enumerate(all_matches[:max_matches]):
        match_num = str(i + 1)

        home_team = match.get("homeTeamAbbName", match.get("homeTeamName", f"主队{i+1}"))
        away_team = match.get("awayTeamAbbName", match.get("awayTeamName", f"客队{i+1}"))
        league = match.get("leagueName", match.get("groupName", ""))
        match_time = match.get("matchDate", "")
        match_num_str = match.get("matchNum", "")

        matches.append({
            "num": match_num,
            "league": league,
            "home": home_team,
            "away": away_team,
            "time": match_time,
            "id": f"match_{match_num}",
            "issue": match.get("_issue", str(match_num_str)),
        })

        # 提取赔率
        spf_odds = {}
        handicap_odds = {}
        handicap_num = 0

        # 从had字段获取胜平负赔率
        had = match.get("had", {})
        if had:
            spf_odds["win"] = float(had.get("h", 0))
            spf_odds["draw"] = float(had.get("d", 0))
            spf_odds["lose"] = float(had.get("a", 0))

        # 从hhad字段获取让球赔率
        hhad = match.get("hhad", {})
        if hhad:
            try:
                handicap_num = int(float(hhad.get("goalLineValue", 0)))
            except (ValueError, TypeError):
                handicap_num = 0
            handicap_odds["win"] = float(hhad.get("h", 0))
            handicap_odds["draw"] = float(hhad.get("d", 0))
            handicap_odds["lose"] = float(hhad.get("a", 0))

        # 备用: 从poolList获取
        pool_list = match.get("poolList", [])
        for pool in pool_list:
            pool_code = pool.get("poolCode", "")
            if pool_code == "HAD" and not spf_odds:
                for odds in pool.get("oddsList", []):
                    if odds.get("code") == "H": spf_odds["win"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "D": spf_odds["draw"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "A": spf_odds["lose"] = float(odds.get("odds", 0))
            elif pool_code == "HHAD" and not handicap_odds:
                try:
                    handicap_num = int(float(pool.get("fixedOdds", 0)))
                except (ValueError, TypeError):
                    handicap_num = 0
                for odds in pool.get("oddsList", []):
                    if odds.get("code") == "H": handicap_odds["win"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "D": handicap_odds["draw"] = float(odds.get("odds", 0))
                    elif odds.get("code") == "A": handicap_odds["lose"] = float(odds.get("odds", 0))

        odds_list.append({
            "num": match_num,
            "spf": spf_odds,
            "handicap": handicap_odds,
            "handicap_num": handicap_num,
        })

    return matches, odds_list


def build_prompt(matches, odds_list, game_type):
    """构建AI prompt"""
    match_lines = []
    for m in matches:
        league_tag = f"[{m['league']}]" if m['league'] else ""
        match_lines.append(f"{m['num']}. {league_tag} {m['home']} vs {m['away']} ({m['time']})")
    match_data = "\n".join(match_lines)

    odds_lines = []
    for o in odds_list:
        spf = o.get("spf", {})
        hc = o.get("handicap", {})
        hn = o.get("handicap_num", 0)
        spf_str = f"胜{spf.get('win', '-')} 平{spf.get('draw', '-')} 负{spf.get('lose', '-')}"
        hc_str = f"让{hn}球 胜{hc.get('win', '-')} 平{hc.get('draw', '-')} 负{hc.get('lose', '-')}"
        odds_lines.append(f"{o['num']}. {spf_str} | {hc_str}")
    odds_data = "\n".join(odds_lines)

    prompt = PROMPT_TEMPLATE.format(
        match_data=match_data,
        odds_data=odds_data,
        match_count=len(matches),
    )
    return prompt


# ============ AI调用 ============

def call_ai(ai_name, prompt):
    """调用指定AI生成预测"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        raise Exception(f"未知AI: {ai_name}")

    fmt = config["format"]

    if fmt == "template":
        return generate_template_prediction(prompt)

    key = os.environ.get(config["key_env"], "")
    if not key:
        raise Exception(f"{ai_name} API Key未配置 ({config['key_env']})")

    rate_limit_kw = ["Arrearage", "Overdue", "quota", "QuotaExceeded", "insufficient",
                     "SetLimitExceeded", "LimitExceeded", "ServerOverloaded",
                     "RequestBurstTooFast", "RateLimitExceeded", "TooManyRequests", "429",
                     "Payment Required"]

    models_to_try = [config["model"]]
    if config.get("fallback_models"):
        models_to_try.extend(config["fallback_models"])

    last_error = None
    for i, model in enumerate(models_to_try):
        try:
            max_tokens = config.get("max_tokens", 4000)
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": max_tokens,
            }

            if fmt == "openai":
                payload["model"] = model
                resp = requests.post(
                    config["url"],
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload, timeout=90,
                )
            elif fmt == "minimax":
                payload["model"] = model
                resp = requests.post(
                    config["url"],
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload, timeout=90,
                )
            else:
                raise Exception(f"未知格式: {fmt}")

            resp.raise_for_status()
            result = resp.json()

            if fmt == "openai":
                content = result["choices"][0]["message"]["content"]
            elif fmt == "minimax":
                # MiniMax v2 API returns choices directly
                choices = result.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                else:
                    # Fallback for older API format
                    content = result.get("reply", {}).get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise Exception("MiniMax返回空内容")
            else:
                content = str(result)

            return parse_ai_response(content)

        except Exception as e:
            last_error = e
            err_msg = str(e)
            is_rate_limit = any(kw in err_msg for kw in rate_limit_kw)
            if is_rate_limit and i < len(models_to_try) - 1:
                print(f"  {ai_name} 模型 {model} 失败，切换 {models_to_try[i+1]}")
                continue
            else:
                raise Exception(f"{ai_name} 调用失败: {last_error}")

    raise Exception(f"{ai_name} 所有模型都失败: {last_error}")


def generate_template_prediction(prompt):
    """扣子模板预测 - 基于赔率"""
    odds_pattern = r"(\d+)\.\s*胜([\d.]+)\s*平([\d.]+)\s*负([\d.]+)"
    found = re.findall(odds_pattern, prompt)

    predictions = []
    for m in found:
        num, win, draw, lose = m
        win, draw, lose = float(win), float(draw), float(lose)
        min_odds = min(win, draw, lose)
        if min_odds == win: spf = "3"
        elif min_odds == draw: spf = "1"
        else: spf = "0"

        predictions.append({
            "match": num, "spf": spf, "handicap": spf, "rq_number": 0,
            "bf": "1:0" if spf == "3" else "0:0" if spf == "1" else "0:1",
            "zjq": "1" if spf == "3" else "0" if spf == "1" else "1",
            "bqc": "33" if spf == "3" else "11" if spf == "1" else "00",
        })

    return {
        "predictions": predictions,
        "ren9": [p["match"] for p in predictions[:9]],
        "confidence": "中",
    }


def parse_ai_response(content):
    """解析AI返回的JSON"""
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return {"predictions": [], "ren9": [], "confidence": "低"}


# ============ 数据库操作 ============

def save_predictions(game_type, ai_name, predictions_data, matches_info=None):
    """保存预测结果"""
    if not DATABASE_URL:
        print("DATABASE_URL 未配置，跳过保存")
        return

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
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
                game_type, ai_name,
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
    """获取预测数据，返回前端期望的格式"""
    if not DATABASE_URL:
        return []

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ai_name, predictions, matches_info, ren9
                FROM traditional_predictions
                WHERE game_type = %s
                ORDER BY created_at DESC
                LIMIT 7
            """, (game_type,))
            rows = cur.fetchall()
            if not rows:
                return []

            matches_info = rows[0][2] if rows[0][2] else []
            if isinstance(matches_info, str):
                matches_info = json.loads(matches_info)

            field_map = {"胜负彩": "spf", "任9": "spf", "半全场": "bqc", "进球彩": "zjq"}
            field_key = field_map.get(game_type, "spf")

            results = []
            for idx, match in enumerate(matches_info):
                for row in rows:
                    ai_name = row[0]
                    predictions = row[1] if isinstance(row[1], list) else json.loads(row[1]) if row[1] else []
                    ren9 = row[3] if isinstance(row[3], list) else json.loads(row[3]) if row[3] else []
                    pred_obj = predictions[idx] if idx < len(predictions) else {}

                    if isinstance(pred_obj, dict):
                        prediction = pred_obj.get(field_key, "")
                    else:
                        prediction = str(pred_obj)

                    # 检查该比赛是否在该AI的任9选择中
                    match_num = str(idx + 1)
                    in_ren9 = match_num in [str(x) for x in ren9]

                    results.append({
                        "match_id": match.get("id", f"match_{idx+1}"),
                        "home_team": match.get("home", "未知"),
                        "away_team": match.get("away", "未知"),
                        "league": match.get("league", ""),
                        "match_time": match.get("time", ""),
                        "ai_name": ai_name,
                        "prediction": prediction,
                        "issue": match.get("issue", ""),
                        "in_ren9": in_ren9,  # 是否在该AI的任9选择中
                        "ren9": ren9,  # 该AI选择的9场编号
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

    if not force:
        existing = get_predictions(game_type)
        if existing and len(existing) >= 7:
            print(f"已有预测，使用 --force 强制刷新")
            return {"status": "skipped", "data": existing}

    print(f"获取体彩API数据...")
    api_data = fetch_sporttery_data(game_type)
    if not api_data:
        return {"status": "error", "message": "获取体彩API数据失败"}

    matches, odds_list = parse_match_data(api_data, game_type)
    if not matches:
        return {"status": "error", "message": "没有可用的比赛数据"}

    print(f"获取到 {len(matches)} 场比赛")
    prompt = build_prompt(matches, odds_list, game_type)

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
            results.append({"ai_name": ai_name, "error": str(e)})

    return {
        "status": "success",
        "game_type": game_type,
        "matches": matches,
        "predictions": results,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="传统足彩7AI预测")
    parser.add_argument("--game", choices=["胜负彩", "任9", "半全场", "进球彩"], default="胜负彩")
    parser.add_argument("--force", action="store_true", help="强制刷新")
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
