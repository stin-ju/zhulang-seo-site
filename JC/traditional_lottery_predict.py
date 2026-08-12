#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2
import json
import re
import requests
from datetime import datetime

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres")

AI_CONFIGS = {
    "DeepSeek": {"url": "https://api.deepseek.com/v1/chat/completions", "key": os.environ.get("DEEPSEEK_API_KEY", "REMOVED"), "model": "deepseek-chat"},
    "MiniMax": {"url": "https://api.minimaxi.com/v1/chat/completions", "key": os.environ.get("MINIMAX_API_KEY", ""), "model": "MiniMax-Text-01"},
    "豆包": {"url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "key": os.environ.get("DOUBAO_API_KEY", ""), "model": "ep-20260706041055-2mgpf"},
    "智谱清言": {"url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "key": os.environ.get("ZHIPU_API_KEY", ""), "model": "glm-4-flash"},
    "文心": {"url": "https://qianfan.baidubce.com/v2/chat/completions", "key": os.environ.get("WENXIN_API_KEY", ""), "model": "ernie-4.0-8k-latest"},
    "混元": {"url": "https://tokenhub.tencentmaas.com/v1/chat/completions", "key": os.environ.get("HUNYUAN_API_KEY", ""), "model": "hy-mt2-lite"},
    "扣子": {"url": "https://7hsjv6c4cn.coze.site/stream_run", "key": os.environ.get("COZE_PROJECT_API_TOKEN", ""), "model": None},
}

def call_ai(ai_name, prompt):
    cfg = AI_CONFIGS.get(ai_name)
    if not cfg:
        return None
    try:
        headers = {"Content-Type": "application/json"}
        if cfg["key"]:
            headers["Authorization"] = f"Bearer {cfg[key]}"
        payload = {"model": cfg["model"], "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 800}
        resp = requests.post(cfg["url"], json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"]
        return None
    except Exception as e:
        print(f"  [{ai_name}] Error: {e}", file=sys.stderr)
        return None

def get_ct_matches(conn, game_type):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, home_team, away_team, metadata FROM matches
        WHERE metadata->>'match_type' = 'ct'
          AND metadata->>'game_type' = %s
          AND metadata->>'status' IN ('on_sale', '已确认')
          AND metadata->>'match_date' >= CURRENT_DATE::text
        ORDER BY metadata->>'match_date', id
    """, (game_type,))
    rows = cur.fetchall()
    conn.commit()
    matches = []
    for row in rows:
        meta = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}
        matches.append({"id": row[0], "home_team": row[1], "away_team": row[2], "metadata": meta})
    return matches

def main():
    game_type = "胜负彩"
    force = False
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--game" and i + 1 < len(sys.argv):
            game_type = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--force":
            force = True
            i += 1
        else:
            i += 1
    conn = psycopg2.connect(DB_URL)
    matches = get_ct_matches(conn, game_type)
    if not matches:
        print(json.dumps({"status": "ok", "game_type": game_type, "message": f"没有找到{game_type}的在售比赛", "predictions": 0}, ensure_ascii=False))
        conn.close()
        return
    cur = conn.cursor()
    match_ids = [m["id"] for m in matches]
    cur.execute("SELECT match_id, ai_name FROM traditional_predictions WHERE match_id = ANY(%s) AND game_type = %s", (match_ids, game_type))
    existing = set()
    for row in cur.fetchall():
        existing.add((row[0], row[1]))
    conn.commit()
    total_created = 0
    total_errors = 0
    for match in matches:
        mid = match["id"]
        teams = f"{match['home_team']} vs {match['away_team']}"
        missing_ais = [ai for ai in AI_CONFIGS if (mid, ai) not in existing]
        if not missing_ais and not force:
            continue
        if force:
            missing_ais = list(AI_CONFIGS.keys())
        prompt = f"你是专业传统足彩分析师。请为以下{game_type}比赛生成预测。\n比赛: {teams}\n联赛: {match['metadata'].get('league', '未知')}\n比赛时间: {match['metadata'].get('match_time', '')}\n请用JSON格式输出预测: {{\"prediction\": \"你的预测\", \"confidence\": 0.7, \"analysis\": \"50字内分析\"}}"
        for ai_name in missing_ais:
            try:
                result = call_ai(ai_name, prompt)
                if result:
                    try:
                        json_match = re.search(r{[^}]+}, result, re.DOTALL)
                        if json_match:
                            pred_data = json.loads(json_match.group())
                        else:
                            pred_data = {"prediction": result[:100], "confidence": 0.5, "analysis": ""}
                    except json.JSONDecodeError:
                        pred_data = {"prediction": result[:100], "confidence": 0.5, "analysis": ""}
                    cur.execute("INSERT INTO traditional_predictions (id, match_id, ai_name, game_type, prediction, analysis, confidence) VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM traditional_predictions), %s, %s, %s, %s, %s, %s)", (mid, ai_name, game_type, json.dumps(pred_data.get("prediction", ""), ensure_ascii=False), pred_data.get("analysis", ""), str(pred_data.get("confidence", 0.5))))
                    conn.commit()
                    total_created += 1
                    print(f"  [OK] {mid} {ai_name}")
                else:
                    total_errors += 1
            except Exception as e:
                print(f"  [FAIL] {mid} {ai_name}: {e}", file=sys.stderr)
                total_errors += 1
    conn.close()
    print(json.dumps({"status": "ok", "game_type": game_type, "matches": len(matches), "predictions_created": total_created, "errors": total_errors}, ensure_ascii=False))

if __name__ == "__main__":
    main()
