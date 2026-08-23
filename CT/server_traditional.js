/**
 * server_traditional.js - 传统彩独立服务
 * 端口: 5001 (可通过 TRADITIONAL_PORT 环境变量覆盖)
 * 数据库: 使用主服务的同一个 PostgreSQL 数据库
 */

const express = require('express');
const { Pool } = require('pg');
const path = require('path');
const fs = require('fs');

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

    // 查询所有数据，包含issue字段
    let query = `SELECT id, game_type, ai_name, issue, predictions, ren9, confidence, matches_info FROM traditional_predictions`;
    let params = [];

    if (issueFilter) {
      query += ` WHERE issue = $1`;
      params.push(issueFilter);
    }
    query += ` ORDER BY game_type, issue DESC, id`;

    const result = await pool.query(query, params);
    const rows = result.rows;

    // game_type 到前端key的映射（任9不单独映射，作为胜负彩的标记）
    const typeMap = { '胜负彩': 'sfc', '半全场': 'htf', '进球彩': 'jqc' };
    // 前端key到预测字段的映射
    const predFieldMap = { 'sfc': 'spf', 'htf': 'bqc', 'jqc': 'zjq' };
    const responseData = { sfc: [], htf: [], jqc: [] };

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集所有任9记录的推荐场次
    const ren9Map = new Map();
    for (const row of rows) {
      if (row.game_type !== '任9') continue;
      const issue = row.issue;
      if (!ren9Map.has(issue)) ren9Map.set(issue, new Map());
      const aiMap = ren9Map.get(issue);
      if (!aiMap.has(row.ai_name)) aiMap.set(row.ai_name, new Set());
      const matchSet = aiMap.get(row.ai_name);
      let preds = row.predictions;
      if (typeof preds === 'string') {
        try { preds = JSON.parse(preds); } catch(e) { preds = []; }
      }
      if (Array.isArray(preds)) {
        preds.forEach(p => {
          if (p.match) matchSet.add(String(p.match).replace(/^0+/, '') || '0');
        });
      }
    }

    // 预收集任9记录，用于胜负彩的is_r9标记
    const ren9Map = new Map(); // key: issue, value: { ai_name: Set(match_numbers) }
    for (const row of rows) {
      if (row.game_type === '任9') {
        const issue = row.issue;
        const aiName = row.ai_name;
        if (!ren9Map.has(issue)) {
          ren9Map.set(issue, {});
        }
        const issueMap = ren9Map.get(issue);
        if (!issueMap[aiName]) {
          issueMap[aiName] = new Set();
        }
        // 解析predictions获取场次
        let predsArr = row.predictions;
        if (typeof predsArr === 'string') {
          try { predsArr = JSON.parse(predsArr); } catch (e) { predsArr = []; }
        }
        if (Array.isArray(predsArr)) {
          predsArr.forEach(p => {
            const matchNum = String(p.match).replace(/^0+/, '') || '0';
            issueMap[aiName].add(matchNum);
          });
        }
      }
    }

    for (const row of rows) {
      const frontendKey = typeMap[row.game_type];
      if (!frontendKey) continue;

      // 解析 matches_info
      let matchesArr = row.matches_info;
      if (typeof matchesArr === 'string') {
        try { matchesArr = JSON.parse(matchesArr); } catch (e) { continue; }
      }
      // 兼容两种格式：数组 或 {matches: []}
      if (matchesArr && !Array.isArray(matchesArr) && Array.isArray(matchesArr.matches)) {
        matchesArr = matchesArr.matches;
      }
      if (!Array.isArray(matchesArr)) continue;

      // 解析 predictions
      let predictionsArr = row.predictions;
      if (typeof predictionsArr === 'string') {
        try { predictionsArr = JSON.parse(predictionsArr); } catch (e) { predictionsArr = null; }
      }

      const predField = predFieldMap[frontendKey] || 'spf';

      // 解析 ren9（任9推荐场次列表）
      let ren9Set = new Set();
      if (row.ren9) {
        let ren9Arr = row.ren9;
        if (typeof ren9Arr === 'string') {
          try { ren9Arr = JSON.parse(ren9Arr); } catch (e) { ren9Arr = []; }
        }
        if (Array.isArray(ren9Arr)) {
          ren9Arr.forEach(n => ren9Set.add(String(n).replace(/^0+/, '') || '0'));
        }
      }

      for (const m of matchesArr) {
        const matchNum = m.num || m.match_num || 0;
        const issue = row.issue || m.issue || '';
        const matchId = m.id || `${issue}_${matchNum}`;

        // 统一的matchNum处理（去除前导零）
        const matchNumStripped = String(matchNum).replace(/^0+/, '') || '0';

        // 获取该场比赛的预测（兼容 "1" 和 "01" 两种格式）
        let prediction = null;
        if (Array.isArray(predictionsArr)) {
          const pred = predictionsArr.find(p => {
            const pMatch = String(p.match).replace(/^0+/, '') || '0';
            return pMatch === matchNumStripped;
          });
          if (pred) prediction = pred[predField] !== undefined ? pred[predField] : null;
        }

        // 从ren9Map补充任9数据（如果当前row的ren9为空，则从任9记录中查找）
        if (frontendKey === 'sfc' && ren9Set.size === 0) {
          const issueRen9 = ren9Map.get(row.issue);
          if (issueRen9 && issueRen9[row.ai_name]) {
            ren9Set = issueRen9[row.ai_name];
          }
        }

        // 判断该场是否在任9推荐中
        if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
                if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
                if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
                if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
                if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
        if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
        if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
        if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
        if (ren9Set.size === 0 && ren9Map.has(issue)) {
          const aiRen9Map = ren9Map.get(issue);
          if (aiRen9Map && aiRen9Map.has(row.ai_name)) {
            aiRen9Map.get(row.ai_name).forEach(n => ren9Set.add(n));
          }
        }
        const isR9 = ren9Set.size > 0 ? ren9Set.has(matchNumStripped) : false;

        responseData[frontendKey].push({
          match_id: matchId,
          match_num: String(matchNum),
          issue: issue,
          home_team: m.home || m.home_team || '',
          away_team: m.away || m.away_team || '',
          league: m.league || '',
          match_time: m.time || m.match_time || '',
          ai_name: row.ai_name || 'system',
          prediction: prediction,
          confidence: row.confidence || null,
          is_r9: isR9,
          lottery_type: frontendKey
        });
      }
    }

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
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Traditional Lottery server running on port ${PORT}`);
  console.log(`Database: ${dbUrl ? 'connected' : 'NOT CONFIGURED'}`);
  console.log(`Available routes:`);
  console.log(`  GET /api/traditional-lottery/predict`);
  console.log(`  GET /api/traditional-lottery/latest`);
  console.log(`  GET /api/traditional-lottery/fetch`);
  console.log(`  GET /ct.html`);
});

// 优雅关闭
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down gracefully...');
  await pool.end();
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('SIGINT received, shutting down gracefully...');
  await pool.end();
  process.exit(0);
});
