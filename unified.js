// unified.js - 单进程统一入口（合并JC竞彩 + CT传统彩），无子进程、无多端口
const http = require('http');
const fs = require('fs');
const path = require('path');
const ctApp = require('./CT/server_traditional.js');
const jcServer = require('./JC/server.js');

const PORT = process.env.DEPLOY_RUN_PORT || 5000;
const HOST = '0.0.0.0';

const CT_PREFIXES = ['/api/traditional-lottery/', '/ct.html', '/CT/ct.html'];

const unified = http.createServer((req, res) => {
  const url = (req.url || '/').split('?')[0];
  if (url === '/health' || url === '/_health') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' });
    res.end(JSON.stringify({ status: 'ok', uptime: process.uptime(), timestamp: Date.now() }));
    return;
  }
  if (url === '/') {
    const ixPath = path.join(__dirname, 'JC', 'ix.html');
    fs.readFile(ixPath, (err, data) => {
      if (err) { res.writeHead(404, { 'Content-Type': 'text/plain' }); res.end('ix.html not found'); return; }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache, no-store, must-revalidate' });
      res.end(data);
    });
    return;
  }
  const isCt = CT_PREFIXES.some(p => p.endsWith('/') ? url.startsWith(p) : url === p);
  if (isCt) { ctApp(req, res); return; }
  jcServer.emit('request', req, res);
});

unified.listen(PORT, HOST, () => {
  console.log('[Unified] 单进程服务运行于 ' + PORT);
});
