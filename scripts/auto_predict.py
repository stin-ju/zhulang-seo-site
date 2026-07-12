#!/usr/bin/env python3
"""
auto_predict.py - 7AI预测调度
为待预测比赛调用7个AI生成预测，写入predictions表。
（等待上传实际脚本替换）
"""
import os
import sys
import json
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "")

AI_LIST = ["混元", "豆包", "DeepSeek", "MiniMax", "扣子", "BetAgent", "Grok"]

def get_db():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)

def get_pending_matches(conn):
    """获取有赔率但缺少预测的比赛"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.id, m.teams, m.match_time, m.handicap,
                   m.win_odds, m.draw_odds, m.lose_odds
            FROM matches m
            WHERE m.status = 'on_sale'
            AND m.win_odds IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM predictions p WHERE p.match_id = m.id
            )
            ORDER BY m.match_time ASC
        """)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def predict_match(match):
    """为单场比赛生成7个AI预测（占位，等待实际脚本替换）"""
    predictions = []
    for ai_name in AI_LIST:
        predictions.append({
            "match_id": match["id"],
            "ai_name": ai_name,
            "spf": "胜",  # 占位
            "handicap_spf": "让胜",
            "score": "1-0",
            "goals": 1,
            "half_full": "胜胜",
            "analysis": f"{ai_name} 预测分析（待替换为实际AI输出）",
            "sport_type": "football"
        })
    return predictions

def run_predict():
    conn = get_db()
    pending = get_pending_matches(conn)
    
    total_predictions = 0
    for match in pending:
        preds = predict_match(match)
        with conn.cursor() as cur:
            for p in preds:
                cur.execute("""
                    INSERT INTO predictions (match_id, ai_name, spf, handicap_spf, score, goals, half_full, analysis, sport_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (p["match_id"], p["ai_name"], p["spf"], p["handicap_spf"], p["score"], p["goals"], p["half_full"], p["analysis"], p["sport_type"]))
                total_predictions += 1
    
    conn.commit()
    conn.close()
    
    result = {"matches_predicted": len(pending), "predictions_created": total_predictions}
    print(json.dumps(result))
    return result

if __name__ == "__main__":
    run_predict()
