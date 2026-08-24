#!/usr/bin/env python3
"""补跑缺失AI预测 - 只补混元(6场)和扣子(1场)"""
import os, sys, json, re, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2

DB_URL = 'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres'

# 混元配置（标准OpenAI格式）
HUNYUAN_CFG = {
    "base_url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
    "api_key": os.environ.get("HUNYUAN_API_KEY", "REMOVED"),
    "model": "hy-mt2-lite",
}

# 扣子配置（coze_code格式，SSE流式）
COZE_CFG = {
    "base_url": "https://7hsjv6c4cn.coze.site/stream_run",
    "api_key": os.environ.get("COZE_PROJECT_API_TOKEN", "REMOVED"),
    "project_id": 7667164681706078217,
}

def get_db():
    return psycopg2.connect(DB_URL)

def get_matches_missing_ai(ai_name):
    """查询缺失指定AI预测的比赛"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.home_team, m.away_team, m.metadata->>'league',
               m.metadata->>'match_time', m.metadata->>'handicap',
               COALESCE(m.metadata->'odds'->'handicap_spf'->>'handicap', ''),
               COALESCE(m.metadata->'odds'->'handicap_spf'->>'win_odds', ''),
               COALESCE(m.metadata->'odds'->'handicap_spf'->>'draw_odds', ''),
               COALESCE(m.metadata->'odds'->'handicap_spf'->>'lose_odds', ''),
               COALESCE(m.metadata->'odds'->'hdc'->>'win_odds', ''),
               COALESCE(m.metadata->'odds'->'hdc'->>'draw_odds', ''),
               COALESCE(m.metadata->'odds'->'hdc'->>'lose_odds', '')
        FROM matches m
        WHERE m.status IN ('on_sale','未开赛')
          AND m.metadata->>'match_time' >= '2026-08-22'
          AND m.metadata->>'match_time' < '2026-08-24'
          AND m.sport_type = 'football'
          AND m.id NOT IN (SELECT match_id FROM predictions WHERE ai_name = %s)
          AND m.id IN (SELECT match_id FROM predictions WHERE ai_name != %s)
        ORDER BY m.id
    """, (ai_name, ai_name))
    rows = cur.fetchall()
    conn.close()
    return [{
        "id": r[0], "home_team": r[1], "away_team": r[2], "league": r[3] or "",
        "match_time": r[4] or "", "handicap": r[5] or "未知",
        "odds": {
            "spf": {"handicap": r[6], "win": r[7], "draw": r[8], "lose": r[9]},
            "hdc": {"win": r[10], "draw": r[11], "lose": r[12]}
        }
    } for r in rows]

def build_prompt(match):
    """构建足球预测prompt - 对齐主预测脚本"""
    odds = match.get("odds", {})
    spf = odds.get("spf", {})
    hdc = odds.get("hdc", {})
    handicap = match.get("handicap", "未知")
    
    prompt = f"""你是一个专业的足球比赛预测分析师。请根据比赛信息做出预测。

## 比赛信息
- 联赛: {match.get('league', '未知')}
- 主队: {match['home_team']}
- 客队: {match['away_team']}
- 比赛时间: {match.get('match_time', '未知')}
- 让球: {handicap}
- 胜平负赔率: 胜{spf.get('win','?')} / 平{spf.get('draw','?')} / 负{spf.get('lose','?')}
- 让球赔率: 让胜{hdc.get('win','?')} / 让平{hdc.get('draw','?')} / 让负{hdc.get('lose','?')}

## 请严格按以下JSON格式输出预测结果:
{{
  "spf": "胜"或"平"或"负",
  "handicap_spf": "让胜"或"让平"或"让负",
  "score": "比分如2-1",
  "goals": 总进球数(整数),
  "half_full": "半全场(必填)",
  "analysis": "50-100字的分析理由"
}}

## 重要：half_full字段必须填写，可选值为：
胜胜/胜平/胜负/平胜/平平/平负/负胜/负平/负负

只输出JSON，不要其他内容。"""
    return prompt

def call_hunyuan(prompt):
    """调用混元API（标准OpenAI格式）"""
    cfg = HUNYUAN_CFG
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800, "temperature": 0.7
    }
    resp = requests.post(cfg["base_url"], headers=headers, json=payload, timeout=60)
    if resp.status_code == 200:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    else:
        print(f"  混元API错误: {resp.status_code} - {resp.text[:200]}")
        return None

def call_coze(prompt):
    """调用扣子API（coze_code格式，SSE流式）"""
    cfg = COZE_CFG
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json"
    }
    payload = {
        "content": {
            "query": {
                "prompt": [{"type": "text", "content": {"text": prompt}}]
            }
        },
        "type": "query",
        "session_id": f"fill_{int(__import__('time').time())}",
        "project_id": cfg["project_id"]
    }
    resp = requests.post(cfg["base_url"], headers=headers, json=payload, timeout=120, stream=True)
    if resp.status_code != 200:
        print(f"  扣子API错误: {resp.status_code} - {resp.text[:200]}")
        return None
    
    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type:
        data = resp.json()
        if "data" in data and isinstance(data["data"], dict):
            msgs = data["data"].get("messages", [])
            for msg in reversed(msgs):
                if msg.get("role") == "assistant" and msg.get("content"):
                    return msg["content"]
        if "result" in data:
            return str(data["result"])
        return json.dumps(data, ensure_ascii=False)
    
    # SSE流式
    chunks = []
    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8").strip()
        if line_str.startswith("data:"):
            line_str = line_str[5:].strip()
            if not line_str:
                continue
            try:
                evt = json.loads(line_str)
                if isinstance(evt, dict) and evt.get("type") == "answer":
                    content = evt.get("content", {})
                    if isinstance(content, dict):
                        chunk = content.get("answer")
                        if chunk:
                            chunks.append(chunk)
            except json.JSONDecodeError:
                pass
    if chunks:
        return "".join(chunks)
    return resp.text[:2000] if resp.text else None

