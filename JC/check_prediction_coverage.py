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
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    cur.execute("""
        SELECT m.id, m.home_team, m.away_team, m.sport_type,
               m.metadata->>'match_date' as match_date,
               m.metadata->>'league' as league,
               COUNT(p.id) as pred_count,
               array_agg(DISTINCT p.ai_name) FILTER (WHERE p.ai_name IS NOT NULL) as ai_names
        FROM matches m
        LEFT JOIN predictions p ON p.match_id = m.id
        WHERE m.metadata->>'status' IN ('on_sale', '已确认')
          AND m.metadata->>'match_date' >= %s
          AND m.metadata->>'match_date' <= %s
          AND (m.metadata->>'match_type' IS NULL OR m.metadata->>'match_type' != 'ct')
        GROUP BY m.id, m.home_team, m.away_team, m.sport_type, m.metadata->>'match_date', m.metadata->>'league'
        ORDER BY m.metadata->>'match_date', m.id
    """, (today_str, tomorrow_str))
    rows = cur.fetchall()
    conn.close()
    total = len(rows)
    fully_covered = 0
    partially_covered = 0
    uncovered = 0
    details = []
    TARGET_AI_COUNT = 7
    for row in rows:
        match_id, home, away, sport, match_date, league, pred_count, ai_names = row
        ai_list = ai_names if ai_names else []
        if pred_count >= TARGET_AI_COUNT:
            fully_covered += 1
            status = "ok"
        elif pred_count > 0:
            partially_covered += 1
            status = "partial"
        else:
            uncovered += 1
            status = "missing"
        details.append({"id": match_id, "teams": f"{home} vs {away}", "league": league or "", "date": str(match_date), "sport": sport, "ai_count": pred_count, "ai_names": ai_list, "status": status})
    result = {"date": today_str, "total_matches": total, "fully_covered": fully_covered, "partially_covered": partially_covered, "uncovered": uncovered, "target_ai_count": TARGET_AI_COUNT, "status": "OK" if uncovered == 0 and partially_covered == 0 else "WARNING", "details": details}
    print(json.dumps(result, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()
