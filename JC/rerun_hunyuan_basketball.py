#!/usr/bin/env python3
"""
补跑混元篮球预测 - 强制prompt版本
解决混元在情报为空时回复"无任何情报无法预测"的问题
"""
import os
import sys
import json
import time
import re
import psycopg2

sys.path.insert(0, os.path.dirname(__file__))
from auto_predict import (
    AI_CONFIGS, call_ai, normalize_basketball_fields,
    validate_basketball_consistency, execute_query
)

DB_URL = os.environ.get('DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

# 需要补跑的14场篮球比赛
TARGET_MATCHES = [
    '20260828_周五301', '20260828_周五302', '20260828_周五303',
    '20260828_周四313', '20260828_周四314', '20260828_周四315',
    '20260829_周五304', '20260829_周五305', '20260829_周五306',
    '20260829_周五307', '20260829_周五308', '20260829_周五309',
    '20260829_周五310'
]

# 强制prompt后缀
FORCE_SUFFIX = """

【重要强制要求】即使情报数据不足或为空，你也必须基于赔率和主客场信息给出全部预测字段。
禁止回复"未知"、"无法预测"、"暂无"等无效内容。每个字段都必须给出明确的预测值。
- win_loss: 必须为"胜"或"负"（胜=主队赢，负=主队输）
- handicap_win_loss: 必须为"让胜"或"让负"
- total_points: 必须为"大"或"小"
- score_diff_range: 必须为"主X-Y胜"或"客X-Y胜"格式，且主/客前缀必须与win_loss方向一致
  (win_loss=胜→主X胜，win_loss=负→客X胜)
"""


def get_match_data(match_id):
    """获取比赛完整数据"""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, sport_type, home_team, away_team, metadata, status
        FROM matches WHERE id = %s
    """, (match_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'id': row[0],
        'sport_type': row[1],
        'home_team': row[2],
        'away_team': row[3],
        'metadata': row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {},
        'status': row[5]
    }


def build_forced_basketball_prompt(match):
    """构建强制篮球预测prompt（基于auto_predict.py的build_basketball_prompt）"""
    from auto_predict import build_basketball_prompt, get_intel
    
    intel_data = get_intel(match['id'])
    base_prompt = build_basketball_prompt(match, intel_data)
    return base_prompt + FORCE_SUFFIX


def save_prediction(match_id, ai_name, prediction):
    """保存或更新预测"""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # 检查是否已存在
    cur.execute("""
        SELECT id FROM predictions WHERE match_id = %s AND ai_name = %s
    """, (match_id, ai_name))
    existing = cur.fetchone()
    
    pred_json = json.dumps(prediction, ensure_ascii=False)
    
    if existing:
        cur.execute("""
            UPDATE predictions 
            SET prediction = %s::jsonb
            WHERE match_id = %s AND ai_name = %s
        """, (pred_json, match_id, ai_name))
    else:
        cur.execute("""
            INSERT INTO predictions (match_id, ai_name, sport_type, prediction, match_date, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, NOW())
        """, (match_id, ai_name, 'basketball', pred_json,
              match_id.split('_')[0]))
    
    conn.commit()
    conn.close()


def main():
    print("=" * 60)
    print("混元篮球补跑 - 强制prompt版本")
    print("=" * 60)
    
    success = 0
    failed = 0
    
    for match_id in TARGET_MATCHES:
        match = get_match_data(match_id)
        if not match:
            print(f"\n[SKIP] {match_id} - 比赛不存在")
            continue
        
        home = match['home_team']
        away = match['away_team']
        print(f"\n[{match_id}] {home} vs {away}")
        
        # 构建强制prompt
        prompt = build_forced_basketball_prompt(match)
        
        # 调用混元API
        print(f"  调用混元(hy-mt2-plus)...", end=" ", flush=True)
        
        try:
            result = call_ai("AI-混元", prompt, "basketball")
            
            if result is None:
                print("返回无法解析")
                failed += 1
                continue
            
            # 规范化字段
            result = normalize_basketball_fields(result)
            result = validate_basketball_consistency(result, match.get('metadata', {}).get('spread_line', 0))
            
            # 验证字段
            wl_map = {"主胜": "胜", "客胜": "负", "home": "胜", "away": "负"}
            wl = wl_map.get(result.get("win_loss", ""), result.get("win_loss", ""))
            if wl not in ("胜", "负"):
                print(f"win_loss非法: {result.get('win_loss')}")
                failed += 1
                continue
            
            hwl_map = {"让球胜": "让胜", "让球负": "让负"}
            hwl = hwl_map.get(result.get("handicap_win_loss", ""), result.get("handicap_win_loss", ""))
            if hwl not in ("让胜", "让负"):
                print(f"handicap非法: {result.get('handicap_win_loss')}")
                failed += 1
                continue
            
            tp_map = {"大分": "大", "小分": "小", "over": "大", "under": "小"}
            tp = tp_map.get(result.get("total_points", ""), result.get("total_points", ""))
            if tp not in ("大", "小"):
                print(f"total非法: {result.get('total_points')}")
                failed += 1
                continue
            
            sdr = str(result.get("score_diff_range", "")).strip()
            sdr = re.sub(r'^(主|客)(\d+[-+]\d*)负$', r'\1\2胜', sdr)
            sdr = re.sub(r'^主负(\d+[-+]\d*|\d+\+?)$', r'客胜\1', sdr)
            sdr = re.sub(r'^客负(\d+[-+]\d*|\d+\+?)$', r'主胜\1', sdr)
            sdr = re.sub(r'^(主|客)胜(\d+[-+]\d*|\d+\+?)$', r'\1\2胜', sdr)
            if not re.match(r'^(主|客)(\d+[-+]\d*|\d+\+?)胜$', sdr):
                print(f"score_diff非法: {sdr}")
                failed += 1
                continue
            
            hwl_half = wl_map.get(result.get("half_win_loss", ""), result.get("half_win_loss", ""))
            if hwl_half not in ("胜", "负"):
                print(f"half非法")
                failed += 1
                continue
            
            pred = {
                "win_loss": wl,
                "handicap_win_loss": hwl,
                "total_points": tp,
                "score_diff_range": sdr,
                "half_win_loss": hwl_half,
                "analysis": result.get("analysis", "")
            }
            
            save_prediction(match_id, "混元", pred)
            print(f"OK -> {wl}/{hwl}/{tp}/{sdr}")
            success += 1
            
        except Exception as e:
            print(f"异常: {str(e)[:100]}")
            failed += 1
        
        time.sleep(2)
    
    print(f"\n{'=' * 60}")
    print(f"补跑完成: 成功{success}, 失败{failed}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
