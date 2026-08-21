#!/usr/bin/env python3
"""
data_quality_check.py - 赛事数据完整性检查与自动补救
运行时机：每日抓取比赛后 + 每日结算后
检查项：
  1. 已完赛比赛：比分是否齐全、让球是否齐全、预测是否已结算
  2. 在售/未开赛比赛：让球是否齐全、赔率是否存在
  3. 预测记录：7个AI是否都有预测、结算结果是否完整
补救措施：
  - 缺比分 → 调用titan007_client重新抓取
  - 缺让球 → 从odds中提取到顶层
  - 预测未结算 → 触发auto_settle
  - 无法补救 → 记录到日志并打印警告
"""
import sys, os, json, psycopg2
from datetime import datetime, timedelta

# 添加脚本目录到path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, 'scripts')  # titan007_client.py 所在位置
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, SCRIPTS_DIR)  # 添加 scripts 目录

DB_URL = 'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres'

AI_NAMES = ['DeepSeek', 'MiniMax', '扣子', '文心', '智谱清言', '混元', '豆包']

def get_conn():
    return psycopg2.connect(DB_URL)

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}')

def extract_handicap_from_odds(meta):
    """从metadata.odds中提取让球到顶层"""
    odds = meta.get('odds', {}) or {}
    h = odds.get('handicap_spf', {}).get('handicap')
    if h is not None:
        return h
    h = odds.get('hdc', {}).get('line')
    if h is not None:
        return h
    return None

def check_and_fix_handicap(conn):
    """检查并修复让球数据：从odds中提取到顶层handicap字段"""
    cur = conn.cursor()
    fixed = 0
    truly_missing = []
    
    for sport in ['football', 'basketball']:
        # 查找缺handicap但有odds的比赛
        cur.execute("""
            SELECT id, home_team, away_team, metadata, status 
            FROM matches 
            WHERE sport_type = %s 
            AND (NOT (metadata ? 'handicap') 
                 OR metadata->>'handicap' IS NULL 
                 OR metadata->>'handicap' = '' 
                 OR metadata->>'handicap' = 'None')
        """, (sport,))
        
        for row in cur.fetchall():
            mid, home, away, meta, status = row
            if isinstance(meta, str):
                meta = json.loads(meta)
            
            hdc = extract_handicap_from_odds(meta)
            if hdc is not None:
                meta['handicap'] = hdc
                cur.execute("UPDATE matches SET metadata = %s WHERE id = %s",
                           (json.dumps(meta, ensure_ascii=False), mid))
                fixed += 1
                log(f'  ✅ 修复让球: {mid} {home} vs {away} → handicap={hdc}')
            else:
                truly_missing.append((mid, home, away, sport, status))
    
    conn.commit()
    
    if truly_missing:
        log(f'  ⚠️ {len(truly_missing)}场缺handicap且odds中也没有:')
        for mid, home, away, sport, status in truly_missing[:20]:
            log(f'    - [{sport}][{status}] {mid} {home} vs {away}')
        if len(truly_missing) > 20:
            log(f'    ... 还有{len(truly_missing)-20}场')
    
    return fixed, truly_missing

def check_score_completeness(conn):
    """检查已完赛比赛的比分完整性"""
    cur = conn.cursor()
    missing = []
    
    for sport in ['football', 'basketball']:
        cur.execute("""
            SELECT id, home_team, away_team, metadata->>'match_date' as match_date
            FROM matches 
            WHERE sport_type = %s AND status = '已完赛'
            AND (NOT (metadata ? 'home_score') 
                 OR metadata->>'home_score' IS NULL 
                 OR metadata->>'home_score' = '' 
                 OR metadata->>'home_score' = 'None')
        """, (sport,))
        for row in cur.fetchall():
            missing.append((row[0], row[1], row[2], sport, row[3] or ''))
    
    return missing

