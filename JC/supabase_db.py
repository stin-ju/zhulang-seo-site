#!/usr/bin/env python3
"""
supabase_db.py - Supabase 数据库接口
适配5字段表结构: id, sport_type, home_team, away_team, metadata(jsonb)
metadata 内包含: match_time, match_date, status, handicap, odds, home_score, away_score,
                 selling_status, league, source, original_id 等所有业务字段。
"""
import os
import json
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def get_client() -> Client:
    """获取 Supabase 客户端"""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _get_metadata(match: dict) -> dict:
    """安全获取 match 的 metadata 字段，兼容字符串和 dict"""
    md = match.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except (json.JSONDecodeError, TypeError):
            md = {}
    return md


# ============ Matches 表操作 ============

def get_all_matches():
    """获取所有比赛"""
    client = get_client()
    result = client.table("matches").select("*").execute()
    return result.data


def get_matches_by_status(statuses):
    """按状态获取比赛（status 在 metadata 中，Python 端过滤）"""
    client = get_client()
    result = client.table("matches").select("*").execute()
    status_set = set(statuses)
    filtered = [
        m for m in result.data
        if _get_metadata(m).get("status") in status_set
    ]
    # 按 metadata.match_time 排序
    filtered.sort(key=lambda m: _get_metadata(m).get("match_time", ""))
    return filtered


def get_matches_by_sport(sport, statuses=None):
    """按运动类型获取比赛（sport_type 仍是独立列，status 在 metadata 中过滤）"""
    client = get_client()
    query = client.table("matches").select("*").eq("sport_type", sport)
    result = query.execute()
    data = result.data

    if statuses:
        status_set = set(statuses)
        data = [
            m for m in data
            if _get_metadata(m).get("status") in status_set
        ]

    # 按 metadata.match_time 排序
    data.sort(key=lambda m: _get_metadata(m).get("match_time", ""))
    return data


def get_match_by_id(match_id):
    """按ID获取比赛"""
    client = get_client()
    result = client.table("matches").select("*").eq("id", match_id).execute()
    return result.data[0] if result.data else None


def get_existing_match_ids():
    """获取所有已存在的比赛ID"""
    client = get_client()
    result = client.table("matches").select("id").execute()
    return {row["id"] for row in result.data}


def insert_match(match_data):
    """插入新比赛。
    match_data 应包含: id, sport_type, home_team, away_team, metadata
    metadata 内包含: match_time, match_date, status, handicap, odds, league, source, original_id 等
    """
    client = get_client()
    result = client.table("matches").insert(dict(match_data)).execute()
    return result.data


def update_match(match_id, update_data):
    """更新比赛。
    update_data 中如果包含 metadata 相关字段（status, handicap, odds 等），
    会自动合并到现有 metadata 中；顶层字段（sport_type, home_team, away_team）直接更新。
    """
    client = get_client()

    # 分离顶层字段和 metadata 字段
    top_level_fields = {"sport_type", "home_team", "away_team", "status"}
    top_level_updates = {}
    metadata_updates = {}

    for key, value in update_data.items():
        if key in top_level_fields:
            top_level_updates[key] = value
        else:
            metadata_updates[key] = value

    # 如果有 metadata 字段需要更新，先读取现有 metadata 再合并
    if metadata_updates:
        current = get_match_by_id(match_id)
        if current:
            current_md = _get_metadata(current)
            current_md.update(metadata_updates)
            top_level_updates["metadata"] = current_md

    if top_level_updates:
        result = client.table("matches").update(top_level_updates).eq("id", match_id).execute()
        return result.data
    return []


def upsert_match(match_data, on_conflict="id"):
    """插入或更新比赛"""
    client = get_client()
    result = client.table("matches").upsert(match_data, on_conflict=on_conflict).execute()
    return result.data


# ============ Predictions 表操作 ============

def get_predictions_by_match(match_id):
    """获取某场比赛的所有预测"""
    client = get_client()
    result = client.table("predictions").select("*").eq("match_id", match_id).execute()
    return result.data


