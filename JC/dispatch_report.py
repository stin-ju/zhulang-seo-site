#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2
import json
from datetime import datetime, timedelta

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres")

def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    now = datetime.utcnow() + timedelta(hours=8)
    today_str = now.strftime("%Y-%m-%d")
    
    cur.execute("""
        SELECT COUNT(*) FROM matches
        WHERE metadata->>'match_date' = %s
          AND (metadata->>'match_type' IS NULL OR metadata->>'match_type' != 'ct')
    """, (today_str,))
    today_total = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(DISTINCT m.id) FROM matches m
        JOIN predictions p ON p.match_id = m.id
        WHERE m.metadata->>'match_date' = %s
          AND (m.metadata->>'match_type' IS NULL OR m.metadata->>'match_type' != 'ct')
    """, (today_str,))
    today_predicted = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM matches
        WHERE metadata->>'match_date' = %s
          AND status = '已完赛'
          AND (metadata->>'match_type' IS NULL OR metadata->>'match_type' != 'ct')
    """, (today_str,))
    today_settled = cur.fetchone()[0]
    
    cur.execute("""
        SELECT p.ai_name, COUNT(*) as total,
               SUM(CASE WHEN p.is_settled = true AND p.hit_status->>'spf' = 'true' THEN 1 ELSE 0 END) as hits
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        WHERE m.metadata->>'match_date' >= (CURRENT_DATE - INTERVAL '7 days')::text
          AND p.sport_type = 'football'
        GROUP BY p.ai_name ORDER BY p.ai_name
    """)
    ai_stats = cur.fetchall()
    
    cur.execute("SELECT COUNT(*) FROM predictions WHERE is_settled = false")
    unsettled = cur.fetchone()[0]
    
    conn.close()
    
    report = {
        "date": today_str,
        "today": {"total_matches": today_total, "predicted": today_predicted, "settled": today_settled},
        "unsettled_predictions": unsettled,
        "ai_stats_7days": [{"ai": s[0], "total": s[1], "hits": s[2], "rate": f"{s[2]/s[1]*100:.1f}%" if s[1] > 0 else "-"} for s in ai_stats]
    }
    print(json.dumps(report, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()
