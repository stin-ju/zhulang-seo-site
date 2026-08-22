import sys
sys.path.insert(0, '/workspace/projects/JC')
import psycopg2
from datetime import datetime
import auto_settle as A

conn = psycopg2.connect('postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

cur = conn.cursor()
cur.execute("SELECT id, sport_type, home_team, away_team, status, metadata FROM matches WHERE id IN ('20260822_周五301','20260822_周五302','20260822_周五303')")
for r in cur.fetchall():
    md = r[5] if r[5] else {}
    print('ROW:', r[0], r[1], r[2], 'vs', r[3], 'status=', r[4], 'match_time=', md.get('match_time'))
    print('  home_score=', md.get('home_score'), 'away_score=', md.get('away_score'),
          'score_unavailable=', md.get('score_unavailable'), 'inner_status=', md.get('status'))

print()
print('=== test fetch basketball 2026-08-22 ===')
matches = A.fetch_scores('basketball', '2026-08-22')
print(f'got {len(matches)} completed matches')
for m in matches:
    if m.get('league') == 'WNBA':
        print(f"  {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}")

# Test find_match
print()
print('=== test matching ===')
for db_home, db_away in [('神秘人','天猫'), ('天空','女武神'), ('节奏','火焰')]:
    found = A.find_match_in_titan_data(db_home, db_away, matches)
    if found:
        print(f"  MATCH {db_home} vs {db_away} -> {found['home_team']} {found['home_score']}-{found['away_score']} {found['away_team']}")
    else:
        print(f"  NO MATCH for {db_home} vs {db_away}")

cur.close()
conn.close()
