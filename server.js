const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const cron = require('node-cron');
const { Pool } = require('pg');

// Load .env file if it exists (for local development)
try {
  const envPath = path.join(__dirname, '.env');
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    envContent.split('\n').forEach(line => {
      const match = line.match(/^([^=]+)=(.*)$/);
      if (match) {
        const key = match[1].trim();
        const value = match[2].trim().replace(/^["']|["']$/g, '');
        if (!process.env[key]) {
          process.env[key] = value;
        }
      }
    });
  }
} catch (e) {
  // Ignore errors loading .env
}

// ============ PostgreSQL Pool (for commentary writes) ============
const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres';
const pgPool = new Pool({
  connectionString: DATABASE_URL,
  ssl: DATABASE_URL ? { rejectUnauthorized: false } : false,
  max: 3,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 10000,
});
pgPool.on('error', (err) => {
  console.error('[PG Pool] Unexpected error on idle client', err.message);
});

const PORT = process.env.DEPLOY_RUN_PORT || 5000;
const HOST = '0.0.0.0';

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8',
};

// ============ Supabase API Proxy ============

function getSupabaseConfig() {
  // 优先使用 br-hip-deer 数据库（有 selling_status 列和最新数据）
  const url = process.env.SUPABASE_URL || 'https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com';
  const key = process.env.SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sashnT6QYhW2_ilgdPxAuPXwtM';
  return { url, key };
}

async function querySupabase(table, params = {}) {
  const { url, key } = getSupabaseConfig();
  if (!key) {
    console.error('Supabase anon key is not set');
    return [];
  }
  const queryStr = new URLSearchParams();
  if (params.select) queryStr.set('select', params.select);
  if (params.order) queryStr.set('order', params.order);
  if (params.limit) queryStr.set('limit', params.limit);
  if (params.filter) {
    for (const [k, v] of Object.entries(params.filter)) {
      if (Array.isArray(v)) {
        // 支持同一字段多个筛选条件（如日期范围 gte + lt）
        v.forEach(cond => queryStr.append(k, cond));
      } else {
        queryStr.set(k, v);
      }
    }
  }

  const fullUrl = `${url}/rest/v1/${table}?${queryStr}`;
  const resp = await fetch(fullUrl, {
    headers: {
      'apikey': key,
      'Authorization': `Bearer ${key}`
    }
  });

  if (!resp.ok) {
    console.error(`Supabase query failed: ${resp.status} ${resp.statusText}`);
    return [];
  }
  return resp.json();
}

// CORS headers for API responses
const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

// ============ Python Script Runner ============

function runPython(scriptName, args = []) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, 'scripts', scriptName);
    const env = { ...process.env };
    
    // 确保 DATABASE_URL 传递到 Python 进程
    if (!env.DATABASE_URL) {
      const envPath = path.join(__dirname, '.env');
      if (fs.existsSync(envPath)) {
        const envContent = fs.readFileSync(envPath, 'utf8');
        const match = envContent.match(/^DATABASE_URL=(.*)$/m);
        if (match) env.DATABASE_URL = match[1].trim().replace(/^["']|["']$/g, '');
      }
    }
    
    const child = execFile('python3', [scriptPath, ...args], {
      cwd: path.join(__dirname, 'scripts'),
      env,
      timeout: 300000, // 5分钟超时
      maxBuffer: 10 * 1024 * 1024
    }, (error, stdout, stderr) => {
      if (error) {
        console.error(`[Python ${scriptName}] Error:`, error.message);
        if (stderr) console.error(`[Python ${scriptName}] Stderr:`, stderr);
        reject(new Error(stderr || error.message));
        return;
      }
      if (stderr) console.warn(`[Python ${scriptName}] Stderr:`, stderr);
      try {
        resolve(JSON.parse(stdout.trim()));
      } catch {
        resolve({ output: stdout.trim() });
      }
    });
  });
}

// 任务执行状态追踪
const taskStatus = {
  discover: { running: false, lastRun: null, lastResult: null },
  predict: { running: false, lastRun: null, lastResult: null },
  settle: { running: false, lastRun: null, lastResult: null },
  report: { running: false, lastRun: null, lastResult: null }
};

// 调度报告生成
const REPORT_PATH = '/tmp/dispatch_report.md';

