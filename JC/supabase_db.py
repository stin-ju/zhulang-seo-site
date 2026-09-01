"""
数据库接口 - 使用 psycopg2 直连 PostgreSQL
"""
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

# 数据库连接配置
DATABASE_URL = os.environ.get('DATABASE_URL', 
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(DATABASE_URL)


def execute_query(sql, params=None, fetch=True):
    """执行 SQL 查询并返回结果（字典列表格式）"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetch:
                rows = cur.fetchall()
                # 将 RealDictRow 转为普通 dict
                return [dict(row) for row in rows]
            else:
                conn.commit()
                return []
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def _get_metadata(match):
    """从比赛记录中获取 metadata（兼容 dict 和 str）"""
    md = match.get("metadata")
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except:
            md = {}
    if not isinstance(md, dict):
        md = {}
    return md


# ============ 兼容层 ============

def get_client():
    """获取数据库客户端（返回连接对象）"""
    return get_connection()


# ============ Matches 表操作 ============

def get_all_matches():
    """获取所有比赛"""
    rows = execute_query("SELECT id, sport_type, home_team, away_team, metadata FROM matches")
    return rows


def get_matches_by_status(statuses):
    """按状态获取比赛（status 在 metadata 中，Python 端过滤）"""
    rows = execute_query("SELECT id, sport_type, home_team, away_team, metadata FROM matches")
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
    rows = execute_query(
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
    rows = execute_query(
        "SELECT id, sport_type, home_team, away_team, metadata FROM matches WHERE id = %s",
        [match_id]
    )
    return rows[0] if rows else None


def get_existing_match_ids():
    """获取所有已存在的比赛ID"""
    rows = execute_query("SELECT id FROM matches")
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
    
    execute_query(
        """INSERT INTO matches (id, sport_type, home_team, away_team, metadata) 
           VALUES (%s, %s, %s, %s, %s::jsonb)""",
        [match_data["id"], match_data["sport_type"], match_data["home_team"], 
         match_data["away_team"], metadata],
        fetch=False
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
        execute_query(sql, params, fetch=False)
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
        execute_query(sql, params, fetch=False)
    else:
        # 插入
        execute_query(
            """INSERT INTO matches (id, sport_type, home_team, away_team, metadata) 
               VALUES (%s, %s, %s, %s, %s::jsonb)""",
            [match_data["id"], match_data["sport_type"], match_data["home_team"],
             match_data["away_team"], metadata],
            fetch=False
        )
    return [match_data]


# ============ Predictions 表操作 ============

def get_predictions_by_match(match_id):
    """获取某场比赛的所有预测"""
    rows = execute_query(
        "SELECT * FROM predictions WHERE match_id = %s",
        [match_id]
    )
    return rows


def get_existing_ai_names(match_id):
    """获取某场比赛已有的AI预测名称集合（返回AI_CONFIGS格式，即带AI-前缀）"""
    rows = execute_query(
        "SELECT ai_name FROM predictions WHERE match_id = %s",
        [match_id]
    )
    raw_names = {row["ai_name"] for row in rows}
    
    # 数据库存的是无前缀名称（如"扣子"），转为AI_CONFIGS格式（如"AI-扣子"）
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
    
    execute_query(
        """INSERT INTO predictions (match_id, ai_name, sport_type, prediction, hit_status, is_settled) 
           VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)""",
        [pred_data["match_id"], pred_data["ai_name"], pred_data.get("sport_type"),
         prediction, hit_status, pred_data.get("is_settled", False)],
        fetch=False
    )
    return [pred_data]


def upsert_prediction(pred_data, on_conflict="match_id,ai_name"):
    """插入或更新预测（使用原子性 UPSERT）"""
    match_id = pred_data.get("match_id")
    ai_name = pred_data.get("ai_name")
    
    # 从 match_id 提取 match_date（格式：20260901_周一004 → 2026-09-01）
    match_date = pred_data.get("match_date")
    if not match_date and match_id and len(match_id) >= 8:
        date_str = match_id[:8]  # "20260901"
        try:
            match_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except:
            match_date = None
    
    # 处理 JSON 字段
    prediction = pred_data.get("prediction")
    if isinstance(prediction, dict):
        prediction = json.dumps(prediction, ensure_ascii=False)
    
    hit_status = pred_data.get("hit_status")
    if isinstance(hit_status, dict):
        hit_status = json.dumps(hit_status, ensure_ascii=False)
    
    # 使用 INSERT ... ON CONFLICT 实现原子性 UPSERT
    execute_query(
        """INSERT INTO predictions (match_id, ai_name, sport_type, prediction, hit_status, is_settled, match_date) 
           VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
           ON CONFLICT (match_id, ai_name) 
           DO UPDATE SET prediction = EXCLUDED.prediction, 
                         hit_status = EXCLUDED.hit_status, 
                         is_settled = EXCLUDED.is_settled,
                         match_date = EXCLUDED.match_date""",
        [match_id, ai_name, pred_data.get("sport_type"), prediction, hit_status, 
         pred_data.get("is_settled", False), match_date],
        fetch=False
    )
    return [pred_data]


def get_all_predictions():
    """获取所有预测"""
    rows = execute_query("SELECT * FROM predictions")
    return rows


def get_predictions_count():
    """获取预测总数"""
    rows = execute_query("SELECT COUNT(*) as count FROM predictions")
    if rows:
        return rows[0].get("count", 0)
    return 0
