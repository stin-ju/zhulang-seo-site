#!/usr/bin/env python3
"""
Generate SEO-optimized static pages for the AI prediction website.
Uses direct PostgreSQL connection instead of Supabase REST API.
"""

import os
import json
import re
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from decimal import Decimal

# Database configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_db_connection():
    """Get a PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


def dict_from_row(row, cursor):
    """Convert a psycopg2 row to a dictionary."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def dicts_from_rows(rows, cursor):
    """Convert psycopg2 rows to a list of dictionaries."""
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def get_lottery_date(match_id=None, match_time_str=None, all_dates=None):
    """
    根据match_time的真实日期分组。
    直接使用match_time的日期部分（YYYY-MM-DD），不进行时区转换。
    """
    if not match_time_str:
        return None
    # 直接取日期部分，不转UTC（避免时区导致日期错误）
    return str(match_time_str).replace(' ', 'T').split('T')[0]


def normalize_match(match):
    """Normalize match data from actual DB schema (same logic as server.js normalizeMatch)."""
    if not match:
        return match
    meta = match.get('metadata') or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    odds_data = meta.get('odds') or match.get('odds') or {}
    if isinstance(odds_data, str):
        odds_data = json.loads(odds_data)
    spf = odds_data.get('spf', {})
    handicap_spf = odds_data.get('handicap_spf', {})

    # Fix match_time: combine match_date and match_time into full datetime string
    match_time = match.get('match_time') or meta.get('match_time', '')
    match_date = match.get('match_date') or meta.get('match_date')

    # Convert date objects to strings
    if hasattr(match_date, 'isoformat'):
        match_date = match_date.isoformat()
    if isinstance(match_date, str) and 'T' in match_date:
        match_date = match_date[:10]

    # If match_time is just a time (HH:MM:SS or HH:MM), prepend the date
    if match_time and '-' not in str(match_time) and match_date:
        time_parts = str(match_time).split(':')
        hhmm = f"{time_parts[0]}:{time_parts[1]}" if len(time_parts) >= 2 else str(match_time)
        match_time = f"{match_date} {hhmm}"
    elif match_time and hasattr(match_time, 'isoformat'):
        match_time = match_time.isoformat()

    home_team = match.get('home_team', '')
    away_team = match.get('away_team', '')
    teams = f"{home_team} vs {away_team}" if home_team and away_team else ''

    home_score = meta.get('home_score')
    if home_score is None:
        home_score = match.get('home_score')
    away_score = meta.get('away_score')
    if away_score is None:
        away_score = match.get('away_score')

    # Update match in place
    match['match_date'] = match_date or ''
    match['match_time'] = str(match_time) if match_time else ''
    match['teams'] = teams
    match['home_team'] = home_team
    match['away_team'] = away_team
    match['win_odds'] = spf.get('win')
    match['draw_odds'] = spf.get('draw')
    match['lose_odds'] = spf.get('lose')
    match['handicap_win_odds'] = handicap_spf.get('win')
    match['handicap_draw_odds'] = handicap_spf.get('draw')
    match['handicap_lose_odds'] = handicap_spf.get('lose')
    match['league_name'] = meta.get('league', '')
    match['home_score'] = home_score
    match['away_score'] = away_score
    match['handicap'] = meta.get('handicap') or match.get('handicap')
    match['selling_status'] = meta.get('selling_status')
    return match


def normalize_prediction(pred):
    """Normalize prediction data from actual DB schema (same logic as server.js normalizePrediction)."""
    if not pred:
        return pred
    prediction = pred.get('prediction') or {}
    if isinstance(prediction, str):
        prediction = json.loads(prediction)
    hit_status = pred.get('hit_status') or {}
    if isinstance(hit_status, str):
        hit_status = json.loads(hit_status)

    hit_fields = ['spf', 'handicap_spf', 'score', 'goals', 'half_full']
    total_hits = sum(1 for f in hit_fields if hit_status.get(f) is True)

    return {
        **pred,
        'spf': prediction.get('spf'),
        'handicap_spf': prediction.get('handicap_spf'),
        'score': prediction.get('score'),
        'goals': prediction.get('goals'),
        'half_full': prediction.get('half_full'),
        'win_loss': prediction.get('win_loss'),
        'handicap_win_loss': prediction.get('handicap_win_loss'),
        'total_points': prediction.get('total_points'),
        'score_diff_range': prediction.get('score_diff_range'),
        'half_win_loss': prediction.get('half_win_loss'),
        'hit_spf': hit_status.get('spf'),
        'hit_handicap': hit_status.get('handicap_spf'),
        'hit_score': hit_status.get('score'),
        'hit_goals': hit_status.get('goals'),
        'hit_half': hit_status.get('half_full'),
        'total_hits': total_hits,
        'analysis': pred.get('analysis', ''),
    }


