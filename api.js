// ============================================================
// 公共 API 模块 - 所有页面共享
// ============================================================

// Supabase 配置
const SUPABASE_URL = 'https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sashnT6QYhW2_ilgdPxAuPXwtM';

// 已结束状态集合（容错判断）
export const DONE_STATUSES = ['已确认', '已完成', '已结束'];

// ============================================================
// 缓存工具
// ============================================================
const CACHE_TTL = 5 * 60 * 1000; // 5分钟

export function getCachedData(key) {
    try {
        const cached = localStorage.getItem(key);
        if (!cached) return null;
        const data = JSON.parse(cached);
        if (Date.now() - data.timestamp > CACHE_TTL) return null;
        return data.value;
    } catch { return null; }
}

export function setCachedData(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify({
            value: value,
            timestamp: Date.now()
        }));
    } catch { /* 忽略存储错误 */ }
}

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
        'id,teams,match_time,handicap,status,selling_status,win_odds,draw_odds,lose_odds,sport_type',
        { sport_type: sport },
        { order: 'match_time.asc', limit: '5000' }
    );
    
    // 容错过滤：只返回未结束且在售的比赛
    const filtered = data.filter(m => {
        if (DONE_STATUSES.includes(m.status)) return false;
        if (m.selling_status && m.selling_status !== 'on_sale') return false;
        // 时间容错：超过开赛前25分钟视为停售
        if (m.match_time) {
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
    const filters = sport ? { sport_type: sport } : null;
    const data = await querySupabase(
        'matches',
        'id,teams,match_time,handicap,status,selling_status,win_odds,draw_odds,lose_odds,sport_type,home_score,away_score,half_home_score,half_away_score,spread_line,total_line',
        filters,
        { order: 'match_time.desc', limit: '5000' }
    );
    
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

    const select = 'match_id,ai_name,spf,handicap_spf,score,goals,half_full,win_loss,total_points,score_diff_range,half_win_loss,hit_handicap,hit_score,hit_goals,hit_half,total_hits,analysis';
    
    // 分页查询绕过Supabase 1000行限制
    let allData = [];
    let offset = 0;
    const pageSize = 1000;
    while (true) {
        const url = `${SUPABASE_URL}/rest/v1/predictions?select=${encodeURIComponent(select)}&order=match_id.asc&limit=${pageSize}&offset=${offset}`;
        const resp = await fetch(url, {
            headers: {
                'apikey': SUPABASE_KEY,
                'Authorization': `Bearer ${SUPABASE_KEY}`,
            }
        });
        if (!resp.ok) {
            const errorText = await resp.text();
            throw new Error(`HTTP ${resp.status}: ${errorText}`);
        }
        const batch = await resp.json();
        allData = allData.concat(batch);
        if (batch.length < pageSize) break;
        offset += pageSize;
    }
    
    console.log(`📦 预测数据分页加载完成，共${allData.length}条`);
    
    // 类型安全匹配：统一转为字符串比较
    const idSet = new Set(matchIds.map(id => String(id)));
    const filtered = allData.filter(p => idSet.has(String(p.match_id)));
    setCachedData(cacheKey, filtered);
    return filtered;
}

// 获取AI排行
export async function fetchAIStats() {
    const cached = getCachedData('ai_stats');
    if (cached) {
        console.log('📦 使用缓存的AI排行');
        return cached;
    }
    const data = await querySupabase(
        'ai_stats',
        'ai_name,rank,total_pnl,hit_rate,matches,let_hit,score_hit,is_active',
        null,
        { order: 'rank.asc' }
    );
    
    setCachedData('ai_stats', data);
    return data;
}

// ============================================================
// 工具函数
// ============================================================

export function esc(s) {
    if (!s) return '';
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