async function generateReport() {
  taskStatus.report.running = true;
  try {
    const result = await runPython('dispatch_report.py');
    taskStatus.report.lastRun = new Date().toISOString();
    taskStatus.report.lastResult = result;
    
    if (result.status === 'ANOMALY') {
      console.error(`[Report] ⚠️ 发现 ${result.anomaly_count} 项异常:`, result.anomalies);
    } else if (result.status === 'OK') {
      console.log(`[Report] ✅ 系统正常 | ${result.total_matches}场比赛 | ${result.on_sale}场在售 | 0异常`);
    }
    return result;
  } catch (err) {
    console.error('[Report] 报告生成失败:', err.message);
    taskStatus.report.lastRun = new Date().toISOString();
    taskStatus.report.lastResult = { status: 'ERROR', error: err.message };
    return { status: 'ERROR', error: err.message };
  } finally {
    taskStatus.report.running = false;
  }
}

// ============ Daily Commentary Generator ============
// 每场比赛单独生成综合评论，基于7个AI的预测数据
// 风格：犀利、口语化，像懂球老友在微信群聊球

const DOUBAO_API_URL = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions';
const DOUBAO_API_KEY = 'ark-e27a1337-a759-46fb-b30c-efe5ce5541bd-2a204';
const DOUBAO_MODEL = 'ep-20260706041055-2mgpf';

