#!/usr/bin/env python3
"""
自动结算脚本 v2 - 扫描已完赛但未结算的比赛，对比AI预测与实际结果
支持足球和篮球，适配当前数据库schema

predictions表关键列：
  足球: spf(胜/平/负), handicap_spf(让胜/让平/让负), goals(int), score(1-0), half_full(胜胜)
  篮球: win_loss(胜/负), handicap_win_loss(让胜/让负), total_points(大/小), score_diff_range(主6-10胜), half_win_loss(胜/负)
  命中列: spf_hit, goals_hit, score_hit, half_full_hit, handicap_spf_hit (bool)
  汇总: hit_status(jsonb), is_settled(bool)
"""

import os
import psycopg2
import json
import sys
import re
from datetime import datetime, timedelta
try:
    from titan007_client import fetch_scores, fetch_scores_range, fetch_over_scores, find_match_in_titan_data
    HAS_TITAN007 = True
except ImportError:
    HAS_TITAN007 = False

DEFAULT_DB_URL = "postgresql://postgres:" + os.environ.get("DB_PASSWORD", "1538PQKpnIj0buIb6Y") + "@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres"


def get_db(db_url=None):
    return psycopg2.connect(db_url or DEFAULT_DB_URL)


def _derive_date_from_id(match_id):
    """从 match ID 推导日期，如 '20260705_周日203' -> '2026-07-05'"""
    m = re.match(r'(\d{4})(\d{2})(\d{2})_', match_id)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _get_pred_field(pred_jsonb, top_level_val, *jsonb_keys):
    """优先从 prediction jsonb 取值，fallback 到顶层列"""
    if pred_jsonb and isinstance(pred_jsonb, dict):
        for key in jsonb_keys:
            v = pred_jsonb.get(key)
            if v is not None:
                return v
    return top_level_val


def _normalize_spf(val):
    """归一化足球胜平负: 主胜→胜, 客胜/客负→负"""
    if val is None:
        return None
    val = str(val).strip()
    mapping = {"主胜": "胜", "客胜": "负", "客负": "负", "主负": "负"}
    return mapping.get(val, val)


def _normalize_handicap_spf(val):
    """归一化让球胜平负: 让主胜→让胜, 让客胜→让负, 让客负→让负"""
    if val is None:
        return None
    val = str(val).strip()
    mapping = {"让主胜": "让胜", "让客胜": "让负", "让客负": "让负", "让主负": "让负"}
    return mapping.get(val, val)


