const http = require('http');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { execFile } = require('child_process');
const { Pool } = require('pg');

// ============ Database Connection ============
const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres';
const pgPool = new Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  max: 10,
  idleTimeoutMillis: 60000,
  connectionTimeoutMillis: 15000,
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

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

// 发送 JSON 响应（支持 gzip 压缩，解决 CDN 响应大小限制）
const RESPONSE_VERSION = 'v20260901c'; // 用于缓存失效 v3
function sendJsonResponse(req, res, data, statusCode = 200) {
  const json = JSON.stringify(data);
  const acceptEncoding = req.headers['accept-encoding'] || '';
  const baseHeaders = {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
    'Pragma': 'no-cache',
    'Expires': '0',
    'X-Response-Version': RESPONSE_VERSION,
    'Vary': 'Accept-Encoding, Cookie, X-Request-Id',
    ...CORS_HEADERS
  };
  
  if (acceptEncoding.includes('gzip') && json.length > 1024) {
    zlib.gzip(Buffer.from(json, 'utf8'), (err, compressed) => {
      if (err) {
        res.writeHead(statusCode, { ...baseHeaders, 'Content-Length': Buffer.byteLength(json) });
        res.end(json);
        return;
      }
      res.writeHead(statusCode, { ...baseHeaders, 'Content-Encoding': 'gzip', 'Content-Length': compressed.length });
      res.end(compressed);
    });
  } else {
    res.writeHead(statusCode, { ...baseHeaders, 'Content-Length': Buffer.byteLength(json) });
    res.end(json);
  }
}

// ============ Task Status Tracking ============
const taskStatus = {
  discover: { running: false, lastRun: null, lastResult: null },
  predict: { running: false, lastRun: null, lastResult: null },
  settle: { running: false, lastRun: null, lastResult: null },
  report: { running: false, lastRun: null, lastResult: null }
};

const REPORT_PATH = '/tmp/dispatch_report.md';

// ============ 防崩溃全局错误处理 ============
// 根因：容器休眠唤醒后PG连接池失效，查询抛未捕获异常导致进程崩溃
process.on('uncaughtException', (err) => {
  console.error('[Server] 未捕获异常（进程保持运行）:', err.message);
});
process.on('unhandledRejection', (reason) => {
  console.error('[Server] 未处理的Promise拒绝（进程保持运行）:', reason);
});

// ============ 数据库连接池自愈 ============
let dbHealthy = true;

async function checkAndRecoverDB() {
  try {
    const client = await pgPool.connect();
    try {
      await client.query('SELECT 1');
      if (!dbHealthy) {
        console.log('[DB] 数据库连接已恢复');
        dbHealthy = true;
      }
    } finally { client.release(); }
  } catch (err) {
    dbHealthy = false;
    console.error('[DB] 连接检查失败，重建连接池:', err.message);
    try {
      await pgPool.end().catch(() => {});
      pgPool.options.connectionString = DATABASE_URL;
      console.log('[DB] 连接池已重建');
    } catch (e) {
      console.error('[DB] 重建失败:', e.message);
    }
  }
}

// 每5分钟ping数据库，防止容器唤醒后连接全部失效
setInterval(() => {
  checkAndRecoverDB();
}, 5 * 60 * 1000);

// ============ Helper Functions ============
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

function runPython(scriptName, args = []) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, scriptName);
    const env = { ...process.env, PATH: '/usr/bin:/usr/local/bin:' + (process.env.PATH || '') };
    if (!env.DATABASE_URL) env.DATABASE_URL = DATABASE_URL;
    
    const child = execFile('/usr/bin/python3', [scriptPath, ...args], {
      cwd: __dirname,
      env,
      timeout: 300000,
      maxBuffer: 10 * 1024 * 1024
    }, (error, stdout, stderr) => {
      if (error) {
        console.error(`[Python ${scriptName}] Error:`, error.message);
        if (stderr) console.error(`[Python ${scriptName}] Stderr:`, stderr);
        reject(new Error(stderr || error.message));
        return;
      }
      if (stderr) console.warn(`[Python ${scriptName}] Stderr:`, stderr);
      const trimmed = stdout.trim();
      const lines = trimmed.split('\n');
      let parsed = null;
      for (let i = lines.length - 1; i >= 0; i--) {
        const line = lines[i].trim();
        if (line.startsWith('{')) {
          try { parsed = JSON.parse(line); break; } catch {}
        }
      }
      resolve(parsed || { output: trimmed });
    });
  });
}

async function generateReport() {
  taskStatus.report.running = true;
  try {
    const result = await runPython('dispatch_report.py');
    taskStatus.report.lastRun = new Date().toISOString();
    taskStatus.report.lastResult = result;
    if (result.status === 'ANOMALY') {
      console.error(`[Report] Found ${result.anomaly_count} anomalies:`, result.anomalies);
    } else if (result.status === 'OK') {
      console.log(`[Report] OK | ${result.total_matches} matches | ${result.on_sale} on sale`);
    }
    return result;
  } catch (err) {
    console.error('[Report] Report generation failed:', err.message);
    taskStatus.report.lastRun = new Date().toISOString();
    taskStatus.report.lastResult = { status: 'ERROR', error: err.message };
    return { status: 'ERROR', error: err.message };
  } finally {
    taskStatus.report.running = false;
  }
}

// ============ Data Normalization ============
// Expand JSONB fields into flat fields for frontend compatibility

// 统一胜分差格式为: 主胜1-5 / 客胜1-5 (统一使用"胜"表述)
function normalizeScoreDiff(sdr) {
  if (!sdr || typeof sdr !== 'string') return sdr;
  sdr = sdr.trim();
  
  // 已经是标准格式 (统一使用"胜")
  if (/^(主|客)胜\d/.test(sdr)) return sdr;
  
  // 如果是旧格式(含"负")，转换为"胜"
  if (/^(主|客)负\d/.test(sdr)) {
    return sdr.replace(/负/, '胜');
  }
  
  let side = '主';  // 默认主队
  let range = sdr;
  
  // 提取主/客
  const sideMatch = sdr.match(/^(主|客)/);
  if (sideMatch) {
    side = sideMatch[1];
    range = sdr.substring(1);
  }
  
  // 提取胜/负（可能在开头或结尾）并移除
  const resultStart = range.match(/^(胜|负)/);
  const resultEnd = range.match(/(胜|负)$/);
  if (resultStart) {
    range = range.substring(1);
  } else if (resultEnd) {
    range = range.substring(0, range.length - 1);
  }
  
  // range 现在应该是纯数字范围如 "1-5" 或 "16-20" 或 "20+"
  range = range.trim();
  if (!range) return sdr; // 无法解析，返回原值
  
  // 统一使用"胜"表述
  return `${side}胜${range}`;
}

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