def fetch_all_matches():
    """
    Fetch all matches with predictions from PostgreSQL using actual DB schema.
    Matches table only has: id, sport_type, home_team, away_team, metadata, status
    All other fields are in metadata JSONB.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Fetch all matches (only 6 columns exist)
        cur.execute("""
            SELECT id, sport_type, home_team, away_team, metadata, status
            FROM matches
            ORDER BY metadata->>'match_date' DESC, metadata->>'match_time' DESC
        """)
        raw_matches = dicts_from_rows(cur.fetchall(), cur)
        
        # Fetch all predictions
        cur.execute("""
            SELECT id, match_id, ai_name, prediction, hit_status, analysis, is_settled, sport_type
            FROM predictions
        """)
        raw_predictions = dicts_from_rows(cur.fetchall(), cur)
        
        # Group predictions by match_id
        predictions_by_match = {}
        for p in raw_predictions:
            mid = p['match_id']
            if mid not in predictions_by_match:
                predictions_by_match[mid] = []
            predictions_by_match[mid].append(p)
        
        # Attach predictions to matches
        for m in raw_matches:
            normalize_match(m)
            mid = m['id']
            if mid in predictions_by_match:
                m['predictions'] = [normalize_prediction(p) for p in predictions_by_match[mid]]
            else:
                m['predictions'] = []
        
        return raw_matches
    except Exception as e:
        print(f"Error fetching all matches: {e}")
        return []
    finally:
        conn.close()


def fetch_match_dates():
    """
    Fetch all unique match dates from PostgreSQL.
    match_date is stored in metadata JSONB.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT metadata->>'match_date' as match_date
            FROM matches
            WHERE metadata->>'match_date' IS NOT NULL
            ORDER BY metadata->>'match_date' DESC
        """)
        dates = []
        for row in cur.fetchall():
            d = row[0]
            if d:
                dates.append(str(d)[:10])
        
        return sorted(list(set(dates)), reverse=True)
    except Exception as e:
        print(f"Error fetching match dates: {e}")
        return []
    finally:
        conn.close()


def fetch_matches_for_date(date_str):
    """
    Fetch matches for a specific date with predictions.
    match_date is stored in metadata JSONB.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Fetch matches for the date (match_date is in metadata JSONB)
        cur.execute("""
            SELECT id, sport_type, home_team, away_team, metadata, status
            FROM matches
            WHERE metadata->>'match_date' = %s
            ORDER BY metadata->>'match_time' ASC
        """, (date_str,))
        raw_matches = dicts_from_rows(cur.fetchall(), cur)
        
        # Fetch predictions for these matches
        match_ids = [m['id'] for m in raw_matches]
        if match_ids:
            cur.execute("""
                SELECT id, match_id, ai_name, prediction, hit_status, analysis, is_settled, sport_type
                FROM predictions
                WHERE match_id = ANY(%s)
            """, (match_ids,))
            raw_predictions = dicts_from_rows(cur.fetchall(), cur)
        else:
            raw_predictions = []
        
        # Group predictions by match_id
        predictions_by_match = {}
        for p in raw_predictions:
            mid = p['match_id']
            if mid not in predictions_by_match:
                predictions_by_match[mid] = []
            predictions_by_match[mid].append(p)
        
        # Attach predictions to matches
        for m in raw_matches:
            normalize_match(m)
            mid = m['id']
            if mid in predictions_by_match:
                m['predictions'] = [normalize_prediction(p) for p in predictions_by_match[mid]]
            else:
                m['predictions'] = []
        
        return raw_matches
    except Exception as e:
        print(f"Error fetching matches for date {date_str}: {e}")
        return []
    finally:
        conn.close()


def fetch_ai_stats():
    """
    Fetch AI statistics from PostgreSQL.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ai_stats ORDER BY rank ASC")
        return dicts_from_rows(cur.fetchall(), cur)
    except Exception as e:
        print(f"Error fetching AI stats: {e}")
        return []
    finally:
        conn.close()


def fetch_chain_bets():
    """
    Fetch chain bets data from PostgreSQL.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM chain_bets ORDER BY bet_date DESC")
        return dicts_from_rows(cur.fetchall(), cur)
    except Exception as e:
        print(f"Error fetching chain bets: {e}")
        return []
    finally:
        conn.close()