def parse_prediction(raw_text, ai_name):
    """解析预测JSON"""
    cleaned = re.sub(r'"goals"\s*:\s*(\d+)\s*-\s*(\d+)', r'"goals": \1', raw_text)
    cleaned = re.sub(r'"goals"\s*:\s*"(\d+)"', r'"goals": \1', cleaned)
    open_braces = cleaned.count('{') - cleaned.count('}')
    if open_braces > 0:
        cleaned += '}' * open_braces
    cleaned = re.sub(r',\s*}', '}', cleaned)
    cleaned = re.sub(r',\s*]', ']', cleaned)
    
    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if not json_match:
        print(f"  [WARN] {ai_name} 未找到JSON: {raw_text[:100]}")
        return None
    
    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        print(f"  [WARN] {ai_name} JSON解析失败: {raw_text[:100]}")
        return None
    
    spf = data.get("spf", "平")
    if spf not in ["胜", "平", "负"]: spf = "平"
    handicap_spf = data.get("handicap_spf", "让负")
    if handicap_spf not in ["让胜", "让平", "让负"]:
        if "让胜" in str(handicap_spf): handicap_spf = "让胜"
        elif "让负" in str(handicap_spf): handicap_spf = "让负"
        else: handicap_spf = "让负"
    goals = data.get("goals", 2)
    try: goals = max(0, min(7, int(goals)))
    except: goals = 2
    score = data.get("score", "1-1")
    if not re.match(r'\d+-\d+', str(score)): score = "1-1"
    half_full = data.get("half_full")
    valid_hf = ["胜胜","胜平","胜负","平胜","平平","平负","负胜","负平","负负"]
    if half_full is None or half_full not in valid_hf:
        half_full = "平平"
    confidence = data.get("confidence", 0.5)
    try: confidence = max(0.3, min(0.95, float(confidence)))
    except: confidence = 0.5
    
    return {
        "spf": spf, "handicap_spf": handicap_spf, "goals": goals,
        "score": score, "half_full": half_full, "confidence": confidence,
        "analysis": data.get("analysis", ""),
    }

def write_prediction(match_id, ai_name, pred_data, raw_response):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM predictions")
        next_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO predictions (
                id, match_id, ai_name, prediction, analysis,
                sport_type, confidence, match_date,
                spf, handicap_spf, goals, score, half_full, raw_response
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            next_id, match_id, ai_name,
            json.dumps(pred_data, ensure_ascii=False),
            pred_data.get("analysis", ""), "football",
            str(pred_data.get("confidence", "")), None,
            pred_data["spf"], pred_data["handicap_spf"],
            pred_data["goals"], pred_data["score"],
            pred_data["half_full"], raw_response,
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] 写入失败: {e}")
        return False
    finally:
        conn.close()

def main():
    print("=== 补跑缺失AI预测 ===\n")
    
    # 1. 补混元（6场）
    hunyuan_matches = get_matches_missing_ai("混元")
    print(f"混元缺失: {len(hunyuan_matches)}场")
    hy_ok = 0
    for m in hunyuan_matches:
        prompt = build_prompt(m)
        raw = call_hunyuan(prompt)
        if raw:
            pred = parse_prediction(raw, "混元")
            if pred and write_prediction(m["id"], "混元", pred, raw):
                print(f"  OK: {m['home_team']} vs {m['away_team']} -> {pred['spf']}, {pred['score']}")
                hy_ok += 1
            else:
                print(f"  FAIL: {m['home_team']} vs {m['away_team']} 解析失败")
        else:
            print(f"  FAIL: {m['home_team']} vs {m['away_team']} API失败")
    print(f"混元完成: {hy_ok}/{len(hunyuan_matches)}\n")
    
    # 2. 补扣子（1场）
    coze_matches = get_matches_missing_ai("扣子")
    print(f"扣子缺失: {len(coze_matches)}场")
    kz_ok = 0
    for m in coze_matches:
        prompt = build_prompt(m)
        raw = call_coze(prompt)
        if raw:
            pred = parse_prediction(raw, "扣子")
            if pred and write_prediction(m["id"], "扣子", pred, raw):
                print(f"  OK: {m['home_team']} vs {m['away_team']} -> {pred['spf']}, {pred['score']}")
                kz_ok += 1
            else:
                print(f"  FAIL: {m['home_team']} vs {m['away_team']} 解析失败")
        else:
            print(f"  FAIL: {m['home_team']} vs {m['away_team']} API失败")
    print(f"扣子完成: {kz_ok}/{len(coze_matches)}\n")
    
    print(f"=== 总计: 混元{hy_ok}/{len(hunyuan_matches)}, 扣子{kz_ok}/{len(coze_matches)} ===")

if __name__ == "__main__":
    main()