function normalizeMatch(match) {
  if (!match) return match;
  // Extract fields from metadata JSONB if not present as direct columns
  const meta = (typeof match.metadata === 'string') ? JSON.parse(match.metadata) : (match.metadata || {});
  const odds = meta.odds || match.odds || {};
  const spf = odds.spf || {};
  const handicapSpf = odds.handicap_spf || {};
  
  // Fix match_time: combine match_date and match_time into full datetime string
  let matchTime = match.match_time || meta.match_time || '';
  let matchDate = match.match_date || meta.match_date;
  
  // If match_date is a Date object, convert to local date string YYYY-MM-DD
  if (matchDate instanceof Date) {
    const y = matchDate.getUTCFullYear();
    const m = String(matchDate.getUTCMonth() + 1).padStart(2, '0');
    const d = String(matchDate.getUTCDate()).padStart(2, '0');
    matchDate = `${y}-${m}-${d}`;
  } else if (typeof matchDate === 'string') {
    // Extract date part from ISO string like "2026-07-15T16:00:00.000Z"
    matchDate = matchDate.substring(0, 10);
  }
  
  // If match_time is just a time (HH:MM:SS or HH:MM), prepend the date
  if (matchTime && !matchTime.includes('-') && matchDate) {
    // Extract just HH:MM from time string like "02:15:00"
    const timeParts = matchTime.split(':');
    const hhmm = timeParts.length >= 2 ? `${timeParts[0]}:${timeParts[1]}` : matchTime;
    matchTime = `${matchDate} ${hhmm}`;
  }
  
  // 精简 metadata：列表接口去掉大文本字段和不必要的嵌套
  // 保留 match_time, match_date, status, home_score, away_score 等已提取到顶层
  const slimMeta = {};
  // 只保留前端可能需要的少量 metadata 字段
  if (meta.match_type) slimMeta.match_type = meta.match_type;
  if (meta.league) slimMeta.league = meta.league;
  if (meta.status) slimMeta.status = meta.status;
  
  return {
    ...match,
    metadata: slimMeta,
    match_date: matchDate,
    match_time: matchTime,
    teams: match.home_team && match.away_team ? `${match.home_team} vs ${match.away_team}` : '',
    win_odds: spf.win || null,
    draw_odds: spf.draw || null,
    lose_odds: spf.lose || null,
    handicap_win_odds: handicapSpf.win || null,
    handicap_draw_odds: handicapSpf.draw || null,
    handicap_lose_odds: handicapSpf.lose || null,
    league_name: (match.metadata && match.metadata.league) || '',
    home_score: meta.home_score != null ? meta.home_score : (match.home_score != null ? match.home_score : null),
    away_score: meta.away_score != null ? meta.away_score : (match.away_score != null ? match.away_score : null),
    handicap: meta.handicap || handicapSpf.handicap || (odds.hdc && odds.hdc.line) || match.handicap || null,
    selling_status: meta.selling_status || null
  };
}

function normalizePrediction(pred, matchMap) {
  if (!pred) return pred;
  const prediction = pred.prediction || {};
  const hitStatus = pred.hit_status || {};
  const match = matchMap ? matchMap[String(pred.match_id)] : null;
  
  const hitFields = ['spf', 'handicap_spf', 'score', 'goals', 'half_full',
                     'win_loss', 'handicap_win_loss', 'total_points', 'score_diff_range', 'half_win_loss'];
  const totalHits = hitFields.filter(f => hitStatus[f] === true).length;
  
  const normalizedSdr = normalizeScoreDiff(prediction.score_diff_range || pred.score_diff_range || pred.score_diff_range_pred) || null;
  const normalizedWl = prediction.win_loss || pred.win_loss || pred.win_loss_pred || null;
  const normalizedHwl = prediction.handicap_win_loss || pred.handicap_win_loss || pred.handicap_win_loss_pred || null;
  const normalizedTp = prediction.total_points || pred.total_points || pred.total_points_pred || null;

  // 精简输出：只保留核心字段，去掉 raw_response/analysis/冗余pred列 以减小响应体积
  const sportType = pred.sport_type || (match ? match.sport_type : null);
  
  // 精简 prediction JSONB：只保留前端需要的字段
  const slimPrediction = {};
  if (prediction.spf) slimPrediction.spf = prediction.spf;
  if (prediction.handicap_spf) slimPrediction.handicap_spf = prediction.handicap_spf;
  if (prediction.score) slimPrediction.score = prediction.score;
  if (prediction.goals) slimPrediction.goals = prediction.goals;
  if (prediction.half_full) slimPrediction.half_full = prediction.half_full;
  if (prediction.win_loss) slimPrediction.win_loss = prediction.win_loss;
  if (prediction.handicap_win_loss) slimPrediction.handicap_win_loss = prediction.handicap_win_loss;
  if (prediction.total_points) slimPrediction.total_points = prediction.total_points;
  if (prediction.score_diff_range) slimPrediction.score_diff_range = prediction.score_diff_range;
  if (prediction.half_win_loss) slimPrediction.half_win_loss = prediction.half_win_loss;
  if (prediction.handicap_result) slimPrediction.handicap_result = prediction.handicap_result;
  if (prediction.score_diff) slimPrediction.score_diff = prediction.score_diff;

  // 精简 hit_status JSONB：只保留 true/false 值
  const slimHitStatus = {};
  for (const k of hitFields) {
    if (hitStatus[k] === true || hitStatus[k] === false) slimHitStatus[k] = hitStatus[k];
  }
  if (hitStatus.reason) slimHitStatus.reason = hitStatus.reason;

  const result = {
    match_id: pred.match_id,
    ai_name: pred.ai_name,
    sport_type: sportType,
    is_settled: pred.is_settled,
    prediction: slimPrediction,
    hit_status: slimHitStatus,
    total_hits: totalHits,
  };
  // 只添加非null的预测值，减少响应体积
  if (prediction.spf) result.spf = prediction.spf;
  if (prediction.handicap_spf) result.handicap_spf = prediction.handicap_spf;
  if (prediction.score) result.score = prediction.score;
  if (prediction.goals) result.goals = prediction.goals;
  if (prediction.half_full) result.half_full = prediction.half_full;
  if (normalizedSdr) result.score_diff_range = normalizedSdr;
  if (normalizedWl) result.win_loss = normalizedWl;
  if (normalizedHwl) result.handicap_win_loss = normalizedHwl;
  if (normalizedTp) result.total_points = normalizedTp;
  // 只添加非null的命中标记
  if (hitStatus.spf !== undefined && hitStatus.spf !== null) result.hit_spf = hitStatus.spf === true ? '✅' : '❌';
  if (hitStatus.handicap_spf !== undefined && hitStatus.handicap_spf !== null) result.hit_handicap = hitStatus.handicap_spf === true ? '✅' : '❌';
  if (hitStatus.score !== undefined && hitStatus.score !== null) result.hit_score = hitStatus.score === true ? '✅' : '❌';
  if (hitStatus.goals !== undefined && hitStatus.goals !== null) result.hit_goals = hitStatus.goals === true ? '✅' : '❌';
  if (hitStatus.half_full !== undefined && hitStatus.half_full !== null) result.hit_half = hitStatus.half_full === true ? '✅' : '❌';
  if (hitStatus.win_loss !== undefined && hitStatus.win_loss !== null) result.hit_win_loss = hitStatus.win_loss === true ? '✅' : '❌';
  if (hitStatus.handicap_win_loss !== undefined && hitStatus.handicap_win_loss !== null) result.hit_handicap_win_loss = hitStatus.handicap_win_loss === true ? '✅' : '❌';
  if (hitStatus.total_points !== undefined && hitStatus.total_points !== null) result.hit_total_points = hitStatus.total_points === true ? '✅' : '❌';
  if (hitStatus.score_diff_range !== undefined && hitStatus.score_diff_range !== null) result.hit_score_diff_range = hitStatus.score_diff_range === true ? '✅' : '❌';
  if (hitStatus.half_win_loss !== undefined && hitStatus.half_win_loss !== null) result.hit_half_win_loss = hitStatus.half_win_loss === true ? '✅' : '❌';
  return result;
}

// ============ Commentary Generator ============
const DOUBAO_API_URL = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions';
const DOUBAO_API_KEY = process.env.DOUBAO_API_KEY || '';
const DOUBAO_MODEL = 'ep-20260706041055-2mgpf';

let commentaryRunning = false;

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

