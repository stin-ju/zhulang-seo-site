#!/usr/bin/env python3
"""
ct_auto_settle_v2.py - 传统彩（CT）自动结算 v2，操作 predictions 表

基于 CT/ct_auto_settle.py（v2 基准，b295441）改造。核心变更：
  1. get_unsettled_predictions 从 predictions 表查询
     WHERE ct_issue IS NOT NULL AND (is_settled = FALSE OR is_settled IS NULL)，
     LEFT JOIN matches 获取球队名与比赛时间。
  2. 按 ct_issue 分组返回，每组含 records 列表（每条 = 一个 match_id + ai_name 单场预测记录）。
  3. collect_scores 收集比分逻辑保留（matches 表精确关联 + 球队名模糊 + titan007 补抓），
     但优先用 predictions 表的 match_id 精确关联 matches 表。
  4. settle_issue 对每个 (match_id, ai_name) 记录单独更新 predictions 表的
     is_settled = TRUE 和 hit_status(jsonb)。
  5. hit_status 包含 {hit, actual, score, reason}。
  6. 保留原有的 titan007 比分抓取、别名映射、胜负判断逻辑。
  7. 保留 --issue 和 --dry-run 参数。
  8. 不再操作 traditional_predictions 表。

比分配对铁律：有比分能判定的记录才标记 is_settled=TRUE；
无比分（no_score/no_half_score）的记录保持 is_settled=FALSE，比分补齐后自动复活重算。

用法:
  python3 ct_auto_settle_v2.py                     # 结算所有未结算 CT 预测
  python3 ct_auto_settle_v2.py --issue 26098       # 结算指定期号（纯数字或 CT 前缀均可）
  python3 ct_auto_settle_v2.py --dry-run           # 试运行，不更新数据库
"""

import os
import sys
import re
import json
import argparse
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta

