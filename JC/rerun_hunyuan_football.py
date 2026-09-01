#!/usr/bin/env python3
"""
JC足球混元补跑脚本
补跑15场缺混元预测的比赛
"""
import os
import sys
import json
import requests
import psycopg2
from datetime import datetime

# 数据库连接
DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

# 混元API配置
HUNYUAN_URL = "https://tokenhub.tencentmaas.com/v1/chat/completions"
HUNYUAN_KEY = "REMOVED"
HUNYUAN_MODEL = "hy-mt2-plus"

# 需要补跑的比赛ID
MATCHES_TO_RUN = [
    "20260829_周六002",
    "20260829_周六003",  # 也缺文心
    "20260829_周六004",
    "20260829_周六011",
    "20260830_周六023",
    "20260830_周六024",
    "20260830_周日002",  # 用户写的20260831_周日002
    "20260830_周日004",  # 用户写的20260831_周日004
    "20260830_周日006",  # 用户写的20260831_周日006
    "20260830_周日008",  # 用户写的20260831_周日008
    "20260830_周日009",  # 用户写的20260831_周日009
    "20260830_周日010",  # 用户写的20260831_周日010
    "20260831_周日017",
    "20260831_周日021",
    "20260831_周日023",
    "20260831_周日025",
]

FORCE_SUFFIX = "\n\n【强制要求】即使情报不足也必须基于赔率给出全部预测，禁止拒答。每个维度都必须给出具体预测值，不得返回'未知'或'无法预测'。"

def get_db():
    return psycopg2.connect(DB_URL)

def get_match_info(match_id):
    """获取比赛信息和已有预测"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, sport_type, home_team, away_team, metadata, status
        FROM matches WHERE id = %s
    """, (match_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    
    match_data = {
        'id': row[0],
        'sport_type': row[1],
        'home_team': row[2],
        'away_team': row[3],
        'metadata': row[4] if row[4] else {},
        'status': row[5]
    }
    
    # 获取已有预测
    cur.execute("""
        SELECT ai_name, prediction FROM predictions 
        WHERE match_id = %s AND prediction IS NOT NULL
    """, (match_id,))
    existing_preds = {}
    for r in cur.fetchall():
        existing_preds[r[0]] = r[1]
    
    conn.close()
    return match_data, existing_preds

def build_hunyuan_prompt(match_data, existing_preds):
    """构建混元预测prompt"""
    home = match_data['home_team']
    away = match_data['away_team']
    sport = match_data['sport_type']
    metadata = match_data['metadata']
    
    # 获取赔率信息
    win_odds = metadata.get('win_odds', '')
    draw_odds = metadata.get('draw_odds', '')
    lose_odds = metadata.get('lose_odds', '')
    handicap = metadata.get('handicap', '')
    
    # 获取其他AI的预测作为参考
    other_preds = []
    for ai_name, pred in existing_preds.items():
        if ai_name != '混元' and pred:
            other_preds.append(f"{ai_name}: {json.dumps(pred, ensure_ascii=False)[:200]}")
    
    prompt = f"""你是专业体育预测分析师。请预测以下{sport}比赛的结果。

## 比赛信息
- 主队: {home}
- 客队: {away}
- 赔率: 胜{win_odds} 平{draw_odds} 负{lose_odds} 让球{handicap}

## 其他AI预测参考
{chr(10).join(other_preds[:5]) if other_preds else '无'}

## 预测要求
请基于赔率和球队实力给出预测，必须包含以下5个维度:
1. win_loss: 胜平负预测 (胜/平/负)
2. handicap: 让球预测 (让胜/让负)
3. score: 比分预测 (如 2:1)
4. goals: 进球数预测 (0/1/2/3/4+)
5. half_full: 半全场预测 (如 胜胜/平胜/负负)

## 输出格式 (严格JSON)
```json
{{
  "win_loss": "胜",
  "handicap": "让胜",
  "score": "2:1",
  "goals": "2",
  "half_full": "胜胜",
  "confidence": 75,
  "analysis": "简要分析"
}}
```
{FORCE_SUFFIX}"""
    
    return prompt

def call_hunyuan(prompt):
    """调用混元API"""
    headers = {
        "Authorization": f"Bearer {HUNYUAN_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": HUNYUAN_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4000
    }
    
    try:
        resp = requests.post(HUNYUAN_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        return content
    except Exception as e:
        print(f"  API调用失败: {e}")
        return None

def parse_prediction(content):
    """解析AI返回的预测"""
    if not content:
        return None
    
    # 尝试提取JSON
    import re
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass
    
    json_match = re.search(r'\{\s*.*?\}', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except:
            pass
    
    return None

def save_prediction(match_id, ai_name, prediction):
    """保存预测到数据库"""
    conn = get_db()
    cur = conn.cursor()
    
    # 检查是否已存在
    cur.execute("""
        SELECT id FROM predictions WHERE match_id = %s AND ai_name = %s
    """, (match_id, ai_name))
    existing = cur.fetchone()
    
    if existing:
        cur.execute("""
            UPDATE predictions SET prediction = %s WHERE match_id = %s AND ai_name = %s
        """, (json.dumps(prediction, ensure_ascii=False), match_id, ai_name))
    else:
        cur.execute("""
            INSERT INTO predictions (match_id, ai_name, prediction, match_date, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (match_id, ai_name, json.dumps(prediction, ensure_ascii=False), match_id[:8] if len(match_id) >= 8 else None))
    
    conn.commit()
    conn.close()

def main():
    print(f"=== JC足球混元补跑 ===")
    print(f"共 {len(MATCHES_TO_RUN)} 场比赛")
    print()
    
    success = 0
    failed = 0
    
    for match_id in MATCHES_TO_RUN:
        print(f"[{match_id}] ", end='', flush=True)
        
        result = get_match_info(match_id)
        if not result:
            print("比赛不存在")
            failed += 1
            continue
        
        match_data, existing_preds = result
        
        # 检查是否已有混元预测
        if '混元' in existing_preds and existing_preds['混元']:
            print("已有混元预测，跳过")
            success += 1
            continue
        
        print(f"{match_data['home_team']} vs {match_data['away_team']} ", end='', flush=True)
        
        # 构建prompt并调用API
        prompt = build_hunyuan_prompt(match_data, existing_preds)
        content = call_hunyuan(prompt)
        
        if not content:
            print("✗ API无响应")
            failed += 1
            continue
        
        prediction = parse_prediction(content)
        if not prediction:
            print(f"✗ 解析失败 (content={content[:100]})")
            failed += 1
            continue
        
        # 保存预测
        save_prediction(match_id, '混元', prediction)
        print(f"✓ 完成")
        success += 1
    
    print()
    print(f"=== 完成 ===")
    print(f"成功: {success}/{len(MATCHES_TO_RUN)}")
    print(f"失败: {failed}/{len(MATCHES_TO_RUN)}")

if __name__ == "__main__":
    main()
