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
} from './api.v20260719c.js';
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
    if (match.match_date) {
        return String(match.match_date).substring(0, 10);
    }
    if (match.match_time) {
        const timeStr = String(match.match_time);
        if (timeStr.length > 8) {
            return timeStr.substring(0, 10);
        }
    }
    return "unknown";
}
function fmtDateLabel(dateStr) {
    if (!dateStr || dateStr === "unknown") return "";
    const d = new Date(dateStr + "T00:00:00");
    if (isNaN(d.getTime())) return dateStr;
    return (d.getMonth() + 1) + "月" + d.getDate() + "日";
}
// ============================================================
// 数据加载
// ============================================================
async function loadAll() {
    try {
        // 直接获取带predictions的比赛数据（include_predictions=true）
        const resp = await fetch('/api/matches?include_predictions=true');
        const allMatches = await resp.json();
        state.allMatches = allMatches;
        
        state.footballMatches = allMatches.filter(m => m.sport_type === 'football');
        state.basketballMatches = allMatches.filter(m => m.sport_type === 'basketball');
        
        // 直接从比赛数据中提取predictions（避免ID格式不匹配问题）
        // 过滤脏数据：排除RETIRED/TO_DELETE + 去重
        const BLACKLIST = new Set(['RETIRED', 'TO_DELETE']);
        state.predictions = [];
        allMatches.forEach(m => {
            if (m.predictions && m.predictions.length > 0) {
                // 排除黑名单
                const valid = m.predictions.filter(p => !BLACKLIST.has(p.ai_name || ''));
                // 去重：同一个AI如果有多条，优先保留AI-前缀的
                const seen = new Map();
                valid.forEach(p => {
                    const rawName = (p.ai_name || '').replace(/^AI-/, '');
                    if (!seen.has(rawName) || p.ai_name.startsWith('AI-')) {
                        seen.set(rawName, p);
                    }
                });
                seen.forEach(p => {
                    state.predictions.push({ ...p, match_id: m.id });
                });
            }
        });
        console.log(`🐾 从matches提取${state.predictions.length}条有效预测（已过滤脏数据+去重）`);
        
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
            footballContainer.innerHTML = renderMatchListWithFold(footballMatches, 'football');
            bindMatchCardEvents(footballContainer);
            bindFoldEvents(footballContainer);
        }
        document.getElementById('football-count-label').textContent = `${footballMatches.length}场`;
    }
    
    const basketballContainer = document.getElementById('view-basketball');
    if (basketballContainer) {
        const basketballMatches = dateMatches.filter(m => m.sport_type === 'basketball');
        if (basketballMatches.length === 0) {
            basketballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">当天没有篮球赛程</div>';
        } else {
            basketballContainer.innerHTML = renderMatchListWithFold(basketballMatches, 'basketball');
            bindMatchCardEvents(basketballContainer);
            bindFoldEvents(basketballContainer);
        }
        document.getElementById('basketball-count-label').textContent = `${basketballMatches.length}场`;
    }
}
// 渲染比赛列表，超过5场默认折叠
function renderMatchListWithFold(matches, prefix) {
    matches = [...matches].sort((a, b) => (a.match_time || '').localeCompare(b.match_time || ''));
    const SHOW_COUNT = 5;
    const cards = matches.map((m, i) => {
        const cls = i >= SHOW_COUNT ? ' hidden-row' : '';
        return `<div class="match-card-wrap${cls}" data-index="${i}">${renderMatchCard(m)}</div>`;
    }).join('');
    
    let foldBtn = '';
    if (matches.length > SHOW_COUNT) {
        const remaining = matches.length - SHOW_COUNT;
        foldBtn = `<div class="show-more-btn" data-prefix="${prefix}" data-expanded="false">
            <span class="fold-text">展开更多（+${remaining}场）</span> <span class="arrow-down">▾</span>
        </div>`;
    }
    return cards + foldBtn;
}
// 绑定折叠/展开事件
function bindFoldEvents(container) {
    const btn = container.querySelector('.show-more-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const expanded = btn.dataset.expanded === 'true';
        const wraps = container.querySelectorAll('.match-card-wrap');
        const textEl = btn.querySelector('.fold-text');
        const arrowEl = btn.querySelector('.arrow-down');
        const total = wraps.length;
        
        if (expanded) {
            // 收起：隐藏第5个以后的
            wraps.forEach((w, i) => { if (i >= 5) w.classList.add('hidden-row'); });
            textEl.textContent = `展开更多（+${total - 5}场）`;
            arrowEl.style.transform = '';
            btn.dataset.expanded = 'false';
        } else {
            // 展开：显示全部
            wraps.forEach(w => w.classList.remove('hidden-row'));
            textEl.textContent = '收起';
            arrowEl.style.transform = 'rotate(180deg)';
            btn.dataset.expanded = 'true';
        }
    });
}
// 绑定比赛卡片点击事件
function bindMatchCardEvents(container) {
    container.querySelectorAll('.view-item-clickable').forEach(item => {
        item.addEventListener('click', () => {
            const matchId = item.dataset.matchId;
            toggleMatchPredictions(matchId, item);
        });
    });
}
// ============================================================
// 渲染比赛卡片 - 使用 .view-item CSS 类名
// ============================================================
function renderMatchCard(match) {
    const matchPredictions = state.predictions.filter(p => String(p.match_id) === String(match.id));
    
    // 队伍名：优先 home_team/away_team，其次从 teams 字段解析
    let homeTeam = match.home_team || '';
    let awayTeam = match.away_team || '';
    if (!homeTeam || !awayTeam) {
        const teams = (match.teams || '').split(/\s*[Vv][Ss]\s*/);
        if (!homeTeam) homeTeam = teams[0] || '主队';
        if (!awayTeam) awayTeam = teams[1] || '客队';
    }
    
    const matchTime = fmtTime(match.match_time);
    const isDone = isMatchDone(match);
    let handicap = match.handicap != null && match.handicap !== '' ? String(match.handicap) : '-';
    if (handicap !== '-' && !handicap.startsWith('-') && !handicap.startsWith('+')) {
        handicap = '+' + handicap;
    }
    // 去掉小数点后的0，如+1.0→+1，-0.25不变
    if (handicap !== '-') {
        handicap = handicap.replace(/\.0$/, '');
    }
    
    // 篮球大小分
    let bTotalHtml = '';
    if (match.sport_type === 'basketball') {
        const mMeta = match.metadata || {};
        let tpl = mMeta.total_points_line;
        if (!tpl && mMeta.odds) {
            tpl = (mMeta.odds.hilo && mMeta.odds.hilo.line) || (mMeta.odds.total_points && mMeta.odds.total_points.line) || (mMeta.odds.goals && mMeta.odds.goals.line);
        }
        if (tpl) {
            bTotalHtml = `<span class="handicap-tag">大小${tpl}</span>`;
        }
    }

    // 构建中间区域：队名+比分/VS（不含让球标签）
    let teamsHtml = '';
    const leagueName = match.league_name || match.league || '';
    const leagueStr = leagueName ? `${leagueName} ` : '';
    if (isDone) {
        const hs = match.home_score != null ? match.home_score : '?';
        const as_ = match.away_score != null ? match.away_score : '?';
        teamsHtml = `${esc(leagueStr)}${esc(homeTeam)} <span class="score-inline">${hs} : ${as_}</span> ${esc(awayTeam)}`;
    } else {
        teamsHtml = `${esc(leagueStr)}${esc(homeTeam)} VS ${esc(awayTeam)}`;
    }
    
    // 让球+大小分标签：独立列，固定宽度保证对齐
    let tagsHtml = '';
    const handicapTag = handicap !== '-' ? `<span class="handicap-tag">[${esc(handicap)}]</span>` : '';
    if (handicapTag || bTotalHtml) {
        tagsHtml = `<div class="handicap-col">${handicapTag}${bTotalHtml}</div>`;
    }
    
    // 构建右侧徽章
    let badges = '';
    if (isDone) {
        badges += `<span class="badge-sm status-done">已完赛</span>`;
    } else if (match.status === '已开赛') {
        badges += `<span class="badge-sm status-done" style="color:#fbbf24;">进行中</span>`;
    } else if (match.status === '已取消') {
        badges += `<span class="badge-sm status-pending">已取消</span>`;
    } else {
        badges += `<span class="badge-sm status-pending">待开赛</span>`;
    }
    
    // 共识度/分歧度 - 根据运动类型选择字段
    const isBasketball = match.sport_type === 'basketball';
    if (matchPredictions.length > 0) {
        const mainField = isBasketball ? 'win_loss' : 'spf';
        const mainPredictions = matchPredictions.filter(p => p.prediction && p.prediction[mainField]);
        if (mainPredictions.length > 0) {
            const counts = {};
            mainPredictions.forEach(p => {
                const choice = p.prediction[mainField];
                counts[choice] = (counts[choice] || 0) + 1;
            });
            const maxCount = Math.max(...Object.values(counts));
            const consensus = maxCount / mainPredictions.length;
            
            if (consensus >= 0.7) {
                const dir = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
                badges += `<span class="badge-sm consensus">共识${dir} ${Math.round(consensus * 100)}%</span>`;
            } else if (consensus <= 0.4) {
                badges += `<span class="badge-sm divergence">分歧大</span>`;
            }
        }
    }
    
    // AI预测数量
    const predCount = matchPredictions.length;
    if (predCount > 0) {
        badges += `<span style="font-size:11px;color:#6b7280;">${predCount}个AI</span>`;
    }
    
    const clickableClass = predCount > 0 ? ' view-item-clickable' : '';
    
    return `
    <div class="view-item${clickableClass}" data-match-id="${match.id}" style="cursor:${predCount > 0 ? 'pointer' : 'default'};">
        ${match.id ? `<span class="match-lottery-id">${match.id.replace(/^\d{8}_/, '')}</span>` : ''}
        <span class="time">${matchTime || ''}</span>
        <div style="flex:1;min-width:0;">
            <span class="match-teams">${teamsHtml}</span>
        </div>
        ${tagsHtml}
        <div class="badge-group">${badges}</div>
        ${predCount > 0 ? '<span class="arrow-sm">▸</span>' : ''}
    </div>
    <div class="match-detail" id="detail-${match.id}"></div>
    `;
}
// ============================================================
// 展开/折叠预测
// ============================================================
function toggleMatchPredictions(matchId, itemEl) {
    const detailEl = document.getElementById('detail-' + matchId);
    if (!detailEl) return;
    
    if (detailEl.classList.contains('open')) {
        detailEl.classList.remove('open');
        return;
    }
    
    const match = state.allMatches.find(m => String(m.id) === String(matchId));
    if (!match) return;
    
    const matchPredictions = state.predictions.filter(p => String(p.match_id) === String(matchId));
    detailEl.innerHTML = renderPredictionsTable(matchPredictions, match);
    detailEl.classList.add('open');
}
// ============================================================
// 渲染AI预测表格
// ============================================================
function renderPredictionsTable(predictions, match) {
    if (!predictions || predictions.length === 0) {
        return '<div style="padding:12px;color:#94a3b8;text-align:center;">暂无AI预测</div>';
    }
    
    const sorted = [...predictions].sort((a, b) => (a.rank || 99) - (b.rank || 99));
    const isDone = isMatchDone(match);
    const isBasketball = match.sport_type === 'basketball';
    
    const hitClass = (key, hitStatus) => {
        if (!isDone) return '';
        if (hitStatus[key] === true) return 'hit';
        if (hitStatus[key] === false) return 'miss';
        return '';
    };
    
    const rows = sorted.map(p => {
        const pred = p.prediction || {};
        const hitStatus = p.hit_status || {};
        
        if (isBasketball) {
            const winLoss = (pred.win_loss != null) ? pred.win_loss : '-';
            const handicap = (pred.handicap_win_loss != null) ? pred.handicap_win_loss : '-';
            const scoreDiff = (pred.score_diff_range != null) ? pred.score_diff_range : '-';
            const totalPts = (pred.total_points != null) ? pred.total_points : '-';
            
            return `
            <tr>
                <td style="text-align:left;font-weight:500;color:#a78bfa;">${esc((p.ai_name || '').replace(/^AI-/, '').replace(/皮皮/g, '扣子'))}</td>
                <td class="${hitClass('win_loss', hitStatus)}">${esc(winLoss)}</td>
                <td class="${hitClass('handicap_win_loss', hitStatus)}">${esc(handicap)}</td>
                <td class="${hitClass('total_points', hitStatus)}">${esc(totalPts)}</td>
                <td class="${hitClass('score_diff_range', hitStatus)}">${esc(scoreDiff)}</td>
                <td style="color:#94a3b8;font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;">${esc(p.reason || '')}</td>
            </tr>
            `;
        } else {
            const hasHandicap = match.handicap != null && match.handicap !== '' && match.handicap !== undefined;
            const spf = pred.spf || '-';
            const handicap = hasHandicap ? (pred.handicap_spf || '-') : '';
            
            // 进球数：优先读顶层 p.goals（后端已计算好），其次读 pred.goals，最后从比分计算
            let goals = '-';
            if (p.goals != null) {
                goals = p.goals;
            } else if (pred.goals != null) {
                goals = pred.goals;
            } else {
                // 从比分计算
                const scoreStr = p.score_pred || pred.score || '';
                const parts = scoreStr.split(/[-:]/);
                if (parts.length === 2) {
                    const g1 = parseInt(parts[0]);
                    const g2 = parseInt(parts[1]);
                    if (!isNaN(g1) && !isNaN(g2)) {
                        goals = g1 + g2;
                    }
                }
            }
            
            const score = pred.score || '-';
            const halfFull = pred.half_full || '-';
            
            return `
            <tr>
                <td style="text-align:left;font-weight:500;color:#a78bfa;">${esc((p.ai_name || '').replace(/^AI-/, '').replace(/皮皮/g, '扣子'))}</td>
                <td class="${hitClass('spf', hitStatus)}">${esc(spf)}</td>
                ${hasHandicap ? `<td class="${hitClass('handicap_spf', hitStatus)}">${esc(handicap)}</td>` : ''}
                <td class="${hitClass('goals', hitStatus)}">${esc(goals)}</td>
                <td class="${hitClass('score', hitStatus)}">${esc(score)}</td>
                <td class="${hitClass('half_full', hitStatus)}">${esc(halfFull)}</td>
                <td style="color:#94a3b8;font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;">${esc(p.reason || '')}</td>
            </tr>
            `;
        }
    }).join('');
    
    if (isBasketball) {
        return `
        <div class="inline-predictions-details" style="overflow-x:auto;">
            <table class="inline-predictions-table">
                <thead>
                    <tr>
                        <th style="text-align:left;">AI</th>
                        <th>胜负</th>
                        <th>让分</th>
                        <th>大小分</th>
                        <th>分差</th>
                        <th>理由</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        `;
    } else {
        const hasHandicap = match.handicap != null && match.handicap !== '' && match.handicap !== undefined;
        return `
        <div class="inline-predictions-details" style="overflow-x:auto;">
            <table class="inline-predictions-table">
                <thead>
                    <tr>
                        <th style="text-align:left;">AI</th>
                        <th>胜平负</th>
                        ${hasHandicap ? '<th>让球</th>' : ''}
                        <th>总进球</th>
                        <th>比分</th>
                        <th>半全场</th>
                        <th>理由</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        `;
    }
}