# ============ 配置 ============
DB_URL = os.environ.get('DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 竞彩简称 ↔ CT彩全名 别名映射
ALIASES = {
    '飞马': ['飞翼', '达拉斯飞翼'],
    '康太阳': ['康涅狄克太阳', '康乃狄克太阳'],
    '迈国际': ['国际迈阿密', '迈阿密国际'],
    '圣路易城': ['圣路易斯城'],
    '洛城银河': ['洛杉矶银河'],
    '坦山猫': ['坦佩雷山猫'],
    '赫尔火花': ['赫尔辛基火花'],
    '布鲁马波': ['布鲁马波卡纳'],
    '腓特烈': ['腓特烈斯塔'],
    '瓦萨': ['VPS瓦萨'],
    '国际图尔': ['英特土尔库', '国际图尔库'],
    '巴竞技': ['巴拉纳竞技'],
    '斯达': ['斯塔贝克', 'Start'],
    '维京': ['Viking', '维京FK'],
    '库奥皮奥': ['KuPS', '库普斯'],
    '弗鲁米嫩塞': ['Fluminense', '富明尼斯'],
    '桑托斯': ['Santos', '桑托斯FC'],
    '辛辛那提': ['FC Cincinnati', '辛辛那提'],
    '圣何塞地震': ['San Jose Earthquakes', '圣何塞'],
    '华盛顿联': ['DC United', '华盛顿联队', '华盛顿'],
    '纳什维尔': ['Nashville SC', '纳什维尔SC'],
    '迈阿密国际': ['Inter Miami', '国际迈阿密'],
    '哥伦布机员': ['Columbus Crew', '哥伦布'],
    '蒙特利尔': ['Montreal Impact', '蒙特利尔冲击'],
    '新英格兰革命': ['New England Revolution', '新英格兰'],
    '温哥华白帽': ['Vancouver Whitecaps', '温哥华'],
    '洛杉矶FC': ['LAFC', '洛杉矶FC'],
    '芝加哥火焰': ['Chicago Fire', '芝加哥'],
    '夏洛特FC': ['Charlotte FC', '夏洛特'],
    '圣路易斯城': ['St. Louis City', '圣路易斯城SC'],
    '皇家盐湖城': ['Real Salt Lake', '皇家盐湖城'],
    '布兰': ['Brann', '布兰足球俱乐部'],
    '罗森博格': ['Rosenborg', '罗森博格BK'],
    '塞伊奈约基': ['SJK', '塞伊奈约基PK'],
    '赫尔辛基': ['HJK Helsinki', 'HJK', '赫尔辛基HJK'],
    '米拉索尔': ['Mirassol', '米拉索尔FC'],
    '格雷米奥': ['Gremio', '格雷米奥FBPA'],
    '索尔纳': ['AIK索尔纳'],
    '哥德堡': ['IFK哥德堡'],
    '奥斯KFUM': ['奥斯陆KFUM'],
    '萨普斯堡': ['萨尔普斯堡'],
}

# ============ 工具函数 ============

def _safe_int(val, default=0):
    if val is None or val == "" or val == "null":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _name_match(name_a, name_b):
    """判断两个球队名是否匹配（模糊匹配）。name_b 可以是字符串或列表。"""
    if not name_a:
        return False
    if isinstance(name_b, (list, tuple)):
        return any(_name_match(name_a, nb) for nb in name_b if nb)
    if not name_b:
        return False
    a = name_a.strip()
    b = name_b.strip()
    if a == b:
        return True
    if a in b or b in a:
        return True
    for alias_key, alias_list in ALIASES.items():
        if a == alias_key or a in alias_list:
            if b == alias_key or b in alias_list:
                return True
    shorter = a if len(a) <= len(b) else b
    longer = b if len(a) <= len(b) else a
    if len(shorter) >= 3:
        for i in range(len(shorter) - 2):
            if shorter[i:i+3] in longer:
                return True
    return False


def get_db():
    return psycopg2.connect(DB_URL)


# ============ 比分查找（三级查找） ============

def load_jc_scores(conn):
    """预加载所有竞彩已完赛有比分的比赛到内存"""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, home_team, away_team,
               (metadata->>'home_score')::int as home_score,
               (metadata->>'away_score')::int as away_score,
               metadata->>'half_home_score' as half_home,
               metadata->>'half_away_score' as half_away,
               metadata->>'match_date' as match_date
        FROM matches
        WHERE id NOT LIKE 'CT%%'
          AND status = '已完赛'
          AND metadata->>'home_score' IS NOT NULL
          AND metadata->>'away_score' IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"[预加载] 竞彩已有比分比赛: {len(rows)} 场", file=sys.stderr)
    return rows


