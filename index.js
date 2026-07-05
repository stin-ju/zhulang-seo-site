// ============================================================
// 首页 JavaScript - 使用 api.js 模块
// ============================================================

import { fetchMatches, fetchPredictions, fetchAIStats, esc, fmtDate, fmtTime, showError, getCachedData, setCachedData, querySupabase, isMatchDone, DONE_STATUSES } from './api.js';

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
            querySupabase('matches', 'id,teams,match_time,status,handicap,win_odds,draw_odds,lose_odds,home_score,away_score,sport_type', null, { order: 'match_time.asc', limit: '5000' }),
            querySupabase('ai_stats', 'ai_name,rank,total_pnl,hit_rate,matches,is_active', null, { order: 'rank.asc' })
        ]);

        ALL_MATCHES = matches || [];
        ALL_RANK = rank || [];

        // 提取唯一日期（按真实比赛时间分组）
        const dateSet = new Set();
        ALL_MATCHES.forEach(m => {
            const d = getLotteryDateFromMatch(m);
            if (d) dateSet.add(d);
        });
        DATES = Array.from(dateSet).sort((a, b) => b.localeCompare(a));

        // 加载预测
        const matchIds = ALL_MATCHES.map(m => m.id);
        ALL_PREDICTIONS = await fetchPredictions(matchIds);

        // 设置默认日期
        if (DATES.length > 0) {
            const today = new Date();
            const todayStr = today.toISOString().slice(0, 10);
            CURRENT_DATE = DATES.includes(todayStr) ? todayStr : DATES[0];
        }

        renderAll();
    } catch (error) {
        console.error('加载数据失败:', error);
        showError('数据加载失败，请刷新重试');
    }
}

// ============================================================
// 渲染
// ============================================================
function renderAll() {
    renderDateTabs();
    renderMatches();
    renderRank();
}

function renderDateTabs() {
    const container = document.getElementById('date-tabs');
    if (!container) return;

    let html = '';
    DATES.forEach(d => {
        const active = d === CURRENT_DATE ? ' active' : '';
        html += `<button class="date-tab${active}" data-date="${d}">${fmtDateLabel(d)}</button>`;
    });
    container.innerHTML = html;

    // 绑定事件
    container.querySelectorAll('.date-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            CURRENT_DATE = btn.dataset.date;
            renderDateTabs();
            renderMatches();
        });
    });
}

function renderMatches() {
    const container = document.getElementById('match-list');
    if (!container) return;

    const filtered = ALL_MATCHES.filter(m => getLotteryDateFromMatch(m) === CURRENT_DATE);

    if (filtered.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#6b7280;padding:40px;">暂无比赛</div>';
        return;
    }

    let html = '';
    filtered.forEach(match => {
        const preds = ALL_PREDICTIONS.filter(p => p.match_id === match.id);
        const { votes, details } = computeVotes(preds, match);
        const totalVotes = votes['胜'] + votes['平'] + votes['负'];
        const isDone = isMatchDone(match);
        const result = getMatchResult(match);

        html += `<div class="match-card" data-match-id="${match.id}">`;
        html += `<div class="match-header">`;
        html += `<span class="match-time">${fmtTime(match.match_time)}</span>`;
        html += `<span class="match-teams">${esc(match.home_team || '')} vs ${esc(match.away_team || '')}</span>`;
        if (isDone && result) {
            html += `<span class="match-result result-${result}">${result}</span>`;
        }
        html += `</div>`;

        // 投票条
        if (totalVotes > 0) {
            const winPct = Math.round((votes['胜'] / totalVotes) * 100);
            const drawPct = Math.round((votes['平'] / totalVotes) * 100);
            const losePct = 100 - winPct - drawPct;
            html += `<div class="vote-bar">`;
            html += `<div class="vote-segment win" style="width:${winPct}%">${winPct > 10 ? winPct + '%' : ''}</div>`;
            html += `<div class="vote-segment draw" style="width:${drawPct}%">${drawPct > 10 ? drawPct + '%' : ''}</div>`;
            html += `<div class="vote-segment lose" style="width:${losePct}%">${losePct > 10 ? losePct + '%' : ''}</div>`;
            html += `</div>`;
        }

        // 赔率
        html += `<div class="odds-row">`;
        html += `<span class="odds-label">胜 ${match.win_odds || '-'}</span>`;
        html += `<span class="odds-label">平 ${match.draw_odds || '-'}</span>`;
        html += `<span class="odds-label">负 ${match.lose_odds || '-'}</span>`;
        html += `</div>`;

        // 详情
        html += `<div class="match-detail" id="detail-${match.id}">`;
        html += renderPredictionTable(match, details);
        html += `</div>`;

        html += `</div>`;
    });

    container.innerHTML = html;

    // 绑定展开事件
    container.querySelectorAll('.match-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.match-detail')) return;
            const matchId = card.dataset.matchId;
            toggleDetail(matchId);
        });
    });
}