function buildMatchCommentaryPrompt(match, preds) {
  const isFootball = (match.sport_type || 'football') === 'football';
  const home = match.home_team || '';
  const away = match.away_team || '';
  const league = (match.metadata && match.metadata.league) || '';
  
  const odds = match.odds || {};
  const spfOdds = odds.spf || {};
  const handicapOdds = odds.handicap_spf || {};

  const spfCounts = {};
  preds.forEach(p => {
    const pred = p.prediction || {};
    const k = (isFootball ? pred.spf : pred.win_loss) || '未预测';
    spfCounts[k] = (spfCounts[k] || 0) + 1;
  });
  const total = preds.length;
  const sorted = Object.entries(spfCounts).sort((a, b) => b[1] - a[1]);
  const consensus = sorted[0];
  const consensusPct = Math.round(consensus[1] / total * 100);

  const dissenters = preds.filter(p => {
    const pred = p.prediction || {};
    return ((isFootball ? pred.spf : pred.win_loss) || '未预测') !== consensus[0];
  });
  let dissenterInfo = '';
  if (dissenters.length > 0) {
    dissenterInfo = dissenters.map(p => {
      const pred = p.prediction || {};
      let s = `${p.ai_name}: "${(isFootball ? pred.spf : pred.win_loss) || '?'}"`;
      if (p.analysis) s += `, reason: ${p.analysis.replace(/\n/g, ' ').slice(0, 80)}`;
      return s;
    }).join('\n');
  }

  const predDetail = preds.map(p => {
    const pred = p.prediction || {};
    let s = `${p.ai_name}: ${isFootball ? 'spf=' : 'win_loss='}${(isFootball ? pred.spf : pred.win_loss) || '?'}`;
    if (isFootball ? pred.handicap_spf : pred.handicap_win_loss) s += `, handicap=${isFootball ? pred.handicap_spf : pred.handicap_win_loss}`;
    if (isFootball ? pred.score : pred.score_diff_range) s += `, ${isFootball ? 'score' : 'score_diff'}=${isFootball ? pred.score : pred.score_diff_range}`;
    if (p.analysis) s += ` | ${p.analysis.replace(/\n/g, ' ').slice(0, 100)}`;
    return s;
  }).join('\n');

  const oddsLine = isFootball
    ? `W${spfOdds.win || '?'} / D${spfOdds.draw || '?'} / L${spfOdds.lose || '?'}`
    : `W${spfOdds.win || '?'} / L${spfOdds.lose || '?'}`;

  const sportLabel = isFootball ? 'football' : 'basketball';

  return `You are a ${sportLabel} commentator for ZhuLang AI Lab. Style: sharp, colloquial, like a knowledgeable friend chatting in a WeChat group.

## Match Info
- League: ${league} | Teams: ${home} VS ${away}
- Handicap: ${match.handicap || 'none'}
- Odds: ${oddsLine}

## ${total} AI Predictions
${predDetail}

## Consensus
${consensusPct}% of AIs (${consensus[1]}/${total}) favor "${consensus[0]}"
${dissenters.length > 0 ? `Dissenters:\n${dissenterInfo}` : 'All agree, no disagreement'}

Generate 150-250 characters of commentary in Chinese:
1. Sharp, colloquial, like chatting with friends in WeChat
2. Focus on AI consensus and disagreement
3. Have your own judgment, don't just repeat data
4. No gambling/betting terms
5. Use Chinese double quotes ""
6. Plain text only, no markdown`;
}

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

async function checkAndGenerateCommentary(options = {}) {
  if (commentaryRunning) {
    console.log('[Commentary] Previous task still running, skipping');
    return { skipped: true, reason: 'already_running' };
  }
  commentaryRunning = true;

  try {
    const forceMatchIds = options.forceMatchIds || [];
    const isForceMode = forceMatchIds.length > 0;

    if (isForceMode) {
      console.log(`[Commentary] Force mode: clearing and regenerating ${forceMatchIds.length} matches`);
      const client = await pgPool.connect();
      try {
        for (const matchId of forceMatchIds) {
          await client.query(
            `UPDATE matches SET metadata = COALESCE(metadata, '{}'::jsonb) - 'daily_commentary' - 'commentary_date' - 'commentary_version' WHERE id = $1`,
            [matchId]
          );
          console.log(`[Commentary] Cleared commentary for ${matchId}`);
        }
      } finally {
        client.release();
      }
    }

    // Find matches that need commentary (football, settled, no commentary yet)
    const client = await pgPool.connect();
    let matchesNeedingCommentary;
    try {
      let query = `
        SELECT m.*, 
          array_agg(json_build_object(
            'ai_name', p.ai_name,
            'prediction', p.prediction,
            'analysis', p.analysis
          )) as predictions
        FROM matches m
        LEFT JOIN predictions p ON p.match_id = m.id
        WHERE m.sport_type = 'football'
          AND m.status IN ('已确认', '已结算')
      `;
      if (isForceMode) {
        query += ` AND m.id = ANY($1)`;
        const res = await client.query(query, [forceMatchIds]);
        matchesNeedingCommentary = res.rows;
      } else {
        query += ` AND (m.metadata->>'daily_commentary') IS NULL
          AND (m.metadata->>'commentary_version') IS DISTINCT FROM '2'
          GROUP BY m.id
          ORDER BY (m.metadata->>'match_time') DESC
          LIMIT 10`;
        const res = await client.query(query);
        matchesNeedingCommentary = res.rows;
      }
    } finally {
      client.release();
    }

    if (matchesNeedingCommentary.length === 0) {
      console.log('[Commentary] No matches need commentary');
      return { generated: 0, skipped: 0 };
    }

    console.log(`[Commentary] Generating commentary for ${matchesNeedingCommentary.length} matches`);
    let generated = 0;
    for (const match of matchesNeedingCommentary) {
      const preds = (match.predictions || []).filter(p => p && p.ai_name);
      if (preds.length < 3) {
        console.log(`[Commentary] Skipping ${match.id}: only ${preds.length} predictions`);
        continue;
      }
      try {
        const prompt = buildMatchCommentaryPrompt(match, preds);
        const commentary = await callDoubaoCommentary(prompt);
        await updateMatchCommentary(match.id, commentary);
        generated++;
        console.log(`[Commentary] Generated for ${match.id} (${match.home_team} vs ${match.away_team})`);
        await sleep(1000);
      } catch (err) {
        console.error(`[Commentary] Failed for ${match.id}:`, err.message);
      }
    }

    console.log(`[Commentary] Done: generated ${generated}/${matchesNeedingCommentary.length}`);
    return { generated, total: matchesNeedingCommentary.length };
  } finally {
    commentaryRunning = false;
  }
}

