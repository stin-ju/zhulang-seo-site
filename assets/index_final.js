// ============================================================
// 首页逻辑 - 使用公共API模块
// ============================================================
import { 
    fetchMatches, 
    fetchPredictions, 
    fetchAIStats,
    fetchAllMatches,
    esc, 
    fmtDate, 
    fmtTime,
    showError,
    getCachedData,
    setCachedData,
    querySupabase,
    isMatchDone
} from './api.js';

// ============================================================
// 日期工具函数（修复时区Bug：用本地时间而非UTC）
// ============================================================
function getLocalDateStr(d) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
}

// ============================================================
// 全局状态
// ============================================================
const state = {
    allMatches: [],
    footballMatches: [],
    basketballMatches: [],
    predictions: [],
    aiStats: [],
    currentDate: null,
    dates: []
};

// ============================================================
// 日期工具函数
// ============================================================
function getMatchDate(match) {
    const timeStr = (match.match_time || '').replace(' ', 'T');
    return timeStr.substring(0, 10);
}

function fmtDateLabel(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T00:00:00');
    if (isNaN(d.getTime())) return dateStr;  // 无效日期直接返回原字符串
    const month = d.getMonth() + 1;
    const day = d.getDate();
    const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    const weekDay = weekDays[d.getDay()];
    return `${month}月${day}日 ${weekDay}`;
}

// ============================================================
// 数据加载
// ============================================================
async function loadAll() {
    try {
        const allMatches = await fetchAllMatches();
        state.allMatches = allMatches;
        
        state.footballMatches = allMatches.filter(m => m.sport_type === 'football');
        state.basketballMatches = allMatches.filter(m => m.sport_type === 'basketball');
        
        const matchIds = allMatches.map(m => m.id);
        if (matchIds.length > 0) {
            state.predictions = await fetchPredictions(matchIds);
        }
        
        state.aiStats = await fetchAIStats();
        
        state.dates = [...new Set(allMatches.map(m => getMatchDate(m)).filter(d => d && d.length === 10))].sort().reverse();
        
        const today = new Date();
        const todayStr = getLocalDateStr(today);
        
        if (state.dates.includes(todayStr)) {
            state.currentDate = todayStr;
        } else {
            const futureDates = state.dates.filter(d => d >= todayStr).sort();
            state.currentDate = futureDates.length > 0 ? futureDates[0] : state.dates[0];
        }
        
        renderAll();
        
    } catch (error) {
        console.error('加载数据失败:', error);
        showError('数据加载失败，请刷新页面重试');
    }
}

// ============================================================
// 渲染函数
// ============================================================
function renderAll() {
    renderDateTabs();
    renderMatches();
    renderStats();
    renderRanking();
}

// 日期标签：7个固定，最新在左
function renderDateTabs() {
    const container = document.getElementById('date-bar');
    if (!container) return;
    
    const today = new Date();
    const todayStr = getLocalDateStr(today);
    
    // 生成7天：后3天+今天+前3天，最新日期在最左边
    const sevenDays = [];
    for (let i = 3; i >= -3; i--) {
        const d = new Date(today);
        d.setDate(today.getDate() + i);
        sevenDays.push(getLocalDateStr(d));
    }
    
    container.innerHTML = sevenDays.map(date => {
        const isToday = date === todayStr;
        const isActive = date === state.currentDate;
        const hasMatches = state.dates.includes(date);
        
        return `
            <button class="date-btn ${isActive ? 'active' : ''} ${!hasMatches ? 'no-matches' : ''}" 
                    data-date="${date}">
                ${fmtDateLabel(date)}${isToday ? ' 今天' : ''}
            </button>
        `;
    }).join('');
    
    container.querySelectorAll('.date-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            state.currentDate = btn.dataset.date;
            renderDateTabs();
            renderMatches();
        });
    });
}

