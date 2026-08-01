#!/usr/bin/env python3
"""
篮球比赛预测结算脚本
为所有已完赛但未结算预测的篮球比赛，结算AI预测的各维度命中情况
"""
import sys
import json
sys.path.insert(0, "/workspace/projects/scripts/")
import supabase_db

client = supabase_db.get_client()

def md(match):
    """安全提取match的metadata字典"""
    m = match.get('metadata') or {}
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except:
            m = {}
    return m

def get_score_diff_range(diff, winner_is_home):
    """根据分差返回区间标签"""
    if diff <= 5:
        range_label = "1-5"
    elif diff <= 10:
        range_label = "6-10"
    elif diff <= 15:
        range_label = "11-15"
    elif diff <= 20:
        range_label = "16-20"
    elif diff <= 25:
        range_label = "21-25"
    else:
        range_label = "26+"
    
    prefix = "主" if winner_is_home else "客"
    return f"{prefix}{range_label}胜"

def settle_basketball_match(match, predictions):
    """结算一场篮球比赛的预测"""
    match_id = match["id"]
    metadata = md(match)
    home_score = metadata.get("home_score")
    away_score = metadata.get("away_score")
    handicap = metadata.get("handicap")
    
    if home_score is None or away_score is None:
        print(f"  ⚠️ {match_id}: 缺少比分，跳过")
        return []
    
    # 解析odds
    odds = metadata.get("odds") or {}
    if isinstance(odds, str):
        odds = json.loads(odds)
    
    # === 计算各维度实际结果 ===
    
    # 1. win_loss（独赢）
    if home_score > away_score:
        actual_win_loss = "胜"
    elif home_score < away_score:
        actual_win_loss = "负"
    else:
        actual_win_loss = "平"  # 篮球一般不会平
    
    # 2. handicap_win_loss（让分）
    actual_handicap_win_loss = None
    if handicap is not None:
        try:
            handicap_val = float(handicap)
            adjusted_home = home_score + handicap_val
            if adjusted_home > away_score:
                actual_handicap_win_loss = "让胜"
            elif adjusted_home < away_score:
                actual_handicap_win_loss = "让负"
            else:
                actual_handicap_win_loss = "走水"
        except (ValueError, TypeError):
            pass
    
    # 3. score_diff_range（分差区间）
    diff = abs(home_score - away_score)
    winner_is_home = home_score > away_score
    actual_score_diff_range = get_score_diff_range(diff, winner_is_home)
    
    # 4. total_points（大小分）
    actual_total_points = None
    total_points_line = None
    
    # 尝试从多个位置获取盘口
    if "goals" in odds and isinstance(odds["goals"], dict) and "line" in odds["goals"]:
        total_points_line = odds["goals"]["line"]
    elif "total_points_line" in metadata:
        total_points_line = metadata["total_points_line"]
    elif "spread" in odds and isinstance(odds["spread"], dict) and "handicap" in odds["spread"]:
        # spread格式可能是 {"over": 1.7, "under": 1.7, "handicap": "-1.5"}
        # 这里handicap是分差盘口，不是总分
        pass
    
    # 尝试从metadata的ai_summary里找
    if total_points_line is None and "ai_summary" in metadata:
        ai_summary = metadata["ai_summary"]
        if "goals" in ai_summary and isinstance(ai_summary["goals"], dict):
            # 有时候goals里有line
            pass
    
    if total_points_line is not None:
        try:
            line_val = float(total_points_line)
            total = home_score + away_score
            if total > line_val:
                actual_total_points = "大"
            elif total < line_val:
                actual_total_points = "小"
            else:
                actual_total_points = "走水"
        except (ValueError, TypeError):
            pass
    
    # 5. half_win_loss（半场胜负）- 没有数据，跳过
    actual_half_win_loss = None
    
    # === 构建实际结果 ===
    actual_result = {
        "win_loss": actual_win_loss,
        "handicap_win_loss": actual_handicap_win_loss,
        "score_diff_range": actual_score_diff_range,
        "total_points": actual_total_points,
        "half_win_loss": actual_half_win_loss,
    }
    
    print(f"  📊 实际结果: {actual_result}")
    print(f"     总分盘口: {total_points_line}, 总分: {home_score + away_score}")
    
    # === 结算每个AI的预测 ===
    results = []
    for pred in predictions:
        ai_name = pred["ai_name"]
        prediction = pred.get("prediction") or {}
        if isinstance(prediction, str):
            try:
                prediction = json.loads(prediction)
            except:
                prediction = {}
        
        hit_status = {}
        hits = 0
        total_dims = 0
        
        # win_loss
        if actual_win_loss and "win_loss" in prediction:
            total_dims += 1
            pred_val = prediction["win_loss"]
            is_hit = pred_val == actual_win_loss
            hit_status["win_loss"] = actual_win_loss
            hit_status["win_loss_hit"] = is_hit
            if is_hit:
                hits += 1
        
        # handicap_win_loss
        if actual_handicap_win_loss and "handicap_win_loss" in prediction:
            total_dims += 1
            pred_val = prediction["handicap_win_loss"]
            is_hit = pred_val == actual_handicap_win_loss
            hit_status["handicap_win_loss"] = actual_handicap_win_loss
            hit_status["handicap_win_loss_hit"] = is_hit
            if is_hit:
                hits += 1
        
        # score_diff_range
        if actual_score_diff_range and "score_diff_range" in prediction:
            total_dims += 1
            pred_val = prediction["score_diff_range"]
            is_hit = pred_val == actual_score_diff_range
            hit_status["score_diff_range"] = actual_score_diff_range
            hit_status["score_diff_range_hit"] = is_hit
            if is_hit:
                hits += 1
        
        # total_points
        if actual_total_points and "total_points" in prediction:
            total_dims += 1
            pred_val = prediction["total_points"]
            is_hit = pred_val == actual_total_points
            hit_status["total_points"] = actual_total_points
            hit_status["total_points_hit"] = is_hit
            if is_hit:
                hits += 1
        
        # half_win_loss
        if actual_half_win_loss and "half_win_loss" in prediction:
            total_dims += 1
            pred_val = prediction["half_win_loss"]
            is_hit = pred_val == actual_half_win_loss
            hit_status["half_win_loss"] = actual_half_win_loss
            hit_status["half_win_loss_hit"] = is_hit
            if is_hit:
                hits += 1
        
        hit_status["hits"] = f"{hits}/{total_dims}"
        
        # 更新数据库
        try:
            client.table("predictions").update({
                "hit_status": hit_status,
                "is_settled": True
            }).eq("id", pred["id"]).execute()
            
            hit_marks = []
            for dim in ["win_loss", "handicap_win_loss", "score_diff_range", "total_points", "half_win_loss"]:
                key = f"{dim}_hit"
                if key in hit_status:
                    hit_marks.append("✅" if hit_status[key] else "❌")
            
            print(f"    {ai_name}: {hit_status['hits']} {''.join(hit_marks)}")
            results.append({
                "ai_name": ai_name,
                "hits": hit_status["hits"],
                "hit_status": hit_status
            })
        except Exception as e:
            print(f"    ❌ {ai_name}: 更新失败 - {e}")
    
    return results