def fill_missing_scores(conn):
    """从 titan007 补全已完赛但缺少比分的比赛，同时检查 on_sale 但可能已完赛的比赛"""
    if not HAS_TITAN007:
        return 0

    # 查所有可能需要补全比分的比赛：已完赛、on_sale、已取消都要查
    # 规则：不管体彩是否取消，只要赛程抓回来就必须做预测及结算
    sql = """
    SELECT m.id, m.sport_type, m.home_team, m.away_team, m.status, m.metadata
    FROM matches m
    WHERE m.status = '已完赛' OR m.status = 'on_sale' OR m.status = '已取消' OR m.status = '未开赛'
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    missing = []
    on_sale_candidates = []
    for row in rows:
        match_id, sport_type, home_team, away_team, top_status, metadata = row
        md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
        # 修改1: 不再跳过 score_unavailable 的比赛，允许重试获取比分

        if top_status == '已完赛':
            # 已完赛但缺比分
            if md.get("home_score") is None or md.get("away_score") is None:
                missing.append({"id": match_id, "sport_type": sport_type,
                              "home_team": home_team, "away_team": away_team, "metadata": md,
                              "top_status": top_status})
        elif top_status == '已取消':
            # 已取消的比赛也要尝试从titan007获取比分，有真实比分就改回已完赛
            # 规则：不管体彩是否取消，只要赛程抓回来就必须做预测及结算
            missing.append({"id": match_id, "sport_type": sport_type,
                          "home_team": home_team, "away_team": away_team, "metadata": md,
                          "top_status": top_status})
        elif top_status == 'on_sale':
            # on_sale 但可能已完赛（比赛时间已过3小时以上）
            mt = md.get("match_time", "")
            if mt:
                try:
                    # match_time 可能是 "18:30:00" 或 "2026-07-19 18:30:00"
                    if " " in mt:
                        match_dt = ((datetime.strptime(mt, "%Y-%m-%d %H:%M:%S") if len(mt.strip().split(":")) == 3 else datetime.strptime(mt, "%Y-%m-%d %H:%M")) if len(mt.strip().split(":")) == 3 else datetime.strptime(mt, "%Y-%m-%d %H:%M"))
                    else:
                        # 仅有时间，需要从 ID 推导日期
                        date_str = _derive_date_from_id(match_id)
                        if date_str:
                            combined = f"{date_str} {mt}"
                            match_dt = (datetime.strptime(combined, "%Y-%m-%d %H:%M:%S") if len(mt.strip().split(":")) == 3 else datetime.strptime(combined, "%Y-%m-%d %H:%M"))
                        else:
                            continue
                    now = datetime.now()
                    if (now - match_dt).total_seconds() > 3 * 3600:  # 开赛3小时后
                        on_sale_candidates.append({"id": match_id, "sport_type": sport_type,
                                                   "home_team": home_team, "away_team": away_team,
                                                   "metadata": md, "top_status": top_status})
                except (ValueError, TypeError) as e:
                    print(f"  [警告] {match_id} on_sale时间解析失败: {mt}, 错误: {e}")
        elif top_status == '未开赛':
            # 未开赛但比赛时间已过3小时以上，可能已完赛但未更新状态
            mt = md.get("match_time", "")
            if mt:
                try:
                    if " " in mt:
                        match_dt = ((datetime.strptime(mt, "%Y-%m-%d %H:%M:%S") if len(mt.strip().split(":")) == 3 else datetime.strptime(mt, "%Y-%m-%d %H:%M")) if len(mt.strip().split(":")) == 3 else datetime.strptime(mt, "%Y-%m-%d %H:%M"))
                    else:
                        date_str = _derive_date_from_id(match_id)
                        if date_str:
                            combined = f"{date_str} {mt}"
                            match_dt = (datetime.strptime(combined, "%Y-%m-%d %H:%M:%S") if len(mt.strip().split(":")) == 3 else datetime.strptime(combined, "%Y-%m-%d %H:%M"))
                        else:
                            continue
                    now = datetime.now()
                    if (now - match_dt).total_seconds() > 3 * 3600:  # 开赛3小时后
                        on_sale_candidates.append({"id": match_id, "sport_type": sport_type,
                                                   "home_team": home_team, "away_team": away_team,
                                                   "metadata": md, "top_status": top_status})
                except (ValueError, TypeError) as e:
                    print(f"  [警告] {match_id} 未开赛时间解析失败: {mt}, 错误: {e}")

    all_to_fill = missing + on_sale_candidates
    if not all_to_fill:
        print("[比分补全] 无需补全")
        return 0

    if missing:
        print(f"[比分补全] 发现 {len(missing)} 场缺少比分的已完赛比赛")
    if on_sale_candidates:
        print(f"[比分补全] 发现 {len(on_sale_candidates)} 场 on_sale 但可能已完赛的比赛")

    football_missing = [m for m in all_to_fill if m["sport_type"] == "football"]
    basketball_missing = [m for m in all_to_fill if m["sport_type"] == "basketball"]

    if not football_missing and not basketball_missing:
        return 0

    # 修改2: 不再区分新旧比赛，统一处理所有比赛
    now = datetime.now()
    dates_needed = set()
    matches_to_process = []  # 所有需要处理的足球比赛

    for m in football_missing:
        mt = m["metadata"].get("match_time", "")
        date_str = None
        if mt:
            try:
                if " " in mt:
                    date_str = mt.split(" ")[0]
            except ValueError as e:
                print(f"  [警告] 日期推导失败: {e}")

        if not date_str:
            date_str = _derive_date_from_id(m["id"])

        if date_str:
            matches_to_process.append(m)
            dates_needed.add(date_str)
            # 将日期存入 metadata 供后续使用
            m["_date_str"] = date_str
        else:
            # 无法确定日期，也加入处理列表，后续用 ID 推导
            matches_to_process.append(m)
            m["_date_str"] = None

    if not matches_to_process and not basketball_missing:
        print(f"[比分补全] 完成，补全 0 场")
        return 0

    # 修改3: 查询 titan007 数据，优先使用 fetch_over_scores，fallback 到 fetch_scores
    # 支持时区日期偏移：体彩日期和titan007可能差1天，查前后各1天合并
    titan_data = {}
    for ds in dates_needed:
        combined = []
        seen_ids = set()
        for offset in [0, -1, 1]:
            dt = datetime.strptime(ds, "%Y-%m-%d")
            target = dt + timedelta(days=offset)
            titan_date = f"{target.year}-{target.month}-{target.day}"
            
            # 优先调用 fetch_over_scores
            matches = fetch_over_scores("football", titan_date)
            source = "over"
            
            # 如果 fetch_over_scores 返回为空，fallback 到 fetch_scores
            if not matches:
                matches = fetch_scores("football", titan_date)
                source = "cp"
            
            if matches:
                for tm in matches:
                    tm_id = f"{tm['home_team']}_{tm['away_team']}_{tm.get('match_time','')}"
                    if tm_id not in seen_ids:
                        seen_ids.add(tm_id)
                        combined.append(tm)
                if offset == 0:
                    print(f"  [titan007-{source}] {ds} 共{len(matches)}场完场")
                elif matches:
                    print(f"  [titan007-{source}] {ds} 偏移{offset:+d}天({titan_date}) 补充{len(matches)}场")
        if combined:
            titan_data[ds] = combined
            print(f"  [titan007] {ds} 合并后共{len(combined)}场(含前后1天偏移)")

    # 也查篮球的 titan007 数据（同样支持日期偏移，优先 fetch_over_scores）
    basketball_titan_data = {}
    if basketball_missing:
        bk_dates_needed = set()
        for m in basketball_missing:
            date_str = _derive_date_from_id(m["id"])
            if date_str:
                bk_dates_needed.add(date_str)
        for ds in bk_dates_needed:
            combined = []
            seen_ids = set()
            for offset in [0, -1, 1]:
                dt = datetime.strptime(ds, "%Y-%m-%d")
                target = dt + timedelta(days=offset)
                titan_date = f"{target.year}-{target.month}-{target.day}"
                
                # 优先调用 fetch_over_scores
                bmatches = fetch_over_scores("basketball", titan_date)
                # fallback 到 fetch_scores
                if not bmatches:
                    bmatches = fetch_scores("basketball", titan_date)
                
                if bmatches:
                    # fetch_over_scores returns dict for basketball: {home_team: (home_score, away_team, away_score)}
                    # fetch_scores returns list of dicts
                    if isinstance(bmatches, dict):
                        # Convert dict to list of match objects
                        bmatches_list = []
                        for home_team, (home_score, away_team, away_score) in bmatches.items():
                            bmatches_list.append({
                                'home_team': home_team,
                                'home_team_trad': home_team,  # Required by find_match_in_titan_data
                                'home_team_official': '',
                                'away_team': away_team,
                                'away_team_trad': away_team,  # Required by find_match_in_titan_data
                                'away_team_official': '',
                                'home_score': home_score,
                                'away_score': away_score,
                            })
                        bmatches = bmatches_list
                    for tm in bmatches:
                        tm_id = f"{tm['home_team']}_{tm['away_team']}_{tm.get('match_time','')}"
                        if tm_id not in seen_ids:
                            seen_ids.add(tm_id)
                            combined.append(tm)
            if combined:
                basketball_titan_data[ds] = combined

    updated = 0
    for m in matches_to_process:
        mt = m["metadata"].get("match_time", "")
        if mt and " " in mt:
            ds = mt.split(" ")[0]
        else:
            ds = _derive_date_from_id(m["id"]) or ""

        titan_matches = titan_data.get(ds, [])
        if not titan_matches:
            # 标记为无法补全，避免重复查询
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "no_titan_data"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            print(f"  [标记跳过] {m['id']}: 无titan007数据({ds})")
            conn.commit()
            continue

        found = find_match_in_titan_data(m["home_team"], m["away_team"], titan_matches)
        if found and found["home_score"] is not None and found["away_score"] is not None:
            md = m["metadata"]
            md["home_score"] = found["home_score"]
            md["away_score"] = found["away_score"]
            md["status"] = "已完赛"
            if found.get("home_half") is not None:
                md["half_home_score"] = found["home_half"]
            if found.get("away_half") is not None:
                md["half_away_score"] = found["away_half"]
            # Auto-extract handicap from odds if missing
            if md.get('handicap') is None:
                try:
                    odds = md.get('odds', {})
                    # Try handicap_spf.handicap first (football)
                    handicap_spf = odds.get('handicap_spf', {})
                    handicap = handicap_spf.get('handicap')
                    if handicap is None:
                        # Try hdc.line (basketball)
                        hdc = odds.get('hdc', {})
                        handicap = hdc.get('line')
                    if handicap is not None:
                        md['handicap'] = handicap
                        print(f"  [让球提取] {m['id']}: handicap={handicap}")
                except (TypeError, ValueError) as e:
                    print(f"  [警告] {m['id']} 让球提取失败: {e}")
            # 同时更新顶层 status
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb, status = '已完赛' WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            updated += 1
            print(f"  [补全] {m['id']}: {m['home_team']} {found['home_score']}-{found['away_score']} {m['away_team']}")
        else:
            # Debug: 打印匹配失败的详情
            print(f"  [DEBUG] 匹配失败 {m['id']}: DB={m['home_team']} vs {m['away_team']}")
            print(f"  [DEBUG] titan007 候选({ds}):")
            for tm in titan_matches:
                print(f"    {tm['home_team']}/{tm.get('home_team_trad','')}/{tm.get('home_team_official','')} vs {tm['away_team']}/{tm.get('away_team_trad','')}/{tm.get('away_team_official','')}")

            # 标记为无法补全
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "match_not_found"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            print(f"  [标记跳过] {m['id']}: {m['home_team']} vs {m['away_team']} (未匹配)")
            conn.commit()

    # 处理篮球比赛
    for m in basketball_missing:
        date_str = _derive_date_from_id(m["id"]) or ""
        titan_matches = basketball_titan_data.get(date_str, [])
        if not titan_matches:
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "no_titan_data"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            conn.commit()
            continue

        found = find_match_in_titan_data(m["home_team"], m["away_team"], titan_matches)
        if found and found["home_score"] is not None and found["away_score"] is not None:
            md = m["metadata"]
            md["home_score"] = found["home_score"]
            md["away_score"] = found["away_score"]
            md["status"] = "已完赛"
            if found.get("home_half") is not None:
                md["half_home_score"] = found["home_half"]
            if found.get("away_half") is not None:
                md["half_away_score"] = found["away_half"]
            # Auto-extract handicap from odds.hdc.line if missing
            if md.get('handicap') is None:
                try:
                    odds = md.get('odds', {})
                    hdc = odds.get('hdc', {})
                    line = hdc.get('line')
                    if line is not None:
                        md['handicap'] = line
                        print(f"  [让球提取] {m['id']}: handicap={line}")
                except (TypeError, ValueError) as e:
                    print(f"  [警告] {m['id']} 让球提取失败: {e}")
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb, status = '已完赛' WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            updated += 1
            print(f"  [补全] {m['id']}: {m['home_team']} {found['home_score']}-{found['away_score']} {m['away_team']}")
        else:
            print(f"  [DEBUG] 匹配失败 {m['id']}: DB={m['home_team']} vs {m['away_team']}")
            md = m["metadata"]
            md["score_unavailable"] = True
            md["score_unavailable_reason"] = "match_not_found"
            with conn.cursor() as cur:
                cur.execute("UPDATE matches SET metadata = %s::jsonb WHERE id = %s",
                           [json.dumps(md, ensure_ascii=False), m["id"]])
            conn.commit()

    if updated > 0:
        conn.commit()
    print(f"[比分补全] 完成，补全 {updated} 场")
    return updated


def get_unsettled(conn):
    """获取所有已完赛但未结算的比赛及其预测
    同时从 prediction jsonb 和顶层列读取，优先 jsonb
    """
    # 规则：不管体彩是否取消，只要有比分就必须结算
    # COALESCE 从 prediction jsonb 和顶层列取值，优先 jsonb
    sql = """
    SELECT m.id, m.sport_type, m.home_team, m.away_team, m.metadata,
           p.id as pred_id, p.ai_name, p.sport_type as p_sport,
           COALESCE(p.prediction->>'spf', p.spf) as spf,
           COALESCE(p.prediction->>'handicap_spf', p.handicap_spf) as handicap_spf,
           COALESCE(p.prediction->>'goals', p.goals::text) as goals,
           COALESCE(p.prediction->>'score', p.score) as score,
           COALESCE(p.prediction->>'half_full', p.half_full) as half_full,
           COALESCE(p.prediction->>'win_loss', p.win_loss) as win_loss,
           COALESCE(p.prediction->>'handicap_win_loss', p.handicap_win_loss) as handicap_win_loss,
           COALESCE(p.prediction->>'handicap_result') as handicap_result,
           COALESCE(p.prediction->>'total_points', p.total_points) as total_points,
           COALESCE(p.prediction->>'score_diff_range', p.score_diff_range,
                    p.prediction->>'score_diff') as score_diff_range,
           COALESCE(p.prediction->>'half_win_loss', p.half_win_loss) as half_win_loss
    FROM matches m
    JOIN predictions p ON p.match_id = m.id
    WHERE m.status = '已完赛'
      AND (p.is_settled = false OR p.is_settled IS NULL)
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def settle_football(row):
    """
    结算足球预测，返回 (hit_dict, hit_cols_dict)
    hit_dict: 用于写入 hit_status jsonb
    hit_cols_dict: 用于写入 xxx_hit boolean 列
    """
    (match_id, sport_type, home_team, away_team, metadata,
     pred_id, ai_name, p_sport,
     spf, handicap_spf, goals, score, half_full,
     win_loss, handicap_win_loss, handicap_result,
     total_points, score_diff_range, half_win_loss) = row

    md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
    home_score = md.get("home_score")
    away_score = md.get("away_score")
    # 适配新schema: handicap 可能在 metadata->odds->handicap_spf->handicap 或 metadata->odds->hdc->line
    _odds = md.get("odds", {}) or {}
    handicap = md.get("handicap") or _odds.get("handicap_spf", {}).get("handicap") or _odds.get("hdc", {}).get("line")

    if home_score is None or away_score is None:
        return None, None

    home_score = int(home_score)
    away_score = int(away_score)

    hit = {}
    hit_cols = {}

    # 1. spf 胜平负 -> 胜/平/负
    if spf is not None:
        spf_norm = _normalize_spf(spf)
        if home_score > away_score:
            actual = "胜"
        elif home_score == away_score:
            actual = "平"
        else:
            actual = "负"
        is_hit = (spf_norm == actual)
        hit["spf"] = is_hit
        hit_cols["spf_hit"] = is_hit

    # 2. handicap_spf 让球胜平负 -> 让胜/让平/让负
    if handicap_spf is not None and handicap is not None:
        hc_norm = _normalize_handicap_spf(handicap_spf)
        adjusted = home_score + float(handicap)
        if adjusted > away_score:
            actual = "让胜"
        elif adjusted == away_score:
            actual = "让平"
        else:
            actual = "让负"
        is_hit = (hc_norm == actual)
        hit["handicap_spf"] = is_hit
        hit_cols["handicap_spf_hit"] = is_hit

    # 3. goals 进球数 (integer)
    if goals is not None:
        total_goals = home_score + away_score
        is_hit = (int(goals) == total_goals)
        hit["goals"] = is_hit
        hit_cols["goals_hit"] = is_hit

    # 4. score 比分 -> "1-0" 格式
    if score is not None:
        actual_score = f"{home_score}-{away_score}"
        is_hit = (score == actual_score)
        hit["score"] = is_hit
        hit_cols["score_hit"] = is_hit

    # 5. half_full 半全场 -> "胜胜" 格式
    if half_full is not None:
        half_home = md.get("half_home_score")
        half_away = md.get("half_away_score")
        if half_home is not None and half_away is not None:
            half_home = int(half_home)
            half_away = int(half_away)
            half_r = "胜" if half_home > half_away else ("平" if half_home == half_away else "负")
            full_r = "胜" if home_score > away_score else ("平" if home_score == away_score else "负")
            actual_hf = f"{half_r}{full_r}"
            is_hit = (half_full == actual_hf)
            hit["half_full"] = is_hit
            hit_cols["half_full_hit"] = is_hit

    return (hit if hit else None), hit_cols


