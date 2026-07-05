// ============================================================
// 首页逻辑 - 使用公共API模块
// ============================================================

import { fetchMatches, fetchPredictions, fetchAIStats, esc, fmtDate, fmtTime, showError, getCachedData, setCachedData, isMatchDone, DONE_STATUSES } from './api.js';

// ============================================================
// 页面特定工具函数
// ============================================================

// Get lottery date based on match_time
function getLotteryDateFromMatch(match) {
    // match_time格式: "2026-07-06T04:00:00" 或 "2026-07-06 04:00:00"
    // 直接取日期部分，不转UTC（避免时区导致日期错误）
    const timeStr = match.match_time.replace(' ', 'T');
    return timeStr.split('T')[0];
}

function fmtDateLabel(dateStr) {
    // 直接截取日期部分，不转UTC（避免时区导致日期错误）
    const parts = dateStr.replace(' ', 'T').substring(0, 10).split('-');
    const m = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    return m + '月' + day + '日';
}

// ============================================================
// 数据获取
// ============================================================
let ALL_MATCHES = [];
let ALL_PREDICTIONS = [];
let ALL_RANK = [];
let DATES = [];
let CURRENT_DATE = '';

async function loadAll() {
    try {
        // 并行加载
        const [matches, rank] = await Promise.all([
            fetchMatches('football', '待比赛'),
            fetchAIStats()
        ]);

        ALL_MATCHES = matches || [];
        ALL_RANK = rank || [];

        // 提取唯一日期（按真实比赛时间分组）
        const dateSet = new Set();
        ALL_MATCHES.forEach(m => {
            const d = getLotteryDateFromMatch(m);
            dateSet.add(d);
        });
        DATES = Array.from(dateSet).sort((a, b) => b.localeCompare(a));
        CURRENT_DATE = DATES[0] || '';

        // 获取所有预测
        const matchIds = ALL_MATCHES.map(m => m.id);
        ALL_PREDICTIONS = matchIds.length > 0 ? await fetchPredictions(matchIds, 'football') : [];

        // 渲染
        renderAll();

    } catch (error) {
        console.error('加载失败:', error);
        showError('数据加载失败，请刷新页面重试');
    }
}

// ============================================================
// 渲染
// ============================================================

function renderAll() {
    renderDateTabs();
    renderMatches();
    renderRank();
    renderStats();
}

function renderDateTabs() {
    const tabs = document.getElementById('dateTabs');
    if (!tabs) return;
    tabs.innerHTML = DATES.map(d => {
        const label = fmtDateLabel(d);
        const active = d === CURRENT_DATE ? 'active' : '';
        return `<button class="date-tab ${active}" data-date="${d}">${label}</button>`;
    }).join('');
    
    tabs.querySelectorAll('.date-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            CURRENT_DATE = btn.dataset.date;
            tabs.querySelectorAll('.date-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderMatches();
        });
    });
}

function renderMatches() {
    const container = document.getElementById('matchesContainer');
    if (!container) return;

    // 过滤当前日期的比赛
    const dateMatches = ALL_MATCHES.filter(m => getLotteryDateFromMatch(m) === CURRENT_DATE);
    
    if (dateMatches.length === 0) {
        container.innerHTML = '<div class="empty">暂无比赛</div>';
        return;
    }

    container.innerHTML = dateMatches.map(m => {
        const preds = ALL_PREDICTIONS.filter(p => p.match_id === m.id);
        const isDone = isMatchDone(m);
        const time = fmtTime(m.match_time);
        const teams = esc(m.teams || '');
        
        return `
            <div class="match-card" data-id="${m.id}">
                <div class="match-header">
                    <span class="match-time">${time}</span>
                    <span class="match-teams">${teams}</span>
                    ${isDone ? '<span class="match-status done">已确认</span>' : '<span class="match-status pending">待比赛</span>'}
                </div>
                <div class="match-body">
                    <div class="match-odds">
                        <span class="odds-label">胜平负</span>
                        <span class="odds-value">${m.win_odds || '-'} / ${m.draw_odds || '-'} / ${m.lose_odds || '-'}</span>
                    </div>
                    <div class="match-odds">
                        <span class="odds-label">让球</span>
                        <span class="odds-value">${m.handicap || '0'}</span>
                    </div>
                    ${isDone ? `
                    <div class="match-result">
                        <span class="result-label">比分</span>
                        <span class="result-value">${m.home_score || 0} - ${m.away_score || 0}</span>
                    </div>
                    ` : ''}
                </div>
                <div class="match-predictions">
                    <span class="pred-count">${preds.length}AI</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderRank() {
    const container = document.getElementById('rankContainer');
    if (!container) return;

    const activeRank = ALL_RANK.filter(r => r.is_active);
    
    if (activeRank.length === 0) {
        container.innerHTML = '<div class="empty">暂无排行</div>';
        return;
    }

    container.innerHTML = activeRank.map((r, i) => {
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : '';
        const pnlClass = r.total_pnl > 0 ? 'positive' : r.total_pnl < 0 ? 'negative' : '';
        
        return `
            <div class="rank-item">
                <span class="rank-position">${medal || (i + 1)}</span>
                <span class="rank-name">${esc(r.ai_name)}</span>
                <span class="rank-pnl ${pnlClass}">${r.total_pnl > 0 ? '+' : ''}${r.total_pnl || 0}</span>
                <span class="rank-rate">${r.hit_rate || 0}%</span>
            </div>
        `;
    }).join('');
}

function renderStats() {
    const totalMatches = ALL_MATCHES.length;
    const doneMatches = ALL_MATCHES.filter(m => isMatchDone(m)).length;
    
    const totalEl = document.getElementById('totalMatches');
    const doneEl = document.getElementById('doneMatches');
    
    if (totalEl) totalEl.textContent = totalMatches;
    if (doneEl) doneEl.textContent = doneMatches;
}

// ============================================================
// 初始化
// ============================================================

document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 加载首页...');
    await loadAll();
    console.log('✅ 首页加载完成', { matches: ALL_MATCHES.length, predictions: ALL_PREDICTIONS.length });
});