let commentaryRunning = false;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// 调用豆包API生成评论，带3次重试
async function callDoubaoCommentary(prompt) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const resp = await fetch(DOUBAO_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${DOUBAO_API_KEY}`
        },
        body: JSON.stringify({
          model: DOUBAO_MODEL,
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.85,
          max_tokens: 600
        })
      });
      if (!resp.ok) {
        const errText = await resp.text();
        console.error(`[Commentary] Doubao API ${resp.status} (attempt ${attempt}): ${errText.slice(0, 200)}`);
        if (attempt < 3) { await sleep(3000 * attempt); continue; }
        throw new Error(`Doubao API ${resp.status}: ${errText.slice(0, 200)}`);
      }
      const data = await resp.json();
      return data.choices[0].message.content.trim();
    } catch (err) {
      if (attempt < 3) { await sleep(3000 * attempt); continue; }
      throw err;
    }
  }
}

// 构建每场比赛的评论prompt
function buildMatchCommentaryPrompt(match, preds) {
  const isFootball = (match.sport_type || 'football') === 'football';
  const teams = match.teams || '';
  const vsIdx = teams.indexOf('VS');
  const home = vsIdx > 0 ? teams.substring(0, vsIdx) : teams;
  const away = vsIdx > 0 ? teams.substring(vsIdx + 2) : '';
  const league = (match.metadata && match.metadata.league) || '';

  // 统计AI预测分布
  const spfCounts = {};
  preds.forEach(p => {
    const k = p.spf || '未预测';
    spfCounts[k] = (spfCounts[k] || 0) + 1;
  });
  const total = preds.length;
  const sorted = Object.entries(spfCounts).sort((a, b) => b[1] - a[1]);
  const consensus = sorted[0]; // [pick, count]
  const consensusPct = Math.round(consensus[1] / total * 100);

  // 找出唱反调的AI
  const dissenters = preds.filter(p => (p.spf || '未预测') !== consensus[0]);
  let dissenterInfo = '';
  if (dissenters.length > 0) {
    dissenterInfo = dissenters.map(p => {
      let s = `${p.ai_name}选了"${p.spf || '?'}"`;
      if (p.analysis) s += `，理由: ${p.analysis.replace(/\n/g, ' ').slice(0, 80)}`;
      return s;
    }).join('\n');
  }

  // 每个AI的预测详情
  const predDetail = preds.map(p => {
    let s = `${p.ai_name}: ${isFootball ? '胜平负=' : '主客='}${p.spf || '?'}`;
    if (p.handicap_spf) s += `, 让球=${p.handicap_spf}`;
    if (p.score) s += `, 比分=${p.score}`;
    if (p.analysis) s += ` | ${p.analysis.replace(/\n/g, ' ').slice(0, 100)}`;
    return s;
  }).join('\n');

  // 赔率行
  const oddsLine = isFootball
    ? `胜${match.win_odds || '?'} / 平${match.draw_odds || '?'} / 负${match.lose_odds || '?'}`
    : `主胜${match.win_odds || '?'} / 客胜${match.lose_odds || '?'}`;

  const sportLabel = isFootball ? '足球' : '篮球';

  return `你是逐浪AI实验室的${sportLabel}评论员，风格犀利、口语化，像懂球老友在微信群聊球。

## 比赛信息
- 联赛: ${league} | 对阵: ${home} VS ${away}
- 让球: ${match.handicap || '无'}
- 赔率: ${oddsLine}

## ${total}个AI的预测
${predDetail}

## 预测共识
${consensusPct}%的AI（${consensus[1]}/${total}）看好"${consensus[0]}"
${dissenters.length > 0 ? `唱反调的:\n${dissenterInfo}` : '全部一致，没有任何分歧'}

请生成150-250字的综合评论，要求:
1. 犀利、口语化，像微信群里跟朋友聊这场球
2. 重点说AI的共识和分歧: 谁看好谁、为什么有分歧、谁在唱反调
3. 有自己的判断和观点，别只复述数据
4. 严禁"投注""盘口""押注""竞彩"等词
5. 用中文双引号""
6. 纯文字输出，不用markdown格式`;
}

// 更新比赛metadata，写入daily_commentary
async function updateMatchCommentary(matchId, commentary) {
  const date = new Date().toISOString().split('T')[0];
  const client = await pgPool.connect();
  try {
    await client.query(
      `UPDATE matches SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('daily_commentary', $1::text, 'commentary_date', $2::text, 'commentary_version', 2) WHERE id = $3`,
      [commentary, date, matchId]
    );
  } finally {
    client.release();
  }
}

// 主函数：检查并生成缺少评论的比赛评论
async function checkAndGenerateCommentary() {
  if (commentaryRunning) {
    console.log('[Commentary] 上次评论生成仍在运行，跳过');
    return;
  }
  commentaryRunning = true;

  try {
    // 日期范围：今天00:00 到 后天00:00（覆盖今天+明天的比赛）
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const dayAfter = new Date(today);
    dayAfter.setDate(dayAfter.getDate() + 2);

    const from = today.toISOString().split('T')[0] + 'T00:00:00';
    const to = dayAfter.toISOString().split('T')[0] + 'T00:00:00';

    console.log(`[Commentary] 检查 ${from} ~ ${to} 的比赛评论...`);

    // 查询今天+明天的比赛
    const matches = await querySupabase('matches', {
      select: '*',
      order: 'match_time.asc',
      limit: '5000',
      filter: { match_time: [`gte.${from}`, `lt.${to}`] }
    });

    if (matches.length === 0) {
      console.log('[Commentary] 没有找到比赛');
      return;
    }

    // 筛选出缺少评论的比赛
    const needCommentary = matches.filter(m => !m.metadata || !m.metadata.daily_commentary || m.metadata.commentary_version !== 2);

    if (needCommentary.length === 0) {
      console.log(`[Commentary] ${matches.length}场比赛都已有v2评论，无需生成`);
      return;
    }

    console.log(`[Commentary] ${matches.length}场比赛中有${needCommentary.length}场缺少评论`);

    // 获取所有预测数据（分页，绕过Supabase 1000条限制）
    let allPreds = [];
    let offset = 0;
    const limit = 1000;
    while (true) {
      const { url, key } = getSupabaseConfig();
      const resp = await fetch(
        `${url}/rest/v1/predictions?select=*&order=id.desc&limit=${limit}&offset=${offset}`,
        { headers: { apikey: key, Authorization: `Bearer ${key}` } }
      );
      const batch = await resp.json();
      allPreds = allPreds.concat(batch);
      if (batch.length < limit) break;
      offset += limit;
    }

    // 逐场生成评论
    let generated = 0, skipped = 0, failed = 0;

    for (const match of needCommentary) {
      try {
        const preds = allPreds.filter(p => p.match_id === match.id);

        if (preds.length === 0) {
          skipped++;
          console.log(`[Commentary] ⏭ ${match.id} ${match.teams} 无AI预测，跳过`);
          continue;
        }

        console.log(`[Commentary] 生成中: ${match.id} ${match.teams} (${preds.length}个AI预测)`);

        const prompt = buildMatchCommentaryPrompt(match, preds);
        const commentary = await callDoubaoCommentary(prompt);

        await updateMatchCommentary(match.id, commentary);

        generated++;
        console.log(`[Commentary] ✅ ${match.id} ${match.teams} 评论已生成 (${commentary.length}字)`);

        // 控制API调用频率，避免触发限流
        await sleep(2000);

      } catch (err) {
        failed++;
        console.error(`[Commentary] ❌ ${match.id} ${match.teams} 生成失败: ${err.message}`);
        // 失败后多等一会儿
        await sleep(5000);
      }
    }

    console.log(`[Commentary] 批次完成: 生成${generated}条, 跳过${skipped}条, 失败${failed}条`);

  } catch (err) {
    console.error('[Commentary] 检查失败:', err.message);
  } finally {
    commentaryRunning = false;
  }
}

// ============ Server ============

const server = http.createServer(async (req, res) => {
  // Parse URL
  const parsedUrl = new URL(req.url, `http://${HOST}:${PORT}`);
  const pathname = parsedUrl.pathname;

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS_HEADERS);
    res.end();
    return;
  }

  // 清洗analysis字段的JSON泄露
  function cleanAnalysis(text) {
    if (!text) return '';
    const jsonPats = [/"spf"\s*:/, /"handicap_spf"\s*:/, /"score"\s*:/,
                      /"win_loss"\s*:/, /"handicap_win_loss"\s*:/,
                      /"half_full"\s*:/, /"confidence"\s*:/,
                      /"market_deviation"\s*:/, /"score_diff_range"\s*:/,
                      /"total_points"\s*:/, /"cold_warning"\s*:/];
    const leakCount = jsonPats.filter(p => p.test(text)).length;
    if (leakCount >= 3) return '';
    text = text.replace(/```(?:json)?\s*[\s\S]*?```/g, '');
    return text.trim();
  }

  // ============ API Routes (before static files) ============

  try {
    // GET /api/matches
    if (pathname === '/api/matches' && req.method === 'GET') {
      const filter = {};

      // 日期筛选：格式 YYYY-MM-DD，按 match_time 的日期部分筛选
      const date = parsedUrl.searchParams.get('date');
      if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
        // 计算下一天（避免时区问题，直接操作日期字符串）
        const [year, month, day] = date.split('-').map(Number);
        const d = new Date(year, month - 1, day);
        d.setDate(d.getDate() + 1);
        const nextDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        // match_time >= dateT00:00:00 AND match_time < nextDateT00:00:00
        filter.match_time = [`gte.${date}T00:00:00`, `lt.${nextDate}T00:00:00`];
      }

      // 运动类型筛选：?sport=football 或 ?sport=basketball
      const sport = parsedUrl.searchParams.get('sport');
      if (sport && (sport === 'football' || sport === 'basketball')) {
        filter.sport_type = `eq.${sport}`;
      }

      const data = await querySupabase('matches', {
        select: '*',
        order: 'match_time.asc',
        limit: '5000',
        filter
      });
      // 提取 metadata.league 作为 league_name
      const enriched = data.map(m => ({
        ...m,
        league_name: (m.metadata && m.metadata.league) || ''
      }));
      // 时间已过但未开赛的比赛，自动标记为已开赛
      const now = new Date();
      enriched.forEach(m => {
        if (new Date(m.match_time) < now && m.status === '未开赛') {
          m.status = '已开赛';
        }
      });
      res.writeHead(200, { 
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
        ...CORS_HEADERS 
      });
      res.end(JSON.stringify(enriched));
      return;
    }

    // GET /api/date-tabs - 获取日期标签（7个，当天在中间）
    if (pathname === '/api/date-tabs' && req.method === 'GET') {
      const today = new Date();
      const tabs = [];
      
      for (let i = -3; i <= 3; i++) {
        const date = new Date(today);
        date.setDate(today.getDate() + i);
        const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
        const displayStr = `${date.getMonth() + 1}月${date.getDate()}日`;
        
        tabs.push({
          date: dateStr,
          display: displayStr,
          isToday: i === 0
        });
      }
      
      const todayTab = tabs.find(t => t.isToday);
      res.writeHead(200, { 
        'Content-Type': 'application/json',
        ...CORS_HEADERS 
      });
      res.end(JSON.stringify({
        tabs: tabs,
        defaultDate: todayTab ? todayTab.date : tabs[3].date
      }));
      return;
    }

    // GET /api/predictions - 分页获取全部预测（绕过Supabase 1000条限制）
    if (pathname === '/api/predictions' && req.method === 'GET') {
      let allData = [];
      let offset = 0;
      const limit = 1000;
      // 运动类型筛选
      const sport = parsedUrl.searchParams.get('sport');
      const sportFilter = (sport && (sport === 'football' || sport === 'basketball'))
        ? `&sport_type=eq.${sport}` : '';
      while (true) {
        const { url, key } = getSupabaseConfig();
        const resp = await fetch(
          `${url}/rest/v1/predictions?select=*&order=id.desc&limit=${limit}&offset=${offset}${sportFilter}`,
          { headers: { apikey: key, Authorization: 'Bearer ' + key } }
        );
        const batch = await resp.json();
        allData = allData.concat(batch);
        if (batch.length < limit) break;
        offset += limit;
      }
      
      // 清洗analysis字段的JSON泄露
      allData = allData.map(p => ({ ...p, analysis: cleanAnalysis(p.analysis) }));
      
      res.writeHead(200, { 
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
        ...CORS_HEADERS 
      });
      res.end(JSON.stringify(allData));
      return;
    }

    // GET /api/chain_bets
    if (pathname === '/api/chain_bets' && req.method === 'GET') {
      const data = await querySupabase('chain_bets', {
        select: '*',
        order: 'bet_date.desc,ai_name.asc'
      });
      res.writeHead(200, { 
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
        ...CORS_HEADERS 
      });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/ai_stats
    if (pathname === '/api/ai_stats' && req.method === 'GET') {
      const filter = {};
      // 运动类型筛选：?sport=football 或 ?sport=basketball，默认football（向后兼容）
      const sport = parsedUrl.searchParams.get('sport');
      if (sport && (sport === 'football' || sport === 'basketball')) {
        filter.sport_type = `eq.${sport}`;
      } else {
        // 默认只返回football，避免重复
        filter.sport_type = 'eq.football';
      }
      // 默认只返回活跃AI
      const active = parsedUrl.searchParams.get('active');
      if (active !== 'false') {
        filter.is_active = 'eq.true';
      }
      const data = await querySupabase('ai_stats', {
        select: '*',
        order: 'rank.asc',
        filter
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/betting_daily
    if (pathname === '/api/betting_daily' && req.method === 'GET') {
      const filter = {};
      // 运动类型筛选：?sport=football 或 ?sport=basketball
      const sport = parsedUrl.searchParams.get('sport');
      if (sport && (sport === 'football' || sport === 'basketball')) {
        filter.sport_type = `eq.${sport}`;
      }
      const data = await querySupabase('betting_daily', {
        select: '*',
        order: 'match_date.desc',
        filter
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/betting_summary
    if (pathname === '/api/betting_summary' && req.method === 'GET') {
      const filter = {};
      // 运动类型筛选：?sport=football 或 ?sport=basketball
      const sport = parsedUrl.searchParams.get('sport');
      if (sport && (sport === 'football' || sport === 'basketball')) {
        filter.sport_type = `eq.${sport}`;
      }
      const data = await querySupabase('betting_summary', {
        select: '*',
        order: 'rank.asc',
        filter
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/briefs
    if (pathname === '/api/briefs' && req.method === 'GET') {
      const data = await querySupabase('briefs', {
        select: '*',
        order: 'date.desc'
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // ============ New API Routes for AI Analysis Page ============

    // GET /api/football-recent - Latest date's matches + predictions
    if (pathname === '/api/football-recent' && req.method === 'GET') {
      // Get the latest match date
      const matches = await querySupabase('matches', {
        select: '*',
        order: 'match_time.desc',
        limit: '500'
      });
      if (matches.length === 0) {
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ date: null, matches: [], predictions: [] }));
        return;
      }
      // Extract date from match_time (format: "2025-06-30T12:00:00" or similar)
      const getDateFromMatchTime = (matchTime) => {
        if (!matchTime) return null;
        return matchTime.substring(0, 10); // Get "YYYY-MM-DD" part
      };
      const latestDate = getDateFromMatchTime(matches[0].match_time);
      const recentMatches = matches.filter(m => getDateFromMatchTime(m.match_time) === latestDate);
      const matchIds = new Set(recentMatches.map(m => m.id));
      
      // Get predictions for these matches
      const allPredictions = await querySupabase('predictions', {
        select: '*',
        order: 'id.desc',
        limit: '5000'
      });
      const recentPredictions = allPredictions.filter(p => matchIds.has(p.match_id))
        .map(p => ({ ...p, analysis: cleanAnalysis(p.analysis) }));
      
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ date: latestDate, matches: recentMatches, predictions: recentPredictions }));
      return;
    }

    // GET /api/football-history - Historical dates' matches + predictions
    if (pathname === '/api/football-history' && req.method === 'GET') {
      const matches = await querySupabase('matches', {
        select: '*',
        order: 'match_time.desc',
        limit: '5000'
      });
      const allPredictions = await querySupabase('predictions', {
        select: '*',
        order: 'id.desc',
        limit: '5000'
      });
      
      // Extract date from match_time
      const getDateFromMatchTime = (matchTime) => {
        if (!matchTime) return null;
        return matchTime.substring(0, 10); // Get "YYYY-MM-DD" part
      };
      
      // Group by date
      const byDate = {};
      for (const m of matches) {
        const date = getDateFromMatchTime(m.match_time);
        if (!date) continue;
        if (!byDate[date]) byDate[date] = [];
        byDate[date].push(m);
      }
      
      // Get all dates except the latest
      const dates = Object.keys(byDate).sort().reverse();
      const latestDate = dates[0];
      const historyDates = dates.slice(1);
      
      const result = historyDates.map(date => ({
        date,
        matches: byDate[date],
        predictions: allPredictions.filter(p => byDate[date].some(m => m.id === p.match_id))
          .map(p => ({ ...p, analysis: cleanAnalysis(p.analysis) }))
      }));
      
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(result));
      return;
    }

    // ============ Admin API Routes (Python Pipeline Triggers) ============

    // POST /api/admin/discover - 触发比赛发现+赔率抓取
    if (pathname === '/api/admin/discover' && req.method === 'POST') {
      if (taskStatus.discover.running) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'discover任务正在运行中' }));
        return;
      }
      taskStatus.discover.running = true;
      try {
        const result = await runPython('discover_matches.py');
        taskStatus.discover.lastRun = new Date().toISOString();
        taskStatus.discover.lastResult = result;
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ success: true, data: result }));
      } catch (err) {
        taskStatus.discover.lastRun = new Date().toISOString();
        taskStatus.discover.lastResult = { error: err.message };
        res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: err.message }));
      } finally {
        taskStatus.discover.running = false;
      }
      return;
    }

    // POST /api/admin/predict - 触发AI预测
    if (pathname === '/api/admin/predict' && req.method === 'POST') {
      if (taskStatus.predict.running) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'predict任务正在运行中' }));
        return;
      }
      taskStatus.predict.running = true;
      try {
        const result = await runPython('auto_predict.py');
        taskStatus.predict.lastRun = new Date().toISOString();
        taskStatus.predict.lastResult = result;
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ success: true, data: result }));
      } catch (err) {
        taskStatus.predict.lastRun = new Date().toISOString();
        taskStatus.predict.lastResult = { error: err.message };
        res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: err.message }));
      } finally {
        taskStatus.predict.running = false;
      }
      return;
    }

    // POST /api/admin/settle - 触发自动结算
    if (pathname === '/api/admin/settle' && req.method === 'POST') {
      if (taskStatus.settle.running) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'settle任务正在运行中' }));
        return;
      }
      taskStatus.settle.running = true;
      try {
        const result = await runPython('auto_settle.py');
        taskStatus.settle.lastRun = new Date().toISOString();
        taskStatus.settle.lastResult = result;
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ success: true, data: result }));
      } catch (err) {
        taskStatus.settle.lastRun = new Date().toISOString();
        taskStatus.settle.lastResult = { error: err.message };
        res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: err.message }));
      } finally {
        taskStatus.settle.running = false;
      }
      return;
    }

    // GET /api/admin/status - 查看任务状态
    if (pathname === '/api/admin/status' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(taskStatus));
      return;
    }

    // GET /api/admin/report - 读取调度报告 (Markdown)
    if (pathname === '/api/admin/report' && req.method === 'GET') {
      try {
        const report = fs.readFileSync(REPORT_PATH, 'utf-8');
        res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', ...CORS_HEADERS });
        res.end(report);
      } catch (err) {
        res.writeHead(404, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: '报告文件不存在，请先运行调度任务' }));
      }
      return;
    }

    // POST /api/admin/report - 手动触发报告生成
    if (pathname === '/api/admin/report' && req.method === 'POST') {
      const result = await generateReport();
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(result));
      return;
    }

    // POST /api/admin/commentary - 手动触发评论生成
    if (pathname === '/api/admin/commentary' && req.method === 'POST') {
      if (commentaryRunning) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: '评论生成正在运行中' }));
        return;
      }
      // 异步触发，立即返回
      checkAndGenerateCommentary();
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ success: true, message: '评论生成已触发' }));
      return;
    }

    // GET /api/parlay-latest - Latest date's chain_bets
    if (pathname === '/api/parlay-latest' && req.method === 'GET') {
      const chainBets = await querySupabase('chain_bets', {
        select: '*',
        order: 'bet_date.desc,ai_name.asc'
      });
      if (chainBets.length === 0) {
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ date: null, records: [] }));
        return;
      }
      const latestDate = chainBets[0].bet_date;
      const latestRecords = chainBets.filter(r => r.bet_date === latestDate);
      
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ date: latestDate, records: latestRecords }));
      return;
    }

    // GET /api/parlay-history - Historical chain_bets
    if (pathname === '/api/parlay-history' && req.method === 'GET') {
      const chainBets = await querySupabase('chain_bets', {
        select: '*',
        order: 'bet_date.desc,ai_name.asc'
      });
      
      // Group by date
      const byDate = {};
      for (const r of chainBets) {
        if (!byDate[r.bet_date]) byDate[r.bet_date] = [];
        byDate[r.bet_date].push(r);
      }
      
      // Get all dates except the latest
      const dates = Object.keys(byDate).sort().reverse();
      const latestDate = dates[0];
      const historyDates = dates.slice(1);
      
      const result = historyDates.map(date => ({
        date,
        records: byDate[date]
      }));
      
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(result));
      return;
    }
  } catch (err) {
    console.error('API error:', err);
    res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
    res.end(JSON.stringify({ error: 'Internal server error' }));
    return;
  }

  // ============ Static File Routes ============

  let urlPath = pathname;
  if (urlPath === '/') urlPath = '/index.html';

  // Security: prevent directory traversal
  const safePath = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, '');
  const filePath = path.join(process.cwd(), safePath);

  // Check if file exists
  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      // SPA fallback: serve index.html for all non-file routes
      const indexPath = path.join(process.cwd(), 'index.html');
      fs.readFile(indexPath, (err2, data) => {
        if (err2) {
          res.writeHead(404, { 'Content-Type': 'text/plain' });
          res.end('404 Not Found');
          return;
        }
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(data);
      });
      return;
    }

    // Serve the file
    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    // Add cache-busting headers for HTML files to prevent browser caching
    const headers = { 'Content-Type': contentType };
    if (ext === '.html') {
      headers['Cache-Control'] = 'no-cache, no-store, must-revalidate';
      headers['Pragma'] = 'no-cache';
      headers['Expires'] = '0';
    }

    const stream = fs.createReadStream(filePath);
    res.writeHead(200, headers);
    stream.pipe(res);
    stream.on('error', () => {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end('500 Internal Server Error');
    });
  });
});

