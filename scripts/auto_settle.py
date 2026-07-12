#!/usr/bin/env python3
"""
auto_settle.py - 自动结算模块
扫描所有开赛时间超过3小时且未结算的比赛，查询体彩官方结果，结算注单。
结算规则：
  1. 当前时间 >= match_time + 3小时 → 可结算
  2. 已取消的比赛跳过
  3. 有分数的直接结算，没分数的尝试从sporttery获取
  4. 更新 matches.selling_status = 'settled'
  5. 更新 user_bets 的 result 和 profit
"""
import os
import sys
import json
import time
import traceback
from datetime import datetime, timedelta, timezone

import psycopg2
import requests

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# 北京时区
CST = timezone(timedelta(hours=8))

# ============ 数据库 ============

def get_db():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)


def query(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or ())
    if cur.description:
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]
    return []


# ============ Sporttery API ============

def fetch_sporttery_results(match_date_str):
    """
    从体彩API获取指定日期的比赛结果
    match_date_str: YYYY-MM-DD 格式
    返回: dict {matchNumStr: {home_score, away_score, status, ...}}
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.sporttery.cn/",
        "Origin": "https://www.sporttery.cn",
        "Accept": "application/json, text/plain, */*"
    }
    
    results = {}
    
    # 尝试足球结果API
    try:
        url = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"
        params = {"poolCode": "HAD,HHAD", "channel": "c"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()
        if data.get("success"):
            for day in data.get("value", {}).get("matchInfoList", []):
                for m in day.get("subMatchList", []):
                    num = m.get("matchNumStr", "")
                    status = m.get("matchStatus", "")
                    full_score = m.get("fullScore")
                    if full_score:
                        scores = str(full_score).split(":")
                        if len(scores) == 2:
                            results[num] = {
                                "home_score": int(scores[0]),
                                "away_score": int(scores[1]),
                                "status": status
                            }
    except Exception as e:
        print(f"[Sporttery] Football API error: {e}", file=sys.stderr)

    # 尝试篮球结果API
    try:
        url = "https://webapi.sporttery.cn/gateway/jc/basketball/getMatchCalculatorV1.qry"
        params = {"poolCode": "HDC,MNL", "channel": "c"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()
        if data.get("success"):
            for day in data.get("value", {}).get("matchInfoList", []):
                for m in day.get("subMatchList", []):
                    num = m.get("matchNumStr", "")
                    status = m.get("matchStatus", "")
                    full_score = m.get("fullScore")
                    if full_score:
                        scores = str(full_score).split(":")
                        if len(scores) == 2:
                            results[num] = {
                                "home_score": int(scores[0]),
                                "away_score": int(scores[1]),
                                "status": status
                            }
    except Exception as e:
        print(f"[Sporttery] Basketball API error: {e}", file=sys.stderr)

    return results


# ============ 结算逻辑 ============

def determine_spf_result(home_score, away_score):
    """胜平负结果: win/draw/lose（相对主队）"""
    if home_score > away_score:
        return "win"
    elif home_score == away_score:
        return "draw"
    else:
        return "lose"


def determine_handicap_spf_result(home_score, away_score, handicap_str):
    """
    让球胜平负结果
    handicap_str: 如 "-1", "+1", "2.0" 等
    """
    try:
        handicap = float(handicap_str)
    except (ValueError, TypeError):
        # 无法解析让球数，按无让球处理
        return determine_spf_result(home_score, away_score)
    
    adjusted_home = home_score + handicap
    if adjusted_home > away_score:
        return "win"
    elif adjusted_home == away_score:
        return "draw"
    else:
        return "lose"


def settle_user_bets(conn, match_id, home_score, away_score, handicap_str, sport_type):
    """结算某个比赛的所有注单"""
    bets = query(conn, """
        SELECT id, bet_type, bet_option, bet_gold, odds
        FROM user_bets
        WHERE match_id = %s AND result IS NULL
    """, (match_id,))
    
    settled_count = 0
    for bet in bets:
        bet_type = bet["bet_type"]
        bet_option = bet["bet_option"]
        bet_gold = bet["bet_gold"]
        odds = float(bet["odds"])
        
        result = None
        profit = 0
        
        if sport_type == "football":
            if bet_type == "spf":
                # 胜平负
                actual = determine_spf_result(home_score, away_score)
                if bet_option == actual:
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                else:
                    result = "lose"
                    profit = -bet_gold
            elif bet_type == "handicap_spf":
                # 让球胜平负
                actual = determine_handicap_spf_result(home_score, away_score, handicap_str)
                if bet_option == actual:
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                else:
                    result = "lose"
                    profit = -bet_gold
            elif bet_type == "score":
                # 比分玩法 - 匹配精确比分
                actual_score = f"{home_score}:{away_score}"
                if bet_option == actual_score:
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                else:
                    result = "lose"
                    profit = -bet_gold
            elif bet_type == "total_goals":
                # 进球数玩法
                total = home_score + away_score
                if bet_option == str(total):
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                else:
                    result = "lose"
                    profit = -bet_gold
            elif bet_type == "half_full":
                # 半全场玩法 - bet_option 格式如 "win/win"
                # 目前简化处理：如果没有半场数据，标记为 pending
                result = "pending"
                profit = 0
            else:
                # 未知玩法，暂不结算
                result = "pending"
                profit = 0
                
        elif sport_type == "basketball":
            if bet_type == "mnl":
                # 篮球胜负
                actual = determine_spf_result(home_score, away_score)
                if bet_option == actual:
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                else:
                    result = "lose"
                    profit = -bet_gold
            elif bet_type == "hdc":
                # 篮球让分胜负
                actual = determine_handicap_spf_result(home_score, away_score, handicap_str)
                if bet_option == actual:
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                else:
                    result = "lose"
                    profit = -bet_gold
            elif bet_type == "total_points":
                # 大小分
                total = home_score + away_score
                try:
                    line = float(handicap_str) if handicap_str else 0
                except (ValueError, TypeError):
                    line = 0
                if bet_option == "over" and total > line:
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                elif bet_option == "under" and total < line:
                    result = "win"
                    profit = int(bet_gold * odds) - bet_gold
                else:
                    result = "lose"
                    profit = -bet_gold
            else:
                result = "pending"
                profit = 0
        else:
            result = "pending"
            profit = 0
        
        # 更新注单
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE user_bets 
                SET result = %s, profit = %s, settled_at = NOW()
                WHERE id = %s
            """, (result, profit, bet["id"]))
        
        settled_count += 1
    
    return settled_count