// ============ HTTP Server ============
const server = http.createServer(async (req, res) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS_HEADERS);
    res.end();
    return;
  }

  const parsedUrl = new URL(req.url, `http://${req.headers.host}`);
  const pathname = parsedUrl.pathname;

  try {
    // ======== 简报动态页（绕开FaaS静态快照白名单：DB渲染，运行时可外网访问） ========
    if (req.method === 'GET' && /^\/brief-\d{4}-\d{2}-\d{2}\.html$/.test(pathname)) {
      const briefDate = pathname.match(/^\/brief-(\d{4}-\d{2}-\d{2})\.html$/)[1];
      const { rows } = await pgPool.query(
        `SELECT id, date, title, summary, match_count, content_html FROM briefs WHERE id = $1`,
        [`brief-${briefDate}`]
      );
      if (rows.length === 0 || !rows[0].content_html) {
        res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(`<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>简报不存在</title></head><body style="font-family:sans-serif;padding:40px;text-align:center;color:#374151"><h2>📭 ${briefDate} 简报尚未生成</h2><p>该日期暂无简报内容。</p><p><a href="/brief.html" style="color:#2563eb">← 返回简报列表</a></p></body></html>`);
        return;
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache, no-store, must-revalidate' });
      res.end(rows[0].content_html);
      return;
    }

    if (pathname === '/brief.html' && req.method === 'GET') {
      const { rows } = await pgPool.query(
        `SELECT id, date, title, summary, match_count FROM briefs WHERE content_html IS NOT NULL AND content_html != '' ORDER BY date DESC LIMIT 60`
      );
      const now = new Date();
      const pageGen = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`;
      const items = rows.map(r => {
        const dateStr = r.date instanceof Date
          ? `${r.date.getFullYear()}-${String(r.date.getMonth()+1).padStart(2,'0')}-${String(r.date.getDate()).padStart(2,'0')}`
          : String(r.date);
        const d = new Date(dateStr + 'T00:00:00');
        const label = `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
        const summary = String(r.summary || '').replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
        return `<a href="/brief-${r.date}.html" class="brief-item">
          <span class="date">${label}</span>
          <span class="title">${r.match_count || 0}场赛事 · 7AI预测</span>
          <span class="arrow">→</span>
        </a>`;
      }).join('\n');
      const listHtml = items || '<div class="empty">暂无简报，每日预测完成后自动生成</div>';
      const html = `<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全部简报 · AI实验室</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f7fa;color:#1f2937}
.navbar{background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);position:sticky;top:0;z-index:10}
.navbar .container{max-width:960px;margin:0 auto;padding:14px 20px;display:flex;justify-content:space-between;align-items:center}
.logo{font-size:18px;font-weight:700;color:#111827;text-decoration:none}
.logo .accent{color:#2563eb}
.nav-links a{color:#4b5563;text-decoration:none;margin-left:20px;font-size:15px}
.nav-links a:hover{color:#2563eb}
main.container{max-width:960px;margin:0 auto;padding:28px 20px 60px}
.breadcrumb{font-size:13px;color:#9ca3af;margin-bottom:16px}
.breadcrumb a{color:#2563eb;text-decoration:none}
.page-title{font-size:26px;margin-bottom:6px}
.page-sub{color:#6b7280;font-size:13px;margin-bottom:24px}
.brief-item{display:flex;align-items:center;gap:16px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:18px 22px;margin-bottom:12px;text-decoration:none;color:inherit;transition:box-shadow .15s,border-color .15s}
.brief-item:hover{border-color:#2563eb;box-shadow:0 4px 14px rgba(37,99,235,.10)}
.brief-item .date{font-size:17px;font-weight:600;min-width:130px;color:#111827}
.brief-item .title{flex:1;color:#4b5563;font-size:14px}
.brief-item .arrow{color:#2563eb;font-size:18px}
.empty{background:#fff;border-radius:12px;padding:40px;text-align:center;color:#9ca3af}
.footer{text-align:center;color:#9ca3af;font-size:13px;padding:30px 20px 40px}
</style></head><body>
<nav class="navbar"><div class="container">
<a href="/" class="logo"><span>🧪</span> <span>AI实验室 <span class="accent">·</span> <span class="accent">体彩</span>好伙伴</span></a>
<div class="nav-links">
<a href="/">首页</a><a href="/football.html">足球</a><a href="/bb2.html">篮球</a><a href="/ca2.html">计算器</a><a href="/rank.html">排行</a>
</div></div></nav>
<main class="container">
<div class="breadcrumb"><a href="/">首页</a> <span>/</span> <span>全部简报</span></div>
<h1 class="page-title">📋 全部简报</h1>
<div class="page-sub">每日赛事预测简报 · 页面更新于 ${pageGen}</div>
<div id="briefList">
${listHtml}
</div>
</main>
<footer class="footer"><p>🧪 AI实验室 · 体彩好伙伴 · 数据仅供研究参考</p></footer>
</body></html>`;
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache, no-store, must-revalidate' });
      res.end(html);
      return;
    }

    // ======== GET /api/matches ========
    if (pathname === '/api/matches' && req.method === 'GET') {
      const date = parsedUrl.searchParams.get('date');
      const sport = parsedUrl.searchParams.get('sport'); // null means all sports
      const includePredictions = parsedUrl.searchParams.get('include_predictions') !== 'false'; // 默认包含预测数据

      const days = parseInt(parsedUrl.searchParams.get('days')) || 30;
      let query = `SELECT * FROM matches`;
      const params = [];
      let paramIdx = 1;
      let hasWhere = false;

      // Default: only return recent N days to avoid massive payloads
      if (!date) {
        query += ` WHERE (metadata->>'match_date') ~ '^\\d{4}-\\d{2}-\\d{2}$' AND (metadata->>'match_date')::date >= CURRENT_DATE - $${paramIdx}::integer`;
        params.push(days);
        paramIdx++;
        hasWhere = true;
      }

      if (sport) {
        if (hasWhere) {
          query += ` AND sport_type = $${paramIdx}`;
        } else {
          query += ` WHERE sport_type = $${paramIdx}`;
          hasWhere = true;
        }
        params.push(sport);
        paramIdx++;
      }

      if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
        const [year, month, day] = date.split('-').map(Number);
        const d = new Date(year, month - 1, day);
        d.setDate(d.getDate() + 1);
        const nextDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        if (hasWhere) {
          query += ` AND (metadata->>'match_time')::date >= $${paramIdx}::date AND (metadata->>'match_time')::date < $${paramIdx + 1}::date`;
        } else {
          query += ` WHERE (metadata->>'match_time')::date >= $${paramIdx}::date AND (metadata->>'match_time')::date < $${paramIdx + 1}::date`;
          hasWhere = true;
        }
        params.push(date, nextDate);
        paramIdx += 2;
      }

      // 排除传统彩票（CT）比赛
      if (hasWhere) {
        query += ` AND (metadata->>'match_type' IS NULL OR metadata->>'match_type' != 'ct')`;
      } else {
        query += ` WHERE (metadata->>'match_type' IS NULL OR metadata->>'match_type' != 'ct')`;
      }

      query += ` ORDER BY (metadata->>'match_time') ASC`;

      const { rows } = await pgPool.query(query, params);
      let enriched = rows.map(normalizeMatch);

      // Auto-mark past unstarted matches as started (but NOT stopped/cancelled ones)
      const now = new Date();
      enriched.forEach(m => {
        const metaStatus = (m.metadata && m.metadata.status) || '';
        const hasScore = m.home_score != null && m.away_score != null;
        
        // 有比分 → 已完赛（优先级最高）
        if (hasScore) {
          m.status = '已完赛';
        }
        // metadata明确标记取消 → 已取消
        else if (metaStatus === '已取消') {
          m.status = '已取消';
        }
        // stopped状态只是不再售卖，不代表取消 → 一律标待比赛（等auto_settle结算）
        else if (metaStatus === 'stopped') {
          m.status = '待比赛';
        }
        // 已过时间但未开赛 → 已开赛
        else if (new Date(m.match_time) < now && (m.status === '未开赛' || m.status === 'on_sale')) {
          m.status = '已开赛';
        }
      });

      // Optionally include predictions
      if (includePredictions && enriched.length > 0) {
        const matchIds = enriched.map(m => String(m.id));
        const predResult = await pgPool.query(
          `SELECT * FROM predictions WHERE match_id = ANY($1) ORDER BY id DESC`,
          [matchIds]
        );
        const matchMap = {};
        enriched.forEach(m => { matchMap[String(m.id)] = m; });
        
        const allPreds = predResult.rows.map(p => {
          const cleaned = { ...p, analysis: cleanAnalysis(p.analysis) };
          return normalizePrediction(cleaned, matchMap);
        });

        const predictionsByMatch = {};
        allPreds.forEach((p, idx) => {
          const matchId = String(predResult.rows[idx].match_id);
          if (!predictionsByMatch[matchId]) predictionsByMatch[matchId] = [];
          predictionsByMatch[matchId].push(p);
        });

        enriched.forEach(m => {
          m.predictions = predictionsByMatch[String(m.id)] || [];
        });
      }

      sendJsonResponse(req, res, enriched);
      return;
    }

    // ======== GET /api/matches/:id ========
    if (pathname.match(/^\/api\/matches\/(.+)$/) && req.method === 'GET') {
      const matchId = decodeURIComponent(pathname.split('/api/matches/')[1]);
      
      const matchRes = await pgPool.query(
        `SELECT * FROM matches WHERE id = $1`,
        [matchId]
      );
      
      if (matchRes.rows.length === 0) {
        res.writeHead(404, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'Match not found' }));
        return;
      }

      const match = normalizeMatch(matchRes.rows[0]);
      
      const predRes = await pgPool.query(
        `SELECT * FROM predictions WHERE match_id = $1 ORDER BY ai_name ASC`,
        [matchId]
      );
      
      const matchMap = { [String(match.id)]: match };
      match.predictions = predRes.rows.map(p => {
        const cleaned = { ...p, analysis: cleanAnalysis(p.analysis) };
        return normalizePrediction(cleaned, matchMap);
      });

      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(match));
      return;
    }

    // ======== GET /api/predictions ========
    if (pathname === '/api/predictions' && req.method === 'GET') {
      try {
      const sport = parsedUrl.searchParams.get('sport') || 'football';
      const days = parseInt(parsedUrl.searchParams.get('days')) || 30;

      // Get predictions joined with matches, only recent N days
      const { rows } = await pgPool.query(
        `SELECT p.*, m.sport_type, m.metadata->>'match_time' as match_time
         FROM predictions p
         JOIN matches m ON m.id = p.match_id
         WHERE m.sport_type = $1
           AND (m.metadata->>'match_date') ~ '^\\d{4}-\\d{2}-\\d{2}$' AND (m.metadata->>'match_date')::date >= CURRENT_DATE - $2::integer
         ORDER BY p.id DESC`,
        [sport, days]
      );

      // Build match map for normalization
      const matchIds = [...new Set(rows.map(r => String(r.match_id)))];
      let matchMap = {};
      if (matchIds.length > 0) {
        const matchRes = await pgPool.query(
          `SELECT id, sport_type FROM matches WHERE id = ANY($1)`,
          [matchIds]
        );
        matchRes.rows.forEach(m => { matchMap[String(m.id)] = m; });
      }

      const enriched = rows.map(p => {
        const cleaned = { ...p, analysis: cleanAnalysis(p.analysis) };
        return normalizePrediction(cleaned, matchMap);
      });

      res.writeHead(200, { 
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        ...CORS_HEADERS 
      });
      res.end(JSON.stringify(enriched));
      return;
      } catch (err) {
        console.error('[/api/predictions] 错误:', err.message);
        if (!res.headersSent) {
          res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        }
        res.end(JSON.stringify({ error: 'Internal Server Error', message: err.message }));
        return;
      }
    }

    // ======== GET /api/chain_bets ========
    if (pathname === '/api/chain_bets' && req.method === 'GET') {
      const { rows } = await pgPool.query(
        `SELECT * FROM chain_bets ORDER BY bet_date DESC, ai_name ASC`
      );
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(rows));
      return;
    }

    // ======== GET /api/ai_stats ========
    if (pathname === '/api/ai_stats' && req.method === 'GET') {
      const sport = parsedUrl.searchParams.get('sport') || 'football';
      const active = parsedUrl.searchParams.get('active');
      
      let query = `SELECT * FROM ai_stats WHERE sport_type = $1`;
      const params = [sport];
      if (active !== 'false') {
        query += ` AND is_active = true`;
      }
      query += ` ORDER BY rank ASC`;
      
      const { rows } = await pgPool.query(query, params);
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(rows));
      return;
    }

    // ======== GET /api/betting_daily ========
    if (pathname === '/api/betting_daily' && req.method === 'GET') {
      const sport = parsedUrl.searchParams.get('sport') || 'football';
      const { rows } = await pgPool.query(
        `SELECT * FROM betting_daily WHERE sport_type = $1 ORDER BY match_date DESC`,
        [sport]
      );
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(rows));
      return;
    }

    // ======== GET /api/betting_summary ========
    if (pathname === '/api/betting_summary' && req.method === 'GET') {
      const sport = parsedUrl.searchParams.get('sport') || 'football';
      const { rows } = await pgPool.query(
        `SELECT * FROM betting_summary WHERE sport_type = $1 ORDER BY rank ASC`,
        [sport]
      );
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(rows));
      return;
    }

    // ======== GET /api/briefs ========
    if (pathname === '/api/briefs' && req.method === 'GET') {
      const { rows } = await pgPool.query(`SELECT * FROM briefs ORDER BY date DESC`);
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(rows));
      return;
    }

    // ======== GET /api/date-tabs ========
    if (pathname === '/api/date-tabs' && req.method === 'GET') {
      const today = new Date();
      const tabs = [];
      for (let i = -3; i <= 3; i++) {
        const date = new Date(today);
        date.setDate(today.getDate() + i);
        const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
        const displayStr = `${date.getMonth() + 1}月${date.getDate()}日`;
        tabs.push({ date: dateStr, display: displayStr, isToday: i === 0 });
      }
      const todayTab = tabs.find(t => t.isToday);
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ tabs, defaultDate: todayTab ? todayTab.date : tabs[3].date }));
      return;
    }

    // ======== GET /api/football-recent ========
    if (pathname === '/api/football-recent' && req.method === 'GET') {
      const matchRes = await pgPool.query(
        `SELECT * FROM matches WHERE sport_type = 'football' AND (metadata->>'match_time') IS NOT NULL AND (metadata->>'match_time') != '' ORDER BY (metadata->>'match_time') DESC LIMIT 500`
      );
      if (matchRes.rows.length === 0) {
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ date: null, matches: [], predictions: [] }));
        return;
      }

      const getMatchTime = (m) => {
        const meta = (typeof m.metadata === 'string') ? JSON.parse(m.metadata) : (m.metadata || {});
        return meta.match_time || m.match_time || null;
      };
      const getDateFromMatchTime = (matchTime) => {
        if (!matchTime) return null;
        return String(matchTime).substring(0, 10);
      };

      const latestDate = getDateFromMatchTime(getMatchTime(matchRes.rows[0]));
      const recentMatches = matchRes.rows.filter(m => getDateFromMatchTime(getMatchTime(m)) === latestDate);
      const matchIds = recentMatches.map(m => m.id);

      const predRes = await pgPool.query(
        `SELECT * FROM predictions WHERE match_id = ANY($1) ORDER BY id DESC`,
        [matchIds]
      );

      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      const predMatchMap = {};
      recentMatches.forEach(m => { predMatchMap[String(m.id)] = m; });
      res.end(JSON.stringify({
        date: latestDate,
        matches: recentMatches.map(normalizeMatch),
        predictions: predRes.rows.map(p => {
          const cleaned = { ...p, analysis: cleanAnalysis(p.analysis) };
          return normalizePrediction(cleaned, predMatchMap);
        })
      }));
      return;
    }

    // ======== GET /api/football-history ========
    if (pathname === '/api/football-history' && req.method === 'GET') {
      const matchRes = await pgPool.query(
        `SELECT * FROM matches WHERE sport_type = 'football' AND (metadata->>'match_time') IS NOT NULL AND (metadata->>'match_time') != '' ORDER BY (metadata->>'match_time') DESC LIMIT 5000`
      );
      const predRes = await pgPool.query(
        `SELECT * FROM predictions ORDER BY id DESC LIMIT 5000`
      );

      const getMatchTime = (m) => {
        const meta = (typeof m.metadata === 'string') ? JSON.parse(m.metadata) : (m.metadata || {});
        return meta.match_time || m.match_time || null;
      };
      const getDateFromMatchTime = (matchTime) => {
        if (!matchTime) return null;
        return String(matchTime).substring(0, 10);
      };

      const byDate = {};
      for (const m of matchRes.rows) {
        const date = getDateFromMatchTime(getMatchTime(m));
        if (!date) continue;
        if (!byDate[date]) byDate[date] = [];
        byDate[date].push(m);
      }

      const dates = Object.keys(byDate).sort().reverse();
      const historyDates = dates.slice(1);

      const historyPredMap = {};
      predRes.rows.forEach(p => { historyPredMap[String(p.match_id)] = predRes.rows.filter(r => r.match_id === p.match_id); });
      const result = historyDates.map(date => {
        const dateMatchMap = {};
        byDate[date].forEach(m => { dateMatchMap[String(m.id)] = m; });
        return {
          date,
          matches: byDate[date].map(normalizeMatch),
          predictions: predRes.rows.filter(p => byDate[date].some(m => m.id === p.match_id))
            .map(p => {
              const cleaned = { ...p, analysis: cleanAnalysis(p.analysis) };
              return normalizePrediction(cleaned, dateMatchMap);
            })
        };
      });

      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(result));
      return;
    }

    // ======== GET /api/parlay-latest ========
    if (pathname === '/api/parlay-latest' && req.method === 'GET') {
      const { rows } = await pgPool.query(
        `SELECT * FROM chain_bets ORDER BY bet_date DESC, ai_name ASC`
      );
      if (rows.length === 0) {
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ date: null, records: [] }));
        return;
      }
      const latestDate = rows[0].bet_date;
      const latestRecords = rows.filter(r => r.bet_date === latestDate);
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ date: latestDate, records: latestRecords }));
      return;
    }

    // ======== GET /api/parlay-history ========
    if (pathname === '/api/parlay-history' && req.method === 'GET') {
      const { rows } = await pgPool.query(
        `SELECT * FROM chain_bets ORDER BY bet_date DESC, ai_name ASC`
      );
      const byDate = {};
      for (const r of rows) {
        if (!byDate[r.bet_date]) byDate[r.bet_date] = [];
        byDate[r.bet_date].push(r);
      }
      const dates = Object.keys(byDate).sort().reverse();
      const historyDates = dates.slice(1);
      const result = historyDates.map(date => ({ date, records: byDate[date] }));
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(result));
      return;
    }

    // ======== Admin API Routes ========

    // POST /api/admin/discover
    if (pathname === '/api/admin/discover' && req.method === 'POST') {
      if (taskStatus.discover.running) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'discover task is running' }));
        return;
      }
      taskStatus.discover.running = true;
      try {
        const result = await runPython('discover_matches.py');
        taskStatus.discover.lastRun = new Date().toISOString();
        taskStatus.discover.lastResult = result;
        
        // 发现新比赛后触发AI预测（与定时任务 runJcDiscover 保持一致）
        const newCount = result.new || result.new_matches_count || 0;
        if (newCount > 0) {
          console.log(`[Admin] 发现${newCount}场新比赛，触发AI预测`);
          await runPython('auto_predict.py', ['football']);
        }
        
        // 新比赛发现后，重新初始化结算定时器
        await initializeSettleTimers();
        
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

    // POST /api/admin/predict
    if (pathname === '/api/admin/predict' && req.method === 'POST') {
      if (taskStatus.predict.running) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'predict task is running' }));
        return;
      }
      taskStatus.predict.running = true;
      let predictBody = {};
      try {
        const rawBody = await readBody(req);
        predictBody = rawBody ? JSON.parse(rawBody) : {};
      } catch(e) { predictBody = {}; }
      const predictSport = predictBody.sport || 'football';
      const predictArgs = predictSport !== 'football' ? ['--sport', predictSport] : [];
      try {
        const result = await runPython('auto_predict.py', predictArgs);
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

    // POST /api/admin/traditional-predict - 触发CT传统彩预测
    if (pathname === '/api/admin/traditional-predict' && req.method === 'POST') {
      if (taskStatus.predict.running) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'predict task is running' }));
        return;
      }
      taskStatus.predict.running = true;
      let ctBody = {};
      try {
        const rawBody = await readBody(req);
        ctBody = rawBody ? JSON.parse(rawBody) : {};
      } catch(e) { ctBody = {}; }
      const ctGame = ctBody.game || null; // 可选: '胜负彩', '任9', '半全场', '进球彩'
      const ctIssue = ctBody.issue || null; // 可选: 指定期号
      const ctGameTypes = ctGame ? [ctGame] : ['胜负彩', '任9', '半全场', '进球彩'];
      const results = {};
      try {
        for (const gt of ctGameTypes) {
          try {
            const args = ['--game', gt, '--force'];
            if (ctIssue) args.push('--issue', ctIssue);
            console.log(`[Admin] CT预测: ${gt}${ctIssue ? ' 期号' + ctIssue : ''}`);
            const result = await runPython('traditional_lottery_predict.py', args);
            results[gt] = result;
          } catch (e) {
            console.error(`[Admin] CT预测${gt}失败:`, e.message);
            results[gt] = { error: e.message };
          }
        }
        taskStatus.predict.lastRun = new Date().toISOString();
        taskStatus.predict.lastResult = results;
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ success: true, data: results }));
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

    // POST /api/admin/settle
    if (pathname === '/api/admin/settle' && req.method === 'POST') {
      if (taskStatus.settle.running) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'settle task is running' }));
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

    // GET /api/admin/status
    if (pathname === '/api/admin/status' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(taskStatus));
      return;
    }

    // GET /api/admin/report
    if (pathname === '/api/admin/report' && req.method === 'GET') {
      try {
        const report = fs.readFileSync(REPORT_PATH, 'utf-8');
        res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', ...CORS_HEADERS });
        res.end(report);
      } catch (err) {
        res.writeHead(404, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'Report file not found' }));
      }
      return;
    }

    // GET /api/ct-review/:file - 提供审阅文件内容
    if (pathname.startsWith('/api/ct-review/') && req.method === 'GET') {
      const fileKey = pathname.split('/').pop();
      const fileMap = {
        'a': 'ct_review_0830a.json',
        'b': 'ct_review_0830b.txt',
        'c': 'ct_review_0830c.json'
      };
      const fileName = fileMap[fileKey];
      if (!fileName) {
        res.writeHead(404, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'File not found. Available: a, b, c' }));
        return;
      }
      const filePath = path.join(process.cwd(), fileName);
      try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const ext = path.extname(filePath).toLowerCase();
        const contentType = MIME_TYPES[ext] || 'application/octet-stream';
        res.writeHead(200, { 'Content-Type': contentType, ...CORS_HEADERS });
        res.end(content);
      } catch (err) {
        res.writeHead(404, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: `File ${fileName} not found` }));
      }
      return;
    }

    // POST /api/admin/report
    if (pathname === '/api/admin/report' && req.method === 'POST') {
      const result = await generateReport();
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(result));
      return;
    }

    // POST /api/admin/commentary
    if (pathname === '/api/admin/commentary' && req.method === 'POST') {
      if (commentaryRunning) {
        res.writeHead(409, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'commentary generation is running' }));
        return;
      }
      const rawBody = await readBody(req);
      let body = {};
      try { body = JSON.parse(rawBody); } catch (e) { /* empty body is ok */ }
      const forceMatchIds = (body && Array.isArray(body.match_ids)) ? body.match_ids : [];
      const isForceMode = forceMatchIds.length > 0;
      
      checkAndGenerateCommentary({ forceMatchIds }).then(result => {
        console.log(`[Commentary] Done:`, result);
      }).catch(err => {
        console.error(`[Commentary] Failed:`, err);
      });
      
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ 
        success: true, 
        message: isForceMode 
          ? `Force mode: triggered ${forceMatchIds.length} matches commentary regeneration` 
          : 'Commentary generation triggered' 
      }));
      return;
    }

    // POST /api/admin/briefing
    if (pathname === '/api/admin/briefing' && req.method === 'POST') {
      const rawBody = await readBody(req);
      let body = {};
      try { body = JSON.parse(rawBody); } catch (e) { /* empty body */ }
      const date = body.date || new Date().toISOString().split('T')[0];
      const type = body.type || 'prediction';
      
      console.log(`[Briefing] Triggering: date=${date}, type=${type}`);
      
      const scriptPath = path.join(process.cwd(), 'generate_brief.py');
      execFile('/usr/bin/python3', [scriptPath, '--date', date, '--type', type, '--output', 'both'], {
        cwd: process.cwd(),
        env: { ...process.env, PYTHONUNBUFFERED: '1', DATABASE_URL }
      }, (error, stdout, stderr) => {
        if (error) {
          console.error(`[Briefing] Failed:`, error.message);
          if (stderr) console.error(`[Briefing] stderr:`, stderr);
          return;
        }
        console.log(`[Briefing] Success:`, stdout);
      });
      
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ success: true, message: `Briefing triggered: ${date} (${type})` }));
      return;
    }

    // ======== 内部查询路由 - 供Python脚本使用 ========
    if (pathname === '/api/internal/query' && req.method === 'POST') {
      const rawBody = await readBody(req);
      let body = {};
      try { body = JSON.parse(rawBody); } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'Invalid JSON' }));
        return;
      }
      
      const { sql, params } = body;
      if (!sql) {
        res.writeHead(400, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'Missing sql parameter' }));
        return;
      }
      
      try {
        const result = await pgPool.query(sql, params || []);
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ rows: result.rows, rowCount: result.rowCount }));
      } catch (err) {
        console.error('[Internal Query] Error:', err.message);
        res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: err.message }));
      }
      return;
    }

    // ======== 传统彩路由 - 代理转发到CT服务 (端口5001) ========
    if (pathname.startsWith('/api/traditional-lottery/')) {
      const http = require('http');
      const ctPort = parseInt(process.env.TRADITIONAL_PORT || '5001', 10);
      const proxyOpts = {
        hostname: '127.0.0.1',
        port: ctPort,
        path: req.url,
        method: req.method,
        headers: { ...req.headers, host: `127.0.0.1:${ctPort}` }
      };
      const proxyReq = http.request(proxyOpts, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
      });
      proxyReq.on('error', (err) => {
        console.error('[Proxy] CT service error:', err.message);
        res.writeHead(502, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ error: 'CT service unavailable', message: err.message }));
      });
      req.pipe(proxyReq);
      return;
    }

  } catch (err) {
    console.error('API error:', err);
    res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
    res.end(JSON.stringify({ error: 'Internal server error', message: err.message }));
    return;
  }

    // ======== GET /api/heartbeat ========
    if (pathname === '/api/heartbeat' && req.method === 'GET') {
      let dbOk = false;
      try {
        const client = await pgPool.connect();
        try { await client.query('SELECT 1'); dbOk = true; } finally { client.release(); }
      } catch(e) { dbOk = false; }
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({ status: 'ok', timestamp: new Date().toISOString(), database: dbOk ? 'connected' : 'disconnected' }));
      return;
    }

  // ============ Static File Routes ============
  let urlPath = pathname;
  // 根路径直接302重定向到ix.html（比JS跳转更可靠，CDN/代理友好）
  if (urlPath === '/') {
    res.writeHead(302, { 'Location': '/ix.html', 'Cache-Control': 'no-cache' });
    res.end();
    return;
  }
  // URL别名（JC服务现在运行在JC/目录下，文件在同级目录）
  const URL_ALIASES = {
    '/ix.html': '/ix.html',
    '/api.js': '/api.js',
    '/index.js': '/index.js',
    '/styles.css': '/styles.css',
    '/basketball.html': '/basketball.html',
    '/basketball.js': '/basketball.js',
    '/ai-analysis.html': '/ai-analysis.html',
    '/ai-analysis.js': '/ai-analysis.js',
    '/ai-hub.html': '/ai-hub.html',
    '/ia2.html': '/ia2.html',
    '/bb2.html': '/bb2.html',
    '/br2.html': '/br2.html',
    '/ca2.html': '/ca2.html',
    '/ca.html': '/ca.html',
    '/calculator.html': '/calculator.html',
    '/calculator.js': '/calculator.js',
    '/briefs.html': '/briefs.html',
    '/briefs.js': '/briefs.js',
  };
  if (URL_ALIASES[urlPath]) urlPath = URL_ALIASES[urlPath];


  const safePath = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, '');
  const filePath = path.join(process.cwd(), safePath);

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
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

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
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

