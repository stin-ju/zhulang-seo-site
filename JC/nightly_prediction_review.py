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
        SELECT m.id, m.home_team, m.away_team, m.metadata->>'league' as league,
               m.status, m.metadata->>'match_time' as match_time,
               COUNT(p.id) as pred_count
        FROM matches m
        LEFT JOIN predictions p ON p.match_id = m.id
        WHERE m.metadata->>'match_date' = %s
          AND (m.metadata->>'match_type' IS NULL OR m.metadata->>'match_type' != 'ct')
        GROUP BY m.id, m.home_team, m.away_team, m.metadata->>'league', m.status, m.metadata->>'match_time'
        ORDER BY m.metadata->>'match_time'
    """, (today_str,))
    matches = cur.fetchall()
    issues = []
    for m in matches:
        match_id, home, away, league, status, match_time, pred_count = m
        if pred_count == 0:
            issues.append({"type": "no_prediction", "match_id": match_id, "teams": f"{home} vs {away}", "league": league or "", "status": status})
        elif pred_count < 5:
            issues.append({"type": "low_coverage", "match_id": match_id, "teams": f"{home} vs {away}", "league": league or "", "ai_count": pred_count})
    conn.close()
    result = {"date": today_str, "total_matches": len(matches), "issues_found": len(issues), "issues": issues, "status": "OK" if not issues else "WARNING"}
    print(json.dumps(result, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()
