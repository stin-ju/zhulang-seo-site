/**
 * server_traditional.js - 传统彩独立服务
 * 端口: 5001 (可通过 TRADITIONAL_PORT 环境变量覆盖)
 * 数据库: 使用主服务的同一个 PostgreSQL 数据库
 */

const express = require('express');
const { Pool } = require('pg');
const path = require('path');
const fs = require('fs');

// ============ 全局异常捕获（防止进程崩溃）============
process.on('uncaughtException', (err) => {
  console.error('[CT] 未捕获异常（进程保持运行）:', err.message);
  console.error(err.stack);
});

process.on('unhandledRejection', (reason) => {
  console.error('[CT] 未处理的Promise拒绝（进程保持运行）:', reason);
});

// ============ 配置 ============
const PORT = parseInt(process.env.TRADITIONAL_PORT || '5001', 10);
const DATABASE_URL = process.env.DATABASE_URL || '';

// 加载 .env 文件
try {
  const envPath = path.join(__dirname, '.env');
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf-8');
    envContent.split('\n').forEach(line => {
      const match = line.match(/^([^#=]+)=(.*)$/);
      if (match) {
        const key = match[1].trim();
        const value = match[2].trim();
        if (!process.env[key]) {
          process.env[key] = value;
        }
      }
    });
  }
} catch (e) {
  console.error('Failed to load .env:', e.message);
}

// 重新读取 DATABASE_URL
const dbUrl = process.env.DATABASE_URL || DATABASE_URL;

// ============ 数据库连接 ============
const pool = new Pool({
  connectionString: dbUrl,
  max: 5,
  idleTimeoutMillis: 30000,
});

pool.on('error', (err) => {
  console.error('Unexpected database error:', err);
});

// ============ Express 应用 ============
const app = express();

// CORS 支持
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  next();
});

// JSON 解析
app.use(express.json());

// ============ API 路由 ============

/**
 * GET /api/traditional-lottery/predict
 * 查询传统彩预测数据 - 返回所有期号的比赛级别数据
 * 支持 ?issue=xxx 筛选指定期号
 * 返回格式: { success: true, data: { sfc: [], htf: [], jqc: [] } }
 */
app.get('/api/traditional-lottery/predict', async (req, res) => {
  try {
    const issueFilter = req.query.issue;

    // 查询所有 CT 比赛（统一 matches 表）
    const matchesRes = await pool.query(`
      SELECT id, home_team, away_team, status,
             metadata->>'match_time' as match_time,
             metadata->>'league' as league,
             metadata->>'home_score' as home_score,
             metadata->>'away_score' as away_score,
             metadata->>'sell_end' as sell_end,
             metadata->>'issue' as issue
      FROM matches
      WHERE id LIKE 'CT%'
      ORDER BY id
    `);

    // 查询所有 CT 预测（统一 predictions 表）
    const predsRes = await pool.query(`
      SELECT match_id, ai_name, spf_pred, ct_ren9, is_settled, hit_status, spf_hit, confidence
      FROM predictions
      WHERE match_id LIKE 'CT%' AND spf_pred IS NOT NULL
      ORDER BY match_id, ai_name
    `);

    // 建立 比赛id -> 比赛信息 映射
    const matchMap = new Map();
    for (const r of matchesRes.rows) {
      const id = r.id;
      const numMatch = id.match(/^CT\d+_(\d+)$/);
      if (!numMatch) continue;
      const numRaw = numMatch[1];
      const numStripped = String(parseInt(numRaw, 10));
      const issue = (r.issue ? 'CT' + r.issue : id.replace(/_\d+$/, ''));

      const hs = r.home_score != null && r.home_score !== '' ? parseInt(r.home_score, 10) : null;
      const as_ = r.away_score != null && r.away_score !== '' ? parseInt(r.away_score, 10) : null;
      let officialResult = null;
      if (hs !== null && as_ !== null) {
        officialResult = hs > as_ ? '3' : (hs === as_ ? '1' : '0');
      }

      matchMap.set(id, {
        match_id: id,
        match_num: numStripped,
        issue: issue,
        home_team: r.home_team || '',
        away_team: r.away_team || '',
        league: r.league || '',
        match_time: r.match_time || '',
        lottery_type: 'sfc',
        home_score: hs,
        away_score: as_,
        result: officialResult,
        sell_end: r.sell_end || '',
        // 该场比赛的投注状态（on_sale=在售/未开赛）
        on_sale: (r.status === '未开赛')
      });
    }

    // 追加 AI 预测到对应比赛
    for (const p of predsRes.rows) {
      const rec = matchMap.get(p.match_id);
      if (!rec) continue;

      // 任9：该场是否在 AI 的任9推荐中
      const numStripped = String(parseInt(p.match_id.replace(/^CT\d+_/, ''), 10));
      let isR9 = false;
      if (Array.isArray(p.ct_ren9)) {
        isR9 = p.ct_ren9.some(n => String(n).replace(/^0+/, '') === numStripped);
      }

      // 命中状态：优先 hit_status.spf_hit，其次 hit_status.hit，再次 spf_hit 列
      let hit = null;
      if (p.is_settled) {
        const hs = p.hit_status && typeof p.hit_status === 'object' ? p.hit_status : {};
        hit = (hs.spf_hit != null) ? hs.spf_hit
            : (hs.hit != null) ? hs.hit
            : (hs.spf != null) ? hs.spf
            : (p.spf_hit != null) ? p.spf_hit
            : null;
      }

      rec[p.ai_name] = {
        prediction: p.spf_pred != null ? String(p.spf_pred) : null,
        confidence: p.confidence || null,
        is_r9: isR9,
        is_settled: p.is_settled || false,
        hit: hit,
        hit_details: p.hit_status || null
      };
    }

    // 胜负彩：全部比赛（含 in-sale + 历史）
    let sfc = Array.from(matchMap.values());

    // 期号过滤：支持 ?issue=CT26122 或 ?issue=26122
    if (issueFilter) {
      const f = String(issueFilter).replace(/^CT/i, '');
      sfc = sfc.filter(it => String(it.issue).replace(/^CT/i, '') === f);
    }

    const responseData = {
      sfc: sfc,
      htf: [],
      jqc: []
    };

    res.json({ success: true, data: responseData });
  } catch (err) {
    console.error('[TraditionalLottery] /predict error:', err.message);
    res.status(500).json({ error: 'Internal server error', message: err.message });
  }
});

