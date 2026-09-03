#!/usr/bin/env python3
"""
简报生成脚本 - 生成每日赛事预测/复盘简报HTML文件

用法:
    python3 generate_brief.py --date 2026-07-15 --type prediction
    python3 generate_brief.py --date 2026-07-14 --type review
    python3 generate_brief.py --date auto  # 自动生成今日简报
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# ====== psycopg2 自愈逻辑 ======
import importlib, subprocess, shutil
try:
    import psycopg2
    psycopg2.__version__
    from psycopg2._psycopg import __file__ as _test
except Exception:
    _target = '/opt/bytefaas/site-packages' if __import__('os').path.exists('/opt/bytefaas/site-packages') else None
    _pip = [__import__('sys').executable, '-m', 'pip', 'install', 'psycopg2-binary', '--no-cache-dir', '--force-reinstall']
    if _target:
        for _p in [_target+'/psycopg2', _target+'/psycopg2_binary']:
            if __import__('os').path.isdir(_p): shutil.rmtree(_p, ignore_errors=True)
        _pip += ['--target', _target]
        if _target not in __import__('sys').path: __import__('sys').path.insert(0, _target)
    subprocess.check_call(_pip, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _m in list(__import__('sys').modules):
        if 'psycopg2' in _m: del __import__('sys').modules[_m]
    import psycopg2
# ====== psycopg2 自愈结束 ======


def md(match):
    """安全提取match的metadata字典"""
    m = match.get('metadata') or {}
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except (json.JSONDecodeError, TypeError):
            m = {}
    return m

# 简报HTML模板
BRIEF_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <meta name="keywords" content="AI预测,体彩预测,赛事分析,竞彩足球,竞彩篮球,{date}">
    <link rel="canonical" href="{canonical_url}">
    <meta property="og:title" content="{og_title}">
    <meta property="og:description" content="{og_description}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{og_url}">
    <meta property="article:published_time" content="{date}">
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
            white-space: pre-line;
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
        
        /* Match card */
        .match-card {{
            background: var(--bg-deep);
            border: 1px solid var(--divider);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .match-card .match-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}
        .match-card .match-id {{
            font-size: 12px;
            color: var(--text-secondary);
            background: var(--bg-elevated);
            padding: 2px 8px;
            border-radius: 4px;
        }}
        .match-card .match-time {{
            font-size: 12px;
            color: var(--text-secondary);
        }}
        .match-card .teams {{
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 12px;
        }}
        .match-card .odds {{
            display: flex;
            gap: 12px;
            font-size: 13px;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }}
        .match-card .odds span {{
            background: var(--bg-elevated);
            padding: 4px 8px;
            border-radius: 4px;
        }}
        
        /* Predictions grid */
        .predictions-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 8px;
        }}
        .prediction-item {{
            background: var(--bg-elevated);
            border: 1px solid var(--divider);
            border-radius: 8px;
            padding: 8px;
            font-size: 12px;
        }}
        .prediction-item .ai-name {{
            color: var(--gold);
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .prediction-item .pred-value {{
            color: var(--text-primary);
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
            .predictions-grid {{ grid-template-columns: repeat(2, 1fr); }}
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
            <div class="meta">{date_str} {weekday} · {match_count}场赛事</div>
        </div>
        
        <!-- Commentary Section -->
        {commentary_section}
        
        <!-- Matches Section -->
        <section class="matches-section">
            <h2>📋 赛事详情</h2>
            {matches_html}
        </section>
    </main>
    
    <footer>
        <p>AI实验室 · 体彩好伙伴 | 数据仅供参考，购彩请理性</p>
    </footer>
</body>
</html>'''

WEEKDAY_MAP = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}

AI_CONFIGS = {
    'AI-DeepSeek': {'display': 'DeepSeek'},
    'AI-MiniMax': {'display': 'MiniMax'},
    'AI-豆包': {'display': '豆包'},
    'AI-智谱清言': {'display': '智谱清言'},
    'AI-文心': {'display': '文心'},
    'AI-混元': {'display': '混元'},
    'AI-扣子': {'display': '扣子'},
}


def get_db_connection():
    """获取数据库连接"""
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(url)


def fetch_matches_by_date(conn, date_str: str, sport_type: str = 'football') -> List[Dict]:
    """获取指定日期的比赛"""
    with conn.cursor() as cur:
        cur.execute('''
            SELECT id, home_team, away_team, sport_type, metadata
            FROM matches
            WHERE (metadata->>'match_date') = %s AND sport_type = %s
            ORDER BY metadata->>'match_time'
        ''', (date_str, sport_type))
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_predictions_for_matches(conn, match_ids: List[str]) -> List[Dict]:
    """获取指定比赛的预测"""
    if not match_ids:
        return []
    with conn.cursor() as cur:
        cur.execute('''
            SELECT match_id, ai_name, spf, handicap_spf, score, goals, half_full, analysis
            FROM predictions
            WHERE match_id = ANY(%s)
            ORDER BY match_id, ai_name
        ''', (match_ids,))
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def generate_commentary(matches: List[Dict], predictions: List[Dict], brief_type: str) -> str:
    """生成简报评论（跳过AI API，直接使用备用评论）"""
    # 构建比赛和预测摘要
    match_summary = []
    for m in matches:
        preds = [p for p in predictions if p['match_id'] == m['id']]
        metadata = md(m)
        odds = metadata.get('odds', {}) or {}
        spf = odds.get('spf', {}) or {}
        teams = f"{m.get('home_team', '')} vs {m.get('away_team', '')}"
        match_summary.append({
            'id': m['id'],
            'teams': teams,
            'time': str(metadata.get('match_time', '')),
            'odds': f"胜{spf.get('win') or '暂无'}/平{spf.get('draw') or '暂无'}/负{spf.get('lose') or '暂无'}",
            'predictions': [{'ai': p['ai_name'], 'spf': p.get('spf', ''), 'handicap': p.get('handicap_spf', '')} for p in preds]
        })
    
    # 直接使用备用评论，跳过AI API调用
    return generate_fallback_commentary(match_summary, brief_type)


def generate_fallback_commentary(match_summary: List[Dict], brief_type: str) -> str:
    """生成备用评论（当AI API不可用时）"""
    match_count = len(match_summary)
    total_preds = sum(len(m['predictions']) for m in match_summary)
    ai_count = len(set(p['ai'] for m in match_summary for p in m['predictions']))
    
    if brief_type == "prediction":
        return f"""今日共有{match_count}场赛事进入预测视野，{ai_count}个AI给出了各自的判断。

