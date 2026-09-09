#!/usr/bin/env python3
"""
临时重跑脚本：强制重跑指定足球比赛的全部7AI预测，
复用 auto_predict.py 的 AI 调用链 + 确定性重算层(validate_football_consistency)，
UPSERT 幂等覆盖 predictions 表。
用法: python3 rerun_football_matches.py <match_id> [<match_id> ...]
"""
import sys
import time

sys.path.insert(0, ".")
import auto_predict as ap

TARGET_MATCHES = sys.argv[1:] or [
    "20260910_周三009",  # 巴黎圣曼 vs 布拉迪斯 (让-3)
    "20260910_周三008",  # 利物浦 vs 马竞 (让-1)
]


def main():
    # 取全部足球比赛（含已开赛），按 id 索引
    all_matches = ap.get_matches_by_sport("football")
    match_map = {m.get("id"): m for m in all_matches}

    for match_id in TARGET_MATCHES:
        match = match_map.get(match_id)
        if not match:
            print(f"\n[跳过] 未找到比赛 {match_id}")
            continue

        home = match.get("home_team", "?")
        away = match.get("away_team", "?")
        print(f"\n{'='*60}")
        print(f"重跑 {match_id}  {home} vs {away}")
        hc, present = ap._get_match_handicap_raw(match)
        print(f"让球盘口: {hc} (present={present})")
        print(f"{'='*60}")

        intel_data = ap.get_intel(match_id)
        prompt = ap.build_football_prompt(match, intel_data)

        for ai_name in ap.AI_CALL_ORDER:
            ai_short = ai_name.replace("AI-", "", 1)
            print(f"\n>>> {match_id} × {ai_short} ...", flush=True)
            try:
                result, raw_text, retries, error = ap._call_ai_single(
                    ai_name, match, "football", prompt, intel_data
                )
                if result is not None:
                    success, summary = ap._process_and_store(
                        ai_name, result, match, "football", raw_text=raw_text
                    )
                    if success:
                        print(f"    OK -> {summary}")
                    else:
                        print(f"    解析失败: {summary}")
                else:
                    print(f"    调用失败: {error}")
            except Exception as e:
                print(f"    异常: {e}")
            time.sleep(ap.AI_CALL_INTERVAL)


if __name__ == "__main__":
    main()
