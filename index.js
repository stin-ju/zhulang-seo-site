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

// 获取比赛的真实日期（基于match_time）
function getMatchDate(match) {
    const timeStr = (match.match_time || '').replace(' ', 'T');
    return timeStr.substring(0, 10);
}

// 格式化日期标签
function fmtDateLabel(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T00:00:00');
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
        // 获取所有比赛（不过滤状态）
        const allMatches = await fetchAllMatches();
        state.allMatches = allMatches;
        
        // 分离足球和篮球
        state.footballMatches = allMatches.filter(m => m.sport_type === 'football');
        state.basketballMatches = allMatches.filter(m => m.sport_type === 'basketball');
        
        // 获取所有比赛的预测
        const matchIds = allMatches.map(m => m.id);
        if (matchIds.length > 0) {
            state.predictions = await fetchPredictions(matchIds);
        }
        
        // 获取AI排行
        state.aiStats = await fetchAIStats();
        
        // 获取可用日期（按真实比赛日期分组）
        state.dates = [...new Set(allMatches.map(m => getMatchDate(m)))].sort().reverse();
        
        // 默认选中今天
        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];
        
        // 如果今天有比赛就选今天，否则选最近的有比赛的日期
        if (state.dates.includes(todayStr)) {
            state.currentDate = todayStr;
        } else {
            // 找最近的日期
            const futureDates = state.dates.filter(d => d >= todayStr).sort();
            state.currentDate = futureDates.length > 0 ? futureDates[0] : state.dates[0];
        }
        
        // 渲染页面
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
    renderBriefList();
}

// 渲染日期标签 - 始终显示7个（前3天 + 今天 + 后3天）
function renderDateTabs() {
    const container = document.getElementById('date-bar');
    if (!container) return;
    
    // 获取今天日期
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    
    // 生成固定的7天日期（前3天 + 今天 + 后3天）
    const sevenDays = [];
    for (let i = -3; i <= 3; i++) {
        const d = new Date(today);
        d.setDate(today.getDate() + i);
        sevenDays.push(d.toISOString().split('T')[0]);
    }
    
    // 始终显示7个日期标签，不管有没有比赛数据
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
    
    // 绑定点击事件
    container.querySelectorAll('.date-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            state.currentDate = btn.dataset.date;
            renderDateTabs();
            renderMatches();
        });
    });
}

// 渲染比赛列表
function renderMatches() {
    // 过滤当前日期的比赛
    const dateMatches = state.allMatches.filter(m => 
        getMatchDate(m) === state.currentDate
    );
    
    // 足球比赛
    const footballContainer = document.getElementById('view-football');
    if (footballContainer) {
        const footballMatches = dateMatches.filter(m => m.sport_type === 'football');
        if (footballMatches.length === 0) {
            footballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">当天没有足球赛程</div>';
        } else {
            footballContainer.innerHTML = footballMatches.map(m => renderMatchCard(m)).join('');
            // 绑定点击事件
            footballContainer.querySelectorAll('.match-card-clickable').forEach(card => {
                card.addEventListener('click', () => toggleMatchPredictions(card.dataset.matchId));
            });
        }
        document.getElementById('football-count-label').textContent = `${footballMatches.length}场`;
    }
    
    // 篮球比赛
    const basketballContainer = document.getElementById('view-basketball');
    if (basketballContainer) {
        const basketballMatches = dateMatches.filter(m => m.sport_type === 'basketball');
        if (basketballMatches.length === 0) {
            basketballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">当天没有篮球赛程</div>';
        } else {
            basketballContainer.innerHTML = basketballMatches.map(m => renderMatchCard(m)).join('');
            // 绑定点击事件
            basketballContainer.querySelectorAll('.match-card-clickable').forEach(card => {
                card.addEventListener('click', () => toggleMatchPredictions(card.dataset.matchId));
            });
        }
        document.getElementById('basketball-count-label').textContent = `${basketballMatches.length}场`;
    }
    
    // 更新总数
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
        badges += `<span class="badge-sm status-done">已确认</span>`;
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
// AI Logo 渲染
// ============================================================
function renderAILogos() {
    const container = document.getElementById('ai-logos');
    if (!container) return;
    
    const aiList = [
        { name: 'DeepSeek', color: '#6366f1' },
        { name: 'MiniMax', color: '#ec4899' },
        { name: '通义千问', color: '#8b5cf6' },
        { name: '腾讯混元', color: '#06b6d4' },
        { name: 'Kimi', color: '#10b981' },
        { name: '讯飞星火', color: '#f59e0b' },
        { name: '商汤', color: '#ef4444' },
    ];
    
    container.innerHTML = aiList.map(ai => `
        <div class="ai-logo">
            <div class="dot" style="background:${ai.color};">${ai.name[0]}</div>
            ${ai.name}
        </div>
    `).join('');
}

// ============================================================
// 初始化
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    renderAILogos();
    loadAll();
});
