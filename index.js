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
    return `${month}月${day}日`;
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
        state.currentDate = state.dates[0];
        
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

// 渲染日期标签
function renderDateTabs() {
    const container = document.getElementById('date-bar');
    if (!container) return;
    
    if (state.dates.length === 0) {
        container.innerHTML = '<div style="color:#94a3b8;font-size:13px;">暂无赛程</div>';
        return;
    }
    
    // 获取今天日期
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    
    // 生成以今天为中心的7天日期（前3天 + 今天 + 后3天）
    const centerDates = [];
    for (let i = -3; i <= 3; i++) {
        const d = new Date(today);
        d.setDate(today.getDate() + i);
        centerDates.push(d.toISOString().split('T')[0]);
    }
    
    // 只显示有比赛数据的日期
    const availableDates = centerDates.filter(date => state.dates.includes(date));
    
    // 如果今天没有比赛，使用第一个可用日期
    const defaultDate = availableDates.includes(todayStr) ? todayStr : (availableDates[0] || state.dates[0]);
    
    // 如果当前日期不在可用日期列表中，设置为默认日期
    if (!availableDates.includes(state.currentDate)) {
        state.currentDate = defaultDate;
    }
    
    container.innerHTML = availableDates.map(date => `
        <button class="date-btn ${date === state.currentDate ? 'active' : ''}" 
                data-date="${date}">
            ${fmtDateLabel(date)}
        </button>
    `).join('');
    
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
            footballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">暂无足球赛程</div>';
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
            basketballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">暂无篮球赛程</div>';
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
    if (isDone) {
        badges += '<span class="badge-sm status-done">已确认</span>';
    } else {
        badges += '<span class="badge-sm status-pending">待比赛</span>';
    }
    if (matchPredictions.length > 0) {
        badges += `<span class="badge-sm consensus">${matchPredictions.length}AI预测</span>`;
    }
    
    // 构建预测摘要
    let predSummary = '';
    if (matchPredictions.length > 0) {
        const avgHits = matchPredictions.reduce((sum, p) => sum + (p.total_hits || 0), 0) / matchPredictions.length;
        predSummary = `
            <div class="pred-summary" style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.08);font-size:12px;color:#94a3b8;">
                <span>AI平均命中: <strong style="color:#10b981;">${avgHits.toFixed(1)}</strong></span>
                <span style="margin-left:12px;">预测数: <strong style="color:#e8eef7;">${matchPredictions.length}</strong></span>
            </div>
        `;
    }
    
    // 构建内联预测详情
    let inlinePredictions = '';
    if (matchPredictions.length > 0) {
        inlinePredictions = buildInlinePredictions(matchPredictions);
    }
    
    return `
        <div class="view-item match-card-clickable" data-match-id="${match.id}" style="cursor:pointer;">
            <span class="time">${matchTime}</span>
            <span class="teams">${esc(match.id)} ${esc(homeTeam)} vs ${esc(awayTeam)}</span>
            <div class="badge-group">
                ${badges}
            </div>
            ${predSummary}
            <div class="inline-predictions" style="display:none;">
                ${inlinePredictions}
            </div>
        </div>
    `;
}

// 构建内联预测内容 - 按行显示每个维度
function buildInlinePredictions(matchPredictions) {
    const dimensions = [
        { key: 'spf', label: '胜平负' },
        { key: 'handicap', label: '让球' },
        { key: 'score', label: '比分' },
        { key: 'goals', label: '进球数' },
        { key: 'half_full', label: '半全场' }
    ];
    
    // 按维度生成行
    const dimensionRows = dimensions.map(dim => {
        const aiItems = matchPredictions.map(p => {
            const val = p[dim.key];
            const hit = p[`${dim.key}_hit`];
            const hitClass = hit === true ? 'hit' : hit === false ? 'miss' : '';
            return `<span class="pred-ai-item ${hitClass}" title="${esc(p.ai_name)}: ${val || '-'}">${esc(p.ai_name)}: ${val || '-'}</span>`;
        }).join('');
        
        return `
            <div class="pred-dimension-row">
                <span class="pred-dim-label">${dim.label}</span>
                <div class="pred-ai-list">${aiItems}</div>
            </div>
        `;
    }).join('');
    
    return `
        <div class="inline-predictions-content">
            ${dimensionRows}
        </div>
    `;
}

// 切换比赛预测详情显示
function toggleMatchPredictions(matchId) {
    const card = document.querySelector(`.match-card-clickable[data-match-id="${matchId}"]`);
    if (!card) return;
    
    const inlinePred = card.querySelector('.inline-predictions');
    if (!inlinePred) return;
    
    const isHidden = inlinePred.style.display === 'none';
    inlinePred.style.display = isHidden ? 'block' : 'none';
}

// 渲染统计数据
function renderStats() {
    const totalMatches = state.allMatches.length;
    const doneMatches = state.allMatches.filter(m => isMatchDone(m)).length;
    
    const matchCountEl = document.getElementById('match-count');
    const doneCountEl = document.getElementById('done-count');
    
    if (matchCountEl) matchCountEl.textContent = totalMatches;
    if (doneCountEl) doneCountEl.textContent = doneMatches;
}

// 渲染简报列表
function renderBriefList() {
    const container = document.getElementById('brief-list');
    if (!container) return;
    
    // 简报列表已经在HTML中静态生成，这里不需要动态渲染
    // 如果需要动态渲染，可以在这里实现
}

// ============================================================
// 初始化
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 加载首页...');
    loadAll();
});
