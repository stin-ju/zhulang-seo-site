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

    // game_type 到前端key的映射
    const typeMap = { '胜负彩': 'sfc', '任9': 'sfc', '半全场': 'htf', '进球彩': 'jqc' };
    // 前端key到预测字段的映射
    const predFieldMap = { 'sfc': 'spf', 'htf': 'bqc', 'jqc': 'zjq' };
    const responseData = { sfc: [], htf: [], jqc: [] };

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

        // 判断该场是否在任9推荐中
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
        predictions,
        matches_info,
        created_at
      FROM traditional_predictions
      WHERE game_type IN ('胜负彩', '半全场', '进球彩', '任9')
      ORDER BY created_at DESC
      LIMIT 7
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
 * 触发传统彩赛程抓取
 */
app.get('/api/traditional-lottery/fetch', async (req, res) => {
  const scriptPath = path.join(__dirname, 'scripts', 'traditional_lottery_predict.py');
  
  if (!fs.existsSync(scriptPath)) {
    return res.status(501).json({ 
      error: 'Not Implemented',
      message: 'traditional_lottery_predict.py script not found'
    });
  }

  try {
    const { execSync } = require('child_process');
    const pythonEnv = { ...process.env, PYTHONUNBUFFERED: '1' };
    
    // 执行抓取脚本
    const result = execSync(
      `python3 "${scriptPath}" --game '胜负彩' --force`,
      {
        cwd: path.join(__dirname, 'scripts'),
        env: pythonEnv,
        timeout: 60000,
        maxBuffer: 10 * 1024 * 1024,
      }
    );

    const data = JSON.parse(result.toString().trim());
    res.json({ success: true, data });
  } catch (err) {
    console.error('[TraditionalLottery] /fetch error:', err.message);
    res.status(500).json({ error: 'Fetch failed', message: err.message });
  }
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