function computeVotes(preds, match) {
    const votes = { '胜': 0, '平': 0, '负': 0 };
    const details = [];

    preds.forEach(p => {
        // 篮球用win_loss，足球用spf
        let choice = (p.spf || '').trim();
        if (!choice && p.win_loss) {
            choice = p.win_loss.trim();
        }

        if (choice === '胜') votes['胜']++;
        else if (choice === '平') votes['平']++;
        else if (choice === '负') votes['负']++;
        else if (choice.includes('胜') && !choice.includes('负')) votes['胜']++;
        else if (choice.includes('负') && !choice.includes('胜')) votes['负']++;
        else if (choice.includes('平')) votes['平']++;

        details.push({
            ai: p.ai_name,
            spf: p.spf || '',
            win_loss: p.win_loss || '',
            handicap: p.handicap_spf || '',
            score: p.score || '',
            total_points: p.total_points || '',
            score_diff_range: p.score_diff_range || '',
            goals: p.goals || '',
            half_full: p.half_full || '',
            half_win_loss: p.half_win_loss || '',
            hit_handicap: p.hit_handicap,
            hit_score: p.hit_score,
            hit_goals: p.hit_goals,
            hit_half: p.hit_half,
            total_hits: p.total_hits
        });
    });

    return { votes, details };
}

function renderPredictionTable(match, details) {
    const isBasketball = match.sport_type === 'basketball';
    const dims = isBasketball ? [
        { key: 'win_loss', label: '胜负' },
        { key: 'handicap', label: `让分(${match.handicap || '?'})` },
        { key: 'total_points', label: '总分' },
        { key: 'score_diff_range', label: '分差' },
        { key: 'half_win_loss', label: '半场胜负' }
    ] : [
        { key: 'spf', label: '胜平负' },
        { key: 'handicap', label: `让球(${match.handicap || '?'})` },
        { key: 'score', label: '比分' },
        { key: 'goals', label: '总进球' },
        { key: 'half_full', label: '半全场' }
    ];

    let html = '<table class="prediction-table"><thead><tr><th>AI</th>';
    dims.forEach(d => {
        html += `<th>${d.label}</th>`;
    });
    html += '<th>命中</th></tr></thead><tbody>';

    details.forEach(d => {
        html += `<tr><td class="ai-name">${esc(d.ai)}</td>`;
        dims.forEach(dim => {
            const val = isBasketball ? (d[dim.key] || d.spf || '-') : (d[dim.key] || '-');
            html += `<td>${esc(val)}</td>`;
        });
        html += `<td class="hits">${d.total_hits || 0}</td></tr>`;
    });

    html += '</tbody></table>';
    return html;
}

function toggleDetail(matchId) {
    const el = document.getElementById('detail-' + matchId);
    if (!el) return;
    const isOpen = el.classList.contains('open');

    // 先关闭所有
    document.querySelectorAll('.match-detail.open').forEach(d => d.classList.remove('open'));

    // 切换
    if (!isOpen) el.classList.add('open');
}

function getMatchResult(match) {
    if (!isMatchDone(match)) return null;
    const h = parseInt(match.home_score);
    const a = parseInt(match.away_score);
    if (isNaN(h) || isNaN(a)) return null;
    // 篮球没有平局
    if (match.sport_type === 'basketball') {
        return h > a ? '胜' : '负';
    }
    if (h > a) return '胜';
    if (h < a) return '负';
    return '平';
}

// ============================================================
// 渲染：AI排行
// ============================================================
function renderRank() {
    const container = document.getElementById('rank-list');
    if (!ALL_RANK || ALL_RANK.length === 0) {
        container.innerHTML = '<div style="color:#6b7280;font-size:13px;">暂无数据</div>';
        return;
    }

    let html = '';
    ALL_RANK.slice(0, 7).forEach((item, i) => {
        const pos = i + 1;
        const gold = pos <= 3 ? ' gold' : '';
        const pnl = parseFloat(item.total_pnl) || 0;
        const pnlCls = pnl > 0 ? 'win' : pnl < 0 ? 'lose' : '';
        const rate = parseFloat(item.hit_rate) || 0;
        const rateStr = Math.round(rate * 100) + '%';
        const activeTag = item.is_active ? '' : ' <span style="font-size:10px;color:#6b7280;">退赛</span>';

        html += '<div class="rank-row">';
        html += '<span class="pos' + gold + '">' + pos + '</span>';
        html += '<span class="name">' + esc(item.ai_name) + activeTag + '</span>';
        html += '<span class="pnl ' + pnlCls + '">' + (pnl > 0 ? '+' : '') + pnl.toFixed(1) + '</span>';
        html += '<span class="rate">' + rateStr + '</span>';
        html += '</div>';
    });

    container.innerHTML = html;
}

// ============================================================
// AI Logo 渲染
// ============================================================
const AI_COLORS = ['#6366f1','#f59e0b','#3b82f6','#10b981','#8b5cf6','#ef4444','#06b6d4','#ec4899','#14b8a6','#f97316'];

function getInitial(name) {
    if (/^[a-zA-Z]/.test(name)) return name.slice(0, 2).toUpperCase();
    return name.charAt(0);
}

// 活跃AI名单（按AGENTS.md定义）
const ACTIVE_AIS = ['混元', '豆包', 'DeepSeek', 'MiniMax', '扣子（皮皮）', 'BetAgent', 'Grok'];

async function renderAiLogos() {
    const container = document.getElementById('ai-logos');
    if (!container) return;
    const names = ACTIVE_AIS;
    container.innerHTML = names.map((name, i) => `
        <a href="#/ai/${encodeURIComponent(name)}" class="ai-logo">
            <span class="dot" style="background:${AI_COLORS[i % AI_COLORS.length]}">${getInitial(name)}</span>
            <span>${name}</span>
        </a>
    `).join('');
}

// ============================================================
// 初始化
// ============================================================
async function init() {
    try {
        await Promise.all([renderAiLogos(), loadAll()]);
        console.log('✅ 首页加载完成');
    } catch (error) {
        console.error('❌ 加载失败:', error);
        showError('加载失败，请刷新重试');
    }
}

document.addEventListener('DOMContentLoaded', init);