function renderMatches() {
    const dateMatches = state.allMatches.filter(m => 
        getMatchDate(m) === state.currentDate
    );
    
    const footballContainer = document.getElementById('view-football');
    if (footballContainer) {
        const footballMatches = dateMatches.filter(m => m.sport_type === 'football');
        if (footballMatches.length === 0) {
            footballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">当天没有足球赛程</div>';
        } else {
            footballContainer.innerHTML = footballMatches.map(m => renderMatchCard(m)).join('');
            footballContainer.querySelectorAll('.match-card-clickable').forEach(card => {
                card.addEventListener('click', () => toggleMatchPredictions(card.dataset.matchId));
            });
        }
        document.getElementById('football-count-label').textContent = `${footballMatches.length}场`;
    }
    
    const basketballContainer = document.getElementById('view-basketball');
    if (basketballContainer) {
        const basketballMatches = dateMatches.filter(m => m.sport_type === 'basketball');
        if (basketballMatches.length === 0) {
            basketballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">当天没有篮球赛程</div>';
        } else {
            basketballContainer.innerHTML = basketballMatches.map(m => renderMatchCard(m)).join('');
            basketballContainer.querySelectorAll('.match-card-clickable').forEach(card => {
                card.addEventListener('click', () => toggleMatchPredictions(card.dataset.matchId));
            });
        }
        document.getElementById('basketball-count-label').textContent = `${basketballMatches.length}场`;
    }
    
    document.getElementById('match-count-label').textContent = `${dateMatches.length}场`;
}

// 渲染比赛卡片
function renderMatchCard(match) {
    const matchPredictions = state.predictions.filter(p => p.match_id === match.id);
    const teams = (match.teams || '').split(/\s*VS\s*/);
    const homeTeam = teams[0] || '主队';
    const awayTeam = teams[1] || '客队';
    const matchTime = fmtTime(match.match_time);
    const isDone = isMatchDone(match);
    
    // 构建 badges
    let badges = '';
    
    // 状态badge
    if (isDone) {
        const hs = match.home_score != null ? match.home_score : '?';
        const as_ = match.away_score != null ? match.away_score : '?';
        badges += `<span class="badge-sm status-done" style="color:#fbbf24;font-weight:700;">${hs}:${as_}</span>`;
    } else if (match.status === '未开赛') {
        badges += `<span class="badge-sm status-pending">待比赛</span>`;
    }
    
    // 共识度/分歧度（基于预测）
    if (matchPredictions.length > 0) {
        const spfPredictions = matchPredictions.filter(p => p.spf).map(p => p.spf);
        if (spfPredictions.length > 0) {
            const counts = {};
            spfPredictions.forEach(p => { counts[p] = (counts[p] || 0) + 1; });
            const maxCount = Math.max(...Object.values(counts));
            const consensus = maxCount / spfPredictions.length;
            
            if (consensus >= 0.7) {
                const dir = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
                const cls = dir === '胜' ? 'win' : dir === '平' ? 'draw' : 'lose';
                badges += `<span class="badge-sm consensus">共识${dir} ${Math.round(consensus * 100)}%</span>`;
            } else if (consensus <= 0.4) {
                badges += `<span class="badge-sm divergence">分歧大</span>`;
            }
        }
    }
    
    // 预测数量
    const predCount = matchPredictions.length;
    
    return `
        <div class="view-item match-card-clickable" data-match-id="${match.id}">
            <span class="time">${matchTime}</span>
            <span class="teams">${esc(homeTeam)} vs ${esc(awayTeam)}</span>
            <div class="badge-group">
                ${badges}
                ${predCount > 0 ? `<span class="badge-sm" style="background:rgba(139,92,246,0.1);color:#a78bfa;">${predCount}AI预测</span>` : ''}
                <span class="arrow-sm">▶</span>
            </div>
        </div>
        <div class="match-detail" id="detail-${match.id}">
            ${renderPredictionsTable(matchPredictions, match)}
        </div>
    `;
}

