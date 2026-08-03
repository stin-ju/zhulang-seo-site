// ======== GET /api/traditional-lottery/predict ========
// 修复版：直接查数据库，不依赖Python脚本
if (pathname === '/api/traditional-lottery/predict' && req.method === 'GET') {
  try {
    const issueFilter = req.query.issue;

    // 查询所有预测数据，包含issue字段
    let query = `SELECT id, game_type, ai_name, issue, predictions, ren9, confidence, matches_info 
                 FROM traditional_predictions`;
    let params = [];

    if (issueFilter) {
      query += ` WHERE issue = $1`;
      params.push(issueFilter);
    }
    query += ` ORDER BY game_type, issue DESC, id`;

    const result = await pgPool.query(query, params);
    const rows = result.rows;

    // game_type 到前端key的映射
    const typeMap = { '胜负彩': 'sfc', '任9': 'r9', '半全场': 'htf', '进球彩': 'jqc' };
    // 前端key到预测字段的映射
    const predFieldMap = { 'sfc': 'spf', 'r9': 'spf', 'htf': 'bqc', 'jqc': 'bf' };
    const responseData = { sfc: [], r9: [], htf: [], jqc: [] };

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
      
      // 解析 ren9
      let ren9Arr = row.ren9;
      if (typeof ren9Arr === 'string') {
        try { ren9Arr = JSON.parse(ren9Arr); } catch (e) { ren9Arr = null; }
      }

      const predField = predFieldMap[frontendKey] || 'spf';

      for (const m of matchesArr) {
        const matchNum = m.num || m.match_num || 0;
        const issue = row.issue || m.issue || '';
        const matchId = m.id || `${issue}_${String(matchNum).padStart(2, '0')}`;

        // 获取该场比赛的预测
        let prediction = null;
        if (Array.isArray(predictionsArr)) {
          const pred = predictionsArr.find(p => String(p.match) === String(matchNum));
          if (pred) prediction = pred[predField] || null;
        }

        // 判断是否任9推荐场次
        const isR9 = ren9Arr && Array.isArray(ren9Arr) 
          ? ren9Arr.some(r => String(r) === String(matchNum) || String(r) === String(matchNum).padStart(2, '0'))
          : false;

        const record = {
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
          lottery_type: frontendKey
        };

        // 添加到对应玩法
        responseData[frontendKey].push(record);
        
        // 任9也添加到r9数组（如果是胜负彩数据）
        if (frontendKey === 'sfc' && ren9Arr) {
          responseData.r9.push({ ...record, ren9: ren9Arr, is_r9: isR9 });
        }
      }
    }

    res.writeHead(200, { 'Content-Type': 'application/json', ...CORS_HEADERS });
    res.end(JSON.stringify({ success: true, data: responseData }));
    return;
  } catch (err) {
    console.error('[TraditionalLottery] /predict error:', err.message);
    res.writeHead(500, { 'Content-Type': 'application/json', ...CORS_HEADERS });
    res.end(JSON.stringify({ error: 'Internal server error', message: err.message }));
    return;
  }
}
