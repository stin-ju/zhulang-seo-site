// ============================================================
// 公共 API 模块 - 所有页面共享
// 适配新schema: matches(odds/metadata JSONB), predictions(prediction/hit_status JSONB)
// ============================================================

// Supabase 配置
const SUPABASE_URL = 'https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sashnT6QYhW2_ilgdPxAuPXwtM';

// 缓存配置
const CACHE_DURATION = 5 * 60 * 1000; // 5分钟缓存
let dataCache = {};
let cacheTimestamp = {};

// ============================================================
// Schema 规范化：新schema JSONB → 旧schema扁平字段（向下兼容）
// ============================================================

/**
 * 规范化 match 数据：从新 schema 的 odds/metadata JSONB 展开为扁平字段
 * 新schema: id, sport_type, match_date, match_time, status, home_team, away_team,
 *           home_score, away_score, handicap, odds(JSONB), metadata(JSONB)
 * 
 * 展开后额外提供:
 *   teams: "主队 VS 客队" (兼容旧字段)
 *   win_odds, draw_odds, lose_odds (从 odds.spf 展开)
 *   handicap_win_odds, handicap_draw_odds, handicap_lose_odds (从 odds.handicap_spf 展开)
 *   score_odds, goals_odds, half_full_odds (从 odds 展开)
 *   selling_status (从 metadata 展开)
 *   half_home_score, half_away_score (从 metadata 展开)
 *   spread_line, total_line (从 metadata 展开)
 *   league (从 metadata.league 展开)
 */
export function normalizeMatch(m) {
    if (!m) return m;
    
    const odds = m.odds || {};
    const metadata = m.metadata || {};
    
    // 构建 teams 字段（兼容旧代码）
    const homeTeam = m.home_team || '';
    const awayTeam = m.away_team || '';
    if (!m.teams && (homeTeam || awayTeam)) {
        m.teams = homeTeam + ' VS ' + awayTeam;
    }
    
    // 从 odds.spf 展开胜平负赔率
    if (odds.spf) {
        if (m.win_odds === undefined) m.win_odds = odds.spf.win;
        if (m.draw_odds === undefined) m.draw_odds = odds.spf.draw;
        if (m.lose_odds === undefined) m.lose_odds = odds.spf.lose;
    }
    
    // 从 odds.handicap_spf 展开让球赔率
    if (odds.handicap_spf) {
        if (m.handicap_win_odds === undefined) m.handicap_win_odds = odds.handicap_spf.win;
        if (m.handicap_draw_odds === undefined) m.handicap_draw_odds = odds.handicap_spf.draw;
        if (m.handicap_lose_odds === undefined) m.handicap_lose_odds = odds.handicap_spf.lose;
    }
    
    // 从 odds 展开其他赔率
    if (m.score_odds === undefined && odds.score) m.score_odds = odds.score;
    if (m.goals_odds === undefined && odds.goals) m.goals_odds = odds.goals;
    if (m.half_full_odds === undefined && odds.half_full) m.half_full_odds = odds.half_full;
    
    // 篮球赔率（从 odds 展开）
    if (odds.spread) {
        if (m.spread_odds === undefined) m.spread_odds = odds.spread;
    }
    if (odds.total) {
        if (m.total_odds === undefined) m.total_odds = odds.total;
    }
    
    // 从 metadata 展开
    if (m.selling_status === undefined && metadata.selling_status) m.selling_status = metadata.selling_status;
    if (m.half_home_score === undefined && metadata.half_home_score !== undefined) m.half_home_score = metadata.half_home_score;
    if (m.half_away_score === undefined && metadata.half_away_score !== undefined) m.half_away_score = metadata.half_away_score;
    if (m.spread_line === undefined && metadata.spread_line !== undefined) m.spread_line = metadata.spread_line;
    if (m.total_line === undefined && metadata.total_line !== undefined) m.total_line = metadata.total_line;
    if (m.league === undefined && metadata.league) m.league = metadata.league;
    if (m.total_points_odds === undefined && metadata.total_points_odds !== undefined) m.total_points_odds = metadata.total_points_odds;
    
    // match_date 兼容
    if (!m.match_date && m.match_time) {
        m.match_date = m.match_time.substring(0, 10);
    }
    
    return m;
}