def load_ct_scores(conn):
    """预加载CT彩有比分的比赛到内存，按 id（即 match_id）索引。
    注意：CT 比赛即使已有比分，status 往往仍是 'on_sale'（不像竞彩会变'已完赛'），
    因此这里【不能】用 status='已完赛' 过滤，只看 metadata 里是否有比分。"""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, home_team, away_team,
               (metadata->>'home_score')::int as home_score,
               (metadata->>'away_score')::int as away_score,
               metadata->>'half_home_score' as half_home,
               metadata->>'half_away_score' as half_away,
               metadata->>'match_date' as match_date
        FROM matches
        WHERE id LIKE 'CT%%'
          AND metadata->>'home_score' IS NOT NULL
          AND metadata->>'away_score' IS NOT NULL
    """)
    rows = cur.fetchall()
    ct_by_id = {}
    for r in rows:
        ct_by_id[r['id']] = r
    print(f"[预加载] CT彩已有比分比赛: {len(rows)} 场", file=sys.stderr)
    return ct_by_id


def find_score_in_rows(home, away, date_str, rows):
    """在预加载的比赛数据中查找比分。返回 score dict 或 None。"""
    if not home or not away:
        return None

    # 生成候选日期（±1天，处理凌晨比赛偏移）
    candidate_dates = set()
    if date_str and re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        candidate_dates.add(date_str)
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            candidate_dates.add((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
            candidate_dates.add((dt + timedelta(days=1)).strftime("%Y-%m-%d"))
        except ValueError:
            pass

    # 先严格匹配（日期+两队精确/包含匹配）
    for row in rows:
        md = row['match_date'] or ''
        if md not in candidate_dates and candidate_dates:
            continue
        h = row['home_team'] or ''
        a = row['away_team'] or ''
        if _name_match(home, h) and _name_match(away, a):
            return _row_to_score(row, "db")

    return None


def _row_to_score(row, source):
    """将数据库行转为比分 dict"""
    half_h = _safe_int(row['half_home']) if row['half_home'] is not None else None
    half_a = _safe_int(row['half_away']) if row['half_away'] is not None else None
    return {
        "home": row['home_score'],
        "away": row['away_score'],
        "half_home": half_h,
        "half_away": half_a,
        "source": f"{source}:{row['id']}"
    }


# ============ titan007 补抓 ============

def _parse_m_array(html):
    matches = {}
    for m in re.finditer(r"M\[(\d+)\]\[(\d+)\]\s*=\s*(.+?)\s*;", html, re.DOTALL):
        row, col = int(m.group(1)), int(m.group(2))
        raw = m.group(3).strip()
        if row not in matches:
            matches[row] = {}
        if raw.startswith(('"', "'")):
            val = raw.strip("\"'")
        elif raw in ("true", "false"):
            val = raw == "true"
        elif raw.startswith("new Date"):
            val = raw
        else:
            try:
                val = int(raw)
            except ValueError:
                try:
                    val = float(raw)
                except ValueError:
                    val = raw
        matches[row][col] = val

    results = []
    for idx in sorted(matches):
        if idx == 0:
            continue
        d = matches[idx]
        home = d.get(17, "")
        away = d.get(20, "")
        if not home or not away:
            continue
        results.append({
            "status_code": d.get(4, 0),
            "home_team": home, "away_team": away,
            "home_team_trad": d.get(18, ""), "away_team_trad": d.get(21, ""),
            "home_team_official": d.get(19, ""), "away_team_official": d.get(22, ""),
            "home_score": _safe_int(d.get(7)), "away_score": _safe_int(d.get(8)),
            "home_half": _safe_int(d.get(11)), "away_half": _safe_int(d.get(12)),
            "match_time": d.get(1, "").strip(),
        })
    return results


def fetch_scores(date_str=None):
    if date_str is None:
        now = datetime.utcnow() + timedelta(hours=8)
        date_str = f"{now.year}-{now.month}-{now.day}"
    url = f"https://cp.titan007.com/buy/JingCai.aspx?typeID=101&oddstype=2&date={date_str}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        print(f"[titan007] 请求失败 {date_str}: {e}", file=sys.stderr)
        return []
    all_matches = _parse_m_array(resp.text)
    completed = [m for m in all_matches if m["status_code"] != 0]
    print(f"[titan007] {date_str}: {len(all_matches)}场, 完场{len(completed)}场", file=sys.stderr)
    return completed


def find_in_titan(home, away, date_str, titan_cache):
    """在titan007数据中查找比分。titan_cache 缓存已抓取日期的数据。"""
    if not home or not away:
        return None

    candidate_dates = set()
    if date_str:
        candidate_dates.add(date_str)
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            candidate_dates.add((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
            candidate_dates.add((dt + timedelta(days=1)).strftime("%Y-%m-%d"))
        except ValueError:
            pass

    for cd in sorted(candidate_dates):
        if cd not in titan_cache:
            titan_cache[cd] = fetch_scores(cd)
        for tm in titan_cache[cd]:
            h = _name_match(home, [tm["home_team"], tm["home_team_trad"], tm.get("home_team_official", "")])
            a = _name_match(away, [tm["away_team"], tm["away_team_trad"], tm.get("away_team_official", "")])
            if h and a and tm["home_score"] is not None:
                return {
                    "home": tm["home_score"],
                    "away": tm["away_score"],
                    "half_home": tm.get("home_half"),
                    "half_away": tm.get("away_half"),
                    "source": f"titan007:{cd}"
                }
    return None


# ============ 数据库操作 ============

def get_unsettled_predictions(conn, issue=None, recheck_bad_settled=False):
    """从 predictions 表查询待结算的 CT 预测记录。

    常规（recheck_bad_settled=False）：
      WHERE ct_issue IS NOT NULL AND (is_settled = FALSE OR is_settled IS NULL)
    重算模式（recheck_bad_settled=True，额外纳入"错误已结算"记录）：
      - is_settled=TRUE 但 spf IS NULL（实际结果缺失，属错误结算，必须回填纠正）
      - is_settled=TRUE 且 hit_status->>'reason'='score_unavailable'（无比分却被标已结算）
    LEFT JOIN matches 获取球队名与比赛时间；按 ct_issue 分组返回。

    Returns:
        dict: {ct_issue: {"game_types": set, "records": [...]}}
    """
    where = ["p.ct_issue IS NOT NULL"]
    if recheck_bad_settled:
        where.append("""(
              p.is_settled = FALSE OR p.is_settled IS NULL
              OR (p.is_settled = TRUE AND p.spf IS NULL)
              OR (p.is_settled = TRUE AND p.hit_status->>'reason' = 'score_unavailable')
          )""")
    else:
        where.append("(p.is_settled = FALSE OR p.is_settled IS NULL)")

    sql = f"""
        SELECT p.match_id, p.ai_name,
               p.ct_game_type AS game_type,
               p.spf_pred, p.half_full_pred, p.prediction,
               p.is_settled AS was_settled,
               p.spf AS spf,
               m.home_team AS home, m.away_team AS away,
               m.metadata->>'match_time' AS match_time
        FROM predictions p
        LEFT JOIN matches m ON m.id = p.match_id
        WHERE {' AND '.join(where)}
    """
    params = []
    if issue:
        iss = str(issue)
        if iss.startswith('CT'):
            iss = iss[2:]
        sql += " AND p.ct_issue = %s"
        params.append(f"CT{iss}")

    sql += " ORDER BY p.ct_issue DESC, p.ct_game_type, p.match_id, p.ai_name"

    groups = {}
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, params)
        for row in cur.fetchall():
            ci = row['match_id'].split('_')[0] if row['match_id'] else None
            # ct_issue 采用 'CT' + 期号 形式；从 match_id 前缀取
            groups.setdefault(ci, {"game_types": set(), "records": []})
            groups[ci]["records"].append({
                "match_id": row['match_id'],
                "ai_name": row['ai_name'],
                "game_type": row['game_type'],
                "spf_pred": row['spf_pred'],
                "half_full_pred": row['half_full_pred'],
                "prediction": row['prediction'] if isinstance(row['prediction'], dict)
                              else (json.loads(row['prediction']) if row['prediction'] else {}),
                "was_settled": bool(row['was_settled']) if row['was_settled'] is not None else False,
                "home": row['home'] or "",
                "away": row['away'] or "",
                "match_time": row['match_time'] or "",
            })
            if row['game_type']:
                groups[ci]["game_types"].add(row['game_type'])

    return groups


# ============ 结算逻辑 ============

def get_result_code(home_score, away_score):
    if home_score is None or away_score is None:
        return None
    if home_score > away_score: return "3"
    elif home_score == away_score: return "1"
    else: return "0"


def get_total_goals(home_score, away_score):
    total = home_score + away_score
    return "7" if total >= 7 else str(total)


def collect_scores(conn, group_records, jc_scores, ct_scores, titan_cache):
    """收集一组记录所需的全部比分。

    三级查找（按 match_id 精确关联优先）：
      Level 1: matches 表按 match_id 直接精确取比分（CT 或竞彩）
      Level 2: 球队名在各比赛行中模糊匹配（jc_scores / ct_scores）
      Level 3: titan007 补抓

    Returns:
        (scores_map, stats): scores_map = {match_id: score_dict}, stats = 来源计数
    """
    scores_map = {}
    stats = {"db_ct_exact": 0, "db_jc_name": 0, "db_ct_name": 0, "titan": 0, "not_found": 0}

    # 预取本组涉及的 matches 精确行（一次查询，避免逐条查询）
    match_ids = list(dict.fromkeys(r["match_id"] for r in group_records))
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, home_team, away_team, status,
                   (metadata->>'home_score')::int as home_score,
                   (metadata->>'away_score')::int as away_score,
                   metadata->>'half_home_score' as half_home,
                   metadata->>'half_away_score' as half_away,
                   metadata->>'match_date' as match_date
            FROM matches
            WHERE id = ANY(%s)
        """, (match_ids,))
        precise = {r['id']: r for r in cur.fetchall()}

    for rid in match_ids:
        row = precise.get(rid)

        # Level 1: 精确关联——只要 metadata 里有比分即可（CT 比赛有比分时 status 常为 on_sale，不能要求'已完赛'）
        is_ct = str(rid).startswith("CT")
        if row and row['home_score'] is not None and row['away_score'] is not None and (is_ct or row['status'] == '已完赛'):
            scores_map[rid] = _row_to_score(row, f"db:match_id")
            stats["db_ct_exact"] += 1
            continue

        home = away = date_str = ""
        for r in group_records:
            if r["match_id"] == rid:
                home = r["home"]
                away = r["away"]
                parts = (r["match_time"] or "").split()
                if parts and re.match(r'\d{4}-\d{2}-\d{2}', parts[0]):
                    date_str = parts[0]
                break

        if not home or not away:
            stats["not_found"] += 1
            continue

        # Level 2: 球队名模糊匹配（竞彩库）
        score = find_score_in_rows(home, away, date_str, jc_scores)
        if score:
            stats["db_jc_name"] += 1
            scores_map[rid] = score
            continue

        # Level 2b: 球队名模糊匹配（CT 库本身）
        score = find_score_in_rows(home, away, date_str, list(ct_scores.values()))
        if score:
            stats["db_ct_name"] += 1
            scores_map[rid] = score
            continue

        # Level 3: titan007 补抓
        score = find_in_titan(home, away, date_str, titan_cache)
        if score:
            stats["titan"] += 1
            scores_map[rid] = score
            continue

        stats["not_found"] += 1

    return scores_map, stats