/**
 * GET /api/traditional-lottery/latest
 * 查询最新的传统彩预测
 */
app.get('/api/traditional-lottery/latest', async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        game_type,
        ai_name,
        issue,
        predictions,
        matches_info,
        created_at
      FROM traditional_predictions
      WHERE game_type IN ('胜负彩', '半全场', '进球彩', '任9')
        AND issue = (SELECT MAX(issue) FROM traditional_predictions WHERE issue ~ '^[0-9]+$')
      ORDER BY game_type, ai_name
    `);

    const latest = result.rows.map(row => ({
      game_type: row.game_type,
      ai_name: row.ai_name,
      predictions: typeof row.predictions === 'string' 
        ? (() => { try { return JSON.parse(row.predictions); } catch { return {}; } })()
        : (row.predictions || {}),
      matches_info: typeof row.matches_info === 'string'
        ? (() => { try { return JSON.parse(row.matches_info); } catch { return {}; } })()
        : (row.matches_info || {}),
      created_at: row.created_at
    }));

    res.json({ success: true, data: latest });
  } catch (err) {
    console.error('[TraditionalLottery] /latest error:', err.message);
    res.status(500).json({ error: 'Internal server error', message: err.message });
  }
});

/**
 * GET /api/traditional-lottery/scores
 * 查询CT比赛的实际比分（用于赛果列显示）
 */
app.get('/api/traditional-lottery/scores', async (req, res) => {
  try {
    const issueFilter = req.query.issue;
    let query = `SELECT id, home_team, away_team, metadata->>'home_score' as home_score, metadata->>'away_score' as away_score, metadata->>'half_home_score' as half_home, metadata->>'half_away_score' as half_away, status FROM matches WHERE id LIKE 'CT%'`;
    const params = [];
    if (issueFilter) {
      query += ` AND id LIKE $1`;
      params.push(`CT${issueFilter}_%`);
    }
    query += ` ORDER BY id`;
    const result = await pool.query(query, params);
    const scores = {};
    for (const row of result.rows) {
      scores[row.id] = {
        home_score: row.home_score ? parseInt(row.home_score) : null,
        away_score: row.away_score ? parseInt(row.away_score) : null,
        half_home: row.half_home ? parseInt(row.half_home) : null,
        half_away: row.half_away ? parseInt(row.half_away) : null,
        status: row.status
      };
    }
    res.json({ success: true, data: scores });
  } catch (err) {
    console.error('[TraditionalLottery] /scores error:', err.message);
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * GET /api/traditional-lottery/fetch
 * 触发传统彩赛程抓取 + 4种玩法预测（异步模式）
 */
app.get('/api/traditional-lottery/fetch', async (req, res) => {
  const ctDiscoverPath = path.join(__dirname, '..', 'JC', 'ct_discover.py');
  const predictPath = path.join(__dirname, '..', 'JC', 'traditional_lottery_predict.py');
  
  if (!fs.existsSync(ctDiscoverPath)) {
    return res.status(501).json({ 
      error: 'Not Implemented',
      message: 'ct_discover.py script not found'
    });
  }

  if (!fs.existsSync(predictPath)) {
    return res.status(501).json({ 
      error: 'Not Implemented',
      message: 'traditional_lottery_predict.py script not found'
    });
  }

  // 立即返回，后台异步执行
  res.json({ 
    success: true, 
    message: 'fetch started',
    timestamp: new Date().toISOString()
  });

  // 后台异步执行
  const { spawn } = require('child_process');
  const pythonEnv = { ...process.env, PYTHONUNBUFFERED: '1' };
  const jcDir = path.join(__dirname, '..', 'JC');

  // Step 1: 执行赛程抓取
  console.log('[TraditionalLottery] Step 1: 执行 ct_discover.py...');
  const discoverProc = spawn('python3', [ctDiscoverPath], {
    cwd: jcDir,
    env: pythonEnv,
  });

  let discoverOutput = '';
  discoverProc.stdout.on('data', (data) => {
    discoverOutput += data.toString();
  });
  discoverProc.stderr.on('data', (data) => {
    console.error(`[TraditionalLottery] ct_discover stderr: ${data}`);
  });

  discoverProc.on('exit', (code) => {
    if (code !== 0) {
      console.error(`[TraditionalLottery] ct_discover.py 退出码: ${code}`);
      return;
    }

    try {
      const discoverData = JSON.parse(discoverOutput.trim());
      const saved = discoverData.saved || 0;
      console.log(`[TraditionalLottery] ct_discover完成, saved=${saved}`);

      // Step 2: 如果有新比赛，依次执行4种玩法的预测
      if (saved > 0) {
        const gameTypes = ['胜负彩', '任9', '半全场', '进球彩'];
        let gameIndex = 0;

        const runNextGame = () => {
          if (gameIndex >= gameTypes.length) {
            console.log('[TraditionalLottery] 所有玩法预测完成');
            return;
          }

          const gameType = gameTypes[gameIndex++];
          console.log(`[TraditionalLottery] Step 2: 执行 ${gameType} 预测...`);

          const predictProc = spawn('python3', [predictPath, '--game', gameType, '--force'], {
            cwd: jcDir,
            env: pythonEnv,
          });

          predictProc.stdout.on('data', (data) => {
            // 可选：记录输出
          });
          predictProc.stderr.on('data', (data) => {
            console.error(`[TraditionalLottery] ${gameType} stderr: ${data}`);
          });

          predictProc.on('exit', (exitCode) => {
            if (exitCode === 0) {
              console.log(`[TraditionalLottery] ${gameType} 预测完成`);
            } else {
              console.error(`[TraditionalLottery] ${gameType} 预测失败, 退出码: ${exitCode}`);
            }
            // 继续执行下一个玩法
            runNextGame();
          });
        };

        runNextGame();
      }
    } catch (err) {
      console.error(`[TraditionalLottery] 解析ct_discover输出失败:`, err.message);
    }
  });
});

/**
 * GET /ct.html
 * 返回传统彩前端页面
 */
app.get('/ct.html', (req, res) => {
  const ctPath = path.join(__dirname, 'ct.html');
  if (fs.existsSync(ctPath)) {
    res.sendFile(ctPath);
  } else {
    // 尝试 public 目录
    const publicCtPath = path.join(__dirname, 'public', 'ct.html');
    if (fs.existsSync(publicCtPath)) {
      res.sendFile(publicCtPath);
    } else {
      res.status(404).json({ error: 'ct.html not found' });
    }
  }
});

// ============ 404 处理 ============
app.use((req, res) => {
  res.status(404).json({ 
    error: 'Not Found',
    message: `Route ${req.method} ${req.path} not found in traditional lottery server`,
    available_routes: [
      'GET /api/traditional-lottery/predict',
      'GET /api/traditional-lottery/latest',
      'GET /api/traditional-lottery/fetch',
      'GET /ct.html'
    ]
  });
});

// ============ 启动服务 ============
const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`Traditional Lottery server running on port ${PORT}`);
  console.log(`Database: ${dbUrl ? 'connected' : 'NOT CONFIGURED'}`);
  console.log(`Available routes:`);
  console.log(`  GET /api/traditional-lottery/predict`);
  console.log(`  GET /api/traditional-lottery/latest`);
  console.log(`  GET /api/traditional-lottery/fetch`);
  console.log(`  GET /ct.html`);
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`[CT] 端口 ${PORT} 被占用，等待释放...`);
    // 不崩溃，让路由器来重启
    setTimeout(() => process.exit(1), 2000);
  } else {
    console.error('[CT] 服务器错误:', err);
  }
});

// 优雅关闭
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down gracefully...');
  try { await pool.end(); } catch (_) {}
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('SIGINT received, shutting down gracefully...');
  try { await pool.end(); } catch (_) {}
  process.exit(0);
});
