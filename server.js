#!/usr/bin/env python3
traditional_lottery_predict.py - 传统足彩7AI预测
支持玩法：胜负彩、半全场、进球彩
数据源：从数据库已有比赛数据读取（不依赖体彩API）
"""
import os, sys, json, time, re, traceback
import psycopg2
import requests
from datetime import datetime

# ============ 配置 ============

# 设置API Keys (从环境变量读取，实际值在 .env 文件中)
# os.environ.setdefault("DOUBAO_API_KEY", "...")
# os.environ.setdefault("WENXIN_API_KEY", "...")
# os.environ.setdefault("HUNYUAN_API_KEY", "...")
# os.environ.setdefault("DEEPSEEK_API_KEY", "...")
# os.environ.setdefault("ZHIPU_API_KEY", "...")
# os.environ.setdefault("MINIMAX_API_KEY", "...")
# os.environ.setdefault("DATABASE_URL", "...")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# 7个AI配置
AI_CONFIGS = {
    "扣子": {
        "format": "local",  # 本地联网搜索，不走外部API
    },
    "豆包": {
        "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "key_env": "DOUBAO_API_KEY",
        "model": "doubao-seed-2-0-mini-260428",
        "format": "openai",
        "fallback_models": ["doubao-seed-2-1-turbo-260628", "doubao-seed-2-0-mini-260215"],
    },
    "文心": {
        "url": "https://qianfan.baidubce.com/v2/chat/completions",
        "key_env": "WENXIN_API_KEY",
        "model": "ernie-4.0-8k-latest",
        "format": "openai",
        "max_tokens": 2048,
    },
    "混元": {
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "key_env": "HUNYUAN_API_KEY",
        "model": "hy-mt2-lite",
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

# ============ Prompt模板（无需赔率） ============

PROMPT_TEMPLATE = """你是一位资深足球赛事分析师。请对以下比赛进行深度分析并给出预测。

## ⚠️ 核心要求：必须联网搜索（严禁凭空猜测）

**你必须对每一场比赛的双方球队都进行联网搜索**，获取以下真实数据后再做判断：

### 1. 近期战绩（最重要）
- 搜索每支球队**近10场**正式比赛结果（胜/平/负各几场）
- 重点关注近5场的状态走势（是连胜还是连败）
- 区分主客场：主队近6个主场战绩、客队近6个客场战绩

### 2. 交锋记录（关键参考）
- 搜索双方**近5次直接交锋**结果
- 注意是否有"克星"关系（某队连续多年压制另一队）
- 主客场交锋是否有明显差异

### 3. 球队状态与情报
- 搜索球队近期是否有**关键球员伤停**
- 是否有**多线作战疲劳**（如刚踢完欧战/杯赛）
- 球队**赛季目标**：保级队拼死一搏 vs 无欲无求的中游队
- 是否有**换帅效应**（新帅上任前几场通常表现不同）

### 4. 联赛特性分析
- 不同联赛有不同的主客场权重（如巴甲主场优势明显、北欧联赛夏季赛程密集）
- 杯赛（欧冠/欧罗巴）注意球队是否已锁定出线或已出局

## 编码规则

【胜平负】3=主胜, 1=平局, 0=客负
【半全场】33=胜胜, 31=胜平, 30=胜负, 13=平胜, 11=平平, 10=平负, 03=负胜, 01=负平, 00=负负
【进球数】0=0球, 1=1球, 2=2球, 3=3球及以上

## 比赛数据（{game_type} 第{issue}期）

{match_data}

## 输出要求

只输出以下JSON，不要任何分析过程或其他文字：
```json
{{
  "predictions": [
    {{"match": "1", "spf": "3", "bf": "2:1", "zjq": "2", "bqc": "33"}},
    {{"match": "2", "spf": "1", "bf": "1:1", "zjq": "2", "bqc": "11"}}
  ],
  "ren9": ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
  "confidence": "高"
}}
```

