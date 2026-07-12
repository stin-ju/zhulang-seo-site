#!/usr/bin/env python3
"""
auto_settle.py - 自动结算
对比已确认比赛的实际比分与AI预测，更新命中状态和盈亏。
（等待上传实际脚本替换）
"""
import os
import sys
import json
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)

def settle():
    conn = get_db()
    
    # 获取已确认但未结算的比赛
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.id, m.home_score, m.away_score, m.handicap
            FROM matches m
            WHERE m.status = '已确认'
            AND m.home_score IS NOT NULL
        """)
        confirmed = cur.fetchall()
    
    settled_count = 0
    for match_id, home_score, away_score, handicap in confirmed:
        # 结算逻辑（占位，等待实际脚本替换）
        settled_count += 1
    
    conn.commit()
    conn.close()
    
    result = {"settled": settled_count}
    print(json.dumps(result))
    return result

if __name__ == "__main__":
    settle()