def parse_score_diff_range(sdr):
    """
    解析胜分差预测值，如 '主6-10胜' -> ('主', 6, 10, '胜')
    或 '客1-5胜' -> ('客', 1, 5, '胜')
    """
    m = re.match(r'([主客])(\d+)-(\d+)(胜|负)', sdr)
    if m:
        return m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    return None


def settle_basketball(row):
    """
    结算篮球预测，返回 (hit_dict, hit_cols_dict)
    兼容多种 win_loss 格式："胜"/"负"、"主胜"/"客胜"/"主负"/"客负"
    兼容 handicap_result（旧key）和 handicap_win_loss
    """
    (match_id, sport_type, home_team, away_team, metadata,
     pred_id, ai_name, p_sport,
     spf, handicap_spf, goals, score, half_full,
     win_loss, handicap_win_loss, handicap_result,
     total_points, score_diff_range, half_win_loss) = row

    md = metadata if isinstance(metadata, dict) else (json.loads(metadata) if metadata else {})
    home_score = md.get("home_score")
    away_score = md.get("away_score")
    # 适配新schema: handicap 可能在 metadata->odds->handicap_spf->handicap 或 metadata->odds->hdc->line
    _odds = md.get("odds", {}) or {}
    handicap = md.get("handicap") or _odds.get("handicap_spf", {}).get("handicap") or _odds.get("hdc", {}).get("line")

    if home_score is None or away_score is None:
        return None, None

    home_score = int(home_score)
    away_score = int(away_score)
    diff = abs(home_score - away_score)

    hit = {}
    hit_cols = {}

    # 1. win_loss 胜负 - 归一化多种格式
    if win_loss is not None:
        wl = str(win_loss).strip()
        if wl in ("主胜", "客负"):
            # 主队赢 = away_team(第二队)赢
            predicted_home_wins = False
        elif wl in ("客胜", "主负"):
            # 客队赢 = home_team(第一队)赢
            predicted_home_wins = True
        elif wl == "胜":
            predicted_home_wins = True  # home_team 胜
        elif wl == "负":
            predicted_home_wins = False  # home_team 负
        else:
            predicted_home_wins = None

        if predicted_home_wins is not None:
            actual_home_wins = home_score > away_score
            is_hit = (predicted_home_wins == actual_home_wins)
            hit["win_loss"] = is_hit
            hit_cols["spf_hit"] = is_hit

    # 2. handicap_win_loss / handicap_result 让分胜负
    # 优先用 handicap_win_loss，fallback 到 handicap_result
    hc_val = handicap_win_loss or handicap_result
    if hc_val is not None and handicap is not None:
        try:
            hc = str(hc_val).strip()
            hc_float = float(handicap)
            adjusted = home_score - away_score - hc_float
            if adjusted < 0:
                actual = "让分主胜"  # 主队(第二队)赢盘
            else:
                actual = "让分主负"  # 客队(第一队)赢盘

            # 归一化预测值
            hc_norm = hc
            if hc == "让胜":
                hc_norm = "让分主胜"
            elif hc == "让负":
                hc_norm = "让分主负"

            is_hit = (hc_norm == actual)
            hit["handicap_win_loss"] = is_hit
            hit_cols["handicap_spf_hit"] = is_hit
        except (ValueError, TypeError) as e:
            print(f"  [警告] {match_id} handicap_spf计算失败: {e}")

    # 3. total_points 大小分 -> 大/小
    if total_points is not None:
        total = home_score + away_score
        tp_str = str(total_points).strip()
        if tp_str in ("大", "小", "大分", "小分"):
            tp_short = tp_str[0]  # 大/小
            line = md.get("total_points_line")
            # 适配新schema: total_line 可能在 metadata->odds->hilo->line
            if line is None:
                _odds2 = md.get("odds", {}) or {}
                line = _odds2.get("hilo", {}).get("line")
            if line is not None:
                line = float(line)
                actual = "大" if total > line else "小"
                is_hit = (tp_short == actual)
                hit["total_points"] = is_hit
                hit_cols["goals_hit"] = is_hit
            else:
                # 没有分界线，尝试从metadata的odds中找
                odds = md.get("odds", {}) or {}
                line = odds.get("total_points_line") or odds.get("total_line") or odds.get("hilo", {}).get("line")
                if line is not None:
                    line = float(line)
                    actual = "大" if total > line else "小"
                    is_hit = (tp_short == actual)
                    hit["total_points"] = is_hit
                    hit_cols["goals_hit"] = is_hit
        else:
            # 带数字的格式如 "210.5大"
            nums = re.findall(r'[\d.]+', tp_str)
            if nums:
                line = float(nums[0])
                predicted_big = "大" in tp_str
                actual_big = total > line
                is_hit = (predicted_big == actual_big)
                hit["total_points"] = is_hit
                hit_cols["goals_hit"] = is_hit

    # 4. score_diff_range 胜分差 -> "主6-10胜" 格式
    if score_diff_range is not None:
        parsed = parse_score_diff_range(score_diff_range)
        if parsed:
            side, low, high, winner = parsed
            actual_winner = "主" if home_score > away_score else "客"
            if side == actual_winner and low <= diff <= high:
                is_hit = True
            else:
                is_hit = False
            hit["score_diff_range"] = is_hit
            hit_cols["score_hit"] = is_hit
        else:
            # 尝试简单格式如 "1-5"
            nums = re.findall(r'\d+', score_diff_range)
            if len(nums) >= 2:
                low, high = int(nums[0]), int(nums[1])
                is_hit = (low <= diff <= high)
                hit["score_diff_range"] = is_hit
                hit_cols["score_hit"] = is_hit

    # 5. half_win_loss 半场胜负 -> 胜/负
    if half_win_loss is not None:
        half_home = md.get("half_home_score")
        half_away = md.get("half_away_score")
        if half_home is not None and half_away is not None:
            half_home = int(half_home)
            half_away = int(half_away)
            actual = "胜" if half_home > half_away else "负"
            is_hit = (half_win_loss == actual)
            hit["half_win_loss"] = is_hit
            hit_cols["half_full_hit"] = is_hit

    return (hit if hit else None), hit_cols