def check_settlement_completeness(conn):
    """检查已完赛比赛的预测结算完整性"""
    cur = conn.cursor()
    unsettled = []
    
    cur.execute("""
        SELECT DISTINCT m.id, m.home_team, m.away_team, m.sport_type,
              count(p.id) as pred_count,
              count(p.id) FILTER (WHERE p.is_settled = true) as settled_count
        FROM matches m
        JOIN predictions p ON m.id = p.match_id
        WHERE m.status = '已完赛'
        GROUP BY m.id, m.home_team, m.away_team, m.sport_type
        HAVING count(p.id) FILTER (WHERE p.is_settled = true) < count(p.id)
    """)
    
    for row in cur.fetchall():
        unsettled.append({
            'match_id': row[0],
            'home': row[1],
            'away': row[2],
            'sport': row[3],
            'total': row[4],
            'settled': row[5]
        })
    
    return unsettled

def check_prediction_coverage(conn):
    """检查在售/未开赛比赛的7个AI预测覆盖"""
    cur = conn.cursor()
    incomplete = []
    
    cur.execute("""
        SELECT p.match_id, m.home_team, m.away_team, m.sport_type,
              array_agg(DISTINCT p.ai_name) as ai_list,
              count(DISTINCT p.ai_name) as ai_count
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        WHERE m.status IN ('on_sale', '未开赛', '已完赛')
        GROUP BY p.match_id, m.home_team, m.away_team, m.sport_type
        HAVING count(DISTINCT p.ai_name) < 7
    """)
    
    for row in cur.fetchall():
        missing_ais = [ai for ai in AI_NAMES if ai not in row[4]]
        incomplete.append({
            'match_id': row[0],
            'home': row[1],
            'away': row[2],
            'sport': row[3],
            'ai_count': row[5],
            'missing_ais': missing_ais
        })
    
    return incomplete

def check_upcoming_handicap(conn):
    """检查在售/未开赛比赛的让球完整性"""
    cur = conn.cursor()
    issues = []
    
    for sport in ['football', 'basketball']:
        cur.execute("""
            SELECT id, home_team, away_team, status,
                   CASE WHEN metadata ? 'odds' THEN true ELSE false END as has_odds,
                   metadata->>'handicap' as handicap
            FROM matches
            WHERE sport_type = %s AND status IN ('on_sale', '未开赛')
        """, (sport,))
        
        for row in cur.fetchall():
            mid, home, away, status, has_odds, handicap = row
            if handicap is None or handicap == '' or handicap == 'None':
                issues.append({
                    'match_id': mid, 'home': home, 'away': away,
                    'sport': sport, 'status': status, 'has_odds': has_odds
                })
    
    return issues

