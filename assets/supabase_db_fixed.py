#!/usr/bin/env python3
"""
supabase_db.py - Supabase 数据库接口
提供与 Supabase 的交互能力，替代直接 PostgreSQL 连接。
"""
import os
import json
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def get_client() -> Client:
    """获取 Supabase 客户端"""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# ============ Matches 表操作 ============

def get_all_matches():
    """获取所有比赛"""
    client = get_client()
    result = client.table("matches").select("*").execute()
    return result.data


def get_matches_by_status(statuses):
    """按状态获取比赛"""
    client = get_client()
    status_filter = ",".join([f'"{s}"' for s in statuses])
    result = client.table("matches").select("*").in_("status", statuses).order("match_time").execute()
    return result.data


def get_matches_by_sport(sport, statuses=None):
    """按运动类型获取比赛"""
    client = get_client()
    query = client.table("matches").select("*").eq("sport_type", sport)
    if statuses:
        query = query.in_("status", statuses)
    result = query.order("match_time").execute()
    return result.data


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
    """插入新比赛"""
    client = get_client()
    result = client.table("matches").insert(match_data).execute()
    return result.data


def update_match(match_id, update_data):
    """更新比赛"""
    client = get_client()
    result = client.table("matches").update(update_data).eq("id", match_id).execute()
    return result.data


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
    """插入或更新预测"""
    client = get_client()
    result = client.table("predictions").upsert(pred_data, on_conflict=on_conflict).execute()
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
    """获取缺少预测的比赛"""
    client = get_client()
    # 获取所有比赛
    matches_result = client.table("matches").select("id").eq("sport_type", sport).in_("status", ["on_sale", "pending", "待比赛", "未开赛"]).execute()
    match_ids = {m["id"] for m in matches_result.data}
    
    # 获取有预测的比赛ID
    preds_result = client.table("predictions").select("match_id").execute()
    pred_match_ids = {p["match_id"] for p in preds_result.data}
    
    # 返回缺少预测的比赛ID
    return match_ids - pred_match_ids


def insert_match(data):
    """插入新比赛"""
    client = get_client()
    row = dict(data)
    if isinstance(row.get("odds"), dict):
        row["odds"] = json.dumps(row["odds"])
    if isinstance(row.get("metadata"), dict):
        row["metadata"] = json.dumps(row["metadata"])
    result = client.table("matches").insert(row).execute()
    return result.data


def update_match(match_id, data):
    """更新比赛"""
    client = get_client()
    if isinstance(data.get("odds"), dict):
        data["odds"] = json.dumps(data["odds"])
    if isinstance(data.get("metadata"), dict):
        data["metadata"] = json.dumps(data["metadata"])
    result = client.table("matches").update(data).eq("id", match_id).execute()
    return result.data


def get_settle_candidates(deadline_str):
    """获取待结算比赛（match_time <= deadline，未取消，未结算）"""
    client = get_client()
    result = client.table("matches").select(
        "id,match_time,status,handicap,sport_type,metadata"
    ).neq("status", "已取消").lte("match_time", deadline_str).order("match_time").execute()
    return result.data or []


def settle_match(match_id, home_score, away_score):
    """结算比赛：更新比分和状态"""
    client = get_client()
    result = client.table("matches").update({
        "home_score": home_score,
        "away_score": away_score,
        "selling_status": "settled",
    }).eq("id", match_id).execute()
    return result.data


if __name__ == "__main__":
    print(f"Supabase URL: {SUPABASE_URL}")
    print(f"Matches: {len(get_all_matches())}")
    print(f"Predictions: {get_predictions_count()}")