def main():
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    db_url = sys.argv[2] if len(sys.argv) > 2 else None

    conn = get_db(db_url)
    
    # 先从 titan007 补全缺失比分
    try:
        filled = fill_missing_scores(conn)
        if filled > 0:
            print(f"已补全 {filled} 场比赛比分\n")
    except Exception as e:
        print(f"[WARN] 比分补全失败（不影响结算）: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    
    rows = get_unsettled(conn)

    if not rows:
        print("无待结算记录")
        conn.close()
        return

    settled_count = 0
    stats = {"football": {}, "basketball": {}}
    details = []

    for row in rows:
        match_id = row[0]
        sport_type = row[1]
        home_team = row[2]
        away_team = row[3]
        pred_id = row[5]
        ai_name = row[6]
        p_sport = row[7]

        # 判断运动类型
        st = (p_sport or sport_type or "").lower()
        if st == "basketball":
            hit_dict, hit_cols = settle_basketball(row)
            stat_key = "basketball"
        else:
            hit_dict, hit_cols = settle_football(row)
            stat_key = "football"

        if hit_dict is None:
            continue

        # 更新数据库
        hit_json = json.dumps(hit_dict, ensure_ascii=False)
        set_clauses = ["hit_status = %s::jsonb", "is_settled = true"]
        params = [hit_json]

        # 更新 xxx_hit boolean 列
        for col, val in hit_cols.items():
            set_clauses.append(f"{col} = %s")
            params.append(val)

        params.append(pred_id)
        sql = f"UPDATE predictions SET {', '.join(set_clauses)} WHERE id = %s"

        with conn.cursor() as cur:
            cur.execute(sql, params)

        settled_count += 1

        # 统计
        hits = sum(1 for v in hit_dict.values() if v is True)
        total_dims = len(hit_dict)
        if ai_name not in stats[stat_key]:
            stats[stat_key][ai_name] = {"total": 0, "hits": 0}
        stats[stat_key][ai_name]["total"] += 1
        stats[stat_key][ai_name]["hits"] += hits

        # 详情日志
        hit_str = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in hit_dict.items())
        details.append(f"  [{stat_key}] {ai_name}: {match_id} {home_team} vs {away_team} -> {hit_str} ({hits}/{total_dims})")

    conn.commit()
    conn.close()

    # 输出结果
    print(f"自动结算完成：共结算 {settled_count} 条预测")
    for d in details:
        print(d)

    for st in ["football", "basketball"]:
        if stats[st]:
            print(f"\n{st.upper()} 汇总:")
            for ai, s in stats[st].items():
                print(f"  {ai}: {s['total']}条, 命中{s['hits']}个维度")

    # 检查剩余未结算数
    conn2 = get_db(db_url)
    with conn2.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM predictions WHERE is_settled = false OR is_settled IS NULL")
        remaining = cur.fetchone()[0]
    conn2.close()
    print(f"\n剩余未结算预测: {remaining}条")


if __name__ == "__main__":
    main()
