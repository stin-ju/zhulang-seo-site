#!/usr/bin/env python3
"""
自动结算脚本 - 扫描已完赛但未结算的比赛，对比AI预测与实际结果
支持足球和篮球
"""

import psycopg2
import json
import sys
from datetime import datetime

DB_URL = "postgresql://postgres:" + process.env.DB_PASSWORD + "@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres"


def get_db():
    return psycopg2.connect(DB_URL)


def get_unsettled_matches(conn):
    """获取所有已完赛但未结算的比赛及其预测"""
    sql = """
    SELECT m.id, m.sport_type, m.home_team, m.away_team, m.metadata,
           p.id as pred_id, p.ai_name, p.prediction,
           p.spf, p.handicap_spf, p.goals, p.score, p.half_full,
           p.win_loss, p.handicap_win_loss, p.total_points, p.score_diff_range, p.half_win_loss
    FROM matches m
    JOIN predictions p ON p.match_id = m.id
    WHERE m.status = '已完赛'
      AND (p.is_settled = false OR p.is_settled IS NULL)
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def settle_football(row):
    """结算足球预测，返回 hit_status dict"""
    (match_id, sport_type, home_team, away_team, metadata,
     pred_id, ai_name, prediction,
     spf, handicap_spf, goals, score, half_full,
     win_loss, handicap_win_loss, total_points, score_diff_range, half_win_loss) = row

    md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
    home_score = md.get("home_score")
    away_score = md.get("away_score")
    handicap = md.get("handicap")

    if home_score is None or away_score is None:
        return None

    home_score = int(home_score)
    away_score = int(away_score)

    hit = {}

    # 1. spf 胜平负
    if spf is not None:
        if home_score > away_score:
            actual = "主胜"
        elif home_score == away_score:
            actual = "平"
        else:
            actual = "客胜"
        hit["spf"] = (spf == actual)

    # 2. handicap_spf 让球胜平负
    if handicap_spf is not None and handicap is not None:
        adjusted = home_score + float(handicap)
        if adjusted > away_score:
            actual = "主胜"
        elif adjusted == away_score:
            actual = "平"
        else:
            actual = "客胜"
        hit["handicap_spf"] = (handicap_spf == actual)

    # 3. goals 进球数
    if goals is not None:
        total_goals = home_score + away_score
        goals_str = str(goals)
        # 预测值可能是 "2/3" 这种范围格式
        if "/" in goals_str:
            parts = goals_str.split("/")
            try:
                low, high = int(parts[0]), int(parts[1])
                hit["goals"] = (low <= total_goals <= high)
            except (ValueError, IndexError):
                hit["goals"] = (goals_str == str(total_goals))
        else:
            try:
                hit["goals"] = (int(goals_str) == total_goals)
            except ValueError:
                hit["goals"] = False

    # 4. score 比分
    if score is not None:
        actual_score = f"{home_score}:{away_score}"
        hit["score"] = (score == actual_score)

    # 5. half_full 半场全场
    if half_full is not None:
        half_home = md.get("half_home_score")
        half_away = md.get("half_away_score")
        if half_home is not None and half_away is not None:
            half_home = int(half_home)
            half_away = int(half_away)
            half_result = "主胜" if half_home > half_away else ("平" if half_home == half_away else "客胜")
            full_result = "主胜" if home_score > away_score else ("平" if home_score == away_score else "客胜")
            actual_hf = f"{half_result}/{full_result}"
            hit["half_full"] = (half_full == actual_hf)
        # 没有半场数据则跳过

    return hit if hit else None


def settle_basketball(row):
    """结算篮球预测，返回 hit_status dict"""
    (match_id, sport_type, home_team, away_team, metadata,
     pred_id, ai_name, prediction,
     spf, handicap_spf, goals, score, half_full,
     win_loss, handicap_win_loss, total_points, score_diff_range, half_win_loss) = row

    md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
    home_score = md.get("home_score")
    away_score = md.get("away_score")
    handicap = md.get("handicap")

    if home_score is None or away_score is None:
        return None

    home_score = int(home_score)
    away_score = int(away_score)

    hit = {}

    # 1. win_loss 胜负
    if win_loss is not None:
        actual = "主胜" if home_score > away_score else "客胜"
        hit["win_loss"] = (win_loss == actual)

    # 2. handicap_win_loss 让分胜负
    if handicap_win_loss is not None and handicap is not None:
        adjusted = home_score + float(handicap)
        actual = "主胜" if adjusted > away_score else "客胜"
        hit["handicap_win_loss"] = (handicap_win_loss == actual)

    # 3. total_points 大小分
    if total_points is not None:
        total = home_score + away_score
        tp_str = str(total_points)
        # 预测值可能是 "210.5大" "大" "小" 等格式
        if "大" in tp_str or "小" in tp_str:
            # 提取分界线
            import re
            nums = re.findall(r'[\d.]+', tp_str)
            if nums:
                line = float(nums[0])
                predicted_big = "大" in tp_str
                actual_big = total > line
                hit["total_points"] = (predicted_big == actual_big)
            else:
                # 没有明确分界线，跳过
                pass
        else:
            try:
                hit["total_points"] = (float(tp_str) == float(total))
            except ValueError:
                hit["total_points"] = False

    # 4. score_diff_range 胜分差
    if score_diff_range is not None:
        diff = abs(home_score - away_score)
        sdr_str = str(score_diff_range)
        # 预测值可能是范围如 "1-5" "6-10" 或具体数字
        import re
        range_match = re.match(r'(\d+)\s*[-~]\s*(\d+)', sdr_str)
        if range_match:
            low, high = int(range_match.group(1)), int(range_match.group(2))
            hit["score_diff_range"] = (low <= diff <= high)
        else:
            try:
                hit["score_diff_range"] = (int(sdr_str) == diff)
            except ValueError:
                hit["score_diff_range"] = False

    # 5. half_win_loss 半场胜负（如果有）
    if half_win_loss is not None:
        half_home = md.get("half_home_score")
        half_away = md.get("half_away_score")
        if half_home is not None and half_away is not None:
            half_home = int(half_home)
            half_away = int(half_away)
            actual = "主胜" if half_home > half_away else "客胜"
            hit["half_win_loss"] = (half_win_loss == actual)

    return hit if hit else None


def main():
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"

    conn = get_db()
    rows = get_unsettled_matches(conn)

    if not rows:
        result = "无待结算记录"
        if result_mode == "display_only":
            print(result)
        elif result_mode == "notify":
            print(result)
        conn.close()
        return result

    settled_count = 0
    stats = {"football": {}, "basketball": {}}

    for row in rows:
        match_id, sport_type = row[0], row[1]
        pred_id, ai_name = row[5], row[6]

        # 判断运动类型 - 从matches表或sport_type字段
        st = (sport_type or "").lower()
        if st == "basketball":
            hit = settle_basketball(row)
            stat_key = "basketball"
        else:
            # 默认足球，也检查match_id前缀
            hit = settle_football(row)
            stat_key = "football"

        if hit is None:
            continue

        # 更新数据库
        hit_json = json.dumps(hit)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE predictions
                SET hit_status = %s::jsonb, is_settled = true
                WHERE id = %s
            """, (hit_json, pred_id))

        settled_count += 1
        if ai_name not in stats[stat_key]:
            stats[stat_key][ai_name] = {"total": 0, "hits": 0}
        stats[stat_key][ai_name]["total"] += 1
        # 计算命中数
        hits = sum(1 for v in hit.values() if v is True)
        stats[stat_key][ai_name]["hits"] += hits

    conn.commit()
    conn.close()

    # 构建结果
    lines = [f"自动结算完成：共结算 {settled_count} 条预测"]
    for st in ["football", "basketball"]:
        if stats[st]:
            lines.append(f"\n{st.upper()}:")
            for ai, s in stats[st].items():
                lines.append(f"  {ai}: {s['total']}条, 命中{s['hits']}个维度")

    result = "\n".join(lines)
    if result_mode in ("display_only", "notify"):
        print(result)
    return result


if __name__ == "__main__":
    main()
