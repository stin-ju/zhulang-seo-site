#!/usr/bin/env python3
"""
周六003文心补跑脚本
补跑大宫松鼠vs湘南海洋的文心预测
"""
import os
import sys
import json
import requests
import psycopg2

# 数据库连接
DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

# 文心API配置
WENXIN_URL = "https://qianfan.baidubce.com/v2/chat/completions"
WENXIN_KEY = "REMOVED"
WENXIN_MODEL = "ernie-4.5-turbo-32k"

MATCH_ID = "20260829_周六003"

def get_db():
    return psycopg2.connect(DB_URL)

def get_match_and_preds():
    """获取比赛信息和已有预测"""
    conn = get_db()
    cur = conn.cursor()
    
    # 获取比赛信息
    cur.execute("""
        SELECT id, sport_type, home_team, away_team, metadata
        FROM matches WHERE id = %s
    """, (MATCH_ID,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None, None, None, None, None
    
    match_id, sport_type, home, away, metadata = row
    
    # 获取已有预测
    cur.execute("""
        SELECT ai_name, prediction FROM predictions 
        WHERE match_id = %s AND prediction IS NOT NULL
    """, (match_id,))
    existing_preds = {}
    for r in cur.fetchall():
        existing_preds[r[0]] = r[1]
    
    conn.close()
    return match_id, sport_type, home, away, metadata, existing_preds

def build_wenxin_prompt(home, away, metadata, existing_preds):
    """构建文心预测prompt"""
    odds = metadata.get('odds', {})
    spf_odds = odds.get('spf', {})
    win_odds = spf_odds.get('win', '')
    draw_odds = spf_odds.get('draw', '')
    lose_odds = spf_odds.get('lose', '')
    
    # 获取其他AI的预测作为参考
    other_preds = []
    for ai_name, pred in existing_preds.items():
        if ai_name != '文心' and pred:
            spf = pred.get('spf', '')
            score = pred.get('score', '')
            other_preds.append(f"{ai_name}: 胜平负={spf}, 比分={score}")
    
    prompt = f"""你是专业足球预测分析师。请预测以下比赛的结果。

## 比赛信息
- 主队: {home}
- 客队: {away}
- 赔率: 胜{win_odds} 平{draw_odds} 负{lose_odds}

## 其他AI预测参考
{chr(10).join(other_preds) if other_preds else '无'}

## 预测要求
请基于赔率和球队实力给出预测，必须包含以下5个维度:
1. spf: 胜平负预测 (胜/平/负)
2. handicap_spf: 让球胜平负预测 (让胜/让平/让负)
3. score: 比分预测 (如 1:2)
4. goals: 总进球数预测 (0/1/2/3/4/5)
5. half_full: 半全场预测 (如 平负/胜胜/负负)

## 输出格式 (严格JSON)
```json
{{
  "spf": "负",
  "handicap_spf": "让负",
  "score": "1-2",
  "goals": 3,
  "half_full": "平负"
}}
```"""
    
    return prompt

def call_wenxin(prompt):
    """调用文心API"""
    headers = {
        "Authorization": f"Bearer {WENXIN_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": WENXIN_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2048
    }
    
    try:
        resp = requests.post(WENXIN_URL, headers=headers, json=payload, timeout=120)
        print(f"API Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Error: {resp.text[:300]}")
            return None
        
        data = resp.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        return content
    except Exception as e:
        print(f"API调用失败: {e}")
        return None

def parse_prediction(content):
    """解析AI返回的预测"""
    if not content:
        return None
    
    import re
    # 尝试提取JSON
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
        print("更新已有记录")
    else:
        cur.execute("""
            INSERT INTO predictions (match_id, ai_name, prediction, match_date)
            VALUES (%s, %s, %s, %s)
        """, (match_id, ai_name, json.dumps(prediction, ensure_ascii=False), match_id[:8] if len(match_id) >= 8 else None))
        print("插入新记录")
    
    conn.commit()
    conn.close()

def main():
    print(f"=== 周六003文心补跑 ===")
    print(f"Match: {MATCH_ID}")
    print()
    
    result = get_match_and_preds()
    if not result or not result[0]:
        print("比赛不存在")
        return
    
    match_id, sport_type, home, away, metadata, existing_preds = result
    print(f"比赛: {home} vs {away} ({sport_type})")
    print(f"已有预测: {list(existing_preds.keys())}")
    
    # 检查是否已有文心预测
    if '文心' in existing_preds:
        print("已有文心预测，跳过")
        return
    
    # 构建prompt并调用API
    prompt = build_wenxin_prompt(home, away, metadata, existing_preds)
    print(f"\nPrompt长度: {len(prompt)} 字符")
    
    content = call_wenxin(prompt)
    if not content:
        print("✗ API无响应")
        return
    
    print(f"\nAPI响应: {content[:200]}")
    
    prediction = parse_prediction(content)
    if not prediction:
        print(f"✗ 解析失败")
        return
    
    print(f"\n解析结果: {json.dumps(prediction, ensure_ascii=False)}")
    
    # 验证必填字段
    required_fields = ['spf', 'handicap_spf', 'score', 'goals', 'half_full']
    missing = [f for f in required_fields if f not in prediction]
    if missing:
        print(f"✗ 缺少字段: {missing}")
        return
    
    # 保存预测
    save_prediction(match_id, '文心', prediction)
    print(f"\n✓ 完成")

if __name__ == "__main__":
    main()