从预测分布来看，AI们在部分场次上形成了共识，但在关键场次上仍存在分歧。这种分歧往往源于对伤停信息、近期状态和赔率走势的不同解读。

值得关注的几点：
1. 赔率与市场态度的关联
2. AI预测的一致性程度
3. 关键场次的分歧分析

今日金句：数据是理性的，但足球从来不只是理性的游戏。"""
    else:
        return f"""今日{match_count}场赛事已尘埃落定，{ai_count}个AI的预测表现各有优劣。

从整体来看，AI们在高共识场次上表现稳定，但在分歧场次上的预测准确率则参差不齐。这也印证了一个规律：当AI意见高度一致时，往往意味着比赛走势相对明朗；而当分歧加大时，冷门的可能性也在增加。

今日金句：预测的价值不在于每次都准，而在于长期的大数定律。"""


def render_match_card(match: Dict, predictions: List[Dict]) -> str:
    """渲染单场比赛卡片"""
    match_preds = [p for p in predictions if p['match_id'] == match['id']]
    metadata = md(match)
    odds = metadata.get('odds', {}) or {}
    spf = odds.get('spf', {}) or {}
    teams = f"{match.get('home_team', '')} vs {match.get('away_team', '')}"
    
    # 赔率显示
    odds_html = ""
    if spf.get('win'):
        odds_html = f'''
        <div class="odds">
            <span>胜 {spf.get('win', '-')}</span>
            <span>平 {spf.get('draw', '-')}</span>
            <span>负 {spf.get('lose', '-')}</span>
        </div>'''
    
    # 预测网格
    preds_html = ""
    if match_preds:
        pred_items = []
        for p in match_preds:
            ai_display = AI_CONFIGS.get(p['ai_name'], {}).get('display', p['ai_name'].replace('AI-', ''))
            pred_items.append(f'''
            <div class="prediction-item">
                <div class="ai-name">{ai_display}</div>
                <div class="pred-value">{p.get('spf', '-')}</div>
            </div>''')
        preds_html = f'<div class="predictions-grid">{"".join(pred_items)}</div>'
    
    return f'''
    <div class="match-card">
        <div class="match-header">
            <span class="match-id">{match['id']}</span>
            <span class="match-time">{str(metadata.get('match_time', ''))[:16]}</span>
        </div>
        <div class="teams">{teams}</div>
        {odds_html}
        {preds_html}
    </div>'''


def generate_brief_html(date_str: str, brief_type: str, matches: List[Dict], predictions: List[Dict]) -> str:
    """生成简报HTML"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    weekday = WEEKDAY_MAP[dt.weekday()]
    type_suffix = "赛事预测" if brief_type == "prediction" else "赛后复盘"
    title = f"{dt.year}年{dt.month}月{dt.day}日 {weekday} {type_suffix}"
    
    # 生成评论
    commentary = generate_commentary(matches, predictions, brief_type)
    commentary_section = f'''
    <section class="commentary">
        <h2>{"📊 预测总论" if brief_type == "prediction" else "🏆 复盘总结"}</h2>
        <p>{commentary}</p>
    </section>'''
    
    # 生成比赛卡片
    matches_html = "\n".join(render_match_card(m, predictions) for m in matches)
    
    # 填充模板
    html = BRIEF_TEMPLATE.format(
        title=title,
        description=commentary[:150] + "..." if len(commentary) > 150 else commentary,
        date=date_str,
        date_str=f"{dt.year}年{dt.month}月{dt.day}日",
        weekday=weekday,
        match_count=len(matches),
        canonical_url=f"https://zhulang.coze.site/brief-{date_str}.html",
        og_title=title,
        og_description=commentary[:150] + "..." if len(commentary) > 150 else commentary,
        og_url=f"https://zhulang.coze.site/brief-{date_str}.html",
        commentary_section=commentary_section,
        matches_html=matches_html
    )
    
    return html


