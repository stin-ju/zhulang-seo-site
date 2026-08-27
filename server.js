const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PORT = 5000;
const JC_PORT = 5002;
const CT_PORT = 5001;

// ============================
// 启动子服务
// ============================
function startService(name, scriptPath, cwd, extraEnv = {}) {
  console.log(`[Router] 启动 ${name}: ${scriptPath}`);
  const proc = spawn('node', [scriptPath], {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, ...extraEnv }
  });
  proc.stdout.on('data', d => console.log(`[${name}]`, d.toString().trim()));
  proc.stderr.on('data', d => console.error(`[${name}]`, d.toString().trim()));
  proc.on('exit', (code) => {
    console.error(`[Router] ${name} 退出 (code=${code}), 5秒后重启`);
    setTimeout(() => startService(name, scriptPath, cwd, extraEnv), 5000);
  });
  return proc;
}

const ctPath = path.join(__dirname, 'CT', 'server_traditional.js');
const jcPath = path.join(__dirname, 'JC', 'server.js');

if (fs.existsSync(ctPath)) startService('CT', ctPath, path.join(__dirname, 'CT'));
else console.warn('[Router] CT服务文件不存在:', ctPath);

if (fs.existsSync(jcPath)) startService('JC', jcPath, path.join(__dirname, 'JC'), { DEPLOY_RUN_PORT: '5002', PORT: '5002' });
else console.warn('[Router] JC服务文件不存在:', jcPath);

// ============================
// 反向代理
// ============================
function proxy(req, res, targetPort) {
  const opt = {
    hostname: '127.0.0.1',
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${targetPort}` }
  };
  const proxyReq = http.request(opt, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });
  proxyReq.on('error', (e) => {
    console.error(`[Router] 代理到 ${targetPort} 失败:`, e.message);
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Service unavailable', port: targetPort }));
  });
  req.pipe(proxyReq);
}

// ============================
// 路由分发（仅此一处判断JC/CT归属）
// ============================
const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0];

  // 根路径直接返回ix.html内容（不代理不重定向，避免CDN/代理层404或缓存问题）
  if (url === '/') {
    const ixPath = path.join(__dirname, 'JC', 'ix.html');
    fs.readFile(ixPath, (err, data) => {
      if (err) {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('ix.html not found');
        return;
      }
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      });
      res.end(data);
    });
    return;
  }

  // CT传统彩路由 → 5001端口
  if (url.startsWith('/api/traditional-lottery/') || url === '/ct.html' || url === '/CT/ct.html') {
    return proxy(req, res, CT_PORT);
  }

  // 其他所有请求 → JC竞彩 5002端口
  proxy(req, res, JC_PORT);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[Router] 路由分发服务运行: http://0.0.0.0:${PORT}`);
  console.log(`[Router]   CT(传统彩) → 127.0.0.1:${CT_PORT}`);
  console.log(`[Router]   JC竞彩) → 127.0.0.1:${JC_PORT}`);
});