server.listen(PORT, HOST, () => {
  console.log(`Server running at http://${HOST}:${PORT}/`);
  console.log(`Supabase URL: ${getSupabaseConfig().url}`); console.log(`Supabase Key: ${getSupabaseConfig().key ? getSupabaseConfig().key.substring(0, 20) + '...' : 'not set'}`);
  console.log(`API endpoints: /api/matches, /api/predictions, /api/chain_bets, /api/ai_stats, /api/betting_daily, /api/betting_summary, /api/briefs`);
  console.log(`Admin endpoints: POST /api/admin/discover, POST /api/admin/predict, POST /api/admin/settle, GET /api/admin/status, GET|POST /api/admin/report, POST /api/admin/commentary`);
});

// ============ Cron Jobs (Asia/Shanghai) ============

// 每天 11:00 增量调度：发现比赛 + 补赔率 + AI预测
cron.schedule('0 11 * * *', async () => {
  console.log('[Cron 11:00] 开始增量调度: discover + predict');
  try {
    const discoverResult = await runPython('discover_matches.py');
    console.log('[Cron 11:00] discover完成:', JSON.stringify(discoverResult));
    taskStatus.discover.lastRun = new Date().toISOString();
    taskStatus.discover.lastResult = discoverResult;
  } catch (err) {
    console.error('[Cron 11:00] discover失败:', err.message);
  }
  try {
    const predictResult = await runPython('auto_predict.py');
    console.log('[Cron 11:00] predict完成:', JSON.stringify(predictResult));
    taskStatus.predict.lastRun = new Date().toISOString();
    taskStatus.predict.lastResult = predictResult;
  } catch (err) {
    console.error('[Cron 11:00] predict失败:', err.message);
  }
  // 调度完成后生成报告
  await generateReport();
}, { timezone: 'Asia/Shanghai' });