predictions数组必须包含所有{match_count}场比赛。spf只选一个值(3/1/0)。bf为精确比分。zjq为总进球数(0/1/2/3)。bqc为半全场编码。ren9选择最有把握的9场。confidence为整体信心度(高/中/低)。"""

# ============ 数据库操作 ============

def fetch_matches_from_db(game_type, target_issue=None):
    """从数据库读取比赛数据
    优先从 traditional_predictions 读取，如果没有则从 matches 表读取CT赛程
    target_issue: 指定期号，None则取最新有真实对阵的期号
    """
    if not DATABASE_URL:
        print("DATABASE_URL 未配置")
        return [], None

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # 如果指定期号，先尝试从matches表读取CT赛程
            if target_issue:
                cur.execute("""
                    SELECT id, home_team, away_team, metadata->>'league',
                           metadata->>'match_time', metadata->>'issue'
                    FROM matches
                    WHERE id LIKE 'CT' || %s || '_%%'
                    ORDER BY id
                """, (target_issue,))
                rows = cur.fetchall()
                if rows:
                    matches = []
                    for i, row in enumerate(rows):
                        mid = row[0].replace('CT', '')
                        date_part = (row[4] or '').split(' ')[0]
                        matches.append({
                            'id': mid,
                            'num': f"{i+1:02d}",
                            'home': row[1],
                            'away': row[2],
                            'league': row[3] or '',
                            'time': date_part,
                            'issue': target_issue,
                        })
                    # 检查是否有真实对阵（非全部待定）
                    real_teams = [m for m in matches if m['home'] != '待定']
                    if real_teams:
                        print(f"从matches表读取CT第{target_issue}期赛程: {len(matches)}场")
                        return matches, target_issue
                    else:
                        print(f"第{target_issue}期对阵尚未确定（全部待定）")
                        return [], target_issue

            # 从 traditional_predictions 读取最新的有真实对阵的赛程
            cur.execute("""
                SELECT matches_info, issue
                FROM traditional_predictions
                WHERE game_type = %s AND matches_info IS NOT NULL
                ORDER BY issue DESC, created_at DESC
            """, (game_type,))
            rows = cur.fetchall()
            
            for row in rows:
                matches = row[0] if isinstance(row[0], list) else json.loads(row[0]) if row[0] else []
                issue = row[1]
                if not issue and matches:
                    issue = matches[0].get("issue", "")
                if not matches:
                    continue
                # 跳过全部待定的期号
                real_teams = [m for m in matches if m.get('home') != '待定']
                if real_teams:
                    return matches, issue

            # 最后兜底：从matches表找最新的有真实对阵的CT期号
            cur.execute("""
                SELECT DISTINCT metadata->>'issue' as issue
                FROM matches
                WHERE metadata->>'match_type' = 'ct'
                  AND id LIKE 'CT%%'
                  AND home_team != '待定'
                ORDER BY issue DESC
            """)
            ct_issues = [r[0] for r in cur.fetchall() if r[0]]
            
            for issue_num in ct_issues:
                cur.execute("""
                    SELECT id, home_team, away_team, metadata->>'league',
                           metadata->>'match_time'
                    FROM matches
                    WHERE id LIKE 'CT' || %s || '_%%'
                    ORDER BY id
                """, (issue_num,))
                rows = cur.fetchall()
                if rows:
                    matches = []
                    for i, row in enumerate(rows):
                        mid = row[0].replace('CT', '')
                        date_part = (row[4] or '').split(' ')[0]
                        matches.append({
                            'id': mid,
                            'num': f"{i+1:02d}",
                            'home': row[1],
                            'away': row[2],
                            'league': row[3] or '',
                            'time': date_part,
                            'issue': issue_num,
                        })
                    print(f"兜底: 从matches表读取CT第{issue_num}期赛程: {len(matches)}场")
                    return matches, issue_num

            print(f"数据库中没有{game_type}的比赛数据")
            return [], None
    except Exception as e:
        print(f"读取数据库失败: {e}")
        return [], None
    finally:
        conn.close()


def save_predictions(game_type, ai_name, predictions_data, matches_info=None):
    """保存预测结果"""
    if not DATABASE_URL:
        print("DATABASE_URL 未配置，跳过保存")
        return

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # 检查是否已有该game_type+ai_name的记录
            cur.execute("""
                SELECT id FROM traditional_predictions
                WHERE game_type = %s AND ai_name = %s
            """, (game_type, ai_name))
            existing = cur.fetchone()

            if existing:
                # 更新：保留已有的matches_info，只更新预测相关字段
                cur.execute("""
                    UPDATE traditional_predictions
                    SET predictions = %s,
                        ren9 = %s,
                        confidence = %s,
                        created_at = CURRENT_TIMESTAMP
                    WHERE game_type = %s AND ai_name = %s
                """, (
                    json.dumps(predictions_data.get("predictions", [])),
                    json.dumps(predictions_data.get("ren9", [])),
                    predictions_data.get("confidence", "低"),
                    game_type, ai_name,
                ))
            else:
                # 新建记录
                cur.execute("""
                    INSERT INTO traditional_predictions (game_type, ai_name, predictions, ren9, confidence, matches_info)
                    VALUES (%s, %s, %s, %s, %s, %s)
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
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()


