const http = require('http');
const fs = require('fs');
const path = require('path');

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
  return {
    url: process.env.COZE_SUPABASE_URL || 'https://br-vocal-kea-f584f76e.supabase2.aidap-global.cn-beijing.volces.com',
    key: process.env.COZE_SUPABASE_ANON_KEY || ''
  };
}

async function querySupabase(table, params = {}) {
  const { url, key } = getSupabaseConfig();
  const queryStr = new URLSearchParams();
  if (params.select) queryStr.set('select', params.select);
  if (params.order) queryStr.set('order', params.order);
  if (params.limit) queryStr.set('limit', params.limit);
  if (params.filter) {
    for (const [k, v] of Object.entries(params.filter)) {
      queryStr.set(k, v);
    }
  }

  const resp = await fetch(`${url}/rest/v1/${table}?${queryStr}`, {
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

  // ============ API Routes (before static files) ============

  try {
    // GET /api/matches
    if (pathname === '/api/matches' && req.method === 'GET') {
      const data = await querySupabase('matches', {
        select: '*',
        order: 'match_time.asc'
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/predictions
    if (pathname === '/api/predictions' && req.method === 'GET') {
      const data = await querySupabase('predictions', {
        select: '*',
        order: 'id.asc'
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/chain_bets
    if (pathname === '/api/chain_bets' && req.method === 'GET') {
      const data = await querySupabase('chain_bets', {
        select: '*',
        order: 'bet_date.desc,ai_name.asc'
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/ai_stats
    if (pathname === '/api/ai_stats' && req.method === 'GET') {
      const data = await querySupabase('ai_stats', {
        select: '*',
        order: 'total_hits.desc'
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/betting_daily
    if (pathname === '/api/betting_daily' && req.method === 'GET') {
      const data = await querySupabase('betting_daily', {
        select: '*',
        order: 'date.desc'
      });
      res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
      res.end(JSON.stringify(data));
      return;
    }

    // GET /api/betting_summary
    if (pathname === '/api/betting_summary' && req.method === 'GET') {
      const data = await querySupabase('betting_summary', {
        select: '*',
        order: 'id.asc'
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

    const stream = fs.createReadStream(filePath);
    res.writeHead(200, { 'Content-Type': contentType });
    stream.pipe(res);
    stream.on('error', () => {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end('500 Internal Server Error');
    });
  });
});

server.listen(PORT, HOST, () => {
  console.log(`Server running at http://${HOST}:${PORT}/`);
  console.log(`Supabase URL: ${getSupabaseConfig().url}`);
  console.log(`API endpoints: /api/matches, /api/predictions, /api/chain_bets, /api/ai_stats, /api/betting_daily, /api/betting_summary, /api/briefs`);
});