// ============================================================
// 渲染统计数据
// ============================================================
function renderStats() {
    const total = state.allMatches.length;
    const done = state.allMatches.filter(m => isMatchDone(m)).length;
    
    document.getElementById('match-count').textContent = total;
    document.getElementById('done-count').textContent = done;
}
// ============================================================
// AI排行渲染 - 5维命中率表格
// ============================================================
function renderRanking() {
    const container = document.getElementById('ranking-list');
    if (!container) return;
    const activeAIs = (state.aiStats || []).filter(ai => ai.is_active === true).sort((a, b) => (b.hit_rate || 0) - (a.hit_rate || 0));
    if (activeAIs.length === 0) {
        container.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">暂无排行数据</div>';
        return;
    }
    const fmt = (v) => (v != null ? Number(v).toFixed(1) + '%' : '-');
    container.innerHTML = '<table style="width:100%;font-size:13px;"><thead><tr style="color:#94a3b8;"><th style="text-align:left;padding:6px 4px;">排名</th><th style="text-align:left;padding:6px 4px;">AI</th><th style="text-align:right;padding:6px 4px;">胜平负</th><th style="text-align:right;padding:6px 4px;">让球</th><th style="text-align:right;padding:6px 4px;">总进球</th><th style="text-align:right;padding:6px 4px;">比分</th><th style="text-align:right;padding:6px 4px;">半全场</th></tr></thead><tbody>' + activeAIs.map((ai, i) => {
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : (i + 1);
        return '<tr><td style="padding:6px 4px;">' + medal + '</td><td style="padding:6px 4px;">' + (ai.ai_name || '').replace(/^AI-/, '').replace(/皮皮/g, '扣子') + '</td><td style="padding:6px 4px;text-align:right;">' + fmt(ai.hit_rate) + '</td><td style="padding:6px 4px;text-align:right;">' + fmt(ai.let_hit) + '</td><td style="padding:6px 4px;text-align:right;">' + fmt(ai.goals_hit) + '</td><td style="padding:6px 4px;text-align:right;">' + fmt(ai.score_hit) + '</td><td style="padding:6px 4px;text-align:right;">' + fmt(ai.half_full_hit) + '</td></tr>';
    }).join('') + '</tbody></table>';
}
// ============================================================
// AI Logo 渲染
// ============================================================
function renderAILogos() {

    const container = document.getElementById('ai-logos');
    if (!container) return;
    
    const aiColors = {
        'DeepSeek': '#6366f1',
        '智谱清言': '#f59e0b',
        '文心': '#3b82f6',
        '混元': '#10b981',
        '扣子': '#8b5cf6',
        '扣子（皮皮）': '#8b5cf6',
        'MiniMax': '#ef4444',
        '豆包': '#06b6d4',
        'Kimi': '#64748b',
        '千问': '#f97316',
        '天工': '#ec4899'
    };
    
    const activeAIs = (state.aiStats || []).filter(ai => ai.is_active === true).sort((a, b) => (a.rank || 99) - (b.rank || 99));
    if (activeAIs.length === 0) return;
    container.innerHTML = activeAIs.map(ai => {
        const color = aiColors[ai.ai_name] || '#6b7280';
        return '<div class="ai-logo"><div class="dot" style="background:' + color + ';">' + (ai.ai_name || '?').replace(/^AI-/, '').replace(/皮皮/g, '扣子')[0] + '</div>' + (ai.ai_name || '未知').replace(/^AI-/, '').replace(/皮皮/g, '扣子') + '</div>';
    }).join('');
}
// ============================================================
// switchSport - 排行榜体育筛选
// ============================================================
function switchSport(sport) {
    document.querySelectorAll(".sport-tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.sport === sport);
    });
    const rows = document.querySelectorAll("#ranking-list tr");
    rows.forEach(row => {
        if (sport === "all") {
            row.style.display = "";
        } else {
            const rowSport = row.dataset.sport || "football";
            row.style.display = rowSport === sport ? "" : "none";
        }
    });
}
window.switchSport = switchSport;
// ============================================================
// 初始化
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
    try {
        state.aiStats = await fetchAIStats();
    } catch (e) {
        console.error('获取AI统计失败:', e);
    }
    renderAILogos();
    loadAll();
});