def settle():
    """主结算流程"""
    conn = get_db()
    now = datetime.now(CST)
    settle_deadline = now - timedelta(hours=3)  # 开赛3小时后才能结算
    
    # 1. 查找所有可结算的比赛
    # 条件：selling_status != 'settled' AND status != '已取消' AND match_time + 3h <= NOW()
    # AND (home_score IS NOT NULL OR status = '已确认')
    candidates = query(conn, """
        SELECT id, teams, match_time, status, selling_status, 
               home_score, away_score, handicap, sport_type
        FROM matches
        WHERE selling_status != 'settled'
          AND status != '已取消'
          AND match_time IS NOT NULL
          AND match_time <= %s
        ORDER BY match_time ASC
    """, (settle_deadline.strftime("%Y-%m-%d %H:%M:%S"),))
    
    if not candidates:
        conn.close()
        result = {"settled": 0, "skipped": 0, "no_score": 0, "message": "无待结算比赛"}
        print(json.dumps(result, ensure_ascii=False))
        return result
    
    print(f"[Settle] 找到 {len(candidates)} 场待检查比赛")
    
    settled_count = 0
    skipped_count = 0
    no_score_count = 0
    error_count = 0
    
    for m in candidates:
        match_id = m["id"]
        teams = m["teams"]
        match_time = m["match_time"]
        status = m["status"]
        selling_status = m["selling_status"]
        home_score = m["home_score"]
        away_score = m["away_score"]
        handicap = m["handicap"]
        sport_type = m["sport_type"]
        
        # 跳过on_sale仍在销售中的比赛（不应该出现，但保险起见）
        if selling_status == "on_sale" and status in ("on_sale", "未开赛"):
            skipped_count += 1
            continue
        
        # 如果比赛没有分数，尝试从sporttery获取
        if home_score is None or away_score is None:
            # 尝试获取分数
            if status == "已确认":
                # 已确认但没分数？异常，记录
                print(f"[Settle] ⚠️ {match_id} ({teams}) status=已确认 但无分数，跳过", file=sys.stderr)
                no_score_count += 1
                continue
            else:
                # 还没确认的比赛，跳过
                skipped_count += 1
                continue
        
        # 执行结算
        try:
            # 更新比赛状态为settled
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE matches 
                    SET selling_status = 'settled'
                    WHERE id = %s AND selling_status != 'settled'
                """, (match_id,))
            
            # 结算相关注单
            bets_settled = settle_user_bets(conn, match_id, home_score, away_score, handicap, sport_type)
            
            conn.commit()
            settled_count += 1
            print(f"[Settle] ✅ {match_id} ({teams}) {home_score}:{away_score} | 注单: {bets_settled}条")
            
        except Exception as e:
            conn.rollback()
            error_count += 1
            print(f"[Settle] ❌ {match_id} ({teams}) 结算失败: {e}", file=sys.stderr)
    
    conn.close()
    
    result = {
        "settled": settled_count,
        "skipped": skipped_count,
        "no_score": no_score_count,
        "errors": error_count,
        "checked": len(candidates),
        "deadline": settle_deadline.strftime("%Y-%m-%d %H:%M:%S"),
        "message": f"检查{len(candidates)}场 | 结算{settled_count}场 | 跳过{skipped_count}场 | 无分数{no_score_count}场 | 错误{error_count}场"
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    try:
        settle()
    except Exception as e:
        error_result = {"settled": 0, "errors": 1, "message": f"结算异常: {str(e)}"}
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)
