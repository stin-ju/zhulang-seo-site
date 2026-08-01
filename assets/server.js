/**
 * 2026世界杯AI预测网站 - 主服务器
 * 功能：API端点 + 定时任务（数据获取、AI预测、自动结算）
 */

const express = require('express');
const { createClient } = require('@supabase/supabase-js');
const axios = require('axios');
const cron = require('node-cron');

const app = express();
const PORT = process.env.PORT || 3000;

// Supabase客户端
const supabase = createClient(
  process.env.SUPABASE_URL || '',
  process.env.SUPABASE_ANON_KEY || ''
);

app.use(express.json());

// ==================== API端点 ====================

/**
 * GET /api/matches - 获取比赛列表
 * 支持日期筛选、分页、排序
 */
app.get('/api/matches', async (req, res) => {
  try {
    const { 
      page = 1, 
      pageSize = 20, 
      date, 
      status, 
      sportType, 
      search,
      sortBy = 'match_time',
      sortOrder = 'desc'
    } = req.query;

    let query = supabase
      .from('matches')
      .select('*', { count: 'exact' });

    // 日期筛选（核心修复）
    if (date) {
      const nextDate = new Date(date);
      nextDate.setDate(nextDate.getDate() + 1);
      query = query
        .gte('match_time', `${date}T00:00:00`)
        .lt('match_time', `${nextDate.toISOString().split('T')[0]}T00:00:00`);
    }

    // 状态筛选
    if (status) {
      query = query.eq('status', status);
    }

    // 赛事类型筛选
    if (sportType) {
      query = query.eq('sport_type', sportType);
    }

    // 搜索（队名/联赛）
    if (search) {
      query = query.or(`teams.ilike.%${search}%,metadata->>league.ilike.%${search}%`);
    }

    // 排序
    const orderColumn = ['match_time', 'created_at', 'status'].includes(sortBy) ? sortBy : 'match_time';
    const orderDirection = sortOrder === 'asc' ? 'asc' : 'desc';
    query = query.order(orderColumn, { ascending: orderDirection === 'asc' });

    // 分页
    const from = (page - 1) * pageSize;
    const to = from + pageSize - 1;
    query = query.range(from, to);

    const { data, error, count } = await query;

    if (error) throw error;

    // 获取每个比赛的AI预测
    const matchesWithPredictions = await Promise.all(
      data.map(async (match) => {
        const { data: predictions } = await supabase
          .from('predictions')
          .select('ai_name, spf, handicap_spf, score, goals, half_full, total_hits, confidence')
          .eq('match_id', match.id)
          .order('total_hits', { ascending: false })
          .limit(5);

        return {
          ...match,
          predictions: predictions || []
        };
      })
    );

    res.json({
      data: matchesWithPredictions,
      pagination: {
        page: parseInt(page),
        pageSize: parseInt(pageSize),
        total: count || 0,
        totalPages: Math.ceil((count || 0) / pageSize)
      }
    });
  } catch (error) {
    console.error('GET /api/matches error:', error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * GET /api/stats - 获取统计数据
 */
app.get('/api/stats', async (req, res) => {
  try {
    const { data: matches } = await supabase
      .from('matches')
      .select('id, status, sport_type');

    const { data: predictions } = await supabase
      .from('predictions')
      .select('id, total_hits, match_id');

    const stats = {
      totalMatches: matches.length,
      confirmedMatches: matches.filter(m => m.status === '已确认').length,
      pendingMatches: matches.filter(m => m.status === '未开赛').length,
      totalPredictions: predictions.length,
      avgHits: predictions.length > 0 
        ? predictions.reduce((sum, p) => sum + (p.total_hits || 0), 0) / predictions.length 
        : 0
    };

    res.json(stats);
  } catch (error) {
    console.error('GET /api/stats error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ==================== 定时任务 ====================

/**
 * 定时任务1：每日03:00 - 自动结算
 */
cron.schedule('0 3 * * *', async () => {
  console.log('[03:00] 开始自动结算...');
  try {
    // 查询昨天结束的比赛
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = yesterday.toISOString().split('T')[0];

    const { data: matches } = await supabase
      .from('matches')
      .select('*')
      .eq('status', '已结束')
      .gte('match_time', `${yesterdayStr}T00:00:00`)
      .lt('match_time', `${yesterday.toISOString().split('T')[0]}T23:59:59`);

    console.log(`[03:00] 找到 ${matches.length} 场需要结算的比赛`);

    for (const match of matches) {
      // 查询该比赛的所有预测
      const { data: predictions } = await supabase
        .from('predictions')
        .select('*')
        .eq('match_id', match.id);

      if (!predictions || predictions.length === 0) continue;

      // 判断每个预测是否命中（这里简化处理，实际需要更复杂的逻辑）
      for (const pred of predictions) {
        let totalHits = 0;

        // 判断胜平负
        if (pred.spf) {
          const result = match.home_score > match.away_score ? '胜' : 
                         match.home_score < match.away_score ? '负' : '平';
          if (pred.spf === result) totalHits++;
        }

        // 更新预测记录
        await supabase
          .from('predictions')
          .update({ total_hits: totalHits })
          .eq('id', pred.id);
      }

      // 更新比赛状态为"已确认"
      await supabase
        .from('matches')
        .update({ status: '已确认' })
        .eq('id', match.id);

      console.log(`[03:00] 比赛 ${match.id} 结算完成，命中数: ${predictions.map(p => p.total_hits).join(',')}`);
    }

    console.log('[03:00] 自动结算完成');
  } catch (error) {
    console.error('[03:00] 自动结算失败:', error);
  }
});

/**
 * 定时任务2：每日11:05 - 增量数据获取
 */
cron.schedule('5 11 * * *', async () => {
  console.log('[11:05] 开始获取最新数据...');
  try {
    // 从体彩官网抓取数据（这里需要实现具体的抓取逻辑）
    // TODO: 实现数据抓取逻辑
    console.log('[11:05] 数据获取完成（TODO: 实现抓取逻辑）');
  } catch (error) {
    console.error('[11:05] 数据获取失败:', error);
  }
});

/**
 * 定时任务3：每日21:30（周一至周五）- 生成AI预测
 */
cron.schedule('30 21 * * 1-5', async () => {
  console.log('[21:30] 开始生成AI预测...');
  try {
    // 查询今天所有未开赛的比赛
    const today = new Date().toISOString().split('T')[0];
    const { data: matches } = await supabase
      .from('matches')
      .select('*')
      .eq('status', '未开赛')
      .gte('match_time', `${today}T00:00:00`)
      .lt('match_time', `${today}T23:59:59`);

    console.log(`[21:30] 找到 ${matches.length} 场未开赛的比赛`);

    for (const match of matches) {
      // TODO: 调用AI API生成预测
      console.log(`[21:30] 为比赛 ${match.id} 生成预测（TODO: 实现AI调用）`);
    }

    console.log('[21:30] AI预测生成完成');
  } catch (error) {
    console.error('[21:30] AI预测生成失败:', error);
  }
});

/**
 * 定时任务4：每日22:30（周六日）- 生成AI预测
 */
cron.schedule('30 22 * * 0,6', async () => {
  console.log('[22:30] 开始生成AI预测...');
  try {
    // 逻辑同21:30
    const today = new Date().toISOString().split('T')[0];
    const { data: matches } = await supabase
      .from('matches')
      .select('*')
      .eq('status', '未开赛')
      .gte('match_time', `${today}T00:00:00`)
      .lt('match_time', `${today}T23:59:59`);

    console.log(`[22:30] 找到 ${matches.length} 场未开赛的比赛`);
    console.log('[22:30] AI预测生成完成（TODO: 实现AI调用）');
  } catch (error) {
    console.error('[22:30] AI预测生成失败:', error);
  }
});

// ==================== 启动服务器 ====================

app.listen(PORT, () => {
  console.log(`🚀 服务器运行在端口 ${PORT}`);
  console.log(`📊 API端点: /api/matches, /api/stats`);
  console.log(`⏰ 定时任务已启动`);
});