def get_existing_ai_names(match_id):
    """获取某场比赛已有的AI名称集合"""
    client = get_client()
    result = client.table("predictions").select("ai_name").eq("match_id", match_id).execute()
    raw_names = {row["ai_name"] for row in result.data}
    normalized = set()
    for name in raw_names:
        if name.startswith("AI-"):
            normalized.add(name)
        else:
            normalized.add(f"AI-{name}")
    return normalized


def insert_prediction(pred_data):
    """插入预测"""
    client = get_client()
    result = client.table("predictions").insert(pred_data).execute()
    return result.data


def upsert_prediction(pred_data, on_conflict="match_id,ai_name"):
    """插入或更新预测（先尝试更新，失败则插入）"""
    client = get_client()
    # 先尝试更新
    match_id = pred_data.get("match_id")
    ai_name = pred_data.get("ai_name")
    update_result = client.table("predictions").update(pred_data).eq("match_id", match_id).eq("ai_name", ai_name).execute()
    if update_result.data:
        return update_result.data
    # 更新无结果，尝试插入
    try:
        result = client.table("predictions").insert(pred_data).execute()
        return result.data
    except Exception as e:
        # 插入失败（可能是并发冲突），再尝试更新
        result = client.table("predictions").update(pred_data).eq("match_id", match_id).eq("ai_name", ai_name).execute()
        return result.data


def get_all_predictions():
    """获取所有预测"""
    client = get_client()
    result = client.table("predictions").select("*").execute()
    return result.data


def get_predictions_count():
    """获取预测总数"""
    client = get_client()
    result = client.table("predictions").select("id", count="exact").execute()
    return result.count


# ============ 统计查询 ============

def get_all_match_ids():
    """获取所有比赛ID集合"""
    client = get_client()
    result = client.table("matches").select("id").execute()
    return {row["id"] for row in result.data}


def get_matches_without_predictions(sport="football"):
    """获取缺少预测的比赛（status 在 metadata 中，Python 端过滤）"""
    client = get_client()
    # 获取指定运动类型的所有比赛
    matches_result = client.table("matches").select("id, metadata").eq("sport_type", sport).execute()

    allowed_statuses = {"on_sale", "pending", "待比赛", "未开赛"}
    match_ids = set()
    for m in matches_result.data:
        md = _get_metadata(m)
        if md.get("status") in allowed_statuses:
            match_ids.add(m["id"])

    # 获取有预测的比赛ID
    preds_result = client.table("predictions").select("match_id").execute()
    pred_match_ids = {p["match_id"] for p in preds_result.data}

    # 返回缺少预测的比赛ID
    return match_ids - pred_match_ids


def get_settle_candidates(deadline_str):
    """获取待结算比赛（metadata.match_time <= deadline，未取消，未结算）
    全部拉取后在 Python 端过滤。
    """
    client = get_client()
    result = client.table("matches").select("*").execute()
    candidates = []
    for m in (result.data or []):
        md = _get_metadata(m)
        status = md.get("status", "")
        match_time = md.get("match_time", "")
        # 排除已取消和已结算
        if status == "已取消" or status == "已完赛":
            continue
        # match_time <= deadline_str
        if match_time and match_time <= deadline_str:
            candidates.append(m)

    # 按 match_time 排序
    candidates.sort(key=lambda m: _get_metadata(m).get("match_time", ""))
    return candidates


def settle_match(match_id, home_score, away_score):
    """结算比赛：更新比分、状态到 metadata 中"""
    client = get_client()
    # 先读取当前 metadata
    current = get_match_by_id(match_id)
    if not current:
        return []
    current_md = _get_metadata(current)
    # 合并结算字段
    current_md["home_score"] = home_score
    current_md["away_score"] = away_score
    current_md["selling_status"] = "settled"
    current_md["status"] = "已完赛"

    result = client.table("matches").update({
        "metadata": current_md,
    }).eq("id", match_id).execute()
    return result.data


if __name__ == "__main__":
    print(f"Supabase URL: {SUPABASE_URL}")
    print(f"Matches: {len(get_all_matches())}")
    print(f"Predictions: {get_predictions_count()}")
