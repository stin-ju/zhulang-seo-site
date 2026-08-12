#!/usr/bin/env python3
"""
supabase_db.py - 数据库接口（HTTP代理版本）
适配5字段表结构: id, sport_type, home_team, away_team, metadata(jsonb)
metadata 内包含: match_time, match_date, status, handicap, odds, home_score, away_score,
                 selling_status, league, source, original_id 等所有业务字段。

使用 HTTP 代理访问数据库，通过 POST http://127.0.0.1:5000/api/internal/query 执行 SQL。
"""
import os
import json
import urllib.request
import urllib.error

SERVER_PORT = os.environ.get('DEPLOY_RUN_PORT', '5000')
SERVER_URL = f'http://127.0.0.1:{SERVER_PORT}/api/internal/query'


def _convert_value(v):
    """将HTTP代理返回的字符串值转换为正确的Python类型"""
    if v is None:
        return None
    if isinstance(v, str):
        # None/null
        if v in ('None', 'null', 'NULL'):
            return None
        # bool
        if v.lower() == 'true':
            return True
        if v.lower() == 'false':
            return False
        # int (纯数字，可能带负号)
        if v and (v.isdigit() or (v[0] in '+-' and v[1:].isdigit())):
            return int(v)
        # float
        try:
            if '.' in v:
                return float(v)
        except (ValueError, TypeError):
            pass
    return v


def _execute_query(sql, params=None):
    """执行 SQL 查询并返回结果"""
    payload = json.dumps({'sql': sql, 'params': params or []}).encode('utf-8')
    req = urllib.request.Request(
        SERVER_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            rows = result.get('rows', [])
            # 转换类型
            converted_rows = []
            for row in rows:
                if isinstance(row, dict):
                    converted_rows.append({k: _convert_value(v) for k, v in row.items()})
                else:
                    converted_rows.append(row)
            return converted_rows
    except urllib.error.HTTPError as e:
        raise Exception(f'DB proxy error ({e.code}): {e.read().decode()}')
    except urllib.error.URLError as e:
        raise Exception(f'DB proxy connection error: {e.reason}')


def _get_metadata(match: dict) -> dict:
    """安全获取 match 的 metadata 字段，兼容字符串和 dict"""
    md = match.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except (json.JSONDecodeError, TypeError):
            md = {}
    return md


# ============ 兼容层 ============

def get_client():
    """获取数据库客户端（HTTP代理版本返回 None）"""
    return None


# ============ Matches 表操作 ============

def get_all_matches():
    """获取所有比赛"""
    rows = _execute_query("SELECT id, sport_type, home_team, away_team, metadata FROM matches")
    return rows


def get_matches_by_status(statuses):
    """按状态获取比赛（status 在 metadata 中，Python 端过滤）"""
    rows = _execute_query("SELECT id, sport_type, home_team, away_team, metadata FROM matches")
    status_set = set(statuses)
    filtered = [
        m for m in rows
        if _get_metadata(m).get("status") in status_set
    ]
    # 按 metadata.match_time 排序
    filtered.sort(key=lambda m: _get_metadata(m).get("match_time", ""))
    return filtered


def get_matches_by_sport(sport, statuses=None):
    """按运动类型获取比赛（sport_type 仍是独立列，status 在 metadata 中过滤）"""
    rows = _execute_query(
        "SELECT id, sport_type, home_team, away_team, metadata FROM matches WHERE sport_type = %s",
        [sport]
    )
    data = rows

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
    rows = _execute_query(
        "SELECT id, sport_type, home_team, away_team, metadata FROM matches WHERE id = %s",
        [match_id]
    )
    return rows[0] if rows else None


def get_existing_match_ids():
    """获取所有已存在的比赛ID"""
    rows = _execute_query("SELECT id FROM matches")
    return {row["id"] for row in rows}


def insert_match(match_data):
    """插入新比赛。
    match_data 应包含: id, sport_type, home_team, away_team, metadata
    metadata 内包含: match_time, match_date, status, handicap, odds, league, source, original_id 等
    """
    # 将 metadata 转为 JSON 字符串
    metadata = match_data.get("metadata")
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata, ensure_ascii=False)
    
    _execute_query(
        """INSERT INTO matches (id, sport_type, home_team, away_team, metadata) 
           VALUES (%s, %s, %s, %s, %s::jsonb)""",
        [match_data["id"], match_data["sport_type"], match_data["home_team"], 
         match_data["away_team"], metadata]
    )
    return [match_data]


def update_match(match_id, update_data):
    """更新比赛。
    update_data 中如果包含 metadata 相关字段（status, handicap, odds 等），
    会自动合并到现有 metadata 中；顶层字段（sport_type, home_team, away_team）直接更新。
    """
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
        # 构建 UPDATE 语句
        set_clauses = []
        params = []
        for key, value in top_level_updates.items():
            if key == "metadata":
                if isinstance(value, dict):
                    value = json.dumps(value, ensure_ascii=False)
                set_clauses.append(f"{key} = %s::jsonb")
            else:
                set_clauses.append(f"{key} = %s")
            params.append(value)
        
        params.append(match_id)
        sql = f"UPDATE matches SET {', '.join(set_clauses)} WHERE id = %s"
        _execute_query(sql, params)
        return [update_data]
    return []


