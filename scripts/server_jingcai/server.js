// server.js - 竞彩服务入口
// 端口：5000（竞彩专用）
// 职责：HTTP路由 + 静态文件服务
const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

// 模块化依赖
const {
  DATABASE_URL, pgPool, taskStatus, REPORT_PATH,
  readBody, runPython, generateReport,
  cleanAnalysis, normalizeMatch, normalizePrediction
} = require('./db');
const { checkAndGenerateCommentary } = require('./commentary');
const { startScheduler } = require('./auto-settle');

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

    // ======== GET /api/matches ========
    if (pathname === '/api/matches' && req.method === 'GET') {
      const date = parsedUrl.searchParams.get('date');
      const sport = parsedUrl.searchParams.get('sport');
      const includePredictions = parsedUrl.searchParams.get('include_predictions') === 'true';

      let query = `SELECT * FROM matches`;
      const params = [];
      let paramIdx = 1;

      // 默认过滤已完赛比赛，除非明确请求 include_finished=true
      const includeFinished = parsedUrl.searchParams.get('include_finished') === 'true';
      let hasWhere = false;

      if (!includeFinished) {
        query += ` WHERE status != '已完赛'`;
        hasWhere = true;
      }

      if (sport) {
        query += hasWhere ? ` AND sport_type = $${paramIdx}` : ` WHERE sport_type = $${paramIdx}`;
        params.push(sport);
        paramIdx++;
        hasWhere = true;
      }

      if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
        const [year, month, day] = date.split('-').map(Number);
        const d = new Date(year, month - 1, day);
        d.setDate(d.getDate() + 1);
        const nextDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        query += hasWhere ? ` AND metadata->>'match_date' >= $${paramIdx} AND metadata->>'match_date' < $${paramIdx + 1}` : ` WHERE metadata->>'match_date' >= $${paramIdx} AND metadata->>'match_date' < $${paramIdx + 1}`;
        params.push(date, nextDate);
        paramIdx += 2;
      }

      query += ` ORDER BY metadata->>'match_date' ASC, metadata->>'match_time' ASC`;

      const { rows } = await pgPool.query(query, params);
      let enriched = rows.map(normalizeMatch);

      // Auto-mark past unstarted matches as started
      const now = new Date();
      enriched.forEach(m => {
        if (new Date(m.match_time) < now && (m.status === '未开赛' || m.status === 'on_sale')) {
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
        allPreds.forEach(p => {
          const matchId = String(p.match_id);
          if (!predictionsByMatch[matchId]) predictionsByMatch[matchId] = [];
          predictionsByMatch[matchId].push(p);
        });

        enriched.forEach(m => {
          m.predictions = predictionsByMatch[String(m.id)] || [];
        });
      }

      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        ...CORS_HEADERS
      });
      res.end(JSON.stringify(enriched));
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
      const sport = parsedUrl.searchParams.get('sport') || 'football';

      const { rows } = await pgPool.query(
        `SELECT p.*, m.sport_type, m.metadata->>'match_date' as match_date, m.metadata->>'match_time' as match_time
         FROM predictions p
         JOIN matches m ON m.id = p.match_id
         WHERE m.sport_type = $1
         ORDER BY p.id DESC`,
        [sport]
      );

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
        `SELECT * FROM matches WHERE sport_type = 'football' ORDER BY metadata->>'match_date' DESC, metadata->>'match_time' DESC LIMIT 500`
      );
      if (matchRes.rows.length === 0) {
        res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
        res.end(JSON.stringify({ date: null, matches: [], predictions: [] }));
        return;
      }

      const getDateFromMeta = (row) => {
        const meta = row.metadata || {};
        return meta.match_date || null;
      };

      const latestDate = getDateFromMeta(matchRes.rows[0]);
      const recentMatches = matchRes.rows.filter(m => getDateFromMeta(m) === latestDate);
      const matchIds = recentMatches.map(m => m.id);

      const predRes = await pgPool.query(
        `SELECT * FROM predictions WHERE match_id = ANY($1) ORDER BY id DESC`,
        [matchIds]
      );

      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify({
        date: latestDate,
        matches: recentMatches.map(normalizeMatch),
        predictions: predRes.rows.map(p => ({ ...p, analysis: cleanAnalysis(p.analysis) }))
      }));
      return;
    }

    // ======== GET /api/football-history ========
    if (pathname === '/api/football-history' && req.method === 'GET') {
      const matchRes = await pgPool.query(
        `SELECT * FROM matches WHERE sport_type = 'football' ORDER BY metadata->>'match_date' DESC, metadata->>'match_time' DESC LIMIT 5000`
      );
      const predRes = await pgPool.query(
        `SELECT * FROM predictions ORDER BY id DESC LIMIT 5000`
      );

      const getDateFromMeta = (row) => {
        const meta = row.metadata || {};
        return meta.match_date || null;
      };

      const byDate = {};
      for (const m of matchRes.rows) {
        const date = getDateFromMeta(m);
        if (!date) continue;
        if (!byDate[date]) byDate[date] = [];
        byDate[date].push(m);
      }

      const dates = Object.keys(byDate).sort().reverse();
      const historyDates = dates.slice(1);

      const result = historyDates.map(date => ({
        date,
        matches: byDate[date].map(normalizeMatch),
        predictions: predRes.rows.filter(p => byDate[date].some(m => m.id === p.match_id))
          .map(p => ({ ...p, analysis: cleanAnalysis(p.analysis) }))
      }));

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

    // POST /api/admin/report
    if (pathname === '/api/admin/report' && req.method === 'POST') {
      const result = await generateReport();
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(result));
      return;
    }

    // POST /api/admin/commentary
    if (pathname === '/api/admin/commentary' && req.method === 'POST') {
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

      const scriptPath = path.join(process.cwd(), 'scripts', 'generate_brief.py');
      execFile('python3', [scriptPath, '--date', date, '--type', type, '--output', 'both'], {
        cwd: path.join(process.cwd(), 'scripts'),
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

  } catch (err) {
    console.error('API error:', err);
    res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
    res.end(JSON.stringify({ error: 'Internal server error', message: err.message }));
    return;
  }

  // ============ Static File Routes ============
  let urlPath = pathname;
  if (urlPath === '/') urlPath = '/index.html';

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

// ============ Start Auto Settlement Scheduler ============
startScheduler();

// ============ Start Server ============
server.listen(PORT, HOST, () => {
  console.log(`[竞彩服务] running at http://${HOST}:${PORT}`);
  console.log(`[竞彩服务] API: /api/matches, /api/predictions, /api/chain_bets, /api/ai_stats, /api/betting_daily, /api/betting_summary, /api/briefs`);
  console.log(`[竞彩服务] Admin: /api/admin/discover, /api/admin/predict, /api/admin/settle, /api/admin/status, /api/admin/report, /api/admin/commentary, /api/admin/briefing`);
});
