#!/usr/bin/env python3
"""
调度报告生成器
在每次调度完成后运行，生成状态摘要和异常检测报告
输出: /tmp/dispatch_report.md
"""

import os
import sys
import json
import psycopg2
from datetime import datetime, timedelta, timezone

REPORT_PATH = '/tmp/dispatch_report.md'

def get_db():
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        print('ERROR: DATABASE_URL not set')
        sys.exit(1)
    return psycopg2.connect(dsn)

def query(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows]

def generate_report():
    conn = get_db()
    now = datetime.now(timezone.utc)
    anomalies = []
    lines = []

    lines.append(f'# 调度报告')
    lines.append(f'')
    lines.append(f'**生成时间**: {now.strftime("%Y-%m-%d %H:%M:%S")} UTC')
    lines.append(f'')

    # === 1. 总体统计 ===
    total = query(conn, "SELECT count(*) as cnt FROM matches")
    football = query(conn, "SELECT count(*) as cnt FROM matches WHERE sport_type = 'football'")
    basketball = query(conn, "SELECT count(*) as cnt FROM matches WHERE sport_type = 'basketball'")
    on_sale = query(conn, "SELECT count(*) as cnt FROM matches WHERE metadata->>'status' = 'on_sale'")
    confirmed = query(conn, "SELECT count(*) as cnt FROM matches WHERE metadata->>'status' = 'confirmed'")
    pending = query(conn, "SELECT count(*) as cnt FROM matches WHERE metadata->>'status' = 'pending'")

    lines.append(f'## 总体统计')
    lines.append(f'')
    lines.append(f'| 指标 | 数量 |')
    lines.append(f'|------|------|')
    lines.append(f'| 总比赛数 | {total[0]["cnt"]} |')
    lines.append(f'| 足球 | {football[0]["cnt"]} |')
    lines.append(f'| 篮球 | {basketball[0]["cnt"]} |')
    lines.append(f'| 在售 (on_sale) | {on_sale[0]["cnt"]} |')
    lines.append(f'| 已确认 (confirmed) | {confirmed[0]["cnt"]} |')
    lines.append(f'| 待定 (pending) | {pending[0]["cnt"]} |')
    lines.append(f'')

    # === 2. 联赛分布 ===
    league_dist = query(conn, """
        SELECT metadata->>'league' as league, sport_type, count(*) as cnt
        FROM matches
        WHERE metadata->>'league' IS NOT NULL
        GROUP BY metadata->>'league', sport_type
        ORDER BY cnt DESC
        LIMIT 15
    """)

    if league_dist:
        lines.append(f'## 联赛分布 (Top 15)')
        lines.append(f'')
        lines.append(f'| 联赛 | 类型 | 比赛数 |')
        lines.append(f'|------|------|--------|')
        for row in league_dist:
            lines.append(f'| {row["league"]} | {row["sport_type"]} | {row["cnt"]} |')
        lines.append(f'')

    # === 3. Pending 比赛清单 ===
    pending_matches = query(conn, """
        SELECT id, home_team, away_team, sport_type, metadata,
               metadata->>'match_time' as match_time,
               metadata->>'league' as league,
               EXTRACT(EPOCH FROM (NOW() - (metadata->>'match_time')::timestamp))/3660 as hours_since_match
        FROM matches
        WHERE metadata->>'status' = 'pending'
        ORDER BY metadata->>'match_time' ASC
    """)

    lines.append(f'## Pending 比赛 ({len(pending_matches)}场)')
    lines.append(f'')

    if pending_matches:
        lines.append(f'| ID | 联赛 | 对阵 | 开赛时间 | 已pending时长 |')
        lines.append(f'|-----|------|------|----------|---------------|')
        for m in pending_matches:
            hours = m.get('hours_since_match', 0) or 0
            hours_str = f'{abs(hours):.1f}h'
            league = m.get('league', '-') or '-'
            teams = f"{m['home_team']} vs {m['away_team']}"
            lines.append(f'| {m["id"]} | {league} | {teams} | {m["match_time"]} | {hours_str} |')

            # 异常检测: pending超过24小时
            if hours > 24:
                anomalies.append(f'⚠️ {m["id"]} ({teams}) pending 超过 {abs(hours):.0f} 小时')
        lines.append(f'')
    else:
        lines.append(f'✅ 无 pending 比赛')
        lines.append(f'')

    # === 4. 预测覆盖缺口 ===
    prediction_gaps = query(conn, """
        SELECT m.id, m.home_team || ' vs ' || m.away_team as teams, m.sport_type,
               m.metadata->>'status' as status,
               m.metadata->>'league' as league,
               COUNT(p.id) as pred_count,
               STRING_AGG(DISTINCT p.ai_name, ', ') as ai_list
        FROM matches m
        LEFT JOIN predictions p ON m.id = p.match_id
        WHERE m.metadata->>'status' = 'on_sale' AND m.metadata->'odds'->'spf'->>'win' IS NOT NULL
        GROUP BY m.id, m.home_team, m.away_team, m.sport_type, m.metadata
        HAVING COUNT(p.id) < 7
        ORDER BY COUNT(p.id) ASC, m.metadata->>'match_time' ASC
    """)

    lines.append(f'## 预测覆盖缺口 ({len(prediction_gaps)}场)')
    lines.append(f'')

    if prediction_gaps:
        lines.append(f'| ID | 联赛 | 对阵 | 已有AI数 | 缺口 |')
        lines.append(f'|-----|------|------|----------|------|')
        for m in prediction_gaps:
            gap = 7 - m['pred_count']
            league = m.get('league', '-') or '-'
            lines.append(f'| {m["id"]} | {league} | {m["teams"]} | {m["pred_count"]}/7 | 缺{gap}个 |')

            # 异常检测: 在售比赛预测不足7个AI
            anomalies.append(f'⚠️ {m["id"]} ({m["teams"]}) 预测覆盖 {m["pred_count"]}/7，缺{gap}个AI')
        lines.append(f'')
    else:
        lines.append(f'✅ 所有在售比赛预测覆盖完整 (7/7)')
        lines.append(f'')

    # === 5. 篮球专项 ===
    bb_total = query(conn, "SELECT count(*) as cnt FROM matches WHERE sport_type = 'basketball'")
    bb_on_sale = query(conn, "SELECT count(*) as cnt FROM matches WHERE sport_type = 'basketball' AND metadata->>'status' = 'on_sale'")
    bb_pending = query(conn, "SELECT count(*) as cnt FROM matches WHERE sport_type = 'basketball' AND metadata->>'status' = 'pending'")
    bb_pred = query(conn, """
        SELECT count(DISTINCT m.id) as cnt
        FROM matches m
        JOIN predictions p ON m.id = p.match_id
        WHERE m.sport_type = 'basketball' AND m.metadata->>'status' = 'on_sale'
    """)

    lines.append(f'## 篮球专项')
    lines.append(f'')
    lines.append(f'| 指标 | 数量 |')
    lines.append(f'|------|------|')
    lines.append(f'| 总比赛 | {bb_total[0]["cnt"]} |')
    lines.append(f'| 在售 | {bb_on_sale[0]["cnt"]} |')
    lines.append(f'| 待定 | {bb_pending[0]["cnt"]} |')
    lines.append(f'| 有预测的在售比赛 | {bb_pred[0]["cnt"]} |')
    lines.append(f'')

    if bb_pending[0]["cnt"] > 0:
        bb_pending_list = query(conn, """
            SELECT id, home_team, away_team, metadata->>'match_time' as match_time,
                   EXTRACT(EPOCH FROM (NOW() - (metadata->>'match_time')::timestamp))/3660 as hours
            FROM matches WHERE sport_type = 'basketball' AND metadata->>'status' = 'pending'
            ORDER BY metadata->>'match_time' ASC
        """)
        for m in bb_pending_list:
            hours = m.get('hours', 0) or 0
            teams = f"{m['home_team']} vs {m['away_team']}"
            if hours > 24:
                anomalies.append(f'⚠️ 篮球 {m["id"]} ({teams}) pending 超过 {abs(hours):.0f} 小时')

    # === 6. 异常汇总 ===
    lines.append(f'## 异常汇总')
    lines.append(f'')

    if anomalies:
        lines.append(f'**发现 {len(anomalies)} 项异常：**')
        lines.append(f'')
        for a in anomalies:
            lines.append(f'- {a}')
    else:
        lines.append(f'✅ 无异常，系统运行正常')

    lines.append(f'')
    lines.append(f'---')
    lines.append(f'*报告由 dispatch_report.py 自动生成*')

    conn.close()

    # 写入报告文件
    report = '\n'.join(lines)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)

    # 同时输出 JSON 摘要到 stdout（供 server.js 读取）
    summary = {
        'report_path': REPORT_PATH,
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'total_matches': total[0]['cnt'],
        'football': football[0]['cnt'],
        'basketball': basketball[0]['cnt'],
        'on_sale': on_sale[0]['cnt'],
        'pending': pending[0]['cnt'],
        'prediction_gaps': len(prediction_gaps),
        'anomaly_count': len(anomalies),
        'anomalies': anomalies,
        'status': 'ANOMALY' if anomalies else 'OK'
    }
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    try:
        generate_report()
    except Exception as e:
        # 即使报告生成失败，也输出错误信息
        error_report = f'# 调度报告\n\n**生成时间**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")} UTC\n\n**ERROR**: {str(e)}\n'
        try:
            with open(REPORT_PATH, 'w', encoding='utf-8') as f:
                f.write(error_report)
        except:
            pass
        print(json.dumps({'status': 'ERROR', 'error': str(e)}, ensure_ascii=False))
        sys.exit(1)