def fetch_betting_daily():
    """
    Fetch betting daily data from PostgreSQL.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT match_date, ai_name, daily_pnl, win_rate, rank_change, sport_type
            FROM betting_daily
            ORDER BY match_date DESC
        """)
        return dicts_from_rows(cur.fetchall(), cur)
    except Exception as e:
        print(f"Error fetching betting daily: {e}")
        return []
    finally:
        conn.close()


def fetch_briefs():
    """
    Fetch briefs data from PostgreSQL.
    Note: briefs table does not exist, return empty list.
    """
    return []


def format_date(date_str):
    """
    Format date string for display.
    """
    try:
        dt = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
        return dt.strftime('%Y年%m月%d日')
    except Exception:
        return str(date_str)


def format_time(match_time_str):
    """
    Format match time for display.
    """
    try:
        match_time_str = str(match_time_str)
        if 'T' in match_time_str:
            dt = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(match_time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%H:%M')
    except Exception:
        return str(match_time_str)


def get_result_class(hit_status):
    """
    Get CSS class for result display.
    """
    if hit_status == '命中':
        return 'hit'
    elif hit_status == '未中':
        return 'miss'
    return ''


def generate_prediction_content(match):
    """
    Generate AI prediction content for a match.
    """
    predictions = match.get('predictions', [])
    if not predictions:
        return '<div class="text-gray-500">暂无预测数据</div>'
    
    # 根据运动类型使用不同术语
    sport_type = match.get('sport_type', 'football')
    is_basketball = sport_type == 'basketball'
    
    # 根据运动类型选择维度名称
    if is_basketball:
        dim_names = {
            'spf': '胜负',
            'handicap': '让分',
            'total_points': '总分',
            'score_diff': '分差',
            'half': '半场胜负'
        }
    else:
        dim_names = {
            'spf': '胜平负',
            'handicap': '让球',
            'score': '比分',
            'goals': '总进球',
            'half_full': '半全场'
        }
    
    content = '<div class="prediction-grid">'
    
    for pred in predictions:
        ai_name = pred.get('ai_name', 'Unknown')
        
        # 根据运动类型获取预测值
        if is_basketball:
            spf = pred.get('win_loss', '-')
            handicap = pred.get('handicap_win_loss', '-')
            total_points = pred.get('total_points', '-')
            score_diff = pred.get('score_diff_range', '-')
            half = pred.get('half_win_loss', '-')
            
            content += f'''
            <div class="prediction-card">
                <div class="ai-name">{ai_name}</div>
                <div class="pred-item"><span class="label">{dim_names["spf"]}:</span> <span class="value">{spf}</span></div>
                <div class="pred-item"><span class="label">{dim_names["handicap"]}:</span> <span class="value">{handicap}</span></div>
                <div class="pred-item"><span class="label">{dim_names["total_points"]}:</span> <span class="value">{total_points}</span></div>
                <div class="pred-item"><span class="label">{dim_names["score_diff"]}:</span> <span class="value">{score_diff}</span></div>
                <div class="pred-item"><span class="label">{dim_names["half"]}:</span> <span class="value">{half}</span></div>
            </div>
            '''
        else:
            spf = pred.get('spf', '-')
            handicap = pred.get('handicap_spf', '-')
            score = pred.get('score', '-')
            goals = pred.get('goals', '-')
            half_full = pred.get('half_full', '-')
            
            content += f'''
            <div class="prediction-card">
                <div class="ai-name">{ai_name}</div>
                <div class="pred-item"><span class="label">{dim_names["spf"]}:</span> <span class="value">{spf}</span></div>
                <div class="pred-item"><span class="label">{dim_names["handicap"]}:</span> <span class="value">{handicap}</span></div>
                <div class="pred-item"><span class="label">{dim_names["score"]}:</span> <span class="value">{score}</span></div>
                <div class="pred-item"><span class="label">{dim_names["goals"]}:</span> <span class="value">{goals}</span></div>
                <div class="pred-item"><span class="label">{dim_names["half_full"]}:</span> <span class="value">{half_full}</span></div>
            </div>
            '''
    
    content += '</div>'
    return content


def generate_review_content(match):
    """
    Generate post-match review content.
    """
    predictions = match.get('predictions', [])
    if not predictions:
        return '<div class="text-gray-500">暂无复盘数据</div>'
    
    home_score = match.get('home_score', '?')
    away_score = match.get('away_score', '?')
    
    # 根据运动类型使用不同术语
    sport_type = match.get('sport_type', 'football')
    is_basketball = sport_type == 'basketball'
    
    # 根据运动类型选择维度名称
    if is_basketball:
        dim_names = {
            'spf': '胜负',
            'handicap': '让分',
            'total_points': '总分',
            'score_diff': '分差',
            'half': '半场胜负'
        }
    else:
        dim_names = {
            'spf': '胜平负',
            'handicap': '让球',
            'score': '比分',
            'goals': '总进球',
            'half_full': '半全场'
        }
    
    content = f'''
    <div class="review-header">
        <div class="score">{home_score} - {away_score}</div>
    </div>
    <div class="review-grid">
    '''
    
    for pred in predictions:
        ai_name = pred.get('ai_name', 'Unknown')
        total_hits = pred.get('total_hits', 0)
        analysis = pred.get('analysis', '')
        
        # 根据运动类型获取预测值和命中状态
        if is_basketball:
            spf = pred.get('win_loss', '-')
            handicap = pred.get('handicap_win_loss', '-')
            total_points = pred.get('total_points', '-')
            score_diff = pred.get('score_diff_range', '-')
            half = pred.get('half_win_loss', '-')
            
            hit_spf = '命中' if pred.get('win_loss') and total_hits > 0 else '未中'
            hit_handicap = pred.get('hit_handicap', '未中')
            hit_score = pred.get('hit_score', '未中')  # 总分
            hit_goals = pred.get('hit_goals', '未中')  # 分差
            hit_half = pred.get('hit_half', '未中')
            
            content += f'''
            <div class="review-card">
                <div class="ai-name">{ai_name} <span class="hits">{total_hits}命中</span></div>
                <div class="review-item"><span class="label">{dim_names["spf"]}:</span> <span class="value">{spf}</span> <span class="result {get_result_class(hit_spf)}">{hit_spf}</span></div>
                <div class="review-item"><span class="label">{dim_names["handicap"]}:</span> <span class="value">{handicap}</span> <span class="result {get_result_class(hit_handicap)}">{hit_handicap}</span></div>
                <div class="review-item"><span class="label">{dim_names["total_points"]}:</span> <span class="value">{total_points}</span> <span class="result {get_result_class(hit_score)}">{hit_score}</span></div>
                <div class="review-item"><span class="label">{dim_names["score_diff"]}:</span> <span class="value">{score_diff}</span> <span class="result {get_result_class(hit_goals)}">{hit_goals}</span></div>
                <div class="review-item"><span class="label">{dim_names["half"]}:</span> <span class="value">{half}</span> <span class="result {get_result_class(hit_half)}">{hit_half}</span></div>
                {f'<div class="analysis">{analysis}</div>' if analysis else ''}
            </div>
            '''
        else:
            spf = pred.get('spf', '-')
            handicap = pred.get('handicap_spf', '-')
            score = pred.get('score', '-')
            goals = pred.get('goals', '-')
            half_full = pred.get('half_full', '-')
            
            hit_spf = '命中' if pred.get('spf') and total_hits > 0 else '未中'
            hit_handicap = pred.get('hit_handicap', '未中')
            hit_score = pred.get('hit_score', '未中')
            hit_goals = pred.get('hit_goals', '未中')
            hit_half = pred.get('hit_half', '未中')
            
            content += f'''
            <div class="review-card">
                <div class="ai-name">{ai_name} <span class="hits">{total_hits}命中</span></div>
                <div class="review-item"><span class="label">{dim_names["spf"]}:</span> <span class="value">{spf}</span> <span class="result {get_result_class(hit_spf)}">{hit_spf}</span></div>
                <div class="review-item"><span class="label">{dim_names["handicap"]}:</span> <span class="value">{handicap}</span> <span class="result {get_result_class(hit_handicap)}">{hit_handicap}</span></div>
                <div class="review-item"><span class="label">{dim_names["score"]}:</span> <span class="value">{score}</span> <span class="result {get_result_class(hit_score)}">{hit_score}</span></div>
                <div class="review-item"><span class="label">{dim_names["goals"]}:</span> <span class="value">{goals}</span> <span class="result {get_result_class(hit_goals)}">{hit_goals}</span></div>
                <div class="review-item"><span class="label">{dim_names["half_full"]}:</span> <span class="value">{half_full}</span> <span class="result {get_result_class(hit_half)}">{hit_half}</span></div>
                {f'<div class="analysis">{analysis}</div>' if analysis else ''}
            </div>
            '''
    
    content += '</div>'
    return content


def generate_match_card(match, show_predictions=True):
    """
    Generate HTML for a match card.
    """
    match_id = match.get('id', '')
    teams = match.get('teams', '')
    match_time = match.get('match_time', '')
    status = match.get('status', '')
    handicap = match.get('handicap', '')
    
    # Parse teams
    team_parts = teams.split(' VS ') if ' VS ' in teams else teams.split('VS')
    home_team = team_parts[0].strip() if len(team_parts) > 0 else ''
    away_team = team_parts[1].strip() if len(team_parts) > 1 else ''
    
    # Format time
    time_str = format_time(match_time)
    
    # Status class
    status_class = 'confirmed' if status == '已确认' else 'pending'
    
    html = f'''
    <div class="match-card {status_class}">
        <div class="match-header">
            <span class="match-id">{match_id}</span>
            <span class="match-time">{time_str}</span>
            <span class="match-status">{status}</span>
        </div>
        <div class="match-teams">
            <span class="home-team">{home_team}</span>
            <span class="vs">VS</span>
            <span class="away-team">{away_team}</span>
        </div>
        {f'<div class="handicap">让球: {handicap}</div>' if handicap else ''}
    </div>
    '''
    
    return html


def generate_daily_page(date_str, matches):
    """
    Generate daily page HTML.
    """
    date_display = format_date(date_str)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{date_display} AI预测简报 - AI实验室·体彩好伙伴</title>
    <meta name="description" content="{date_display}AI预测简报，共{len(matches)}场赛事">
    <meta property="og:title" content="{date_display} AI预测简报">
    <meta property="og:description" content="{date_display}AI预测简报，共{len(matches)}场赛事">
    <link rel="stylesheet" href="/styles.css">
</head>
<body>
    <header>
        <nav>
            <a href="/" class="logo">AI实验室</a>
            <ul>
                <li><a href="/">首页</a></li>
                <li><a href="/basketball.html">篮球</a></li>
                <li><a href="/ai-analysis.html">AI分析</a></li>
                <li><a href="/calculator.html">计算器</a></li>
            </ul>
        </nav>
    </header>
    
    <main>
        <h1>{date_display} AI预测简报</h1>
        <div class="meta">{date_display} · {len(matches)}场赛事</div>
        
        <div class="matches-list">
    '''
    
    for match in matches:
        html += generate_match_card(match)
    
    html += '''
        </div>
        
        <section style="margin-top:48px;padding:24px;background:var(--bg-elevated);border-radius:12px;">
            <h2 style="font-size:20px;font-weight:600;margin-bottom:16px;color:var(--text-primary);">AI预测简报</h2>
            <div style="display:grid;gap:12px;">
    '''
    
    # Get latest 5 briefs
    brief_files = sorted([f for f in os.listdir('.') if f.startswith('brief-2026-') and f.endswith('.html')], reverse=True)[:5]
    weekday_map = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    
    for f in brief_files:
        match = re.search(r'brief-(\d{4}-\d{2}-\d{2})\.html', f)
        if match:
            date_str = match.group(1)
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            weekday = weekday_map[dt.weekday()]
            display_date = f'{dt.month}月{dt.day}日 {weekday}'
            html += f'''
                <a href="/{f}" style="display:flex;align-items:center;padding:12px 16px;background:var(--bg-deep);border-radius:8px;text-decoration:none;color:var(--text-primary);transition:all 0.2s;">
                    <span style="font-size:20px;margin-right:12px;">📈</span>
                    <span style="flex:1;font-weight:500;">{display_date} 赛事预测</span>
                    <span style="font-size:12px;color:var(--turf);">查看详情 →</span>
                </a>
            '''
    
    html += '''
            </div>
            <a href="/brief.html" style="display:block;text-align:center;margin-top:16px;padding:10px;color:var(--turf);text-decoration:none;font-size:14px;">查看全部简报 →</a>
        </section>
    </main>
    
    <footer>
        <p>© 2026 AI实验室. 本站仅供学习研究使用。</p>
    </footer>
</body>
</html>
'''
    
    return html


def generate_brief_page(brief):
    """
    Generate brief page HTML.
    """
    date_str = brief.get('date', '')
    date_display = format_date(date_str)
    matches = brief.get('matches', [])
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{date_display} AI复盘简报 - AI实验室·体彩好伙伴</title>
    <meta name="description" content="{date_display}AI复盘简报，共{len(matches)}场赛事">
    <meta property="og:title" content="{date_display} AI复盘简报">
    <meta property="og:description" content="{date_display}AI复盘简报，共{len(matches)}场赛事">
    <link rel="stylesheet" href="/styles.css">
</head>
<body>
    <header>
        <nav>
            <a href="/" class="logo">AI实验室</a>
            <ul>
                <li><a href="/">首页</a></li>
                <li><a href="/basketball.html">篮球</a></li>
                <li><a href="/ai-analysis.html">AI分析</a></li>
                <li><a href="/calculator.html">计算器</a></li>
            </ul>
        </nav>
    </header>
    
    <main>
        <h1>{date_display} AI复盘简报</h1>
        <div class="meta">{date_display} · {len(matches)}场赛事</div>
        
        <div class="briefs-list">
    '''
    
    for match in matches:
        html += generate_match_card(match, show_predictions=False)
        html += generate_review_content(match)
    
    html += '''
        </div>
    </main>
    
    <footer>
        <p>© 2026 AI实验室. 本站仅供学习研究使用。</p>
    </footer>
</body>
</html>
'''
    
    return html


def generate_index_page(dates, matches, briefs, ai_stats, chain_bets, betting_daily):
    """
    Generate index page HTML.
    """
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI实验室 - AI预测简报</title>
    <meta name="description" content="AI实验室，AI预测简报，每日AI预测分析">
    <link rel="stylesheet" href="/styles.css">
</head>
<body>
    <header>
        <nav>
            <a href="/" class="logo">AI实验室</a>
            <ul>
                <li><a href="/">首页</a></li>
                <li><a href="/basketball.html">篮球</a></li>
                <li><a href="/ai-analysis.html">AI分析</a></li>
                <li><a href="/calculator.html">计算器</a></li>
            </ul>
        </nav>
    </header>
    
    <main>
        <h1>AI预测简报</h1>
        <div class="meta">每日AI预测分析</div>
        
        <div class="dates-list">
    '''
    
    for date_str in dates[:30]:  # Show last 30 days
        date_display = format_date(date_str)
        # Count matches for this date
        match_count = sum(1 for m in matches if get_lottery_date(match_time_str=m.get('match_time')) == date_str)
        
        html += f'''
        <div class="date-card">
            <a href="/daily/{date_str}.html">
                <div class="date">{date_display}</div>
                <div class="count">{match_count}场赛事</div>
            </a>
        </div>
        '''
    
    html += '''
        </div>
    </main>
    
    <footer>
        <p>© 2026 AI实验室. 本站仅供学习研究使用。</p>
    </footer>
</body>
</html>
'''
    
    return html


def generate_sitemap(dates, matches, briefs):
    """
    Generate sitemap.xml.
    """
    domain = os.environ.get("COZE_PROJECT_DOMAIN_DEFAULT", "https://example.com")
    
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{domain}/</loc>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
'''.format(domain=domain)
    
    for date_str in dates:
        xml += f'''    <url>
        <loc>{domain}/daily/{date_str}.html</loc>
        <changefreq>daily</changefreq>
        <priority>0.8</priority>
    </url>
'''
    
    xml += '''</urlset>
'''
    
    return xml


def main():
    """
    Main function to generate all SEO pages.
    """
    print("Fetching data from database...")
    
    # Fetch all data
    matches = fetch_all_matches()
    dates = fetch_match_dates()
    ai_stats = fetch_ai_stats()
    chain_bets = fetch_chain_bets()
    betting_daily = fetch_betting_daily()
    briefs = fetch_briefs()
    
    print(f"Fetched {len(matches)} matches, {len(dates)} dates")
    
    # Create output directories
    os.makedirs("public/daily", exist_ok=True)
    
    # Generate index page
    index_html = generate_index_page(dates, matches, briefs, ai_stats, chain_bets, betting_daily)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    print("Generated index.html")
    
    # Generate daily pages
    for date_str in dates:
        date_matches = [m for m in matches if get_lottery_date(match_time_str=m.get('match_time')) == date_str]
        if date_matches:
            daily_html = generate_daily_page(date_str, date_matches)
            with open(f"public/daily/{date_str}.html", "w", encoding="utf-8") as f:
                f.write(daily_html)
    
    print(f"Generated {len(dates)} daily pages")
    
    # Generate sitemap
    sitemap_xml = generate_sitemap(dates, matches, briefs)
    with open("public/sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print("Generated sitemap.xml")
    
    print("SEO pages generated successfully!")


if __name__ == "__main__":
    main()