// 渲染AI预测表格（每个AI一行，列是胜平负/让球/比分/进球数/半全场）
function renderPredictionsTable(predictions, match) {
    if (!predictions || predictions.length === 0) {
        return '<div style="padding:12px 0;color:#94a3b8;font-size:13px;">暂无AI预测</div>';
    }
    
    // 按总命中数降序排列
    const sorted = [...predictions].sort((a, b) => (b.total_hits || 0) - (a.total_hits || 0));
    
    // 判断命中状态
    function cellClass(pred, field) {
        const hitFieldMap = {
            'spf': 'hit_handicap',
            'handicap_spf': 'hit_handicap',
            'score': 'hit_score',
            'goals': 'hit_goals',
            'half_full': 'hit_half'
        };
        const hitKey = hitFieldMap[field];
        if (!hitKey || pred[hitKey] === undefined || pred[hitKey] === null) return '';
        return pred[hitKey] === true ? 'hit' : 'miss';
    }
    
    return `
        <div class="inline-predictions-table-wrap">
            <table class="inline-predictions-table">
                <thead>
                    <tr>
                        <th>AI</th>
                        <th>胜平负</th>
                        <th>让球</th>
                        <th>比分</th>
                        <th>进球数</th>
                        <th>半全场</th>
                        <th>命中</th>
                    </tr>
                </thead>
                <tbody>
                    ${sorted.map(p => `
                        <tr>
                            <td>${esc(p.ai_name)}</td>
                            <td class="${cellClass(p, 'spf')}">${p.spf || '-'}</td>
                            <td class="${cellClass(p, 'handicap_spf')}">${p.handicap_spf || '-'}</td>
                            <td class="${cellClass(p, 'score')}">${p.score || '-'}</td>
                            <td class="${cellClass(p, 'goals')}">${p.goals || '-'}</td>
                            <td class="${cellClass(p, 'half_full')}">${p.half_full || '-'}</td>
                            <td style="color:${(p.total_hits || 0) >= 3 ? '#10b981' : (p.total_hits || 0) >= 1 ? '#a78bfa' : '#6b7280'};font-weight:600;">${p.total_hits || 0}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// 展开/折叠预测
function toggleMatchPredictions(matchId) {
    const detail = document.getElementById(`detail-${matchId}`);
    if (!detail) return;
    
    const isOpen = detail.classList.contains('open');
    
    if (isOpen) {
        detail.classList.remove('open');
    } else {
        detail.classList.add('open');
    }
}

// 渲染统计数据
function renderStats() {
    const total = state.allMatches.length;
    const done = state.allMatches.filter(m => isMatchDone(m)).length;
    
    document.getElementById('match-count').textContent = total;
    document.getElementById('done-count').textContent = done;
}

// 渲染简报列表
function renderBriefList() {
    // 简报列表已经在HTML中静态生成，这里不需要动态渲染
}

// ============================================================
// AI排行渲染（动态从数据库获取）
// ============================================================
function renderRanking() {
    const container = document.getElementById('ranking-list');
    if (!container) return;
    const activeAIs = (state.aiStats || []).filter(ai => ai.is_active === true).sort((a, b) => (a.rank || 99) - (b.rank || 99));
    if (activeAIs.length === 0) {
        container.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">暂无排行数据</div>';
        return;
    }
    container.innerHTML = '<table style="width:100%;font-size:13px;"><thead><tr style="color:#94a3b8;"><th style="text-align:left;padding:6px 4px;">排名</th><th style="text-align:left;padding:6px 4px;">AI</th><th style="text-align:right;padding:6px 4px;">盈亏</th></tr></thead><tbody>' + activeAIs.map(ai => {
        const pnl = ai.total_pnl || 0;
        const pnlColor = pnl >= 0 ? '#10b981' : '#ef4444';
        const medal = ai.rank === 1 ? '🥇' : ai.rank === 2 ? '🥈' : ai.rank === 3 ? '🥉' : ai.rank;
        return '<tr><td style="padding:6px 4px;">' + medal + '</td><td style="padding:6px 4px;">' + (ai.ai_name || '') + '</td><td style="padding:6px 4px;text-align:right;color:' + pnlColor + ';font-weight:600;">' + (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + '</td></tr>';
    }).join('') + '</tbody></table>';
}

// ============================================================
// AI Logo 渲染（动态从数据库获取，不再硬编码）
// ============================================================
function renderAILogos() {
    const container = document.getElementById('ai-logos');
    if (!container) return;
    const aiColors = {
        'DeepSeek': '#6366f1',
        'MiniMax': '#ec4899',
        '扣子（皮皮）': '#8b5cf6',
        '混元': '#06b6d4',
        '豆包': '#10b981',
        '文心': '#f59e0b',
        '智谱清言': '#ef4444'
    };
    const activeAIs = (state.aiStats || []).filter(ai => ai.is_active === true).sort((a, b) => (a.rank || 99) - (b.rank || 99));
    if (activeAIs.length === 0) return;
    container.innerHTML = activeAIs.map(ai => {
        const color = aiColors[ai.ai_name] || '#6b7280';
        return '<div class="ai-logo"><div class="dot" style="background:' + color + ';">' + (ai.ai_name || '?')[0] + '</div>' + (ai.ai_name || '未知') + '</div>';
    }).join('');
}

// ============================================================
// 初始化
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
    // 先加载AI数据，再渲染Logo
    try {
        state.aiStats = await fetchAIStats();
    } catch (e) {
        console.error('获取AI统计失败:', e);
    }
    renderAILogos();
    loadAll();
});
