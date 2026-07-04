#!/usr/bin/env python3
"""
Generate SEO-optimized static pages for the AI prediction website.
"""

import os
import json
import requests
from datetime import datetime, timedelta

# Supabase configuration
SUPABASE_URL = "https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sashnT6QYhW2_ilgdPxAuPXwtM"


def get_lottery_date(match_id=None, match_time_str=None, all_dates=None):
    """
    根据match_time的真实日期分组。
    直接使用match_time的日期部分（YYYY-MM-DD），不进行时区转换。
    """
    if not match_time_str:
        return None
    # 直接取日期部分，不转UTC（避免时区导致日期错误）
    return match_time_str.replace(' ', 'T').split('T')[0]


def fetch_today_matches():
    """
    Fetch today's matches with predictions from Supabase using nested query.
    """
    # 获取当前日期范围（包括昨天和明天，以覆盖所有可能的比赛）
    today = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 使用嵌套查询一次性获取比赛和预测数据
    query = f"""
    select=id,teams,match_time,handicap,status,win_odds,draw_odds,lose_odds,handicap_win_odds,handicap_draw_odds,handicap_lose_odds,home_score,away_score,predictions(id,ai_name,spf,handicap_spf,score,goals,half_full,win_loss,handicap_win_loss,total_points,score_diff_range,half_win_loss,hit_handicap,hit_score,hit_goals,hit_half)
    """
    
    url = f"{SUPABASE_URL}/rest/v1/matches?{query}&match_time=gt.{yesterday}T00:00:00&match_time=lt.{tomorrow}T23:59:59&order=match_time.asc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching matches: {e}")
        return []


def fetch_all_matches():
    """
    Fetch all matches with predictions from Supabase.
    """
    query = "select=id,teams,match_time,handicap,status,win_odds,draw_odds,lose_odds,handicap_win_odds,handicap_draw_odds,handicap_lose_odds,home_score,away_score,sport_type,metadata,predictions(id,ai_name,spf,handicap_spf,score,goals,half_full,win_loss,total_points,score_diff_range,half_win_loss,hit_handicap,hit_score,hit_goals,hit_half,total_hits,analysis)"
    
    url = f"{SUPABASE_URL}/rest/v1/matches?{query}&order=match_time.desc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching all matches: {e}")
        return []


def fetch_match_dates():
    """
    Fetch all unique match dates from Supabase.
    """
    url = f"{SUPABASE_URL}/rest/v1/matches?select=match_time,id&order=match_time.desc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        matches = response.json()
        
        # 使用get_lottery_date函数提取唯一日期
        dates = set()
        for m in matches:
            date = get_lottery_date(
                match_id=m.get('id'),
                match_time_str=m.get('match_time')
            )
            if date:
                dates.add(date)
        
        return sorted(list(dates), reverse=True)
    except Exception as e:
        print(f"Error fetching match dates: {e}")
        return []


def fetch_matches_for_date(date_str):
    """
    Fetch matches for a specific date with predictions.
    使用match_time的真实日期分组。
    """
    # 从date_str 12:00:00到date_str+1 11:59:59获取比赛
    # 这样能覆盖体彩日期的所有比赛
    start_time = f"{date_str}T12:00:00"
    end_date = datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)
    end_time = f"{end_date.strftime('%Y-%m-%d')}T11:59:59"
    
    query = "select=id,teams,match_time,handicap,status,win_odds,draw_odds,lose_odds,handicap_win_odds,handicap_draw_odds,handicap_lose_odds,home_score,away_score,sport_type,metadata,predictions(id,ai_name,spf,handicap_spf,score,goals,half_full,win_loss,total_points,score_diff_range,half_win_loss,hit_handicap,hit_score,hit_goals,hit_half,total_hits,analysis)"
    
    url = f"{SUPABASE_URL}/rest/v1/matches?{query}&match_time=gt.{start_time}&match_time=lt.{end_time}&order=match_time.asc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        matches = response.json()
        
        # 过滤：只保留get_lottery_date返回date_str的比赛
        filtered_matches = []
        for m in matches:
            match_date = get_lottery_date(
                match_id=m.get('match_id'),
                match_time_str=m.get('match_time')
            )
            if match_date == date_str:
                filtered_matches.append(m)
        
        return filtered_matches
    except Exception as e:
        print(f"Error fetching matches for date {date_str}: {e}")
        return []


