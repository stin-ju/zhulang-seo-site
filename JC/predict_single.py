#!/usr/bin/env python3
"""单场比赛预测脚本"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auto_predict import (
    get_existing_predictions, get_intel,
    build_basketball_prompt, call_ai, validate_basketball_consistency,
    normalize_basketball_fields, AI_CALL_ORDER
)
from supabase_db import get_match_by_id, upsert_prediction

def predict_single_match(match_id, sport="basketball"):
    """为单场比赛生成所有AI预测"""
    match_data = get_match_by_id(match_id)
    if not match_data:
        print(f"比赛 {match_id} 不存在")
        return
    
    match = {
        "id": match_id,
        "home_team": match_data.get("home_team"),
        "away_team": match_data.get("away_team"),
        "metadata": match_data.get("metadata", {})
    }
    
    # 获取已有预测
    existing = get_existing_predictions(match_id)
    missing_ais = [ai for ai in AI_CALL_ORDER if ai not in existing]
    
    if not missing_ais:
        print(f"比赛 {match_id} 已有全部AI预测")
        return
    
    print(f"比赛: {match['home_team']} vs {match['away_team']}")
    print(f"待预测AI: {', '.join(missing_ais)}")
    
    # 获取情报
    intel_data = get_intel(match_id)
    
    # 构建Prompt
    prompt = build_basketball_prompt(match, intel_data) if sport == "basketball" else None
    
    success_count = 0
    for ai_name in missing_ais:
        try:
            print(f"  调用 {ai_name}...", end=" ", flush=True)
            result = call_ai(ai_name, prompt, sport)
            
            if result is None:
                print("返回无法解析")
                continue
            
            # 规范化
            if sport == "basketball":
                result = validate_basketball_consistency(result, 0)
                result = normalize_basketball_fields(result)
            
            # 保存
            ai_short_name = ai_name.replace("AI-", "", 1)
            pred_data = {
                "match_id": match_id,
                "ai_name": ai_short_name,
                "sport_type": sport,
                "prediction": result,
                "hit_status": None,
                "is_settled": False
            }
            upsert_prediction(pred_data)
            print(f"✓ 已保存")
            success_count += 1
            
        except Exception as e:
            print(f"✗ 错误: {e}")
    
    print(f"\n完成: {success_count}/{len(missing_ais)} 个AI预测已保存")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 predict_single.py <match_id> [sport]")
        sys.exit(1)
    
    match_id = sys.argv[1]
    sport = sys.argv[2] if len(sys.argv) > 2 else "basketball"
    predict_single_match(match_id, sport)
