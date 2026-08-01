#!/usr/bin/env python3
"""
比赛发现 + AI预测（分批执行，每批5场）
数据源: webapi.sporttery.cn
"""
import os, sys, json, re, time, traceback, requests
from datetime import datetime

# ============ 数据库连接 ============
from supabase_db import get_client, insert_match, update_match, insert_football_prediction, insert_basketball_prediction, get_existing_predictions

# ============ AI配置 ============
AI_CONFIGS = {
    "AI-DeepSeek": {"url": "https://api.deepseek.com/chat/completions", "key_env": "DEEPSEEK_API_KEY", "model": "deepseek-chat", "format": "openai"},
    "AI-MiniMax": {"url": "https://api.minimax.chat/v1/text/chatcompletion_v2", "key_env": "MINIMAX_API_KEY", "model": "MiniMax-Text-01", "format": "minimax"},
    "AI-豆包": {"url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "key_env": "DOUBAO_API_KEY", "model": "doubao-seed-evolving", "format": "openai", "fallback_models": ["doubao-seed-2-1-turbo-260628", "doubao-seed-2-0-mini-260428"]},
    "AI-智谱清言": {"url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "key_env": "ZHIPU_API_KEY", "model": "glm-4-flash", "format": "openai"},
    "AI-文心": {"url": "https://qianfan.baidubce.com/v2/chat/completions", "key_env": "WENXIN_API_KEY", "model": "ernie-4.0-8k-latest", "format": "openai"},
    "AI-混元": {"url": "https://tokenhub.tencentmaas.com/v1/chat/completions", "key_env": "HUNYUAN_API_KEY", "model": "hy-mt2-lite", "format": "openai", "fallback_models": ["hy3-preview"]},
    "AI-扣子（皮皮）": {"url": None, "key_env": None, "model": None, "format": "template"},
}

AI_NAME_MAPPING = {
    "AI-DeepSeek": "DeepSeek", "AI-MiniMax": "MiniMax", "AI-豆包": "豆包",
    "AI-智谱清言": "智谱清言", "AI-文心": "文心", "AI-混元": "混元", "AI-扣子（皮皮）": "扣子", "皮皮": "扣子",
}

BATCH_SIZE = 1  # 每批处理1场比赛

def md(m):
    metadata = m.get("metadata") or {}
    if isinstance(metadata, str):
        try: metadata = json.loads(metadata)
        except: metadata = {}
    return metadata

# ============ 数据抓取 ============
def fetch_sporttery_matches(sport="football"):
    """从 sporttery.cn API 抓取在售比赛"""
    if sport == "football":
        pool_code = "HAD,HHAD,CRS,TTG,HAFU"
        url = f"https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode={pool_code}&channel=c"
    else:
        pool_code = "MNL,HDC,CRS"
        url = f"https://webapi.sporttery.cn/gateway/jc/basketball/getMatchCalculatorV1.qry?poolCode={pool_code}&channel=c"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36", "Referer": "https://www.sporttery.cn/"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        if not data.get("success"):
            print(f"[{sport}] API返回失败: {data}")
            return []
        
        match_info_list = data.get("value", {}).get("matchInfoList", [])
        matches = []
        for group in match_info_list:
            date = group.get("businessDate", "")
            for item in group.get("subMatchList", []):
                match = parse_sporttery_match(item, date, sport)
                if match:
                    matches.append(match)
        print(f"[{sport}] 抓取到 {len(matches)} 场比赛")
        return matches
    except Exception as e:
        print(f"[{sport}] 抓取失败: {e}")
        return []

def parse_sporttery_match(item, date, sport):
    """解析 sporttery API 返回的单场比赛数据"""
    match_num = item.get("matchNumStr", "")
    real_date = item.get("matchDate", date)
    match_id = f"{real_date.replace('-','')}_{match_num}"
    
    home_team = item.get("homeTeamAbbName", "")
    away_team = item.get("awayTeamAbbName", "")
    league = item.get("leagueAbbName", "") or item.get("leagueAllName", "")
    match_time = item.get("matchTime", "")
    
    # 构建 odds
    odds = {}
    if sport == "football":
        had = item.get("had", {})
        hhad = item.get("hhad", {})
        if had:
            odds["had"] = {"h": had.get("h",""), "d": had.get("d",""), "a": had.get("a","")}
        if hhad:
            odds["hhad"] = {"h": hhad.get("h",""), "d": hhad.get("d",""), "a": hhad.get("a",""), "goalLine": hhad.get("goalLine","")}
        # CRS (比分)
        crs = item.get("crs", {})
        if crs:
            odds["crs"] = {k: v for k, v in crs.items() if k not in ("goalLine", "goalLineValue", "updateDate", "updateTime")}
        # TTG (总进球)
        ttg = item.get("ttg", {})
        if ttg:
            odds["ttg"] = {k: v for k, v in ttg.items() if k not in ("goalLine", "goalLineValue", "updateDate", "updateTime")}
        # HAFU (半全场)
        hafu = item.get("hafu", {})
        if hafu:
            odds["hafu"] = {k: v for k, v in hafu.items() if k not in ("goalLine", "goalLineValue", "updateDate", "updateTime")}
        
        handicap = float(hhad.get("goalLine", 0)) if hhad else 0
    else:
        mnl = item.get("mnl", {})
        hdc = item.get("hdc", {})
        if mnl:
            odds["mnl"] = {"win": mnl.get("h",""), "lose": mnl.get("a","")}
        if hdc:
            odds["hdc"] = {"win": hdc.get("h",""), "lose": hdc.get("a",""), "line": hdc.get("goalLine","")}
        handicap = float(hdc.get("goalLine", 0)) if hdc else 0
    
    metadata = {
        "match_date": real_date,
        "match_time": match_time,
        "status": "on_sale",
        "selling_status": "on_sale",
        "league": league,
        "original_id": match_num,
        "handicap": handicap,
        "odds": odds,
        "match_uid": match_id,
    }
    
    return {
        "id": match_id,
        "sport_type": sport,
        "home_team": home_team,
        "away_team": away_team,
        "metadata": metadata,
    }

# ============ 入库 ============
def discover_and_insert(sport="football"):
    """抓取并入库"""
    client = get_client()
    matches = fetch_sporttery_matches(sport)
    new_count = 0
    update_count = 0
    
    # 获取已有比赛
    existing = client.table("matches").select("id, metadata").execute()
    existing_map = {}
    for row in existing.data:
        existing_map[row["id"]] = row
    
    for match in matches:
        match_id = match["id"]
        if match_id in existing_map:
            # 更新已有比赛
            update_match(match_id, match["metadata"])
            update_count += 1
        else:
            insert_match(match)
            new_count += 1
    
    print(f"[{sport}] 新增 {new_count} 场, 更新 {update_count} 场")
    return new_count

# ============ AI调用（从 auto_predict.py 复用逻辑）============
def normalize_ai_name(ai_name):
    return AI_NAME_MAPPING.get(ai_name, ai_name)

def call_openai_compatible(url, key, model, prompt, timeout=60):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    resp = requests.post(url, headers=headers, json=data, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def call_minimax(url, key, model, prompt, timeout=60):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    resp = requests.post(url, headers=headers, json=data, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def call_wenxin(url, key, model, prompt, timeout=60):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    resp = requests.post(url, headers=headers, json=data, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["result"]

def call_ai(ai_name, prompt, sport="football"):
    config = AI_CONFIGS[ai_name]
    if config["format"] == "template":
        return template_predict(prompt, sport)
    
    key = os.environ.get(config["key_env"])
    if not key:
        raise Exception(f"缺少环境变量 {config['key_env']}")
    
    models_to_try = [config["model"]]
    if config.get("fallback_models"):
        models_to_try.extend(config["fallback_models"])
    
    for i, model in enumerate(models_to_try):
        try:
            if config["format"] == "minimax":
                raw = call_minimax(config["url"], key, model, prompt)
            elif config["format"] == "openai":
                raw = call_openai_compatible(config["url"], key, model, prompt)
            else:
                raw = call_openai_compatible(config["url"], key, model, prompt)
            return parse_ai_response(raw, sport)
        except Exception as e:
            err = str(e).lower()
            is_rate_limit = "rate" in err or "quota" in err or "429" in err or "insufficient" in err
            if is_rate_limit and i < len(models_to_try) - 1:
                print(f"  [fallback] {ai_name} {model} 限流，切换备用模型...")
                continue
            raise

def template_predict(prompt, sport):
    """扣子模板预测"""
    return {"spf": "胜", "handicap_spf": "让胜", "score": "2-1", "goals": 3, "half_full": "胜胜", "analysis": "扣子模板预测"}

def parse_ai_response(text, sport="football"):
    """解析AI返回的JSON"""
    text = text.strip()
    # 提取JSON
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    # 尝试直接解析
    try:
        return json.loads(text)
    except:
        pass
    # 返回默认值
    if sport == "basketball":
        return {"win_loss": "胜", "handicap_win_loss": "让胜", "total_points": "大", "score_diff_range": "主6-10胜", "analysis": text[:500]}
    return {"spf": "胜", "handicap_spf": "让胜", "score": "1-0", "goals": 1, "half_full": "胜胜", "analysis": text[:500]}

# ============ Prompt构建 ============
def build_football_prompt(match):
    odds = match.get("odds", {})
    had = odds.get("had", {})
    hhad = odds.get("hhad", {})
    
    prompt = f"""请预测以下足球比赛结果：
比赛: {match['home_team']} vs {match['away_team']}
联赛: {match.get('league', '')}
时间: {match.get('match_date', '')} {match.get('match_time', '')}
让球: {hhad.get('goalLine', 'N/A')}

赔率信息:
- 胜平负(HAD): 胜{had.get('h','-')} 平{had.get('d','-')} 负{had.get('a','-')}
- 让球胜平负(HHAD): 胜{hhad.get('h','-')} 平{hhad.get('d','-')} 负{hhad.get('a','-')}

请返回JSON格式:
{{"spf": "胜/平/负", "handicap_spf": "让胜/让平/让负", "score": "X-Y", "goals": 总进球数, "half_full": "胜胜/胜平/...", "analysis": "简要分析"}}"""
    return prompt

def build_basketball_prompt(match):
    odds = match.get("odds", {})
    mnl = odds.get("mnl", {})
    hdc = odds.get("hdc", {})
    
    prompt = f"""请预测以下篮球比赛结果：
比赛: {match['home_team']} vs {match['away_team']}
联赛: {match.get('league', '')}
时间: {match.get('match_date', '')} {match.get('match_time', '')}
让分: {hdc.get('line', 'N/A')}

赔率信息:
- 胜负(MNL): 胜{mnl.get('win','-')} 负{mnl.get('lose','-')}
- 让分胜负(HDC): 胜{hdc.get('win','-')} 负{hdc.get('lose','-')}

请返回JSON格式:
{{"win_loss": "胜/负", "handicap_win_loss": "让胜/让负", "total_points": "大/小", "score_diff_range": "主X-Y胜/负", "analysis": "简要分析"}}"""
    return prompt

# ============ 分批预测 ============
def get_pending_matches_for_predict(sport="football"):
    """获取待预测的比赛（从数据库）"""
    client = get_client()
    statuses = {"on_sale", "pending", "待比赛", "未开赛"}
    result = client.table("matches").select("*").eq("sport_type", sport).execute()
    
    matches = []
    for m in result.data:
        metadata = md(m)
        status = metadata.get("status", "")
        if status not in statuses:
            continue
        odds = metadata.get("odds") or {}
        if isinstance(odds, str):
            try: odds = json.loads(odds)
            except: odds = {}
        
        match = {
            "id": m["id"],
            "home_team": m.get("home_team", ""),
            "away_team": m.get("away_team", ""),
            "match_time": metadata.get("match_time", ""),
            "match_date": metadata.get("match_date", ""),
            "handicap": metadata.get("handicap"),
            "match_uid": metadata.get("match_uid", ""),
            "league": metadata.get("league", ""),
            "odds": odds,
        }
        if sport == "basketball":
            match["spread_line"] = odds.get("hdc", {}).get("line")
        matches.append(match)
    return matches

def run_predict_batch(sport="football"):
    """分批执行AI预测，每批5场"""
    matches = get_pending_matches_for_predict(sport)
    
    if not matches:
        print(f"[{sport}] 没有待预测的比赛")
        return 0, 0
    
    total_predictions = 0
    total_errors = 0
    
    # 分批处理
    for batch_start in range(0, len(matches), BATCH_SIZE):
        batch = matches[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(matches) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"\n{'='*50}")
        print(f"[{sport}] 第 {batch_num}/{total_batches} 批 ({len(batch)}场)")
        print(f"{'='*50}")
        
        for match in batch:
            match_id = match["id"]
            existing = get_existing_predictions(match_id)
            
            if sport == "basketball":
                prompt = build_basketball_prompt(match)
            else:
                prompt = build_football_prompt(match)
            
            missing_ais = [ai for ai in AI_CONFIGS if ai not in existing]
            if not missing_ais:
                print(f"  {match_id}: 已有全部AI预测，跳过")
                continue
            
            print(f"\n  预测: {match['home_team']} vs {match['away_team']} ({match_id})")
            
            for ai_name in missing_ais:
                try:
                    result = call_ai(ai_name, prompt, sport)
                    
                    if sport == "basketball":
                        wl = result.get("win_loss", "胜")
                        if wl not in ("胜", "负"): wl = "胜"
                        hwl = result.get("handicap_win_loss", "让胜")
                        if hwl not in ("让胜", "让负"): hwl = "让胜"
                        tp = result.get("total_points", "大")
                        if tp not in ("大", "小"): tp = "大"
                        sdr = result.get("score_diff_range", "主6-10胜")
                        if not re.match(r'^(主|客)\d+[-+]\d*(胜|负)$', sdr): sdr = "主6-10胜"
                        analysis = result.get("analysis", "")[:500]
                        
                        pred = {
                            "match_id": match_id, "match_uid": match.get("match_uid", match_id),
                            "ai_name": normalize_ai_name(ai_name),
                            "win_loss": wl, "handicap_win_loss": hwl,
                            "total_points": tp, "score_diff_range": sdr, "analysis": analysis,
                        }
                        insert_basketball_prediction(pred)
                    else:
                        spf = result.get("spf", "胜")
                        if spf not in ("胜", "平", "负"): spf = "胜"
                        handicap_spf = result.get("handicap_spf", "让胜")
                        if handicap_spf not in ("让胜", "让平", "让负"): handicap_spf = "让胜"
                        score = result.get("score", "1-0")
                        if not re.match(r'^\d+-\d+$', score): score = "1-0"
                        goals = int(result.get("goals", 1))
                        half_full = result.get("half_full", "胜胜")
                        if half_full not in ("胜胜","胜平","胜负","平胜","平平","平负","负胜","负平","负负"): half_full = "胜胜"
                        analysis = result.get("analysis", "")[:500]
                        
                        pred = {
                            "match_id": match_id, "match_uid": match.get("match_uid", match_id),
                            "ai_name": normalize_ai_name(ai_name),
                            "spf": spf, "handicap_spf": handicap_spf,
                            "score": score, "goals": goals, "half_full": half_full, "analysis": analysis,
                        }
                        insert_football_prediction(pred)
                    
                    total_predictions += 1
                    print(f"    ✓ {ai_name} 完成")
                    time.sleep(1)  # 避免频率限制
                    
                except Exception as e:
                    total_errors += 1
                    print(f"    ✗ {ai_name} 失败: {str(e)[:100]}")
        
        # 批次间间隔
        if batch_start + BATCH_SIZE < len(matches):
            print(f"\n  --- 批次间休息3秒 ---")
            time.sleep(3)
    
    return total_predictions, total_errors

# ============ 主流程 ============
if __name__ == "__main__":
    print("=" * 60)
    print("比赛发现 + AI预测 批量执行")
    print(f"时间: {datetime.now()}")
    print(f"批次大小: {BATCH_SIZE}")
    print("=" * 60)
    
    # Step 1: 抓取并入库
    print("\n[Step 1] 抓取比赛数据...")
    fb_new = discover_and_insert("football")
    bb_new = discover_and_insert("basketball")
    print(f"\n入库完成: 足球新增{fb_new}场, 篮球新增{bb_new}场")
    
    # Step 2: 分批AI预测
    print("\n[Step 2] AI预测...")
    fb_pred, fb_err = run_predict_batch("football")
    bb_pred, bb_err = run_predict_batch("basketball")
    
    print(f"\n{'='*60}")
    print(f"执行完成!")
    print(f"足球: 新增{fb_new}场, 预测{fb_pred}条, 失败{fb_err}条")
    print(f"篮球: 新增{bb_new}场, 预测{bb_pred}条, 失败{bb_err}条")
    print(f"{'='*60}")
