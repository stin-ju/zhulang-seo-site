#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2
import json
from datetime import datetime, timedelta

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres")

def check_db():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM matches")
        match_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM predictions")
        pred_count = cur.fetchone()[0]
        conn.close()
        return {"status": "ok", "matches": match_count, "predictions": pred_count}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def check_prediction_coverage():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        today = datetime.utcnow() + timedelta(hours=8)
        today_str = today.strftime("%Y-%m-%d")
        tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        cur.execute("""
            SELECT m.id, m.home_team, m.away_team, m.metadata->>'match_date' as match_date,
                   COUNT(p.id) as pred_count
            FROM matches m
            LEFT JOIN predictions p ON p.match_id = m.id
            WHERE m.metadata->>'status' IN ('on_sale', '已确认')
              AND m.metadata->>'match_date' >= %s
              AND m.metadata->>'match_date' <= %s
              AND (m.metadata->>'match_type' IS NULL OR m.metadata->>'match_type' != 'ct')
            GROUP BY m.id, m.home_team, m.away_team, m.metadata->>'match_date'
            ORDER BY m.metadata->>'match_date', m.id
        """, (today_str, tomorrow_str))
        rows = cur.fetchall()
        conn.close()
        total = len(rows)
        missing = []
        covered = 0
        for row in rows:
            match_id, home, away, match_date, pred_count = row
            if pred_count < 3:
                missing.append({"id": match_id, "teams": f"{home} vs {away}", "date": match_date, "ai_count": pred_count})
            else:
                covered += 1
        return {"status": "ok" if not missing else "warning", "total": total, "covered": covered, "missing_count": len(missing), "missing": missing[:10]}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def check_score_completeness():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        now = datetime.utcnow() + timedelta(hours=8)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%S")
        cur.execute("""
            SELECT id, home_team, away_team, metadata->>'match_time' as match_time
            FROM matches
            WHERE status IN ('已完赛', '已开赛')
              AND metadata->>'match_time' < %s
              AND (metadata->>'home_score' IS NULL OR metadata->>'away_score' IS NULL)
              AND (metadata->>'status' != '已取消')
            ORDER BY metadata->>'match_time' DESC LIMIT 20
        """, (now_str,))
        rows = cur.fetchall()
        conn.close()
        missing = [{"id": r[0], "teams": f"{r[1]} vs {r[2]}", "time": r[3]} for r in rows]
        return {"status": "ok" if not missing else "warning", "missing_count": len(missing), "missing": missing}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def check_brief_status():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT id, brief_date, created_at FROM briefs ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"status": "warning", "message": "无任何简报记录"}
        brief_date = str(row[1]) if row[1] else ""
        today = datetime.utcnow() + timedelta(hours=8)
        today_str = today.strftime("%Y-%m-%d")
        if brief_date >= today_str:
            return {"status": "ok", "latest_date": brief_date}
        else:
            days_behind = (today - datetime.strptime(brief_date, "%Y-%m-%d")).days if brief_date else -1
            return {"status": "warning", "latest_date": brief_date, "days_behind": days_behind}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def main():
    results = {"timestamp": datetime.now().isoformat(), "checks": {}}
    results["checks"]["database"] = check_db()
    results["checks"]["prediction_coverage"] = check_prediction_coverage()
    results["checks"]["score_completeness"] = check_score_completeness()
    results["checks"]["brief_status"] = check_brief_status()
    statuses = [c.get("status") for c in results["checks"].values()]
    if "error" in statuses:
        results["status"] = "ERROR"
        results["anomaly_count"] = statuses.count("error")
    elif "warning" in statuses:
        results["status"] = "WARNING"
        results["anomaly_count"] = statuses.count("warning")
    else:
        results["status"] = "OK"
        results["anomaly_count"] = 0
    print(json.dumps(results, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()
