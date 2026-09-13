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
    const issueFilter = req.query.issue
      ? String(req.query.issue).replace(/^CT/i, '')
      : null;

    // ---------- 1) 从统一 matches 表构建全部 CT 场次骨架（胜负彩） ----------
    // 在售期（CT26122+）数据来自 predictions 表（胜负彩按场×AI粒度），
    // 必须从 matches 表补齐，前端才能得到完整的期号下拉 / 默认期 / 截止时间。
    const matchesRes = await pool.query(`
      SELECT id, home_team, away_team, status,
             metadata->>'match_time' as match_time,
             metadata->>'league' as league,
             metadata->>'home_score' as home_score,
             metadata->>'away_score' as away_score,
             metadata->>'half_home_score' as half_home,
             metadata->>'half_away_score' as half_away,
             metadata->>'sell_end' as sell_end,
             metadata->>'issue' as issue,
             metadata->>'status' as meta_status
      FROM matches
      WHERE id ~ '^CT[0-9]+_[0-9]+$'
      ORDER BY id
    `);

    const scoreMap = {};
    const matchMap = { sfc: new Map(), htf: new Map(), jqc: new Map() };

    const parseScore = (v) => (v != null && v !== '' ? parseInt(v, 10) : null);

    for (const r of matchesRes.rows) {
      const numMatch = r.id.match(/^CT(\d+)_(\d+)$/);
      if (!numMatch) continue;
      const issueNum = r.issue || numMatch[1];
      const issueKey = 'CT' + issueNum;
      const numStripped = String(parseInt(numMatch[2], 10));

      const hs = parseScore(r.home_score);
      const as_ = parseScore(r.away_score);
      const hh = parseScore(r.half_home);
      const ha = parseScore(r.half_away);

      scoreMap[r.id] = { home_score: hs, away_score: as_, half_home: hh, half_away: ha };

      let officialResult = null;
      if (hs !== null && as_ !== null) {
        officialResult = hs > as_ ? '3' : (hs === as_ ? '1' : '0');
      }

      // 投注状态：metadata.status === 'on_sale'（在售/未开赛）
      const onSale = (r.meta_status === 'on_sale' || r.status === '未开赛');

      matchMap.sfc.set(r.id, {
        match_id: r.id,
        match_num: numStripped,
        issue: issueKey,
        home_team: r.home_team || '',
        away_team: r.away_team || '',
        league: r.league || '',
        match_time: r.match_time || '',
        lottery_type: 'sfc',
        home_score: hs,
        away_score: as_,
        result: officialResult,
        sell_end: r.sell_end || '',
        on_sale: onSale
      });
    }

    // ---------- 2) predictions 表的 AI 预测（单场 × AI 粒度，含 ct_issue/ct_game_type/spf_pred） ----------
    let query = `
      SELECT match_id, ai_name, ct_issue, ct_game_type, ct_ren9,
             spf_pred, goals_pred, half_full_pred, score_pred,
             prediction, confidence, hit_status, is_settled
      FROM predictions
      WHERE ct_issue IS NOT NULL AND ct_game_type IS NOT NULL
    `;
    const params = [];
    if (issueFilter) {
      query += ` AND ct_issue = $1`;
      params.push('CT' + issueFilter);
    }
    query += ` ORDER BY ct_game_type, ct_issue DESC, match_id`;

    const result = await pool.query(query, params);
    const rows = result.rows;

    const typeMap = { '胜负彩': 'sfc', '半全场': 'htf', '进球彩': 'jqc' };

    // 预收集所有任9推荐的场次（ct_ren9，jsonb 数组）
    const ren9Map = new Map(); // key: issue, value: Map(ai_name -> Set(matchNum))
    for (const row of rows) {
      if (!row.ct_ren9) continue;
      const ri = row.ct_issue.replace(/^CT/i, '');
      if (!ren9Map.has(ri)) ren9Map.set(ri, new Map());
      const am = ren9Map.get(ri);
      if (!am.has(row.ai_name)) am.set(row.ai_name, new Set());
      const ms = am.get(row.ai_name);
      const r9 = row.ct_ren9;
      const arr = Array.isArray(r9) ? r9 : (typeof r9 === 'string' ? (() => { try { return JSON.parse(r9); } catch { return []; } })() : []);
      arr.forEach(n => ms.add(String(n).replace(/^0+/, '') || '0'));
    }

    const parseJson = (v, fallback) => {
      if (typeof v === 'string') {
        try { return JSON.parse(v); } catch (e) { return fallback; }
      }
      return v != null ? v : fallback;
    };

    // predictions 表为单场 × AI 粒度，按 match_id 归并多 AI
    for (const row of rows) {
      const frontendKey = typeMap[row.ct_game_type];
      if (!frontendKey) continue;

      const mid = row.match_id;
      const numMatch = mid && mid.match(/^CT\d+_(\d+)$/);
      if (!numMatch) continue;
      const matchNumStripped = String(parseInt(numMatch[1], 10)); // 01 -> 1
      const issue = row.ct_issue.replace(/^CT/i, '');
      const matchId = mid;

      let prediction = null;
      if (frontendKey === 'sfc') {
        prediction = row.spf_pred != null ? String(row.spf_pred) : null;
      } else if (frontendKey === 'htf') {
        prediction = row.half_full_pred != null ? String(row.half_full_pred) : null;
      } else if (frontendKey === 'jqc') {
        const predObj = parseJson(row.prediction, {});
        prediction = {
          zjq_home: predObj.zjq_home || predObj.zjq_home || '',
          zjq_away: predObj.zjq_away || ''
        };
      }

      // 任9：某 AI 的推荐场次集合
      let isR9 = false;
      if (ren9Map.has(issue)) {
        const arm = ren9Map.get(issue);
        if (arm && arm.has(row.ai_name)) {
          isR9 = arm.get(row.ai_name).has(matchNumStripped);
        }
      } else {
        // 兜底：本条 ct_ren9 若含当前场序号也视为任9
        const r9 = row.ct_ren9;
        const arr = Array.isArray(r9) ? r9 : (typeof r9 === 'string' ? (() => { try { return JSON.parse(r9); } catch { return []; } })() : []);
        isR9 = arr.some(n => String(n).replace(/^0+/, '') === matchNumStripped);
      }

      const currentMap = matchMap[frontendKey];
      if (!currentMap.has(matchId)) {
        const skeleton = matchMap.sfc.get(matchId);
        const scores = scoreMap[matchId] || {};
        const homeScore = scores.home_score != null ? scores.home_score : null;
        const awayScore = scores.away_score != null ? scores.away_score : null;

        let officialResult = null;
        if (homeScore !== null && awayScore !== null) {
          if (frontendKey === 'sfc') {
            officialResult = homeScore > awayScore ? '3' : (homeScore === awayScore ? '1' : '0');
          } else if (frontendKey === 'htf') {
            const halfHome = scores.half_home;
            const halfAway = scores.half_away;
            if (halfHome !== null && halfAway !== null) {
              const halfResult = halfHome > halfAway ? '3' : (halfHome === halfAway ? '1' : '0');
              const fullResult = homeScore > awayScore ? '3' : (homeScore === awayScore ? '1' : '0');
              officialResult = halfResult + fullResult;
            }
          } else if (frontendKey === 'jqc') {
            officialResult = { home: homeScore, away: awayScore };
          }
        }

        currentMap.set(matchId, {
          match_id: matchId,
          match_num: matchNumStripped,
          issue: 'CT' + issue,
          home_team: skeleton ? skeleton.home_team : '',
          away_team: skeleton ? skeleton.away_team : '',
          league: skeleton ? skeleton.league : '',
          match_time: skeleton ? skeleton.match_time : '',
          lottery_type: frontendKey,
          home_score: homeScore,
          away_score: awayScore,
          result: officialResult,
          sell_end: skeleton ? skeleton.sell_end : '',
          on_sale: skeleton ? skeleton.on_sale : false
        });
      }

      const matchRecord = currentMap.get(matchId);
      const aiName = row.ai_name || 'system';

      let hit = null;
      if (row.is_settled) {
        const hs = parseJson(row.hit_status, null);
        if (hs && typeof hs === 'object') {
          hit = hs[frontendKey] != null ? hs[frontendKey] : (hs.spf != null ? hs.spf : null);
        }
      }

      matchRecord[aiName] = {
        prediction: prediction,
        confidence: row.confidence || null,
        is_r9: isR9,
        is_settled: row.is_settled || false,
        hit: hit,
        hit_details: row.hit_status || null
      };
    }

    let sfc = Array.from(matchMap.sfc.values());
    if (issueFilter) {
      sfc = sfc.filter(it => String(it.issue).replace(/^CT/i, '') === issueFilter);
    }

    const responseData = {
      sfc: sfc,
      htf: Array.from(matchMap.htf.values()),
      jqc: Array.from(matchMap.jqc.values())
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