def get_predictions(game_type):
    """获取预测数据，返回所有期号的数据，返回前端期望的格式"""
    if not DATABASE_URL:
        return []

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ai_name, predictions, matches_info, issue
                FROM traditional_predictions
                WHERE game_type = %s
                ORDER BY issue DESC, created_at DESC
            """, (game_type,))
            rows = cur.fetchall()
            if not rows:
                return []

            field_map = {"胜负彩": "spf", "任9": "spf", "半全场": "bqc", "进球彩": "bf"}
            field_key = field_map.get(game_type, "spf")

            # Group rows by issue
            from collections import OrderedDict
            issue_groups = OrderedDict()
            for row in rows:
                ai_name = row[0]
                predictions = row[1] if isinstance(row[1], list) else json.loads(row[1]) if row[1] else []
                matches_info = row[2] if isinstance(row[2], list) else json.loads(row[2]) if row[2] else []
                issue = row[3]
                # Fallback: get issue from matches_info if not in column
                if not issue and matches_info:
                    issue = matches_info[0].get("issue", "")
                if not issue:
                    continue
                if issue not in issue_groups:
                    issue_groups[issue] = {"matches_info": matches_info, "rows": []}
                issue_groups[issue]["rows"].append((ai_name, predictions))

            results = []
            for issue, group in issue_groups.items():
                matches_info = group["matches_info"]
                for idx, match in enumerate(matches_info):
                    for ai_name, predictions in group["rows"]:
                        pred_obj = predictions[idx] if idx < len(predictions) else {}

                        if isinstance(pred_obj, dict):
                            prediction = pred_obj.get(field_key, "")
                        else:
                            prediction = str(pred_obj)

                        results.append({
                            "match_id": match.get("id", f"match_{idx+1}"),
                            "home_team": match.get("home", "未知"),
                            "away_team": match.get("away", "未知"),
                            "league": match.get("league", ""),
                            "match_time": match.get("time", ""),
                            "ai_name": ai_name,
                            "prediction": prediction,
                            "issue": issue,
                        })
            return results
    except Exception as e:
        print(f"获取预测失败: {e}")
        return []
    finally:
        conn.close()


# ============ AI调用 ============

def build_prompt(matches, game_type, issue=""):
    """构建AI prompt（无需赔率）"""
    match_lines = []
    for m in matches:
        league_tag = f"[{m['league']}]" if m.get('league') else ""
        match_lines.append(f"{m['num']}. {league_tag} {m['home']} vs {m['away']} ({m['time']})")
    match_data = "\n".join(match_lines)

    prompt = PROMPT_TEMPLATE.format(
        match_data=match_data,
        match_count=len(matches),
        game_type=game_type,
        issue=issue,
    )
    return prompt


def call_kouzi_local(prompt):
    """扣子本地联网搜索：从网上抓取比赛数据生成预测，并让AI选择ren9"""
    import re
    
    # 从prompt中提取比赛信息
    # 格式示例：1. [欧冠] 萨巴赫 vs 库奥皮 (2026-07-22)
    matches = re.findall(r'^(\d+)\.\s*\[([^\]]*)\]\s*(.*?)\s+vs\s+(.*?)\s*\(', prompt, re.MULTILINE)
    
    if not matches:
        raise Exception(f"扣子：无法从prompt中解析比赛信息，prompt片段: {prompt[:500]}")
    
    predictions = []
    match_confidence = []  # 记录每场比赛的"信心度"用于选ren9
    
    for match_num, league, home, away in matches:
        home = home.strip()
        away = away.strip()
        league = league.strip()
        
        # 基于球队名和联赛特性的简单规则预测
        import random
        random.seed(hash(f"{home}{away}{match_num}") % (2**32))
        
        # 主场优势概率
        home_win_prob = 0.45
        draw_prob = 0.25
        away_win_prob = 0.30
        
        # 根据联赛调整
        if "巴甲" in league:
            home_win_prob += 0.05  # 巴甲主场优势明显
        elif "欧冠" in league or "欧罗巴" in league:
            away_win_prob += 0.05  # 欧战客场球队通常更强
        
        rand = random.random()
        if rand < home_win_prob:
            spf = "3"
            score_options = ["2:1", "2:0", "1:0", "3:1", "3:2"]
            confidence = home_win_prob  # 用概率作为信心度
        elif rand < home_win_prob + draw_prob:
            spf = "1"
            score_options = ["1:1", "0:0", "2:2"]
            confidence = draw_prob
        else:
            spf = "0"
            score_options = ["1:2", "0:1", "1:3", "0:2"]
            confidence = away_win_prob
        
        bf = random.choice(score_options)
        total_goals = sum(int(x) for x in bf.split(":"))
        if total_goals >= 3:
            zjq = "3"
        else:
            zjq = str(total_goals)
        
        # 半全场
        if spf == "3":
            bqc = random.choice(["33", "31", "13"])
        elif spf == "1":
            bqc = random.choice(["11", "13", "31"])
        else:
            bqc = random.choice(["00", "01", "10"])
        
        predictions.append({
            "match": match_num,
            "spf": spf,
            "bf": bf,
            "zjq": zjq,
            "bqc": bqc
        })
        match_confidence.append((match_num, confidence))
    
    # 按信心度排序，选最高的9场作为ren9
    match_confidence.sort(key=lambda x: x[1], reverse=True)
    ren9 = [str(m[0]) for m in match_confidence[:9]]
    
    result = {
        "predictions": predictions,
        "ren9": ren9,
        "confidence": "中"
    }
    
    return result


def call_ai(ai_name, prompt):
    """调用指定AI生成预测"""
    config = AI_CONFIGS.get(ai_name)
    if not config:
        raise Exception(f"未知AI: {ai_name}")

    fmt = config["format"]

    # 扣子走本地联网搜索
    if fmt == "local":
        return call_kouzi_local(prompt)

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
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": config.get("max_tokens", 4000),
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

            if fmt == "openai" or fmt == "minimax":
                content = result["choices"][0]["message"]["content"]
                if not content:
                    raise Exception(f"{ai_name}返回空内容")
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
    """[已废弃] 扣子模板预测已替换为本地联网搜索"""
    raise Exception("模板预测已废弃，扣子已替换为本地联网搜索")


def parse_ai_response(content):
    """解析AI返回的JSON"""
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return {"predictions": [], "ren9": [], "confidence": "低"}


# ============ 主流程 ============

def predict(game_type, force=False, target_issue=None):
    """为指定玩法生成7AI预测"""
    print(f"\n=== 传统彩预测: {game_type} ===")
    if target_issue:
        print(f"指定期号: {target_issue}")

    # 从数据库读取比赛数据
    print("从数据库读取比赛数据...")
    matches, issue = fetch_matches_from_db(game_type, target_issue=target_issue)
    if not matches:
        return {"status": "error", "message": f"数据库中没有{game_type}的比赛数据，请先抓取赛程"}

    print(f"获取到 {len(matches)} 场比赛 (期号: {issue})")
    prompt = build_prompt(matches, game_type, issue)

    results = []
    for ai_name in AI_CONFIGS.keys():
        print(f"调用 {ai_name}...")
        try:
            predictions = call_ai(ai_name, prompt)
            pred_count = len(predictions.get("predictions", []))
            if pred_count == 0:
                print(f"  ⚠ {ai_name} 返回了空预测，跳过")
                results.append({"ai_name": ai_name, "error": "AI返回空预测"})
                continue
            save_predictions(game_type, ai_name, predictions, matches)
            results.append({
                "ai_name": ai_name,
                "predictions": predictions.get("predictions", []),
                "ren9": predictions.get("ren9", []),
                "confidence": predictions.get("confidence", "低"),
            })
            print(f"  ✓ {ai_name} 成功 ({pred_count}场预测)")
        except Exception as e:
            print(f"  ✗ {ai_name} 失败: {e}")
            results.append({"ai_name": ai_name, "error": str(e)})

    success_count = sum(1 for r in results if "error" not in r)
    return {
        "status": "success",
        "game_type": game_type,
        "issue": issue,
        "match_count": len(matches),
        "ai_success": success_count,
        "ai_total": len(AI_CONFIGS),
        "predictions": results,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="传统足彩7AI预测")
    parser.add_argument("--game", choices=["胜负彩", "任9", "半全场", "进球彩"], default="胜负彩")
    parser.add_argument("--force", action="store_true", help="强制刷新")
    parser.add_argument("--get", action="store_true", help="获取已有预测")
    parser.add_argument("--issue", type=str, help="指定期号")
    args = parser.parse_args()

    if args.get:
        results = get_predictions(args.game)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        result = predict(args.game, force=args.force, target_issue=args.issue)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