def run_quality_check(skip_remediation=False):
    """执行完整的数据质量检查"""
    log('=' * 60)
    log('🔍 开始数据质量检查...')
    log('=' * 60)
    
    conn = get_conn()
    report = {
        'timestamp': datetime.now().isoformat(),
        'handicap_fixed': 0,
        'handicap_missing': [],
        'scores_missing': [],
        'unsettled_predictions': [],
        'incomplete_predictions': [],
        'upcoming_no_handicap': [],
        'errors': []
    }
    
    try:
        # 1. 检查并修复让球（从odds中提取）
        log('')
        log('📊 1/5 检查让球数据完整性...')
        fixed, missing = check_and_fix_handicap(conn)
        report['handicap_fixed'] = fixed
        report['handicap_missing'] = len(missing)
        log(f'  修复让球: {fixed}场, 缺失: {len(missing)}场')
        
        # 2. 检查比分
        log('')
        log('📊 2/5 检查比分完整性...')
        missing_scores = check_score_completeness(conn)
        report['scores_missing'] = len(missing_scores)
        if missing_scores:
            log(f'  ⚠️ {len(missing_scores)}场已完赛但缺比分:')
            for mid, home, away, sport, mdate in missing_scores:
                log(f'    - [{sport}] {mid} {home} vs {away} ({mdate})')
            
            # 尝试补救：调用titan007_client重新抓取
            if not skip_remediation:
                log('  🔧 尝试补救：调用titan007_client抓取比分...')
                try:
                    from titan007_client import fetch_scores
                    for mid, home, away, sport, mdate in missing_scores:
                        if not mdate:
                            continue
                        date_str = mdate.replace('-', '')
                        try:
                            scores = fetch_scores(sport, date_str)
                            if scores:
                                # 查找匹配的比赛
                                for s in scores:
                                    s_home = s.get('home_team', '')
                                    s_away = s.get('away_team', '')
                                    if (home in s_home or s_home in home or 
                                        away in s_away or s_away in away):
                                        hs = s.get('home_score')
                                        aws = s.get('away_score')
                                        if hs is not None and aws is not None:
                                            cur = conn.cursor()
                                            cur.execute("""
                                                UPDATE matches SET 
                                                metadata = jsonb_set(
                                                    jsonb_set(metadata, '{home_score}', %s::jsonb),
                                                    '{away_score}', %s::jsonb
                                                ), status = '已完赛'
                                                WHERE id = %s
                                            """, (json.dumps(hs), json.dumps(aws), mid))
                                            conn.commit()
                                            log(f'    ✅ 补全比分: {mid} → {hs}-{aws}')
                                            break
                        except Exception as e:
                            log(f'    ❌ 抓取失败 [{sport}] {date_str}: {e}')
                except ImportError as e:
                    log(f'  ⚠️ 无法导入titan007_client: {e}')
            else:
                log('  ⏭️ 跳过补救（skip_remediation=True）')
        
        # 3. 检查结算
        log('')
        log('📊 3/5 检查预测结算完整性...')
        unsettled = check_settlement_completeness(conn)
        report['unsettled_predictions'] = len(unsettled)
        if unsettled:
            log(f'  ⚠️ {len(unsettled)}场比赛有未结算预测:')
            for u in unsettled[:10]:
                log(f'    - [{u["sport"]}] {u["match_id"]} {u["home"]} vs {u["away"]}: {u["settled"]}/{u["total"]}已结算')
            
            # 尝试补救：触发auto_settle
            if not skip_remediation:
                log('  🔧 尝试补救：触发auto_settle...')
                try:
                    from auto_settle import main as settle_main
                    settle_main()
                    log('  ✅ auto_settle执行完成')
                except ImportError as e:
                    log(f'  ⚠️ 无法导入auto_settle: {e}')
            else:
                log('  ⏭️ 跳过补救')
        
        # 4. 检查预测覆盖
        log('')
        log('📊 4/5 检查7个AI预测覆盖...')
        incomplete = check_prediction_coverage(conn)
        report['incomplete_predictions'] = len(incomplete)
        if incomplete:
            log(f'  ⚠️ {len(incomplete)}场比赛预测不完整（<7个AI）:')
            for i in incomplete[:10]:
                log(f'    - [{i["sport"]}] {i["match_id"]} {i["home"]} vs {i["away"]}: {i["ai_count"]}/7 AI')
                if i['missing_ais']:
                    log(f'      缺少: {", ".join(i["missing_ais"][:3])}...')
        
        # 5. 检查在售/未开赛让球
        log('')
        log('📊 5/5 检查在售/未开赛比赛让球...')
        upcoming = check_upcoming_handicap(conn)
        report['upcoming_no_handicap'] = len(upcoming)
        if upcoming:
            log(f'  ⚠️ {len(upcoming)}场在售/未开赛比赛缺让球:')
            for u in upcoming[:10]:
                odds_status = '有odds' if u['has_odds'] else '无odds'
                log(f'    - [{u["sport"]}][{u["status"]}] {u["match_id"]} {u["home"]} vs {u["away"]} ({odds_status})')
        
        # 总结
        log('')
        log('=' * 60)
        log('📋 检查完成')
        log('=' * 60)
        log(f'  让球修复: {report["handicap_fixed"]}场')
        log(f'  让球缺失: {report["handicap_missing"]}场')
        log(f'  比分缺失: {report["scores_missing"]}场')
        log(f'  预测未结算: {report["unsettled_predictions"]}场')
        log(f'  预测不完整: {report["incomplete_predictions"]}场')
        log(f'  在售缺让球: {report["upcoming_no_handicap"]}场')
        
    except Exception as e:
        log(f'❌ 检查过程出错: {e}')
        report['errors'].append(str(e))
    finally:
        conn.close()
    
    # 保存报告
    report_path = os.path.join(SCRIPT_DIR, 'data_quality_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f'📄 报告已保存: {report_path}')
    
    return report

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='数据质量检查')
    parser.add_argument('--skip-remediation', action='store_true', help='跳过自动补救')
    args = parser.parse_args()
    
    run_quality_check(skip_remediation=args.skip_remediation)