// 每天 21:30 主力调度：发现比赛 + AI预测
cron.schedule('30 21 * * *', async () => {
  console.log('[Cron 21:30] 开始主力调度: discover + predict');
  try {
    const discoverResult = await runPython('discover_matches.py');
    console.log('[Cron 21:30] discover完成:', JSON.stringify(discoverResult));
    taskStatus.discover.lastRun = new Date().toISOString();
    taskStatus.discover.lastResult = discoverResult;
  } catch (err) {
    console.error('[Cron 21:30] discover失败:', err.message);
  }
  try {
    const predictResult = await runPython('auto_predict.py');
    console.log('[Cron 21:30] predict完成:', JSON.stringify(predictResult));
    taskStatus.predict.lastRun = new Date().toISOString();
    taskStatus.predict.lastResult = predictResult;
  } catch (err) {
    console.error('[Cron 21:30] predict失败:', err.message);
  }
  // 调度完成后生成报告
  await generateReport();
}, { timezone: 'Asia/Shanghai' });

// ============ 自动结算（每5分钟扫描，开赛3小时后自动结算） ============
const SETTLE_INTERVAL_MS = 5 * 60 * 1000; // 5分钟

async function autoSettle() {
  if (taskStatus.settle.running) {
    console.log('[AutoSettle] 上一次结算仍在运行，跳过');
    return;
  }
  taskStatus.settle.running = true;
  console.log('[AutoSettle] 开始扫描待结算比赛...');
  try {
    const settleResult = await runPython('auto_settle.py');
    console.log('[AutoSettle] 完成:', JSON.stringify(settleResult));
    taskStatus.settle.lastRun = new Date().toISOString();
    taskStatus.settle.lastResult = settleResult;
    if (settleResult && settleResult.settled > 0) {
      await generateReport();
    }
  } catch (err) {
    console.error('[AutoSettle] 失败:', err.message);
  } finally {
    taskStatus.settle.running = false;
  }
}

