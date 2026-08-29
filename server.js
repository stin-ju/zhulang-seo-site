const http = require('http');
const net = require('net');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PORT = 5000;
const JC_PORT = 5002;
const CT_PORT = 5001;

// ============================
// 子服务注册表（名称→脚本路径/端口/启动状态）
// ============================
const serviceRegistry = {};

// ============================
// 启动子服务
// ============================
function startService(name, scriptPath, cwd, extraEnv = {}) {
  const port = extraEnv.PORT || extraEnv.DEPLOY_RUN_PORT || (name === 'CT' ? CT_PORT : JC_PORT);
  console.log(`[Router] 启动 ${name}: ${scriptPath}`);

  // 标记为启动中
  if (serviceRegistry[name]) serviceRegistry[name].starting = true;

  const proc = spawn('node', [scriptPath], {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, ...extraEnv }
  });
  proc.stdout.on('data', d => console.log(`[${name}]`, d.toString().trim()));
  proc.stderr.on('data', d => console.error(`[${name}]`, d.toString().trim()));
  proc.on('exit', (code) => {
    if (serviceRegistry[name]) {
      serviceRegistry[name].starting = false;
      serviceRegistry[name].exited = true;  // 标记进程已退出，供ensureServiceAlive判断
    }
    console.error(`[Router] ${name} 退出 (code=${code}), 5秒后重启`);
    setTimeout(() => startService(name, scriptPath, cwd, extraEnv), 5000);
  });

  // 注册服务信息
  serviceRegistry[name] = { proc, scriptPath, cwd, extraEnv, port, starting: true, exited: false };

  // 监听端口就绪
  waitForPort(port, 30000).then(ok => {
    if (serviceRegistry[name]) serviceRegistry[name].starting = false;
    if (ok) console.log(`[Router] ${name} 端口 ${port} 已就绪`);
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
// 端口探测（TCP connect 检测）
// ============================
function checkPort(port) {
  return new Promise(resolve => {
    const sock = new net.Socket();
    sock.setTimeout(800);
    sock.on('connect', () => { sock.destroy(); resolve(true); });
    sock.on('timeout', () => { sock.destroy(); resolve(false); });
    sock.on('error', () => { sock.destroy(); resolve(false); });
    sock.connect(port, '127.0.0.1');
  });
}

// 等待端口就绪（轮询）
function waitForPort(port, maxWaitMs) {
  const start = Date.now();
  return new Promise(resolve => {
    const tick = async () => {
      if (await checkPort(port)) return resolve(true);
      if (Date.now() - start >= maxWaitMs) return resolve(false);
      setTimeout(tick, 500);
    };
    tick();
  });
}

// ============================
// 确保子服务存活（代理层触发拉起）
// ============================
const healCooldowns = {};
function ensureServiceAlive(name) {
  const svc = serviceRegistry[name];
  if (!svc) return;
  // 冷却：30秒内不重复触发
  if (healCooldowns[name] && Date.now() - healCooldowns[name] < 30000) return;
  healCooldowns[name] = Date.now();

  // 检查进程是否还在（进程自崩时proc.killed不置位，用exited标志兜底）
  if (svc.proc && !svc.proc.killed && !svc.exited) {
    // 进程在但端口没起来，可能还在启动中，不干预
    return;
  }
  // 进程不在了，主动拉起
  console.log(`[Router] 自愈: ${name} 进程不在，主动拉起`);
  startService(name, svc.scriptPath, svc.cwd, svc.extraEnv);
}

// ============================
// 健壮反向代理（带重试 + 503兜底）
// ============================
const PROXY_MAX_WAIT = 12000;   // 最长等待12秒
const PROXY_RETRY_MS = 500;     // 每500ms重试一次

function proxy(req, res, targetPort) {
  const serviceName = targetPort === CT_PORT ? 'CT' : targetPort === JC_PORT ? 'JC' : 'unknown';

  // 先收集请求体（POST/PUT等需要重放）
  const chunks = [];
  req.on('data', chunk => chunks.push(chunk));
  req.on('end', () => {
    const bodyBuf = Buffer.concat(chunks);
    doProxyWithRetry(req, res, targetPort, serviceName, bodyBuf, Date.now());
  });
  // 如果请求没有body（GET），end事件可能不会触发
  // 对于GET请求，req.on('end') 在 stream 结束时触发，http.IncomingMessage 会在无body时立即触发end
}

function doProxyWithRetry(req, res, targetPort, serviceName, bodyBuf, startTime) {
  const elapsed = Date.now() - startTime;

  // 超时：返回503
  if (elapsed >= PROXY_MAX_WAIT) {
    console.error(`[Router] ${serviceName}(${targetPort}) 等待${PROXY_MAX_WAIT}ms仍不可用，返回503`);
    if (!res.headersSent) {
      res.writeHead(503, {
        'Content-Type': 'application/json',
        'Retry-After': '5'
      });
      res.end(JSON.stringify({
        success: false,
        message: '服务正在启动，请5秒后刷新重试',
        retry_after: 5
      }));
    }
    return;
  }

  const opt = {
    hostname: '127.0.0.1',
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${targetPort}` }
  };
  if (bodyBuf.length > 0) {
    opt.headers['content-length'] = bodyBuf.length;
    delete opt.headers['transfer-encoding'];
  }

  const proxyReq = http.request(opt, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on('error', (e) => {
    if (e.code === 'ECONNREFUSED' || e.code === 'ECONNRESET') {
      // 目标不可用，触发拉起并等待重试
      ensureServiceAlive(serviceName);
      console.log(`[Router] ${serviceName}(${targetPort}) 连接被拒，等待重试... (${Math.round(elapsed/1000)}s/${PROXY_MAX_WAIT/1000}s)`);
      setTimeout(() => {
        doProxyWithRetry(req, res, targetPort, serviceName, bodyBuf, startTime);
      }, PROXY_RETRY_MS);
    } else {
      // 其他错误（如 ETIMEDOUT），也重试
      console.error(`[Router] 代理到 ${targetPort} 失败: ${e.code || e.message}`);
      setTimeout(() => {
        doProxyWithRetry(req, res, targetPort, serviceName, bodyBuf, startTime);
      }, PROXY_RETRY_MS);
    }
  });

  if (bodyBuf.length > 0) {
    proxyReq.write(bodyBuf);
  }
  proxyReq.end();
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
  console.log(`[Router]   JC竞彩 → 127.0.0.1:${JC_PORT}`);
});