def fetch_ai_stats():
    """
    Fetch AI statistics from Supabase.
    """
    url = f"{SUPABASE_URL}/rest/v1/ai_stats?select=*&order=rank.asc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching AI stats: {e}")
        return []


def fetch_chain_bets():
    """
    Fetch chain bets data from Supabase.
    """
    url = f"{SUPABASE_URL}/rest/v1/chain_bets?select=*&order=bet_date.desc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching chain bets: {e}")
        return []


def fetch_betting_daily():
    """
    Fetch betting daily data from Supabase.
    """
    url = f"{SUPABASE_URL}/rest/v1/betting_daily?select=match_date,daily_summary,daily_commentary&order=match_date.desc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching betting daily: {e}")
        return []


def fetch_briefs():
    """
    Fetch briefs data from Supabase.
    """
    url = f"{SUPABASE_URL}/rest/v1/briefs?select=date,match_ids,matches(id,teams,match_time,sport_type,home_score,away_score,predictions(ai_name,spf,handicap_spf,score,goals,half_full,win_loss,total_points,score_diff_range,half_win_loss,hit_handicap,hit_score,hit_goals,hit_half,total_hits,analysis))&order=date.desc"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching briefs: {e}")
        return []


def format_date(date_str):
    """
    Format date string for display.
    """
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%Y年%m月%d日')
    except Exception:
        return date_str


def format_time(match_time_str):
    """
    Format match time for display.
    """
    try:
        if 'T' in match_time_str:
            dt = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(match_time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%H:%M')
    except Exception:
        return match_time_str


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
            
            hit_handicap = pred.get('hit_handicap', '')
            hit_score = pred.get('hit_score', '')  # 总分
            hit_goals = pred.get('hit_goals', '')  # 分差
            hit_half = pred.get('hit_half', '')
            
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
            
            hit_handicap = pred.get('hit_handicap', '')
            hit_score = pred.get('hit_score', '')
            hit_goals = pred.get('hit_goals', '')
            hit_half = pred.get('hit_half', '')
            
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
        
        <div class="matches-list">
    '''
    
    for match in matches:
        html += generate_match_card(match, show_predictions=False)
        html += f'''
        <div class="review-section">
            <h3>赛后复盘</h3>
            {generate_review_content(match)}
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


def main():
    """
    Main function to generate all SEO pages.
    """
    print("Fetching data from Supabase...")
    
    # Fetch all data
    all_matches = fetch_all_matches()
    match_dates = fetch_match_dates()
    ai_stats = fetch_ai_stats()
    chain_bets = fetch_chain_bets()
    betting_daily = fetch_betting_daily()
    briefs = fetch_briefs()
    
    print(f"Fetched {len(all_matches)} matches, {len(match_dates)} dates")
    
    # Generate daily pages
    output_dir = '/workspace/projects'
    
    for date_str in match_dates[:30]:  # Generate pages for last 30 days
        matches = fetch_matches_for_date(date_str)
        if matches:
            html = generate_daily_page(date_str, matches)
            filename = f"daily-{date_str}.html"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"Generated {filename} with {len(matches)} matches")
    
    # Generate brief pages
    for brief in briefs[:30]:  # Generate pages for last 30 briefs
        date_str = brief.get('date', '')
        html = generate_brief_page(brief)
        filename = f"brief-{date_str}.html"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Generated {filename}")
    
    print("SEO pages generated successfully!")


if __name__ == '__main__':
    main()
