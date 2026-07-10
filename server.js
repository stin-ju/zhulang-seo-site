const http = require('http');
const fs = require('fs');
const path = require('path');

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
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

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
});