def _score_to_hit(score, reason_prefix=""):
    """由比分构造 hit_status 基础字段（actual / score 段）"""
    actual = get_result_code(score["home"], score["away"])
    score_str = f"{score['home']}-{score['away']}"
    return actual, score_str


def settle_record(rec, score):
    """计算单场 (match_id, ai_name) 记录的命中判定。

    CT 胜负彩只结算【胜平负 3/1/0】这 1 个维度：
      - 让球 handicap_spf / 进球数 goals / 半全场 half_full 在 CT 胜负彩【不适用】，不判。
      - 比分只用于推导实际胜平负，不比预测比分。
    Returns:
        hit_status dict: {spf_hit, hit, actual, score, pred, reason}
        - reason='ok'：有比分且有预测，可判定
        - reason='score_unavailable'：无比分（不结算，保持 is_settled=false）
        - reason='no_pred'：有比分但模型没给胜平负预测
    """
    if not score:
        return {"spf_hit": None, "hit": None, "actual": None, "score": None,
                "pred": rec.get("spf_pred"), "reason": "score_unavailable"}

    game_type = (rec.get("game_type") or "胜负彩")
    actual, score_str = _score_to_hit(score)

    # 胜负彩 & 任9：只结胜平负 3/1/0
    if game_type in ("胜负彩", "任9", ""):
        pred = rec.get("spf_pred")
        if pred is None or str(pred).strip() in ("", "-"):
            return {"spf_hit": None, "hit": None, "actual": actual, "score": score_str,
                    "pred": pred, "reason": "no_pred"}
        is_hit = str(pred).strip() == str(actual)
        return {"spf_hit": is_hit, "hit": is_hit, "actual": actual,
                "score": score_str, "pred": str(pred).strip(), "reason": "ok"}

    if game_type == "半全场":
        pred = rec.get("half_full_pred")
        half_home = score.get("half_home")
        half_away = score.get("half_away")
        if pred is None or str(pred).strip() in ("", "-"):
            return {"spf_hit": None, "hit": None, "actual": None, "score": score_str,
                    "reason": "no_pred"}
        if half_home is None or half_away is None:
            return {"spf_hit": None, "hit": None, "actual": None, "score": score_str,
                    "reason": "score_unavailable"}
        half_result = get_result_code(half_home, half_away)
        full_result = actual
        actual_hf = (half_result or "") + (full_result or "")
        is_hit = str(pred).strip() == str(actual_hf)
        return {"spf_hit": None, "hit": is_hit, "actual": actual_hf,
                "score": f"{half_home}-{half_away}/{score['home']}-{score['away']}", "reason": "ok"}

    # 进球彩：进到 raw prediction JSONB 里取 zjq_home/zjq_away（无则 fallback 总进球）
    if game_type == "进球彩":
        pred = rec.get("prediction") or {}
        zjq_home = pred.get("zjq_home")
        zjq_away = pred.get("zjq_away")
        if zjq_home is not None and zjq_away is not None:
            is_hit = (_safe_int(zjq_home) == _safe_int(score["home"]) and
                      _safe_int(zjq_away) == _safe_int(score["away"]))
            return {"spf_hit": None, "hit": is_hit, "actual": f"{score['home']}-{score['away']}",
                    "score": score_str, "reason": "ok"}
        total_pred = pred.get("zjq")
        if total_pred is None:
            return {"spf_hit": None, "hit": None, "actual": None, "score": score_str,
                    "reason": "no_pred"}
        actual_total = get_total_goals(score["home"], score["away"])
        return {"spf_hit": None, "hit": str(total_pred).strip() == actual_total,
                "actual": actual_total, "score": score_str, "reason": "ok"}

    # 未知玩法按胜平负兜底
    pred = rec.get("spf_pred")
    if pred is None or str(pred).strip() in ("", "-"):
        return {"spf_hit": None, "hit": None, "actual": actual, "score": score_str,
                "reason": "no_pred"}
    is_hit = str(pred).strip() == str(actual)
    return {"spf_hit": is_hit, "hit": is_hit, "actual": actual,
            "score": score_str, "pred": str(pred).strip(), "reason": "ok"}


