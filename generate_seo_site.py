#!/usr/bin/env python3
"""
Generate SEO-friendly static HTML pages for the AI prediction website.
This script generates brief.html with daily hot news from Weibo and Toutiao.
"""

import urllib.request
import json
import os
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
                <a href="{url}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:8px;padding:8px 10px;margin-bottom:4px;border-radius:8px;background:{bg_color};text-decoration:none;color:var(--text-primary);transition:all 0.2s;">
                    <span style="font-size:14px;font-weight:700;color:{rank_color};min-width:20px;">{rank}</span>
                    <span style="flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{title}</span>
                    <span style="font-size:11px;color:var(--text-secondary);">{date_str}</span>
                    <span style="font-size:11px;color:var(--text-secondary);">{hot_value:,}</span>
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
            url = item.get('url', item.get('mobile_url', '#'))
            
            # Highlight top 3
            if rank <= 3:
                bg_color = 'var(--gold-soft)'
                rank_color = 'var(--gold)'
            else:
                bg_color = 'transparent'
                rank_color = 'var(--text-secondary)'
            
            html += f'''
                <a href="{url}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:8px;padding:8px 10px;margin-bottom:4px;border-radius:8px;background:{bg_color};text-decoration:none;color:var(--text-primary);transition:all 0.2s;">
                    <span style="font-size:14px;font-weight:700;color:{rank_color};min-width:20px;">{rank}</span>
                    <span style="flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{title}</span>
                    <span style="font-size:11px;color:var(--text-secondary);">{date_str}</span>
                    <span style="font-size:11px;color:var(--text-secondary);">{hot_value:,}</span>
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


def generate_brief_page():
    """
    Generate the brief.html page with daily hot news.
    """
    # Fetch hot news
    news_data = fetch_hot_news()
    news_html = generate_news_html(news_data)
    
    # Read the existing brief.html template
    brief_path = os.path.join(os.path.dirname(__file__), 'brief.html')
    
    if os.path.exists(brief_path):
        with open(brief_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Insert news_html after header and before brief-content
        # Find the position after the header section
        header_end = content.find('</div>', content.find('class="header"'))
        if header_end != -1:
            header_end = content.find('>', header_end) + 1
            # Find the position before brief-content
            brief_content_start = content.find('class="brief-content"')
            if brief_content_start != -1:
                brief_content_start = content.rfind('<div', 0, brief_content_start)
                
                if brief_content_start != -1:
                    # Insert news_html between header and brief-content
                    new_content = content[:header_end] + news_html + content[header_end:]
                    
                    # Write the updated content
                    with open(brief_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"✓ brief.html 已更新，插入热点新闻板块")
                else:
                    print("✗ 未找到 brief-content 位置")
            else:
                print("✗ 未找到 brief-content 位置")
        else:
            print("✗ 未找到 header section")
    else:
        print(f"✗ brief.html 不存在: {brief_path}")


if __name__ == '__main__':
    print("开始生成 SEO 页面...")
    generate_brief_page()
    print("完成！")
