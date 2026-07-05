// ============================================================
// 公共 API 模块 - 所有页面共享
// ============================================================
const SUPABASE_URL = 'https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sawnT6QYhW2_ilgdPxAuPXwtM';

const DONE_STATUSES = ['已确认', '已完成', '已结束'];

const CACHE_TTL = 5 * 60 * 1000;

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
        localStorage.setItem(key, JSON.stringify({ value: value, timestamp: Date.now() }));
    } catch {}
}

export async function querySupabase(table, select, filters, options = {}) {
    const params = new URLSearchParams();
    params.append('select', select);
    if (filters) {
        Object.entries(filters).forEach(([key, val]) => {
            params.append(key, `eq.${val}`);
        });
    }
    if (options.order) params.append('order', options.order);
    if (options.limit) params.append('limit', options.limit);
    
    const url = `${SUPABASE_URL}/rest/v1/${table}?${params.toString()}`;
    const headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': `Bearer ${SUPABASE_KEY}`,
    };
    if (options.range) headers['Range'] = options.range;
    
    const resp = await fetch(url, { headers });
    if (!resp.ok) {
        const errorText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errorText}`);
    }
    return resp.json();
}

export async function fetchMatches(sport = 'football', status = '未开赛') {
    const cacheKey = `matches_${sport}_${status}`;
    const cached = getCachedData(cacheKey);
    if (cached) return cached;
    
    const data = await querySupabase(
        'matches',
        'id,teams,match_time,handicap,status,selling_status,win_odds,draw_odds,lose_odds,sport_type,home_score,away_score',
        { sport_type: sport },
        { order: 'match_time.asc', limit: '5000' }
    );
    
    const filtered = data.filter(m => {
        if (DONE_STATUSES.includes(m.status)) return false;
        if (m.selling_status && m.selling_status !== 'on_sale') return false;
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

export async function fetchAllMatches(sport = null) {
    const cacheKey = `all_matches_${sport || 'all'}`;
    const cached = getCachedData(cacheKey);
    if (cached) return cached;
    
    const filters = sport ? { sport_type: sport } : null;
    const data = await querySupabase(
        'matches',
        'id,teams,match_time,handicap,status,selling_status,win_odds,draw_odds,lose_odds,sport_type,home_score,away_score',
        filters,
        { order: 'match_time.desc', limit: '5000' }
    );
    
    setCachedData(cacheKey, data);
    return data;
}

export async function fetchPredictions(matchIds, sport = 'football') {
    if (!matchIds || matchIds.length === 0) return [];
    
    // 统一转字符串，解决数字/字符串类型不匹配
    const matchIdsStr = matchIds.map(id => String(id));
    
    const cacheKey = `predictions_${sport}_${matchIdsStr.sort().join('_')}`;
    const cached = getCachedData(cacheKey);
    if (cached) return cached;
    
    const select = 'match_id,ai_name,spf,handicap_spf,score,goals,half_full,win_loss,total_points,score_diff_range,half_win_loss,hit_handicap,hit_score,hit_goals,hit_half,total_hits,analysis';
    const data = await querySupabase(
        'predictions',
        select,
        null,
        { order: 'match_id.asc', limit: '5000' }
    );
    
    // 类型安全匹配
    const filtered = data.filter(p => matchIdsStr.includes(String(p.match_id)));
    
    setCachedData(cacheKey, filtered);
    return filtered;
}

export async function fetchAIStats() {
    const cached = getCachedData('ai_stats');
    if (cached) return cached;
    
    const data = await querySupabase(
        'ai_stats',
        'ai_name,rank,total_pnl,hit_rate,matches,let_hit,score_hit,is_active',
        null,
        { order: 'rank.asc' }
    );
    
    setCachedData('ai_stats', data);
    return data;
}

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