def main():
    print("=" * 60)
    print("篮球比赛预测结算脚本")
    print("=" * 60)
    
    # 1. 查询所有篮球比赛（Python端过滤status）
    matches_result = client.table("matches").select(
        "id, home_team, away_team, sport_type, metadata"
    ).eq("sport_type", "basketball").execute()
    
    # Python端过滤已完赛的比赛
    matches = [m for m in (matches_result.data or []) if md(m).get("status") == "已完赛"]
    print(f"\n找到 {len(matches)} 场已完赛的篮球比赛")
    
    total_settled = 0
    total_predictions = 0
    
    for match in matches:
        match_id = match["id"]
        home = match.get("home_team", "")
        away = match.get("away_team", "")
        metadata = md(match)
        score = f"{metadata.get('home_score')}-{metadata.get('away_score')}"
        
        print(f"\n{'─' * 50}")
        print(f"🏀 {match_id}: {home} {score} {away}")
        
        # 2. 获取这场比赛的所有预测
        preds_result = client.table("predictions").select(
            "id, ai_name, prediction, hit_status, is_settled"
        ).eq("match_id", match_id).execute()
        
        predictions = preds_result.data
        
        # 检查是否已经结算
        unsettled = [p for p in predictions if not p.get("is_settled")]
        
        if not unsettled:
            print(f"  ✅ 已结算，跳过")
            continue
        
        if not predictions:
            print(f"  ⚠️ 无预测数据，跳过")
            continue
        
        print(f"  预测数: {len(predictions)}, 未结算: {len(unsettled)}")
        
        # 3. 结算
        results = settle_basketball_match(match, predictions)
        total_settled += 1
        total_predictions += len(results)
    
    print(f"\n{'=' * 60}")
    print(f"结算完成!")
    print(f"  结算比赛数: {total_settled}")
    print(f"  结算预测数: {total_predictions}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