def upsert_match(match_data, on_conflict="id"):
    """插入或更新比赛"""
    # 先尝试更新
    metadata = match_data.get("metadata")
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata, ensure_ascii=False)
    
    # 检查是否存在
    existing = get_match_by_id(match_data["id"])
    if existing:
        # 更新
        set_clauses = []
        params = []
        for key, value in match_data.items():
            if key == "id":
                continue
            if key == "metadata":
                if isinstance(value, dict):
                    value = json.dumps(value, ensure_ascii=False)
                set_clauses.append(f"{key} = %s::jsonb")
            else:
                set_clauses.append(f"{key} = %s")
            params.append(value)
        params.append(match_data["id"])
        sql = f"UPDATE matches SET {', '.join(set_clauses)} WHERE id = %s"
        _execute_query(sql, params)
    else:
        # 插入
        _execute_query(
            """INSERT INTO matches (id, sport_type, home_team, away_team, metadata) 
               VALUES (%s, %s, %s, %s, %s::jsonb)""",
            [match_data["id"], match_data["sport_type"], match_data["home_team"],
             match_data["away_team"], metadata]
        )
    return [match_data]


# ============ Predictions 表操作 ============

def get_predictions_by_match(match_id):
    """获取某场比赛的所有预测"""
    rows = _execute_query(
        "SELECT * FROM predictions WHERE match_id = %s",
        [match_id]
    )
    return rows


def get_existing_ai_names(match_id):
    """获取某场比赛已有的AI预测名称集合（返回AI_CONFIGS格式，即带AI-前缀）"""
    rows = _execute_query(
        "SELECT ai_name FROM predictions WHERE match_id = %s",
        [match_id]
    )
    raw_names = {row["ai_name"] for row in rows}
    
    # 数据库存的是无前缀名称（如"扣子（皮皮）"），转为AI_CONFIGS格式（如"AI-扣子（皮皮）"）
    result_set = set()
    for name in raw_names:
        if not name.startswith("AI-"):
            result_set.add("AI-" + name)
        else:
            result_set.add(name)
    return result_set


def insert_prediction(pred_data):
    """插入预测"""
    # 处理 JSON 字段
    prediction = pred_data.get("prediction")
    if isinstance(prediction, dict):
        prediction = json.dumps(prediction, ensure_ascii=False)
    
    hit_status = pred_data.get("hit_status")
    if isinstance(hit_status, dict):
        hit_status = json.dumps(hit_status, ensure_ascii=False)
    
    _execute_query(
        """INSERT INTO predictions (match_id, ai_name, sport_type, prediction, hit_status, is_settled) 
           VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)""",
        [pred_data["match_id"], pred_data["ai_name"], pred_data.get("sport_type"),
         prediction, hit_status, pred_data.get("is_settled", False)]
    )
    return [pred_data]


def upsert_prediction(pred_data, on_conflict="match_id,ai_name"):
    """插入或更新预测（先尝试更新，失败则插入）"""
    match_id = pred_data.get("match_id")
    ai_name = pred_data.get("ai_name")
    
    # 检查是否存在
    existing = _execute_query(
        "SELECT id FROM predictions WHERE match_id = %s AND ai_name = %s",
        [match_id, ai_name]
    )
    
    # 处理 JSON 字段
    prediction = pred_data.get("prediction")
    if isinstance(prediction, dict):
        prediction = json.dumps(prediction, ensure_ascii=False)
    
    hit_status = pred_data.get("hit_status")
    if isinstance(hit_status, dict):
        hit_status = json.dumps(hit_status, ensure_ascii=False)
    
    if existing:
        # 更新
        _execute_query(
            """UPDATE predictions SET prediction = %s::jsonb, hit_status = %s::jsonb, is_settled = %s
               WHERE match_id = %s AND ai_name = %s""",
            [prediction, hit_status, pred_data.get("is_settled", False), match_id, ai_name]
        )
    else:
        # 插入
        _execute_query(
            """INSERT INTO predictions (match_id, ai_name, sport_type, prediction, hit_status, is_settled) 
               VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)""",
            [match_id, ai_name, pred_data.get("sport_type"), prediction, hit_status, 
             pred_data.get("is_settled", False)]
        )
    return [pred_data]


def get_all_predictions():
    """获取所有预测"""
    rows = _execute_query("SELECT * FROM predictions")
    return rows


def get_predictions_count():
    """获取预测总数"""
    rows = _execute_query("SELECT COUNT(*) as count FROM predictions")
    if rows:
        return rows[0].get("count", 0)
    return 0