// 比赛级别定时结算：为每场比赛设置3小时后的定时器
const settleTimers = new Map(); // matchId -> timeout

async function scheduleMatchSettle(matchId, matchTime) {
  // 清除旧的定时器
  if (settleTimers.has(matchId)) {
    clearTimeout(settleTimers.get(matchId));
  }
  
  // 计算结算时间（开赛后3小时）
  const settleTime = new Date(matchTime);
  settleTime.setHours(settleTime.getHours() + 3);
  
  const delay = settleTime.getTime() - Date.now();
  
  if (delay <= 0) {
    // 已经到了结算时间，立即结算
    console.log(`[AutoSettle] 比赛 ${matchId} 已到结算时间，立即结算`);
    triggerMatchSettle(matchId);
    return;
  }
  
  // 设置定时器
  const timer = setTimeout(() => {
    console.log(`[AutoSettle] 触发比赛 ${matchId} 的结算`);
    triggerMatchSettle(matchId);
    settleTimers.delete(matchId);
  }, delay);
  
  settleTimers.set(matchId, timer);
  console.log(`[AutoSettle] 比赛 ${matchId} 将在 ${Math.round(delay/1000/60)} 分钟后结算 (${settleTime.toISOString()})`);
}

async function triggerMatchSettle(matchId) {
  if (taskStatus.settle.running) {
    // 防止锁卡死：如果运行超过10分钟，强制释放
    if (taskStatus.settle.lastRun) {
      const elapsed = Date.now() - new Date(taskStatus.settle.lastRun).getTime();
      if (elapsed > 10 * 60 * 1000) {
        console.warn(`[AutoSettle] 结算任务运行超时(${Math.round(elapsed/60000)}分钟)，强制释放锁`);
        taskStatus.settle.running = false;
      } else {
        console.log(`[AutoSettle] 结算任务正在运行，等待完成后再处理比赛 ${matchId}`);
        setTimeout(() => triggerMatchSettle(matchId), 60000); // 1分钟后重试
        return;
      }
    } else {
      console.log(`[AutoSettle] 结算任务正在运行，等待完成后再处理比赛 ${matchId}`);
      setTimeout(() => triggerMatchSettle(matchId), 60000);
      return;
    }
  }
  
  taskStatus.settle.running = true;
  try {
    // 调用auto_settle.py结算特定比赛
    const result = await runPython('auto_settle.py', ['--match-id', String(matchId)]);
    taskStatus.settle.lastRun = new Date().toISOString();
    taskStatus.settle.lastResult = result;
    console.log(`[AutoSettle] 比赛 ${matchId} 结算完成:`, result);
  } catch (err) {
    taskStatus.settle.lastRun = new Date().toISOString();
    taskStatus.settle.lastResult = { error: err.message };
    console.error(`[AutoSettle] 比赛 ${matchId} 结算失败:`, err.message);
  } finally {
    taskStatus.settle.running = false;
  }
}