def settle_issue(conn, ct_issue, group, scores_map, dry_run=False):
    """对该期号下每个 (match_id, ai_name) 记录单独结算更新。

    判定规则：
      - 有比分且可判定（reason=ok）：回填 spf=实际3/1/0，is_settled=TRUE，hit_status 带 spf_hit。
      - 无比分（reason=score_unavailable）：hit_status 标 score_unavailable，【is_settled=FALSE】，
        比分到位后再次运行自动结算；若之前被误标为 TRUE，这里纠正回 FALSE。
      - 有比分但无预测（reason=no_pred）：回填 spf，标记已结算但不计命中。
    """
    updated = 0
    skipped = 0
    no_score = 0
    with conn.cursor() as cur:
        for rec in group["records"]:
            score = scores_map.get(rec["match_id"])
            hit_status = settle_record(rec, score)
            reason = hit_status.get("reason")

            # 无比分：标记 score_unavailable，强制 is_settled=FALSE（纠正可能的误标 TRUE）
            if reason == "score_unavailable":
                no_score += 1
                skipped += 1
                if dry_run:
                    print(f"  [DRY] {rec['match_id']} {rec['ai_name']:12s} "
                          f"{rec['home'] or '?'} vs {rec['away'] or '?'}: "
                          f"无比分→score_unavailable, is_settled=FALSE(待比分)")
                    continue
                cur.execute("""
                    UPDATE predictions
                    SET is_settled = FALSE,
                        hit_status = %s::jsonb
                    WHERE match_id = %s AND ai_name = %s
                """, (json.dumps(hit_status, ensure_ascii=False),
                      rec["match_id"], rec["ai_name"]))
                continue

            actual = hit_status.get("actual")
            spf_hit = hit_status.get("spf_hit")

            if dry_run:
                print(f"  [DRY] {rec['match_id']} {rec['ai_name']:12s} "
                      f"{rec['home'] or '?'} vs {rec['away'] or '?'}: "
                      f"比分{hit_status.get('score')} 实际spf={actual} pred={rec.get('spf_pred')} "
                      f"spf_hit={spf_hit} reason={reason}")
                updated += 1
                continue

            # 有比分：回填 spf=实际结果，写 is_settled + hit_status
            cur.execute("""
                UPDATE predictions
                SET spf = %s,
                    is_settled = TRUE,
                    hit_status = %s::jsonb
                WHERE match_id = %s AND ai_name = %s
            """, (actual,
                  json.dumps(hit_status, ensure_ascii=False),
                  rec["match_id"], rec["ai_name"]))
            updated += 1
    if not dry_run:
        conn.commit()
    return updated, skipped, no_score


