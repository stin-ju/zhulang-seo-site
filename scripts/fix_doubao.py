import os, json, time, re, requests
from datetime import datetime

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')
DOUBAO_API_KEY = os.environ.get('DOUBAO_API_KEY')
DOUBAO_BASE = 'https://ark.cn-beijing.volces.com/api/v3'
HEADERS = {'Authorization': f'Bearer {DOUBAO_API_KEY}', 'Content-Type': 'application/json'}
DB_HEAD = {'apikey': SUPABASE_ANON_KEY, 'Authorization': f'Bearer {SUPABASE_ANON_KEY}'}

MATCHES = [
    '20260718_周五205', '20260718_周五208', '20260718_周五302',
    '20260718_周五303', '20260718_周五304', '20260718_周六201',
    '20260718_周六202', '20260718_周六203', '20260718_周六204',
    '20260719_周六103', '20260719_周日201', '20260719_周日202'
]

def get_match(mid):
    r = requests.get(f'{SUPABASE_URL}/rest/v1/matches?id=eq.{mid}&select=*', headers=DB_HEAD, timeout=15)
    return r.json()[0] if r.status_code == 200 and r.json() else None

def get_other_preds(mid):
    r = requests.get(f'{SUPABASE_URL}/rest/v1/predictions?match_id=eq.{mid}&ai_name=neq.AI-豆包&select=*', headers=DB_HEAD, timeout=15)
    return r.json() if r.status_code == 200 else []

def build_prompt(md, others, sport):
    meta = md.get('metadata', {}) or {}
    odds = meta.get('odds', {}) or {}
    hc = meta.get('handicap', 0)
    home, away = md.get('home_team', ''), md.get('away_team', '')
    ctx = ''
    for p in others:
        pred = p.get('prediction', {}) or {}
        if isinstance(pred, str):
            try: pred = json.loads(pred.replace("'", '"'))
            except: continue
        if sport == 'football':
            ctx += f"{p['ai_name']}: SPF={pred.get('spf','')},让球={pred.get('handicap_spf','')},比分={pred.get('score','')},进球={pred.get('goals','')},半全场={pred.get('half_full','')}\n"
        else:
            ctx += f"{p['ai_name']}: 胜负={pred.get('win_loss','')},让分={pred.get('handicap_win_loss','')},大小分={pred.get('total_points','')},胜分差={pred.get('score_diff','')}\n"
    if sport == 'football':
        return f'专业足球分析师预测：\n{home} vs {away}\n让球:{hc}\n赔率:{json.dumps(odds,ensure_ascii=False)}\n参考:\n{ctx}\nJSON回复:\n{{"spf":"胜/平/负","handicap_spf":"胜/平/负","score":"如2:1","goals":"2/3/4/5/6","half_full":"胜胜/平胜/...","analysis":"50字内"}}'
    else:
        return f'专业篮球分析师预测：\n{home} vs {away}\n让分:{hc}\n赔率:{json.dumps(odds,ensure_ascii=False)}\n参考:\n{ctx}\nJSON回复:\n{{"win_loss":"胜/负","handicap_win_loss":"胜/负","total_points":"大/小","score_diff":"如1-5","analysis":"50字内"}}'

def call_doubao(prompt):
    for model in ['doubao-seed-evolving', 'doubao-seed-2-1-turbo-260628', 'doubao-seed-2-0-mini-260428']:
        t = time.time()
        try:
            r = requests.post(f'{DOUBAO_BASE}/chat/completions', headers=HEADERS, timeout=90,
                json={'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.7, 'max_tokens': 1024})
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content'], time.time() - t
            print(f'  {model}: {r.status_code} ({time.time()-t:.0f}s)')
        except Exception as e:
            print(f'  {model}: {str(e)[:50]} ({time.time()-t:.0f}s)')
    return None, 0

def parse_json(s):
    s = s.strip()
    for pat in [r'```json\s*(.*?)\s*```', r'```\s*(.*?)\s*```']:
        m = re.search(pat, s, re.DOTALL)
        if m:
            try: return json.loads(m.group(1))
            except: pass
    m = re.search(r'\{.*\}', s, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except: pass
    try: return json.loads(s)
    except: return None

def upsert_pred(mid, sport, pred, analysis):
    data = {'prediction': pred, 'analysis': analysis}
    if sport == 'football':
        for k in ['spf', 'handicap_spf', 'goals', 'score', 'half_full']:
            data[k] = pred.get(k)
    else:
        data['win_loss'] = pred.get('win_loss')
        data['handicap_win_loss'] = pred.get('handicap_win_loss')
        data['total_points'] = pred.get('total_points')
        data['score_diff_range'] = pred.get('score_diff')
        data['score_diff'] = pred.get('score_diff')
    # 先查是否存在
    r = requests.get(f'{SUPABASE_URL}/rest/v1/predictions?match_id=eq.{mid}&ai_name=eq.AI-豆包&select=id', headers=DB_HEAD, timeout=15)
    if r.status_code == 200 and r.json():
        eid = r.json()[0]['id']
        r2 = requests.patch(f'{SUPABASE_URL}/rest/v1/predictions?id=eq.{eid}',
            headers={**DB_HEAD, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}, json=data, timeout=15)
    else:
        r2 = requests.post(f'{SUPABASE_URL}/rest/v1/predictions',
            headers={**DB_HEAD, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
            json={'match_id': mid, 'ai_name': 'AI-豆包', 'sport_type': sport, **data}, timeout=15)
    return r2.status_code in [200, 201, 204]

print(f'=== 豆包补全开始 {datetime.now().strftime("%H:%M:%S")} ===')
ok, fail = 0, 0
for i, mid in enumerate(MATCHES):
    print(f'[{i+1}/12] {mid}', end=' ')
    md = get_match(mid)
    if not md:
        print('无数据'); fail += 1; continue
    sport = md.get('sport_type', 'football')
    others = get_other_preds(mid)
    prompt = build_prompt(md, others, sport)
    content, elapsed = call_doubao(prompt)
    if not content:
        print(f'全部失败'); fail += 1; continue
    pred = parse_json(content)
    if not pred:
        print(f'解析失败'); fail += 1; continue
    ana = pred.pop('analysis', '')
    if upsert_pred(mid, sport, pred, ana):
        print(f'OK ({elapsed:.1f}s)')
        ok += 1
    else:
        print(f'写入失败'); fail += 1
    time.sleep(1)
print(f'\n=== 完成: 成功{ok} 失败{fail} ===')