setTimeout(() => {
  console.log('[AutoSettle] 首次结算检查...');
  autoSettle();
  setInterval(autoSettle, SETTLE_INTERVAL_MS);
  console.log(`[AutoSettle] 定时结算已启动，间隔 ${SETTLE_INTERVAL_MS / 1000} 秒`);
}, 30000);

console.log('[Cron] 定时任务已注册: 11:00 增量调度 | 21:30 主力调度 (Asia/Shanghai)');
console.log('[AutoSettle] 自动结算: 每5分钟扫描，开赛3小时后自动结算');
console.log('[Cron] 每次调度完成后自动生成调度报告 → /tmp/dispatch_report.md');

// ============ Commentary Auto-Check (每小时检查一次，启动时也检查) ============
const COMMENTARY_CHECK_INTERVAL_MS = 60 * 60 * 1000; // 1小时

setTimeout(() => {
  console.log('[Commentary] 首次评论检查（延迟60秒，等待数据就绪）...');
  checkAndGenerateCommentary();
  setInterval(checkAndGenerateCommentary, COMMENTARY_CHECK_INTERVAL_MS);
  console.log(`[Commentary] 评论自动检查已启动，间隔 ${COMMENTARY_CHECK_INTERVAL_MS / 1000} 秒`);
}, 60000); // 延迟60秒启动，给discover/predict流水线时间先跑

console.log('[Commentary] 评论自动生成: 启动时+每小时检查，覆盖今天+明天比赛');