async function initializeSettleTimers() {
  try {
    // 只查询未来24小时内需要结算的足球比赛（排除CT比赛，CT有独立结算逻辑）
    const now = new Date();
    const future24h = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    
    const result = await pgPool.query(`
      SELECT id, metadata->>'match_time' as match_time
      FROM matches
      WHERE id NOT LIKE 'CT%'
        AND (metadata->>'status' != '已取消' OR status != '已取消')
        AND (metadata->>'selling_status' IS DISTINCT FROM 'settled')
        AND (metadata->>'match_time') IS NOT NULL
        AND (metadata->>'match_time') ~ '^\d{4}-\d{2}-\d{2}'
      ORDER BY (metadata->>'match_time') ASC
    `);
    
    // 过滤出24小时内的比赛
    const upcomingMatches = result.rows.filter(row => {
      const matchTime = new Date(row.match_time);
      return matchTime <= future24h && matchTime >= now;
    });
    
    console.log(`[AutoSettle] 初始化定时器，找到 ${upcomingMatches.length} 场24小时内需结算的比赛（共 ${result.rows.length} 场未结算）`);
    
    // 使用 setImmediate 避免阻塞事件循环
    for (const row of upcomingMatches) {
      const matchId = row.id;
      const matchTime = row.match_time;
      if (matchTime) {
        setImmediate(() => scheduleMatchSettle(matchId, matchTime).catch(e => console.error(`[AutoSettle] 调度失败:`, e.message)));
      }
    }
  } catch (err) {
    console.error('[AutoSettle] 初始化定时器失败:', err.message);
  }
}