# ============ 主流程 ============

def main():
    parser = argparse.ArgumentParser(description="CT彩自动结算 v2 (操作 predictions 表)")
    parser.add_argument("--issue", help="指定期号（纯数字或 CT 前缀均可）")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不更新数据库")
    parser.add_argument("--recheck", action="store_true",
                        help="重算模式：纳入 is_settled=TRUE 但 spf IS NULL 或 reason=score_unavailable 的错误已结算记录并纠正")
    args = parser.parse_args()

    print("=" * 60)
    if args.recheck:
        print("CT彩自动结算 v2 [RECHECK重算模式] (predictions 表, 纠正错误已结算记录)")
    else:
        print("CT彩自动结算 v2 (predictions 表, 按 match_id 精确关联比分)")
    print("=" * 60)

    conn = get_db()

    groups = get_unsettled_predictions(conn, args.issue, recheck_bad_settled=args.recheck)
    total_records = sum(len(g["records"]) for g in groups.values())
    if not groups:
        print("没有待结算的 CT 预测")
        conn.close()
        return
    bad_settled = sum(1 for g in groups.values() for r in g["records"] if r.get("was_settled"))
    if args.recheck:
        print(f"[RECHECK] 其中已错误结算(is_settled=TRUE但实际结果缺失/score_unavailable): {bad_settled} 条")
    print(f"发现 {len(groups)} 个期号, {total_records} 条待结算记录")

    # 预加载比分数据
    jc_scores = load_jc_scores(conn)
    ct_scores = load_ct_scores(conn)

    # titan007 缓存（按日期）
    titan_cache = {}

    total_updated = 0
    total_skipped = 0
    total_noscore = 0
    total_stats = {"db_ct_exact": 0, "db_jc_name": 0, "db_ct_name": 0, "titan": 0, "not_found": 0}

    for ct_issue, group in sorted(groups.items(), reverse=True):
        # 只处理包含所需记录的比赛
        scores_map, stats = collect_scores(conn, group["records"], jc_scores, ct_scores, titan_cache)
        for k in total_stats:
            total_stats[k] += stats[k]

        found = len(scores_map)
        total = len(dict.fromkeys(r["match_id"] for r in group["records"]))
        print(f"\n{ct_issue}: {found}/{total} 场有比分, 玩法: {sorted(group['game_types'])}")

        updated, skipped, no_score = settle_issue(conn, ct_issue, group, scores_map, dry_run=args.dry_run)
        total_updated += updated
        total_skipped += skipped
        total_noscore += no_score

    conn.close()

    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"[DRY-RUN] 试运行，未实际更新数据库")
    print(f"结算完成!")
    print(f"  可结算（有比分, 将置 is_settled=TRUE）: {total_updated} 条")
    print(f"  跳过（无比分/缺预测, 保持未结算）: {total_skipped} 条")
    print(f"  比分来源: match_id精确={total_stats['db_ct_exact']}, "
          f"竞彩球队名={total_stats['db_jc_name']}, CT球队名={total_stats['db_ct_name']}, "
          f"titan007={total_stats['titan']}, 未找到={total_stats['not_found']}")
    print("=" * 60)

    result = {
        "status": "OK",
        "settled": total_updated,
        "skipped": total_skipped,
        "no_score": total_noscore,
        "scores_from_match_id": total_stats['db_ct_exact'],
        "scores_from_jc_db": total_stats['db_jc_name'],
        "scores_from_ct_db": total_stats['db_ct_name'],
        "scores_from_titan": total_stats['titan'],
        "scores_not_found": total_stats['not_found']
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()