/**
 * 规范化 prediction 数据：从新 schema 的 prediction/hit_status JSONB 展开为扁平字段
 * 新schema: id, match_id, ai_name, prediction(JSONB), hit_status(JSONB), analysis, is_settled
 * 
 * prediction格式: {"spf":"胜","handicap_spf":"让胜","score":"3-1","goals":4,"half_full":"胜胜",
 *                  "win_loss":"胜","handicap_win_loss":"让胜","total_points":"大","score_diff_range":"6-10","half_win_loss":"胜胜"}
 * hit_status格式: {"spf":true,"handicap_spf":false,"score":null,"goals":null,"half_full":null,
 *                  "win_loss":true,"handicap_win_loss":false,"total_points":null,"score_diff_range":null,"half_win_loss":null}
 */
export function normalizePrediction(p, matchMap) {
    if (!p) return p;
    
    const pred = p.prediction || {};
    const hits = p.hit_status || {};
    
    // 足球预测字段
    if (p.spf === undefined && pred.spf !== undefined) p.spf = pred.spf;
    if (p.handicap_spf === undefined && pred.handicap_spf !== undefined) p.handicap_spf = pred.handicap_spf;
    if (p.score === undefined && pred.score !== undefined) p.score = pred.score;
    if (p.goals === undefined && pred.goals !== undefined) p.goals = pred.goals;
    if (p.half_full === undefined && pred.half_full !== undefined) p.half_full = pred.half_full;
    
    // 篮球预测字段
    if (p.win_loss === undefined && pred.win_loss !== undefined) p.win_loss = pred.win_loss;
    if (p.handicap_win_loss === undefined && pred.handicap_win_loss !== undefined) p.handicap_win_loss = pred.handicap_win_loss;
    if (p.total_points === undefined && pred.total_points !== undefined) p.total_points = pred.total_points;
    if (p.score_diff_range === undefined && pred.score_diff_range !== undefined) p.score_diff_range = pred.score_diff_range;
    if (p.half_win_loss === undefined && pred.half_win_loss !== undefined) p.half_win_loss = pred.half_win_loss;
    
    // 命中状态（转换为 ✅/❌ 格式）
    const hitMap = {
        'spf': 'hit_spf',
        'handicap_spf': 'hit_handicap',
        'score': 'hit_score',
        'goals': 'hit_goals',
        'half_full': 'hit_half',
        'win_loss': 'hit_win_loss',
        'handicap_win_loss': 'hit_handicap_win_loss',
        'total_points': 'hit_total_points',
        'score_diff_range': 'hit_score_diff_range',
        'half_win_loss': 'hit_half_win_loss'
    };
    
    for (const [predKey, hitKey] of Object.entries(hitMap)) {
        if (p[hitKey] === undefined && hits[predKey] !== undefined) {
            const val = hits[predKey];
            p[hitKey] = val === true ? '✅' : val === false ? '❌' : null;
        }
    }
    
    // 计算总命中数
    if (p.total_hits === undefined) {
        const hitKeys = ['hit_spf', 'hit_handicap', 'hit_score', 'hit_goals', 'hit_half',
                        'hit_win_loss', 'hit_handicap_win_loss', 'hit_total_points', 
                        'hit_score_diff_range', 'hit_half_win_loss'];
        p.total_hits = hitKeys.filter(k => p[k] === '✅').length;
    }
    
    // 从 matchMap 获取 sport_type
    if (p.sport_type === undefined && matchMap && p.match_id) {
        const match = matchMap[String(p.match_id)];
        if (match) {
            p.sport_type = match.sport_type || 'football';
        }
    }
    if (p.sport_type === undefined) p.sport_type = 'football';
    
    return p;
}

// ============================================================
// 缓存工具
// ============================================================

export function getCachedData(key) {
    const timestamp = cacheTimestamp[key];
    if (timestamp && Date.now() - timestamp < CACHE_DURATION) {
        return dataCache[key];
    }
    return null;
}

export function setCachedData(key, data) {
    dataCache[key] = data;
    cacheTimestamp[key] = Date.now();
}

// 已结束状态集合（容错判断）
export const DONE_STATUSES = ['已确认', '已完成', '已结束', '已完赛'];

