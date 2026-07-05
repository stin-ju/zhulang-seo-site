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

// 获取比赛的体彩日期（基于match_id前缀）
function getLotteryDateFromMatch(match) {
    const matchId = match.id || '';
    const prefix = matchId.match(/^(周[一二三四五六日])/);
    if (!prefix) {
        // 如果没有周X前缀，使用match_time的日期
        const timeStr = (match.match_time || '').replace(' ', 'T');
        return timeStr.substring(0, 10);
    }
    
    const weekdayMap = {
        '周一': 1, '周二': 2, '周三': 3, '周四': 4,
        '周五': 5, '周六': 6, '周日': 0
    };
    
    const targetWeekday = weekdayMap[prefix[1]];
    if (targetWeekday === undefined) {
        const timeStr = (match.match_time || '').replace(' ', 'T');
        return timeStr.substring(0, 10);
    }
    
    // 获取当前日期
    const now = new Date();
    const currentWeekday = now.getDay();
    
    // 计算目标日期
    let daysDiff = targetWeekday - currentWeekday;
    if (daysDiff > 0) daysDiff -= 7; // 如果目标日期在未来，改为上周
    
    const targetDate = new Date(now);
    targetDate.setDate(now.getDate() + daysDiff);
    
    return targetDate.toISOString().split('T')[0];
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
        
        // 获取可用日期
        state.dates = [...new Set(allMatches.map(m => getLotteryDateFromMatch(m)))].sort().reverse();
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
    
    container.innerHTML = state.dates.map(date => `
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
        getLotteryDateFromMatch(m) === state.currentDate
    );
    
    // 足球比赛
    const footballContainer = document.getElementById('view-football');
    if (footballContainer) {
        const footballMatches = dateMatches.filter(m => m.sport_type === 'football');
        if (footballMatches.length === 0) {
            footballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">暂无足球赛程</div>';
        } else {
            footballContainer.innerHTML = footballMatches.map(m => renderMatchCard(m)).join('');
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
    
    return `
        <div class="match-item ${isDone ? 'done' : ''}">
            <div class="match-header">
                <span class="match-id">${esc(match.id)}</span>
                <span class="match-time">${matchTime}</span>
                ${isDone ? '<span class="match-status">已完赛</span>' : ''}
            </div>
            <div class="match-teams">
                <span class="team home">${esc(homeTeam)}</span>
                <span class="vs">VS</span>
                <span class="team away">${esc(awayTeam)}</span>
            </div>
            ${isDone && match.home_score !== undefined ? `
                <div class="match-score">
                    ${match.home_score} - ${match.away_score}
                </div>
            ` : ''}
            <div class="match-predictions">
                ${matchPredictions.length > 0 ? `
                    <span class="pred-count">${matchPredictions.length}AI预测</span>
                ` : '<span class="pred-count" style="color:#64748b;">暂无预测</span>'}
            </div>
        </div>
    `;
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
