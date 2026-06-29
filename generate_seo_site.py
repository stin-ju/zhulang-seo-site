#!/usr/bin/env python3
"""
Generate SEO-friendly static HTML pages for the AI prediction website.
This script generates:
- brief.html: Index page with list of daily brief articles
- brief-{date}.html: Individual article pages for each date
"""

import urllib.request
import json
import os
import re
from datetime import datetime

# Supabase configuration
SUPABASE_URL = "https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sashnT6QYhW2_ilgdPxAuPXwtM"


def fetch_hot_news():
    """
    Fetch hot news from Weibo and Toutiao APIs.
    Returns a dict with 'weibo' and 'toutiao' keys, each containing a list of news items.
    """
    news_data = {
        'weibo': [],
        'toutiao': []
    }
    
    # Fetch Weibo hot search
    try:
        weibo_url = "https://60s.viki.moe/v2/weibo"
        req = urllib.request.Request(weibo_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('code') == 200 and 'data' in data:
                # Sort by hot_value descending and take top 10
                items = sorted(data['data'], key=lambda x: x.get('hot_value', 0), reverse=True)[:10]
                news_data['weibo'] = items
                print(f"✓ 微博热搜: 获取 {len(items)} 条")
    except Exception as e:
        print(f"✗ 微博热搜获取失败: {e}")
    
    # Fetch Toutiao hot list
    try:
        toutiao_url = "https://60s.viki.moe/v2/toutiao"
        req = urllib.request.Request(toutiao_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('code') == 200 and 'data' in data:
                # Sort by hot_value descending and take top 10
                items = sorted(data['data'], key=lambda x: x.get('hot_value', 0), reverse=True)[:10]
                news_data['toutiao'] = items
                print(f"✓ 头条热榜: 获取 {len(items)} 条")
    except Exception as e:
        print(f"✗ 头条热榜获取失败: {e}")
    
    return news_data


def generate_news_html(news_data):
    """
    Generate HTML for the hot news section.
    Two-column layout: Weibo + Toutiao.
    Each news item shows: rank + title + date (M/D format) + hot_value.
    Top 3 items are highlighted with gold color.
    """
    today = datetime.now()
    date_str = f"{today.month}/{today.day}"
    
    html = '''
    <!-- ===== 每日热点新闻 ===== -->
    <section style="margin-bottom:24px;">
        <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px;">
            🔥 每日热点新闻
            <span style="font-size:13px;font-weight:400;color:var(--text-secondary);">微博热搜 + 头条热榜</span>
        </h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            <!-- 微博热搜 -->
            <div style="background:var(--bg-deep);border:1px solid var(--divider);border-radius:12px;padding:16px;">
                <h3 style="font-size:15px;font-weight:600;margin-bottom:12px;color:var(--gold);">
                    微博热搜
                </h3>
'''
    
    # Weibo news items
    if news_data.get('weibo'):
        for i, item in enumerate(news_data['weibo'][:10]):
            rank = i + 1
            title = item.get('title', item.get('name', '未知'))
            hot_value = item.get('hot_value', item.get('hot', 0))
            url = item.get('url', item.get('mobile_url', '#'))
            
            # Highlight top 3
            if rank <= 3:
                bg_color = 'var(--gold-soft)'
                rank_color = 'var(--gold)'
            else:
                bg_color = 'transparent'
                rank_color = 'var(--text-secondary)'
            
            html += f'''
                <a href="{url}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:10px;padding:8px;border-radius:8px;background:{bg_color};text-decoration:none;color:var(--text-primary);margin-bottom:6px;">
                    <span style="font-size:14px;font-weight:700;color:{rank_color};min-width:20px;">{rank}</span>
                    <span style="flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{title}</span>
                    <span style="font-size:11px;color:var(--text-secondary);">{date_str}</span>
                </a>
'''
    else:
        html += '<p style="color:var(--text-secondary);font-size:13px;">暂无数据</p>'
    
    html += '''
            </div>
            <!-- 头条热榜 -->
            <div style="background:var(--bg-deep);border:1px solid var(--divider);border-radius:12px;padding:16px;">
                <h3 style="font-size:15px;font-weight:600;margin-bottom:12px;color:var(--turf);">
                    头条热榜
                </h3>
'''
    
    # Toutiao news items
    if news_data.get('toutiao'):
        for i, item in enumerate(news_data['toutiao'][:10]):
            rank = i + 1
            title = item.get('title', item.get('name', '未知'))
            hot_value = item.get('hot_value', item.get('hot', 0))
            url = item.get('url', '#')
            
            # Highlight top 3
            if rank <= 3:
                bg_color = 'var(--turf-soft)'
                rank_color = 'var(--turf)'
            else:
                bg_color = 'transparent'
                rank_color = 'var(--text-secondary)'
            
            html += f'''
                <a href="{url}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:10px;padding:8px;border-radius:8px;background:{bg_color};text-decoration:none;color:var(--text-primary);margin-bottom:6px;">
                    <span style="font-size:14px;font-weight:700;color:{rank_color};min-width:20px;">{rank}</span>
                    <span style="flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{title}</span>
                    <span style="font-size:11px;color:var(--text-secondary);">{date_str}</span>
                </a>
'''
    else:
        html += '<p style="color:var(--text-secondary);font-size:13px;">暂无数据</p>'
    
    html += '''
            </div>
        </div>
    </section>
'''
    
    return html


def fetch_briefs():
    """
    Fetch all briefs from the briefs table.
    Returns a list of brief objects sorted by date descending.
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/briefs?select=*&order=date.desc"
        req = urllib.request.Request(url, headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            print(f"✓ 从 briefs 表获取到 {len(data)} 条简报")
            return data
    except Exception as e:
        print(f"✗ 获取简报列表失败: {e}")
        return []


def fetch_match_dates():
    """
    Fetch all unique match dates from the matches table.
    Returns a list of date strings in YYYY-MM-DD format, sorted descending.
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/matches?select=match_time&order=match_time.desc"
        req = urllib.request.Request(url, headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            # Extract unique dates
            dates = set()
            for item in data:
                match_time = item.get('match_time', '')
                if match_time:
                    date_str = match_time.split('T')[0]
                    dates.add(date_str)
            # Sort descending
            sorted_dates = sorted(dates, reverse=True)
            print(f"✓ 获取到 {len(sorted_dates)} 个比赛日期")
            return sorted_dates
    except Exception as e:
        print(f"✗ 获取比赛日期失败: {e}")
        return []


def fetch_matches_for_date(date_str):
    """
    Fetch all matches for a specific date.
    Returns a list of match objects.
    """
    try:
        # Use gte/lt for timestamp range query
        start_time = f"{date_str}T00:00:00"
        end_time = f"{date_str}T23:59:59"
        url = f"{SUPABASE_URL}/rest/v1/matches?select=*&match_time=gte.{start_time}&match_time=lte.{end_time}&order=match_time.asc"
        req = urllib.request.Request(url, headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except Exception as e:
        print(f"✗ 获取 {date_str} 比赛数据失败: {e}")
        return []


def fetch_predictions_for_matches(match_ids):
    """
    Fetch all predictions for a list of match IDs.
    Returns a list of prediction objects.
    """
    if not match_ids:
        return []
    
    try:
        # Build or filter
        or_filter = ','.join([f'match_id.eq.{mid}' for mid in match_ids])
        url = f"{SUPABASE_URL}/rest/v1/predictions?select=*&or=({or_filter})"
        req = urllib.request.Request(url, headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except Exception as e:
        print(f"✗ 获取预测数据失败: {e}")
        return []


def fetch_metadata_for_date(date_str):
    """
    Fetch metadata for a specific date from betting_daily table.
    Returns the metadata object or None.
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/betting_daily?select=*&match_date=eq.{date_str}"
        req = urllib.request.Request(url, headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data:
                # Map betting_daily fields to expected metadata format
                item = data[0]
                return {
                    'title': item.get('daily_summary', {}).get('title', ''),
                    'daily_commentary': item.get('daily_commentary', '')
                }
            return None
    except Exception as e:
        print(f"✗ 获取 {date_str} 元数据失败: {e}")
        return None


def generate_brief_page(news_data, all_dates):
    """
    Generate the brief index page HTML with collapsible list of all briefs.
    Returns (html, article_list) where article_list contains all dates.
    """
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    # Generate articles for all dates
    article_list = []
    for date_str in all_dates:
        matches = fetch_matches_for_date(date_str)
        metadata = fetch_metadata_for_date(date_str)
        # Determine type: latest date is prediction, others are review
        article_type = 'prediction' if date_str == all_dates[0] else 'review'
        article_list.append({
            'date': date_str,
            'matches': matches,
            'metadata': metadata,
            'match_count': len(matches),
            'type': article_type
        })
    
    # Build pinned articles HTML
    pinned_html = ''
    for article in article_list:
        date_str = article['date']
        match_count = article['match_count']
        article_type = article.get('type', 'prediction')
        metadata = article.get('metadata')
        
        # Format date for display
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            display_date = dt.strftime('%m月%d日')
            weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][dt.weekday()]
            display_date_full = f"{dt.month}月{dt.day}日 {weekday}"
        except:
            display_date = date_str
            display_date_full = date_str
        
        # Get title and icon based on type
        if article_type == 'prediction':
            icon = '🔮'
            type_label = '今日预测'
            type_color = 'var(--gold)'
            type_bg = 'var(--gold-soft)'
            if metadata and metadata.get('title'):
                title = metadata['title']
            else:
                title = f"{display_date_full} AI预测简报"
        else:
            icon = '📊'
            type_label = '昨日复盘'
            type_color = 'var(--turf)'
            type_bg = 'var(--turf-soft)'
            if metadata and metadata.get('title'):
                title = metadata['title']
            else:
                title = f"{display_date_full} AI复盘简报"
        
        # Generate article URL
        article_url = f"/brief-{date_str}.html"
        
        pinned_html += f'''
        <a href="{article_url}" style="display:flex;align-items:center;gap:16px;padding:20px 24px;background:var(--bg-deep);border:1px solid var(--divider);border-radius:12px;text-decoration:none;color:var(--text-primary);transition:all 0.2s;">
            <div style="font-size:32px;">{icon}</div>
            <div style="flex:1;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                    <span style="font-size:12px;padding:2px 8px;border-radius:4px;background:{type_bg};color:{type_color};font-weight:600;">{type_label}</span>
                </div>
                <div style="font-size:16px;font-weight:600;margin-bottom:4px;">{title}</div>
                <div style="font-size:13px;color:var(--text-secondary);">{display_date_full} · {match_count}场赛事</div>
            </div>
            <div style="font-size:20px;color:var(--text-secondary);">→</div>
        </a>
'''
    
    # Build brief list HTML (collapsible list of all briefs)
    brief_list_html = ''
    for article in article_list:
        date_str = article['date']
        match_count = article['match_count']
        article_type = article.get('type', 'prediction')
        
        # Format date for display
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            display_date = dt.strftime('%m月%d日')
            weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][dt.weekday()]
            display_date_full = f"{dt.month}月{dt.day}日 {weekday}"
        except:
            display_date = date_str
            display_date_full = date_str
        
        # Get title and icon based on type
        if article_type == 'prediction':
            icon = '🔮'
            type_label = '预测'
            type_bg = 'var(--turf-soft)'
            type_color = 'var(--turf)'
            title = f"{display_date_full} AI预测简报"
        else:
            icon = '📊'
            type_label = '复盘'
            type_bg = 'var(--gold-soft)'
            type_color = 'var(--gold)'
            title = f"{display_date_full} AI复盘简报"
        
        # Generate article URL
        article_url = f"/brief-{date_str}.html"
        
        brief_list_html += f'''
        <details style="margin-bottom:8px;border:1px solid var(--divider);border-radius:8px;overflow:hidden;">
            <summary style="padding:12px 16px;background:var(--bg-elevated);cursor:pointer;display:flex;align-items:center;gap:12px;list-style:none;">
                <span style="font-size:20px;">{icon}</span>
                <span style="flex:1;font-weight:500;">{title}</span>
                <span style="font-size:12px;color:var(--text-secondary);">{match_count}场</span>
                <span style="font-size:12px;color:var(--text-secondary);">▼</span>
            </summary>
            <div style="padding:12px 16px;background:var(--bg-deep);border-top:1px solid var(--divider);">
                <a href="{article_url}" style="display:inline-block;padding:8px 16px;background:var(--turf);color:white;border-radius:6px;text-decoration:none;font-size:14px;font-weight:500;">查看详情 →</a>
            </div>
        </details>
'''
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI预测简报 - AI实验室·体彩好伙伴</title>
    <meta name="description" content="每日AI预测简报，汇总7大AI模型对竞彩足球和篮球的预测分析，帮助用户了解AI的预测准确率。">
    <meta name="keywords" content="AI预测,体彩预测,赛事分析,竞彩足球,竞彩篮球,AI实验室">
    <link rel="canonical" href="https://zhulang.coze.site/brief.html">
    <meta property="og:title" content="AI预测简报 - AI实验室·体彩好伙伴">
    <meta property="og:description" content="每日AI预测简报，汇总7大AI模型对竞彩足球和篮球的预测分析。">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://zhulang.coze.site/brief.html">
    <style>
        :root {{
            --bg-night: #0B1220;
            --bg-deep: #0F1A2E;
            --bg-elevated: #16243D;
            --turf: #10B981;
            --turf-soft: rgba(16,185,129,0.15);
            --gold: #F5C242;
            --gold-soft: rgba(245,194,66,0.12);
            --miss: #3F4A60;
            --text-primary: #E8EEF7;
            --text-secondary: #94A3B8;
            --divider: rgba(255,255,255,0.08);
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
            background: var(--bg-night);
            color: var(--text-primary);
            line-height: 1.6;
        }}
        a {{ color: inherit; }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 0 20px; }}
        
        /* Navbar */
        .navbar {{
            background: rgba(11, 18, 32, 0.92);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--divider);
            padding: 10px 0;
            position: sticky;
            top: 0;
            z-index: 50;
        }}
        .navbar .container {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
        .logo {{ font-size: 18px; font-weight: 800; color: var(--gold); text-decoration: none; }}
        .logo span {{ color: var(--text-primary); }}
        .nav-links {{ display: flex; gap: 2px; flex-wrap: wrap; }}
        .nav-links a {{
            padding: 5px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
            text-decoration: none;
            transition: all 0.2s;
        }}
        .nav-links a:hover {{ color: var(--text-primary); background: rgba(255,255,255,0.04); }}
        .nav-links a.active {{ color: var(--gold); background: var(--gold-soft); }}
        
        /* Hero */
        .hero {{
            text-align: center;
            padding: 40px 20px;
            background: linear-gradient(135deg, var(--bg-deep) 0%, var(--bg-elevated) 100%);
            border-bottom: 1px solid var(--divider);
            margin-bottom: 24px;
        }}
        .hero h1 {{
            font-size: 32px;
            font-weight: 900;
            margin-bottom: 8px;
            background: linear-gradient(135deg, var(--gold) 0%, var(--turf) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .hero p {{
            font-size: 15px;
            color: var(--text-secondary);
        }}
        
        /* Pinned section */
        .pinned-section {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 24px;
        }}
        .pinned-section a:hover {{
            border-color: var(--gold) !important;
            transform: translateY(-2px);
        }}
        
        /* Footer */
        footer {{
            text-align: center;
            padding: 20px;
            border-top: 1px solid var(--divider);
            color: var(--text-secondary);
            font-size: 12px;
        }}
        
        @media (max-width: 600px) {{
            .hero h1 {{ font-size: 24px; }}
            .hero p {{ font-size: 13px; }}
        }}
    </style>
</head>
<body>
    <!-- Navbar -->
    <nav class="navbar">
        <div class="container">
            <a href="/" class="logo">AI实验室<span>·</span>体彩好伙伴</a>
            <div class="nav-links">
                <a href="/">首页</a>
                <a href="/brief.html" class="active">简报</a>
                <a href="/calculator.html">计算器</a>
                <a href="/ai-analysis.html">AI分析</a>
            </div>
        </div>
    </nav>
    
    <!-- Hero -->
    <section class="hero">
        <h1>AI预测简报</h1>
        <p>每日AI预测汇总，7大AI模型为您分析赛事</p>
    </section>
    
    <main class="container">
        <!-- All Briefs List (Collapsible) -->
        <section style="margin-bottom:24px;">
            <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px;">
                📋 全部简报 <span style="font-size:14px;color:var(--text-secondary);font-weight:400;">({len(article_list)}篇)</span>
            </h2>
            <div class="brief-list">
                {brief_list_html}
            </div>
        </section>
    </main>
    
    <footer>
        <p>AI实验室·体彩好伙伴 - 数据仅供参考，请理性看待</p>
    </footer>
</body>
</html>'''
    
    return html, article_list


def generate_brief_article(article, news_data):
    """
    Generate an individual article page for a specific date.
    Returns the HTML string.
    """
    date_str = article['date']
    matches = article['matches']
    metadata = article.get('metadata')
    match_count = article['match_count']
    article_type = article.get('type', 'prediction')
    
    # Format date for display
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        display_date = dt.strftime('%m月%d日')
        weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][dt.weekday()]
        display_date_full = f"{dt.year}年{dt.month}月{dt.day}日 {weekday}"
    except:
        display_date = date_str
        display_date_full = date_str
    
    # Get title and commentary from metadata, with type-based defaults
    if article_type == 'review':
        default_title = f"{display_date_full} AI复盘简报"
        section_title = "📊 AI复盘"
    else:
        default_title = f"{display_date_full} AI预测简报"
        section_title = "🔮 AI总评"
    
    title = default_title
    commentary = ""
    if metadata:
        if metadata.get('title'):
            title = metadata['title']
        if metadata.get('daily_commentary'):
            commentary = metadata['daily_commentary']
    
    # Generate matches table HTML
    matches_html = ''
    for match in matches:
        match_id = match.get('id', '')
        teams = match.get('teams', '')
        match_time = match.get('match_time', '')
        home_score = match.get('home_score')
        away_score = match.get('away_score')
        status = match.get('status', '')
        
        # Format time
        try:
            mt = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
            time_str = mt.strftime('%H:%M')
        except:
            time_str = match_time
        
        # Score display
        if home_score is not None and away_score is not None:
            score_str = f'{home_score}-{away_score}'
        else:
            score_str = 'VS'
        
        matches_html += f'''
        <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--bg-elevated);border:1px solid var(--divider);border-radius:8px;margin-bottom:8px;">
            <div style="display:flex;align-items:center;gap:12px;">
                <span style="font-size:13px;color:var(--text-secondary);min-width:40px;">{time_str}</span>
                <span style="font-size:14px;font-weight:500;">{teams}</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="font-size:16px;font-weight:700;color:var(--gold);">{score_str}</span>
                <span style="font-size:11px;padding:2px 6px;border-radius:4px;background:{'var(--turf-soft)' if status == 'confirmed' else 'var(--miss)'};color:{'var(--turf)' if status == 'confirmed' else 'var(--text-secondary)'};">{'已确认' if status == 'confirmed' else '待确认'}</span>
            </div>
        </div>
'''
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - AI实验室·体彩好伙伴</title>
    <meta name="description" content="{commentary[:150] if commentary else f'{display_date_full}AI预测简报，共{match_count}场赛事'}">
    <meta name="keywords" content="AI预测,体彩预测,赛事分析,竞彩足球,竞彩篮球,{date_str}">
    <link rel="canonical" href="https://zhulang.coze.site/brief-{date_str}.html">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{commentary[:150] if commentary else f'{display_date_full}AI预测简报'}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="https://zhulang.coze.site/brief-{date_str}.html">
    <meta property="article:published_time" content="{date_str}">
    <style>
        :root {{
            --bg-night: #0B1220;
            --bg-deep: #0F1A2E;
            --bg-elevated: #16243D;
            --turf: #10B981;
            --turf-soft: rgba(16,185,129,0.15);
            --gold: #F5C242;
            --gold-soft: rgba(245,194,66,0.12);
            --miss: #3F4A60;
            --text-primary: #E8EEF7;
            --text-secondary: #94A3B8;
            --divider: rgba(255,255,255,0.08);
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
            background: var(--bg-night);
            color: var(--text-primary);
            line-height: 1.6;
        }}
        a {{ color: inherit; }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 0 20px; }}
        
        /* Navbar */
        .navbar {{
            background: rgba(11, 18, 32, 0.92);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--divider);
            padding: 10px 0;
            position: sticky;
            top: 0;
            z-index: 50;
        }}
        .navbar .container {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
        .logo {{ font-size: 18px; font-weight: 800; color: var(--gold); text-decoration: none; }}
        .logo span {{ color: var(--text-primary); }}
        .nav-links {{ display: flex; gap: 2px; flex-wrap: wrap; }}
        .nav-links a {{
            padding: 5px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
            text-decoration: none;
            transition: all 0.2s;
        }}
        .nav-links a:hover {{ color: var(--text-primary); background: rgba(255,255,255,0.04); }}
        .nav-links a.active {{ color: var(--gold); background: var(--gold-soft); }}
        
        /* Back link */
        .back-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            margin: 16px 0;
            background: var(--bg-deep);
            border: 1px solid var(--divider);
            border-radius: 8px;
            text-decoration: none;
            color: var(--text-secondary);
            font-size: 13px;
            transition: all 0.2s;
        }}
        .back-link:hover {{
            border-color: var(--gold);
            color: var(--gold);
        }}
        
        /* Article header */
        .article-header {{
            text-align: center;
            padding: 32px 20px;
            background: linear-gradient(135deg, var(--bg-deep) 0%, var(--bg-elevated) 100%);
            border: 1px solid var(--divider);
            border-radius: 16px;
            margin-bottom: 24px;
        }}
        .article-header h1 {{
            font-size: 28px;
            font-weight: 900;
            margin-bottom: 8px;
            color: var(--gold);
        }}
        .article-header .meta {{
            font-size: 14px;
            color: var(--text-secondary);
        }}
        
        /* Commentary */
        .commentary {{
            background: var(--bg-deep);
            border: 1px solid var(--divider);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .commentary h2 {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 12px;
            color: var(--turf);
        }}
        .commentary p {{
            font-size: 14px;
            line-height: 1.8;
            color: var(--text-primary);
        }}
        
        /* Matches section */
        .matches-section {{
            margin-bottom: 24px;
        }}
        .matches-section h2 {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 16px;
        }}
        
        /* Footer */
        footer {{
            text-align: center;
            padding: 20px;
            border-top: 1px solid var(--divider);
            color: var(--text-secondary);
            font-size: 12px;
            margin-top: 24px;
        }}
        
        @media (max-width: 600px) {{
            .article-header h1 {{ font-size: 22px; }}
        }}
    </style>
</head>
<body>
    <!-- Navbar -->
    <nav class="navbar">
        <div class="container">
            <a href="/" class="logo">AI实验室<span>·</span>体彩好伙伴</a>
            <div class="nav-links">
                <a href="/">首页</a>
                <a href="/brief.html" class="active">简报</a>
                <a href="/calculator.html">计算器</a>
                <a href="/ai-analysis.html">AI分析</a>
            </div>
        </div>
    </nav>
    
    <main class="container">
        <!-- Back link -->
        <a href="/brief.html" class="back-link">← 返回简报列表</a>
        
        <!-- Article header -->
        <div class="article-header">
            <h1>{title}</h1>
            <div class="meta">{display_date_full} · {match_count}场赛事</div>
        </div>
        
        <!-- Commentary -->
        {f'<div class="commentary"><h2>{section_title}</h2><p>{commentary}</p></div>' if commentary else ''}
        
        <!-- Matches -->
        <div class="matches-section">
            <h2>赛事列表</h2>
            {matches_html if matches_html else '<p style="color:var(--text-secondary);">暂无赛事数据</p>'}
        </div>
    </main>
    
    <footer>
        <p>AI实验室·体彩好伙伴 - 数据仅供参考，请理性看待</p>
    </footer>
</body>
</html>'''
    
    return html


def main():
    """
    Main function to generate all pages.
    """
    print("开始生成 SEO 页面...")
    
    # Fetch hot news
    news_data = fetch_hot_news()
    
    # Fetch all match dates
    all_dates = fetch_match_dates()
    
    if not all_dates:
        print("✗ 未获取到比赛日期，退出")
        return
    
    # Generate brief index page
    print("生成简报索引页...")
    brief_html, article_list = generate_brief_page(news_data, all_dates)
    
    # Write brief.html
    output_dir = os.path.dirname(os.path.abspath(__file__))
    brief_path = os.path.join(output_dir, 'brief.html')
    with open(brief_path, 'w', encoding='utf-8') as f:
        f.write(brief_html)
    print(f"✓ brief.html 已生成")
    
    # Generate individual article pages (only 2: latest + second latest)
    print("生成独立文章页...")
    article_dates_for_sitemap = []
    for article in article_list:
        date_str = article['date']
        article_html = generate_brief_article(article, news_data)
        article_path = os.path.join(output_dir, f'brief-{date_str}.html')
        with open(article_path, 'w', encoding='utf-8') as f:
            f.write(article_html)
        print(f"✓ brief-{date_str}.html 已生成")
        article_dates_for_sitemap.append(date_str)
    
    # Generate sitemap (only include the 2 generated article pages)
    sitemap_urls = ['https://zhulang.coze.site/', 'https://zhulang.coze.site/brief.html']
    for date_str in article_dates_for_sitemap:
        sitemap_urls.append(f'https://zhulang.coze.site/brief-{date_str}.html')
    
    sitemap_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
'''
    for url in sitemap_urls:
        sitemap_xml += f'  <url><loc>{url}</loc></url>\n'
    sitemap_xml += '</urlset>'
    
    sitemap_path = os.path.join(output_dir, 'sitemap.xml')
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write(sitemap_xml)
    print(f"✓ sitemap.xml 已生成，包含 {len(sitemap_urls)} 个URL")
    
    # Update index.html brief section with latest data
    print("更新首页简报区块...")
    update_index_brief(output_dir, article_list)
    
    # Update brief.html with collapsible list
    print("更新简报列表页...")
    update_brief_page(output_dir, article_list)
    
    print("完成！")


def update_index_brief(output_dir, article_list):
    """Update the brief section in index.html with a list of brief titles from article_list."""
    if not article_list:
        print("  ⚠ 没有简报数据")
        return
    
    # Generate brief list HTML (latest 5 briefs)
    brief_items = []
    for article in article_list[:5]:
        date_str = article.get('date', '')
        article_type = article.get('type', 'prediction')
        match_count = article.get('match_count', 0)
        
        # Parse date for display
        try:
            if isinstance(date_str, str):
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                dt = datetime.combine(date_str, datetime.min.time())
            weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
            date_display = f"{dt.month}月{dt.day}日 {weekdays[dt.weekday()]}"
        except:
            date_display = date_str
        
        # Determine label and icon based on type
        is_prediction = article_type == 'prediction'
        label = "预测" if is_prediction else "复盘"
        icon = "🔮" if is_prediction else "📊"
        
        # Link to article page
        article_url = f"/brief-{date_str}.html"
        
        brief_items.append(f'''                <a href="{article_url}" class="brief-item">
                    <div class="top">
                        <span class="icon">{icon}</span>
                        <span class="title">{date_display} {label}</span>
                        <span class="count">{match_count}场</span>
                        <span class="arrow">→</span>
                    </div>
                </a>''')
    
    if not brief_items:
        return
    
    brief_list_html = '\n'.join(brief_items)
    
    # Read index.html
    index_path = os.path.join(output_dir, 'index.html')
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ✗ 读取index.html失败: {e}")
        return
    
    # Update brief-content
    new_brief_content = f'<!-- BRIEF_LIST_START -->\n{brief_list_html}\n                <!-- BRIEF_LIST_END -->'
    content = re.sub(
        r'<!-- BRIEF_LIST_START -->.*?<!-- BRIEF_LIST_END -->',
        new_brief_content,
        content,
        flags=re.DOTALL
    )
    
    # Write back
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ 首页简报已更新: {len(brief_items)}条简报")
    except Exception as e:
        print(f"  ✗ 写入index.html失败: {e}")


def update_brief_page(output_dir, article_list):
    """Update brief.html with collapsible list of all briefs from article_list."""
    if not article_list:
        print("  ⚠ 没有简报数据")
        return
    
    # Generate collapsible list HTML
    brief_sections = []
    for article in article_list:
        date_str = article.get('date', '')
        article_type = article.get('type', 'prediction')
        match_count = article.get('match_count', 0)
        
        # Parse date for display
        try:
            if isinstance(date_str, str):
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                dt = datetime.combine(date_str, datetime.min.time())
            weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
            date_display = f"{dt.year}年{dt.month}月{dt.day}日 {weekdays[dt.weekday()]}"
        except:
            date_display = date_str
        
        # Determine label and icon based on type
        is_prediction = article_type == 'prediction'
        label = "AI预测" if is_prediction else "AI复盘"
        icon = "🔮" if is_prediction else "📊"
        
        # Link to article page
        article_url = f"/brief-{date_str}.html"
        
        brief_sections.append(f'''            <div class="brief-section">
                <div class="brief-header" onclick="toggleBrief(this)">
                    <span class="arrow">▶</span>
                    <span class="icon">{icon}</span>
                    <span class="title">{date_display} {label}</span>
                    <span class="count">{match_count}场</span>
                    <a href="{article_url}" class="view-link" onclick="event.stopPropagation()">查看 →</a>
                </div>
                <div class="brief-body hidden">
                    <div class="brief-summary">
                        <p>点击查看{date_display}的{label}详情，包含AI分析、预测数据和比赛信息。</p>
                    </div>
                </div>
            </div>''')
    
    if not brief_sections:
        return
    
    brief_list_html = '\n'.join(brief_sections)
    
    # Read brief.html
    brief_path = os.path.join(output_dir, 'brief.html')
    try:
        with open(brief_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ✗ 读取brief.html失败: {e}")
        return
    
    # Update brief-list
    new_brief_list = f'<!-- BRIEF_LIST_START -->\n{brief_list_html}\n            <!-- BRIEF_LIST_END -->'
    content = re.sub(
        r'<!-- BRIEF_LIST_START -->.*?<!-- BRIEF_LIST_END -->',
        new_brief_list,
        content,
        flags=re.DOTALL
    )
    
    # Write back
    try:
        with open(brief_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ 简报列表页已更新: {len(brief_sections)}条简报")
    except Exception as e:
        print(f"  ✗ 写入brief.html失败: {e}")


if __name__ == '__main__':
    main()
