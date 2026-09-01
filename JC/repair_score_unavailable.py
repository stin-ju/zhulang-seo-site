#!/usr/bin/env python3
"""
一次性数据修复脚本 v2：清除 score_unavailable 脏标记 + 重算命中（足球+篮球）

根因：比分抓取脚本在暂时没抓到比分时写了 metadata.score_unavailable=true，
但后来比分抓到了，这个脏标记从来没被清除。导致 predictions 表有大量
is_settled=true 但 hit_status={'reason':'score_unavailable'} 的记录。

修复：
1. 清除 matches.metadata 中的 score_unavailable 脏标记（前提是有真实比分）
2. 对 predictions 中 hit_status->>'reason'='score_unavailable' 的记录，
   重新计算命中并写入正确的 hit_status + 布尔列
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supabase_db import execute_query, get_connection


def normalize_spf(spf):
    if not spf:
        return None
    spf = str(spf).strip()
    if spf in ("胜", "主胜", "让胜"):
        return "胜"
    if spf in ("平", "平局", "让平"):
        return "平"
    if spf in ("负", "客胜", "客负", "让负"):
        return "负"
    return spf


def normalize_handicap_spf(h):
    if not h:
        return None
    h = str(h).strip()
    if "胜" in h and "负" not in h and "平" not in h:
        return "胜"
    if "平" in h:
        return "平"
    if "负" in h:
        return "负"
    return h


def compute_football_hits(home_score, away_score, handicap, pred):
    hit = {}
    hit_cols = {}
    
    spf = pred.get("spf")
    if spf is not None:
        spf_norm = normalize_spf(spf)
        actual = "胜" if home_score > away_score else ("平" if home_score == away_score else "负")
        is_hit = (spf_norm == actual)
        hit["spf"] = is_hit
        hit_cols["spf_hit"] = is_hit
    
    handicap_spf = pred.get("handicap_spf")
    if handicap_spf is not None and handicap is not None:
        hc_norm = normalize_handicap_spf(handicap_spf)
        adjusted = home_score + float(handicap)
        actual = "让胜" if adjusted > away_score else ("让平" if adjusted == away_score else "让负")
        is_hit = (hc_norm == actual)
        hit["handicap_spf"] = is_hit
        hit_cols["handicap_spf_hit"] = is_hit
    
    score = pred.get("score")
    if score is not None:
        actual_score = f"{home_score}-{away_score}"
        is_hit = (str(score) == actual_score)
        hit["score"] = is_hit
        hit_cols["score_hit"] = is_hit
    
    goals = pred.get("goals")
    if goals is not None:
        total_goals = home_score + away_score
        try:
            is_hit = (int(goals) == total_goals)
        except (ValueError, TypeError):
            is_hit = False
        hit["goals"] = is_hit
        hit_cols["goals_hit"] = is_hit
    
    half_full = pred.get("half_full")
    half_home = pred.get("half_home_score")
    half_away = pred.get("half_away_score")
    if half_full is not None and half_home is not None and half_away is not None:
        half_result = "胜" if half_home > half_away else ("平" if half_home == half_away else "负")
        full_result = "胜" if home_score > away_score else ("平" if home_score == away_score else "负")
        actual_hf = f"{half_result}{full_result}"
        is_hit = (str(half_full) == actual_hf)
        hit["half_full"] = is_hit
        hit_cols["half_full_hit"] = is_hit
    
    return hit, hit_cols


def compute_basketball_hits(home_score, away_score, handicap, pred, md):
    hit = {}
    hit_cols = {}
    diff = abs(home_score - away_score)
    
    # 1. win_loss 胜负
    win_loss = pred.get("win_loss")
    if win_loss is not None:
        wl = str(win_loss).strip()
        predicted_home_wins = None
        if wl in ("主胜", "胜", "客负"):
            predicted_home_wins = True
        elif wl in ("客胜", "负", "主负"):
            predicted_home_wins = False
        if predicted_home_wins is not None:
            actual_home_wins = home_score > away_score
            is_hit = (predicted_home_wins == actual_home_wins)
            hit["win_loss"] = is_hit
            hit_cols["spf_hit"] = is_hit
    
    # 2. handicap_win_loss 让分胜负
    handicap_win_loss = pred.get("handicap_win_loss") or pred.get("handicap_result")
    if handicap_win_loss is not None and handicap is not None:
        try:
            hc_str = str(handicap_win_loss).strip()
            hc_float = float(handicap)
            adjusted = home_score + hc_float - away_score
            if adjusted > 0:
                actual_hc = "让胜"
            else:
                actual_hc = "让负"
            hc_norm = hc_str
            if hc_norm in ("让分主胜",):
                hc_norm = "让胜"
            elif hc_norm in ("让分主负",):
                hc_norm = "让负"
            is_hit = (hc_norm == actual_hc)
            hit["handicap_win_loss"] = is_hit
            hit_cols["handicap_spf_hit"] = is_hit
        except (ValueError, TypeError):
            pass
    
    # 3. total_points 大小分
    total_points = pred.get("total_points")
    if total_points is not None:
        total = home_score + away_score
        tp_str = str(total_points).strip()
        if tp_str in ("大", "小", "大分", "小分"):
            tp_short = tp_str[0]
            line = md.get("total_points_line")
            if line is None:
                _odds2 = md.get("odds", {}) or {}
                line = _odds2.get("total_points", {}).get("line")
            if line is not None:
                try:
                    line_f = float(line)
                    if tp_short == "大":
                        is_hit = total > line_f
                    else:
                        is_hit = total < line_f
                    hit["total_points"] = is_hit
                    hit_cols["goals_hit"] = is_hit
                except (ValueError, TypeError):
                    pass
    
    # 4. score_diff_range 分差区间
    score_diff_range = pred.get("score_diff_range") or pred.get("score_diff")
    if score_diff_range is not None:
        sdr_str = str(score_diff_range).strip()
        is_hit = False
        if "1-5" in sdr_str:
            is_hit = 1 <= diff <= 5
        elif "6-10" in sdr_str:
            is_hit = 6 <= diff <= 10
        elif "11-15" in sdr_str:
            is_hit = 11 <= diff <= 15
        elif "16-20" in sdr_str:
            is_hit = 16 <= diff <= 20
        elif "21+" in sdr_str or "21以上" in sdr_str:
            is_hit = diff >= 21
        hit["score_diff_range"] = is_hit
        hit_cols["score_hit"] = is_hit
    
    # 5. half_win_loss 半场胜负
    half_win_loss = pred.get("half_win_loss")
    half_home = pred.get("half_home_score")
    half_away = pred.get("half_away_score")
    if half_win_loss is not None and half_home is not None and half_away is not None:
        hwl = str(half_win_loss).strip()
        predicted_home_wins = None
        if hwl in ("主胜", "胜", "客负"):
            predicted_home_wins = True
        elif hwl in ("客胜", "负", "主负"):
            predicted_home_wins = False
        if predicted_home_wins is not None:
            actual_home_wins = half_home > half_away
            is_hit = (predicted_home_wins == actual_home_wins)
            hit["half_win_loss"] = is_hit
            hit_cols["half_full_hit"] = is_hit
    
    return hit, hit_cols


def main():
    print("=" * 60)
    print("一次性数据修复 v2：清除 score_unavailable 脏标记 + 重算命中（足球+篮球）")
    print("=" * 60)
    
    conn = get_connection()
    
    # Step 1: 清除 matches 脏标记
    print("\n[Step 1] 查找有真实比分但带 score_unavailable 脏标记的比赛...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, home_team, away_team, metadata
            FROM matches
            WHERE (metadata->>'score_unavailable')::boolean = true
              AND metadata->>'home_score' IS NOT NULL
              AND metadata->>'away_score' IS NOT NULL
        """)
        dirty_matches = cur.fetchall()
    
    print(f"  找到 {len(dirty_matches)} 场脏标记比赛")
    
    if dirty_matches:
        cleaned = 0
        for match_id, home_team, away_team, metadata in dirty_matches:
            md = metadata if isinstance(metadata, dict) else json.loads(metadata)
            md.pop("score_unavailable", None)
            md.pop("score_unavailable_reason", None)
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), match_id])
            cleaned += 1
        conn.commit()
        print(f"  已清除 {cleaned} 场比赛的 score_unavailable 脏标记")
    
    # Step 2: 查找剩余 score_unavailable 预测
    print("\n[Step 2] 查找 hit_status='score_unavailable' 的已结算预测...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.match_id, p.ai_name, p.prediction,
                   m.metadata, m.sport_type, m.home_team, m.away_team
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            WHERE p.hit_status->>'reason' = 'score_unavailable'
              AND p.is_settled = true
        """)
        dirty_preds = cur.fetchall()
    
    print(f"  找到 {len(dirty_preds)} 条脏预测")
    
    if not dirty_preds:
        print("  无需修复 predictions 表")
        conn.close()
        return
    
    # Step 3: 重新计算命中
    print("\n[Step 3] 重新计算命中...")
    rescued = 0
    no_score = 0
    no_pred = 0
    
    for pred_id, match_id, ai_name, prediction, metadata, sport_type, home_team, away_team in dirty_preds:
        md = metadata if isinstance(metadata, dict) else json.loads(metadata)
        home_score = md.get("home_score")
        away_score = md.get("away_score")
        
        if home_score is None or away_score is None:
            no_score += 1
            continue
        
        home_score = int(home_score)
        away_score = int(away_score)
        
        # 获取让球/大小分线
        odds = md.get("odds", {}) or {}
        handicap = md.get("handicap") or odds.get("handicap_spf", {}).get("handicap") or odds.get("hdc", {}).get("line")
        
        # 获取预测值
        pred = prediction if isinstance(prediction, dict) else (json.loads(prediction) if prediction else {})
        
        # 判断运动类型
        st = (sport_type or "").lower()
        
        # 计算命中
        if st == "basketball":
            hit, hit_cols = compute_basketball_hits(home_score, away_score, handicap, pred, md)
        else:
            hit, hit_cols = compute_football_hits(home_score, away_score, handicap, pred)
        
        if not hit:
            no_pred += 1
            continue
        
        # 写入数据库
        hit_json = json.dumps(hit, ensure_ascii=False)
        set_clauses = ["hit_status = %s::jsonb"]
        params = [hit_json]
        
        for col, val in hit_cols.items():
            set_clauses.append(f"{col} = %s")
            params.append(val)
        
        params.append(pred_id)
        sql = f"UPDATE predictions SET {', '.join(set_clauses)} WHERE id = %s"
        
        with conn.cursor() as cur:
            cur.execute(sql, params)
        
        rescued += 1
        hits = sum(1 for v in hit.values() if v is True)
        total = len(hit)
        print(f"  重算: {match_id} {ai_name} ({st}) -> {hits}/{total} 命中")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'=' * 60}")
    print(f"修复完成:")
    print(f"  matches 脏标记清除: {len(dirty_matches)} 场")
    print(f"  predictions 重算命中: {rescued} 条")
    print(f"  跳过(无比分): {no_score} 条")
    print(f"  跳过(无预测值): {no_pred} 条")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
