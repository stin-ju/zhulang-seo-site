// unified.js - 单进程统一入口（合并JC竞彩 + CT传统彩），无子进程、无多端口
// rebuild: 20260930-explicit-static-map (前端文件唯一来源 JC/)
const http = require('http');
const fs = require('fs');
const path = require('path');
const ctApp = require('./CT/server_traditional.js');
const jcServer = require('./JC/server.js');

const PORT = process.env.DEPLOY_RUN_PORT || 5000;
const HOST = '0.0.0.0';

const CT_PREFIXES = ['/api/traditional-lottery/', '/ct.html', '/CT/ct.html'];

// 前端静态文件唯一来源：JC 目录（消除根目录同名文件歧义）
const JC_WEB_ROOT = path.join(__dirname, 'JC');
const STATIC_WHITELIST = new Set([
  '/index.js', '/api.js', '/styles.css',
  '/index.html', '/ix.html',
  '/football.html', '/basketball.html', '/ai-model.html',
  '/analysis.html', '/calculator.html', '/admin.html',
  '/favicon.ico', '/logo.png'
]);
const MIME = {
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.png': 'image/png'
};

function serveStatic(req, res, relPath) {
  const filePath = path.join(JC_WEB_ROOT, relPath);
  // 防目录稿越
  if (!filePath.startsWith(JC_WEB_ROOT)) { res.writeHead(403); res.end('Forbidden'); return; }
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404, { 'Content-Type': 'text/plain' }); res.end('Not found'); return; }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': 'no-cache, no-store, must-revalidate'
    });
    res.end(data);
  });
}

const unified = http.createServer((req, res) => {
  const url = (req.url || '/').split('?')[0];
  if (url === '/health' || url === '/_health') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' });
    res.end(JSON.stringify({ status: 'ok', uptime: process.uptime(), timestamp: Date.now() }));
    return;
  }
  // 显式静态文件：始终从 JC 目录提供
  if (STATIC_WHITELIST.has(url)) {
    if (url === '/ix.html' || url === '/index.html') {
      serveStatic(req, res, 'ix.html');
      return;
    }
    serveStatic(req, res, '.' + url);
    return;
  }
  if (url === '/') {
    serveStatic(req, res, 'ix.html');
    return;
  }
  const isCt = CT_PREFIXES.some(p => p.endsWith('/') ? url.startsWith(p) : url === p);
  if (isCt) { ctApp(req, res); return; }
  jcServer.emit('request', req, res);
});

unified.listen(PORT, HOST, () => {
  console.log('[Unified] 单进程服务运行于 ' + PORT + '（静态根=JC/）');
});