// ============ 定时抓取任务 ============
const scheduleTimers = [];

// 计算距下一个目标时间的毫秒数
function msUntil(hour, minute) {
  const now = new Date();
  const target = new Date(now);
  target.setHours(hour, minute, 0, 0);
  if (target <= now) target.setDate(target.getDate() + 1);
  return target.getTime() - now.getTime();
}

// 通用定时调度器
function scheduleDaily(hour, minute, label, taskFn) {
  const DAY = 24 * 60 * 60 * 1000;
  let firstDelay = msUntil(hour, minute);
  console.log(`[Schedule] ${label}: 每天 ${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')} 执行，首次 ${Math.round(firstDelay/3600000*10)/10}h后`);
  
  const timer = setTimeout(() => {
    console.log(`[Schedule] 开始执行: ${label}`);
    taskFn().catch(err => console.error(`[Schedule] ${label}失败:`, err.message));
    // 之后每24小时执行
    const interval = setInterval(() => {
      console.log(`[Schedule] 开始执行: ${label}`);
      taskFn().catch(err => console.error(`[Schedule] ${label}失败:`, err.message));
    }, DAY);
    scheduleTimers.push(interval);
  }, firstDelay);
  scheduleTimers.push(timer);
}

// JC定时抓取 - 每天10:00和18:00
async function runJcDiscover() {
  if (taskStatus.discover.running) {
    console.log('[Schedule] JC抓取已在运行，跳过');
    return;
  }
  taskStatus.discover.running = true;
  try {
    const result = await runPython('discover_matches.py');
    taskStatus.discover.lastRun = new Date().toISOString();
    taskStatus.discover.lastResult = result;
    console.log(`[Schedule] JC抓取完成:`, JSON.stringify(result).slice(0, 200));
    // 发现新比赛后触发预测
    const newCount = result.new || result.new_matches_count || 0;
    if (newCount > 0) {
      console.log(`[Schedule] 发现${newCount}场新比赛，触发AI预测`);
      await runPython('auto_predict.py', ['football']);
    }
    // 重新初始化结算定时器
    await initializeSettleTimers();
  } catch (err) {
    taskStatus.discover.lastRun = new Date().toISOString();
    taskStatus.discover.lastResult = { error: err.message };
    console.error(`[Schedule] JC抓取失败:`, err.message);
  } finally {
    taskStatus.discover.running = false;
  }
}

