#!/usr/bin/env python3
"""
discover_matches.py - 比赛发现 + 赔率抓取
从 sporttery.cn 抓取在售比赛，对比数据库已有比赛，增量入库。
（等待上传实际脚本替换）
"""
import os
import sys
import json
import psycopg2
from sporttery_client import get_matches, parse_match

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)

def get_existing_ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM matches")
        return {row[0] for row in cur.fetchall()}

def discover():
    conn = get_db()
    existing = get_existing_ids(conn)
    raw_matches = get_matches()
    
    new_count = 0
    update_count = 0
    
    for day_group in raw_matches:
        for item in day_group.get("subMatchList", []):
            parsed = parse_match(item)
            mid = parsed["id"]
            
            if mid in existing:
                # 更新赔率
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE matches SET 
                            win_odds=%s, draw_odds=%s, lose_odds=%s,
                            handicap_win_odds=%s, handicap_draw_odds=%s, handicap_lose_odds=%s,
                            handicap=%s, status=%s
                        WHERE id=%s
                    """, (
                        parsed["win_odds"], parsed["draw_odds"], parsed["lose_odds"],
                        parsed["handicap_win_odds"], parsed["handicap_draw_odds"], parsed["handicap_lose_odds"],
                        parsed["handicap"], "on_sale", mid
                    ))
                update_count += 1
            else:
                # 插入新比赛
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO matches (id, teams, match_time, handicap, status,
                            win_odds, draw_odds, lose_odds,
                            handicap_win_odds, handicap_draw_odds, handicap_lose_odds,
                            sport_type, match_date, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        mid, parsed["teams"], parsed["match_time"], parsed["handicap"], "on_sale",
                        parsed["win_odds"], parsed["draw_odds"], parsed["lose_odds"],
                        parsed["handicap_win_odds"], parsed["handicap_draw_odds"], parsed["handicap_lose_odds"],
                        "football", parsed["match_time"].split(" ")[0],
                        json.dumps({"league": parsed["league"], "source": "sporttery.cn"})
                    ))
                new_count += 1
    
    conn.commit()
    conn.close()
    
    result = {"new": new_count, "updated": update_count, "total_existing": len(existing)}
    print(json.dumps(result))
    return result

if __name__ == "__main__":
    discover()