def save_brief_to_db(conn, date_str: str, brief_type: str, matches: List[Dict], commentary: str, content_html: str = ''):
    """保存简报到数据库"""
    brief_id = f"brief-{date_str}"
    match_ids = [m['id'] for m in matches]
    
    with conn.cursor() as cur:
        cur.execute('''
            INSERT INTO briefs (id, date, type, title, summary, match_ids, match_count, ai_analysis, sport_type, content_html)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                summary = EXCLUDED.summary,
                match_ids = EXCLUDED.match_ids,
                match_count = EXCLUDED.match_count,
                ai_analysis = EXCLUDED.ai_analysis,
                content_html = EXCLUDED.content_html
        ''', (
            brief_id,
            date_str,
            brief_type,
            f"{date_str} {'赛事预测' if brief_type == 'prediction' else '赛后复盘'}",
            commentary,
            json.dumps(match_ids),
            len(matches),
            json.dumps({'generated_at': datetime.now().isoformat()}),
            'football',
            content_html
        ))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='生成赛事简报')
    parser.add_argument('--date', default='auto', help='日期 (YYYY-MM-DD) 或 auto')
    parser.add_argument('--type', choices=['prediction', 'review'], default='prediction', help='简报类型')
    parser.add_argument('--output', default='html', choices=['html', 'db', 'both'], help='输出方式')
    args = parser.parse_args()
    
    # 确定日期
    if args.date == 'auto':
        date_str = datetime.now().strftime('%Y-%m-%d')
    else:
        date_str = args.date
    
    print(f"生成简报: {date_str} ({args.type})")
    
    # 连接数据库
    conn = get_db_connection()
    
    try:
        # 获取比赛数据
        matches = fetch_matches_by_date(conn, date_str)
        if not matches:
            print(f"警告: {date_str} 没有比赛数据")
            # 尝试查找最近的比赛日期
            return
        
        match_ids = [m['id'] for m in matches]
        print(f"找到 {len(matches)} 场比赛")
        
        # 获取预测数据
        predictions = fetch_predictions_for_matches(conn, match_ids)
        print(f"找到 {len(predictions)} 条预测")
        
        # 生成HTML
        html = generate_brief_html(date_str, args.type, matches, predictions)
        
        # 输出
        if args.output in ['html', 'both']:
            filename = f"brief-{date_str}.html"
            filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"HTML已保存: {filepath}")
        
        if args.output in ['db', 'both']:
            commentary = generate_commentary(matches, predictions, args.type)
            save_brief_to_db(conn, date_str, args.type, matches, commentary, content_html=html)
            print(f"简报已保存到数据库(含content_html {len(html)}字符)")
        
        print("简报生成完成!")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