// ============================================================
// Supabase 查询工具
// ============================================================
export async function querySupabase(table, select, filters, options = {}) {
    const params = new URLSearchParams();
    params.append('select', select);
    if (filters) {
        Object.entries(filters).forEach(([key, val]) => {
            params.append(key, `eq.${val}`);
        });
    }
    if (options.order) {
        params.append('order', options.order);
    }
    if (options.limit) {
        params.append('limit', options.limit);
    }
    if (options.offset) {
        params.append('offset', options.offset);
    }
    const url = `${SUPABASE_URL}/rest/v1/${table}?${params.toString()}`;
    
    const headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': `Bearer ${SUPABASE_KEY}`,
    };
    if (options.range) {
        headers['Range'] = options.range;
    }
    const resp = await fetch(url, { headers });
    if (!resp.ok) {
        const errorText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errorText}`);
    }
    return resp.json();
}

// ============================================================
// 业务查询函数
// ============================================================

// 获取赛事列表
export async function fetchMatches(sport = 'football', status = '未开赛') {
    const cacheKey = `matches_${sport}_${status}`;
    const cached = getCachedData(cacheKey);
    if (cached) {
        console.log(' 使用缓存数据:', cacheKey);
        return cached;
    }
    const data = await querySupabase(
        'matches',
        'id,sport_type,match_date,match_time,status,home_team,away_team,home_score,away_score,handicap,odds,metadata',
        { sport_type: sport },
        { order: 'match_time.asc', limit: '5000' }
    );
    
    // 规范化 + 容错过滤
    const normalized = data.map(normalizeMatch);
    const filtered = normalized.filter(m => {
        if (DONE_STATUSES.includes(m.status)) return false;
        if (m.selling_status && m.selling_status !== 'on_sale' && m.selling_status !== 'pending') return false;
        if (m.selling_status === 'on_sale' && m.match_time) {
            const matchStart = new Date(m.match_time.replace(' ', 'T'));
            const cutoff = new Date(matchStart.getTime() - 25 * 60 * 1000);
            if (new Date() >= cutoff) return false;
        }
        return true;
    });
    
    setCachedData(cacheKey, filtered);
    return filtered;
}

// 获取所有赛事（不过滤状态，用于首页展示全部）
export async function fetchAllMatches(sport = null) {
    const cacheKey = `all_matches_${sport || 'all'}`;
    const cached = getCachedData(cacheKey);
    if (cached) {
        console.log('📦 使用缓存数据:', cacheKey);
        return cached;
    }
    // 使用本地API替代Supabase REST API
    const url = sport ? `/api/matches?sport=${sport}` : '/api/matches';
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    
    setCachedData(cacheKey, data);
    return data;
}

// 获取AI预测（支持足球和篮球字段）
export async function fetchPredictions(matchIds, sport = 'football') {
    if (!matchIds || matchIds.length === 0) return [];
    
    const cacheKey = `predictions_${sport}_${matchIds.sort().join('_')}`;
    const cached = getCachedData(cacheKey);
    if (cached) {
        console.log('📦 使用缓存的预测数据:', cacheKey);
        return cached;
    }

    // 使用本地API替代Supabase REST API
    const resp = await fetch('/api/predictions');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const allData = await resp.json();
    console.log(`🐾 fetchPredictions: 获取${allData.length}条预测`);
    
    // 类型安全匹配：统一转为字符串比较
    const idSet = new Set(matchIds.map(id => String(id)));
    const filtered = allData.filter(p => idSet.has(String(p.match_id)));
    
    // 规范化预测数据（本地API已返回规范化数据，无需再次规范化）
    const normalized = filtered;
    
    setCachedData(cacheKey, normalized);
    return normalized;
}

// 获取AI排行
export async function fetchAIStats(sport = 'football') {
    const cacheKey = 'ai_stats_' + sport;
    const cached = getCachedData(cacheKey);
    if (cached) {
        console.log('📦 使用缓存的AI排行(' + sport + ')');
        return cached;
    }
    // 使用本地API替代Supabase REST API
    const resp = await fetch(`/api/ai_stats?sport=${sport}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    
    setCachedData(cacheKey, data);
    return data;
}

// ============================================================
// 工具函数
// ============================================================

export function esc(s) {
    if (s === null || s === undefined || s === '') return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

export function fmtDate(dt) {
    if (!dt) return '';
    try {
        const dateStr = dt.replace(' ', 'T').substring(0, 10);
        const parts = dateStr.split('-');
        return parseInt(parts[1], 10) + '月' + parseInt(parts[2], 10) + '日';
    } catch { return dt.slice(5, 10); }
}

export function fmtTime(dt) {
    if (!dt) return '';
    try { return dt.slice(11, 16); } catch { return ''; }
}

export function isMatchDone(match) {
    return DONE_STATUSES.includes(match.status);
}

export function showError(message) {
    const existing = document.querySelector('.error-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.innerHTML = `
        <div style="background:rgba(239,68,68,0.1);border:1px solid #ef4444;border-radius:12px;padding:16px 20px;color:#ef4444;font-size:14px;max-width:500px;margin:0 auto;text-align:center;">
            <span style="font-size:20px;margin-right:8px;">⚠️</span>
            ${message}
            <button onclick="this.parentElement.parentElement.remove()" style="margin-left:12px;background:none;border:none;color:#ef4444;cursor:pointer;font-size:16px;">✕</button>
        </div>
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 5000);
}
// version: 2026070722