// CT定时抓取 - 每天10:30
async function runCtDiscover() {
  if (taskStatus.discover.running) {
    console.log('[Schedule] 预测任务正在运行，等待30秒后重试CT');
    setTimeout(runCtDiscover, 30000);
    return;
  }
  taskStatus.discover.running = true;
  try {
    const result = await runPython('ct_discover.py');
    taskStatus.discover.lastRun = new Date().toISOString();
    taskStatus.discover.lastResult = result;
    console.log(`[Schedule] CT抓取完成:`, JSON.stringify(result).slice(0, 200));
    // 发现新比赛后触发CT预测（4种玩法）
    const saved = result.saved || 0;
    if (saved > 0) {
      console.log(`[Schedule] CT发现${saved}场新比赛，触发CT AI预测`);
      const ctGameTypes = ['胜负彩', '任9', '半全场', '进球彩'];
      for (const gt of ctGameTypes) {
        try {
          console.log(`[Schedule] CT预测: ${gt}`);
          await runPython('traditional_lottery_predict.py', ['--game', gt, '--force']);
        } catch (e) {
          console.error(`[Schedule] CT预测${gt}失败:`, e.message);
        }
      }
    }
    await initializeSettleTimers();
  } catch (err) {
    taskStatus.discover.lastRun = new Date().toISOString();
    taskStatus.discover.lastResult = { error: err.message };
    console.error(`[Schedule] CT抓取失败:`, err.message);
  } finally {
    taskStatus.discover.running = false;
  }
}

// 每日定时结算（同时处理竞彩和CT彩）
async function runDailySettle() {
  // 竞彩结算
  if (taskStatus.settle.running) {
    console.log('[Schedule] 竞彩结算已在运行，跳过');
    return;
  }
  taskStatus.settle.running = true;
  try {
    console.log('[Schedule] 开始竞彩结算...');
    const jcResult = await runPython('auto_settle.py');
    taskStatus.settle.lastRun = new Date().toISOString();
    taskStatus.settle.lastResult = jcResult;
    console.log(`[Schedule] 竞彩结算完成:`, JSON.stringify(jcResult).slice(0, 200));
  } catch (err) {
    taskStatus.settle.lastRun = new Date().toISOString();
    taskStatus.settle.lastResult = { error: err.message };
    console.error(`[Schedule] 竞彩结算失败:`, err.message);
  } finally {
    taskStatus.settle.running = false;
  }

  // CT彩结算（使用CT目录下的脚本）
  try {
    console.log('[Schedule] 开始CT彩结算...');
    const ctScriptPath = path.join(__dirname, '..', 'CT', 'ct_auto_settle.py');
    const env = { ...process.env, PATH: '/usr/bin:/usr/local/bin:' + (process.env.PATH || '') };
    if (!env.DATABASE_URL) env.DATABASE_URL = DATABASE_URL;
    
    const ctResult = await new Promise((resolve, reject) => {
      execFile('/usr/bin/python3', [ctScriptPath], {
        cwd: path.join(__dirname, '..', 'CT'),
        env,
        timeout: 300000,
        maxBuffer: 10 * 1024 * 1024
      }, (error, stdout, stderr) => {
        if (error) {
          console.error(`[Python ct_auto_settle.py] Error:`, error.message);
          if (stderr) console.error(`[Python ct_auto_settle.py] Stderr:`, stderr);
          reject(new Error(stderr || error.message));
          return;
        }
        if (stderr) console.warn(`[Python ct_auto_settle.py] Stderr:`, stderr);
        try {
          resolve(JSON.parse(stdout.trim()));
        } catch {
          resolve({ output: stdout.trim() });
        }
      });
    });
    console.log(`[Schedule] CT彩结算完成:`, JSON.stringify(ctResult).slice(0, 200));
  } catch (err) {
    console.error(`[Schedule] CT彩结算失败:`, err.message);
  }
}

// 每日数据备份 (凌晨2点)
async function runDailyBackup() {
  const { execFile } = require('child_process');
  const scriptPath = path.join(__dirname, '..', 'scripts', 'daily_backup.py');
  const env = { ...process.env, PATH: '/usr/bin:/usr/local/bin:' + (process.env.PATH || '') };
  if (!env.DATABASE_URL) env.DATABASE_URL = DATABASE_URL;

  return new Promise((resolve, reject) => {
    execFile('/usr/bin/python3', [scriptPath], {
      cwd: __dirname,
      env,
      timeout: 300000,
      maxBuffer: 10 * 1024 * 1024
    }, (error, stdout, stderr) => {
      if (error) {
        console.error('[Backup] Error:', error.message);
        if (stderr) console.error('[Backup] Stderr:', stderr);
        reject(error);
        return;
      }
      console.log('[Backup] Output:', stdout.slice(0, 500));
      resolve(stdout);
    });
  });
}

// 注册定时任务
scheduleDaily(10, 0, 'JC上午抓取', runJcDiscover);
scheduleDaily(18, 0, 'JC下午抓取', runJcDiscover);
scheduleDaily(10, 30, 'CT每日抓取', runCtDiscover);
scheduleDaily(0, 30, '每日凌晨结算', runDailySettle);
scheduleDaily(12, 30, '每日午间结算', runDailySettle);
scheduleDaily(2, 0, '每日数据备份', runDailyBackup);

// ============ 自监控看门狗 ============
// 每3分钟自检，确保server.js在容器唤醒后能自动恢复
setInterval(async () => {
  try {
    const client = await pgPool.connect();
    try { await client.query('SELECT 1'); } finally { client.release(); }
    console.log(`[Watchdog] OK - ${new Date().toISOString()} - settle_running=${taskStatus.settle.running} discover_running=${taskStatus.discover.running}`);
  } catch (err) {
    console.error('[Watchdog] 数据库异常，尝试恢复...');
    await checkAndRecoverDB();
  }
}, 3 * 60 * 1000);

server.listen(PORT, HOST, () => {
  console.log(`Server running at http://${HOST}:${PORT}`);
  console.log(`API endpoints: /api/matches, /api/predictions, /api/chain_bets, /api/ai_stats, /api/betting_daily, /api/betting_summary, /api/briefs`);
  
  // 启动时检查数据库连接（容器唤醒后连接可能已失效）
  checkAndRecoverDB().catch(e => console.error('[Server] 启动DB检查失败:', e.message));
  
  // 初始化比赛级别定时结算（不阻塞启动）
  initializeSettleTimers().catch(err => console.error('[AutoSettle] 启动初始化失败:', err.message));
});
// force-redeploy: 1788343553
