#!/usr/bin/env python3
"""
从titan007获取比分并更新到数据库
"""

import os
import re
import psycopg2
import requests
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

# 已完赛但缺少比分的比赛
MATCHES_NEED_SCORE = [
    '20260729_周三001',
    '20260730_周三002',
    '20260730_周三003',
    '20260730_周三004',
    '20260730_周三005',
    '20260730_周三006',
    '20260730_周三301',
    '20260730_周三302',
    '20260731_周四001',
    '20260731_周四002',
    '20260731_周四003',
    '20260731_周四004',
    '20260731_周四005',
    '20260731_周四006',
    '20260731_周四301',
    '20260731_周四302',
    '20260731_周四303',
]

def fetch_titan007_scores():
    """从titan007获取足球比分"""
    url = "https://live.titan007.com/ajaxSoccerLive.aspx"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://live.titan007.com/'
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        return resp.text
    except Exception as e:
        print(f"获取titan007数据失败: {e}")
        return None

def parse_match_id(match_db_id):
    """从数据库ID提取日期和序号"""
    # 例如: 20260729_周三001 -> 20260729, 001
    parts = match_db_id.split('_')
    if len(parts) != 2:
        return None, None
    date_str = parts[0]  # 20260729
    seq_part = parts[1]  # 周三001 or 周三301
    
    # 提取数字序号
    seq_match = re.search(r'(\d+)$', seq_part)
    if seq_match:
        seq = seq_match.group(1)
        return date_str, seq
    return None, None

def update_match_score(cursor, match_id, score, half_score=None):
    """更新比赛比分到数据库"""
    try:
        # 读取现有metadata
        cursor.execute("SELECT metadata FROM matches WHERE id = %s", (match_id,))
        result = cursor.fetchone()
        if not result:
            print(f"  比赛 {match_id} 不存在")
            return False
        
        metadata = result[0]
        if isinstance(metadata, str):
            import json
            metadata = json.loads(metadata)
        
        # 更新比分
        if score:
            metadata['score'] = score
        if half_score:
            metadata['half_score'] = half_score
        
        # 写回数据库
        import json
        cursor.execute(
            "UPDATE matches SET metadata = %s WHERE id = %s",
            (json.dumps(metadata), match_id)
        )
        return True
    except Exception as e:
        print(f"  更新 {match_id} 失败: {e}")
        return False

def main():
    print("=" * 60)
    print("从titan007获取比分并更新数据库")
    print("=" * 60)
    
    # 连接数据库
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # 先查看哪些比赛需要更新比分
    print("\n需要更新比分的比赛:")
    matches_to_update = []
    for match_id in MATCHES_NEED_SCORE:
        cur.execute("""
            SELECT id, metadata->>'match_time' as match_time, 
                   metadata->>'home_team' as home, metadata->>'away_team' as away,
                   metadata->>'score' as score
            FROM matches WHERE id = %s
        """, (match_id,))
        result = cur.fetchone()
        if result:
            if result[4] is None or result[4] == '':
                print(f"  {match_id} | {result[1]} | 需要更新")
                matches_to_update.append(match_id)
            else:
                print(f"  {match_id} | 已有比分: {result[4]}")
        else:
            print(f"  {match_id} | 不存在")
    
    if not matches_to_update:
        print("\n所有比赛都已有比分，无需更新")
        cur.close()
        conn.close()
        return
    
    print(f"\n共 {len(matches_to_update)} 场比赛需要更新比分")
    
    # 尝试从titan007获取数据
    print("\n正在从titan007获取比分数据...")
    titan_data = fetch_titan007_scores()
    
    if titan_data:
        print(f"获取到 {len(titan_data)} 字节的数据")
        # 解析titan007数据（这里需要根据实际格式解析）
        # titan007的数据格式比较复杂，需要根据实际情况处理
        print("注意: titan007数据格式需要手动解析")
    
    # 如果没有从titan007获取到数据，提示用户手动输入
    print("\n" + "=" * 60)
    print("由于titan007数据格式复杂，建议手动查询并更新比分")
    print("=" * 60)
    
    # 查询每场比赛的详细信息
    print("\n比赛详情:")
    for match_id in matches_to_update:
        cur.execute("""
            SELECT id, metadata->>'match_time' as match_time,
                   metadata->>'league' as league,
                   metadata->>'home_team' as home, 
                   metadata->>'away_team' as away
            FROM matches WHERE id = %s
        """, (match_id,))
        result = cur.fetchone()
        if result:
            print(f"  {result[0]} | {result[1]} | {result[2]} | {result[3]} vs {result[4]}")
    
    cur.close()
    conn.close()
    
    print("\n请使用以下SQL手动更新比分:")
    print("UPDATE matches SET metadata = jsonb_set(metadata, '{score}', '\"2-1\"') WHERE id = '20260729_周三001';")

if __name__ == '__main__':
    main()
