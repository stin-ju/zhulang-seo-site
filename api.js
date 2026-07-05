// ============================================================
// 公共 API 模块 - 所有页面共享
// ============================================================

// Supabase 配置
const SUPABASE_URL = 'https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sashnT6QYhW2_ilgdPxAuPXwtM';

// 已结束状态集合（容错判断）
const DONE_STATUSES = ['已确认', '已完成', '已结束'];

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
        console.log('📦 使用缓存数据:', cacheKey);
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

// 获取所有赛事（不过滤状态，用于简报等页面）
export async function fetchAllMatches(sport = 'football') {
    const cacheKey = `all_matches_${sport}`;
    const cached = getCachedData(cacheKey);
    if (cached) {
        console.log('📦 使用缓存数据:', cacheKey);
        return cached;
    }

    const data = await querySupabase(
        'matches',
        'id,teams,match_time,handicap,status,selling_status,win_odds,draw_odds,lose_odds,sport_type',
        { sport_type: sport },
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
    if (cached) return cached;

    // 足球和篮球字段都查询
    const select = 'match_id,ai_name,spf,handicap_spf,score,goals,half_full,win_loss,total_points,score_diff_range,half_win_loss,hit_handicap,hit_score,hit_goals,hit_half,total_hits,analysis';
    const data = await querySupabase(
        'predictions',
        select,
        null,
        { order: 'match_id.asc', limit: '5000' }
    );
    
    const filtered = data.filter(p => matchIds.includes(p.match_id));
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

// 时区安全的日期格式化 - 直接截取字符串，不经过UTC转换
export function fmtDate(dt) {
    if (!dt) return '';
    try {
        // 直接截取日期部分，避免时区问题
        const dateStr = dt.replace(' ', 'T').substring(0, 10);
        const parts = dateStr.split('-');
        const month = parseInt(parts[1], 10);
        const day = parseInt(parts[2], 10);
        return month + '月' + day + '日';
    } catch { return dt.slice(5, 10); }
}

// 时区安全的时间格式化
export function fmtTime(dt) {
    if (!dt) return '';
    try { return dt.slice(11, 16); } catch { return ''; }
}

// 判断比赛是否已结束（容错）
export function isMatchDone(match) {
    return DONE_STATUSES.includes(match.status);
}

export function showError(message) {
    // 显示友好错误提示
    const existing = document.querySelector('.error-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.innerHTML = `
        <div style="background:rgba(239,68,68,0.1);border:1px solid #ef4444;border-radius:12px;padding:16px 20px;color:#ef4444;font-size:14px;max-width:500px;margin:0 auto;text-align:center;">
            <span style="font-size:20px;margin-right:8px;">⚠️</span>
            ${message}
            <button onclick="this.parentElement.parentElement.remove()" style="margin-left:12px;background:transparent;border:1px solid #ef4444;color:#ef4444;border-radius:6px;padding:2px 12px;cursor:pointer;">关闭</button>
        </div>
    `;
    
    const container = document.querySelector('main') || document.body;
    container.prepend(toast);
    
    // 5秒后自动消失
    setTimeout(() => { if (toast.parentElement) toast.remove(); }, 5000);
}
