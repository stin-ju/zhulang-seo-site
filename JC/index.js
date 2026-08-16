// v=202607150416 cache bust
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
// 固定AI列表（不再从数据库动态获取）
// ============================================================
const AI_NAMES = [
    "扣子",
    "豆包",
    "文心",
    "混元",
    "DeepSeek",
    "智谱清言",
    "MiniMax"
];

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
    dates: [],
    expandedLeft: false,
    expandedRight: false
};

// 增量统计缓存
let dimStatsCache = null;
let lastPredictionsLength = -1;
let lastMatchesLength = -1;

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
            // 分别获取足球和篮球预测（API按sport过滤）
            const [footballPreds, basketballPreds] = await Promise.all([
                fetchPredictions(matchIds, 'football'),
                fetchPredictions(matchIds, 'basketball')
            ]);
            state.predictions = [...footballPreds, ...basketballPreds];
        }
        
        state.aiStats = await fetchAIStats();
        
        state.dates = [...new Set(allMatches.map(m => getMatchDate(m)))].sort().reverse();
        
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

// 日期标签：前2日+当日+后4日，其余折叠
function renderDateTabs() {
    const container = document.getElementById('date-bar');
    if (!container) return;
    
    const today = new Date();
    const todayStr = getLocalDateStr(today);
    
    // state.dates已按时间倒序排列（最新在左）
    const allDates = state.dates;
    const todayIndex = allDates.indexOf(todayStr);
    
    // 计算可见范围：前2日+当日+后4日 = 7天
    // 倒序数组中：todayIndex左边是未来日期（后4日），右边是过去日期（前2日）
    let visibleStart = Math.max(0, todayIndex - 4); // 后4日（未来）
    let visibleEnd = Math.min(allDates.length - 1, todayIndex + 2); // 前2日（过去）
    
    // 处理展开状态
    if (state.expandedLeft) {
        visibleStart = 0; // 展开所有更新的日期
    }
    if (state.expandedRight) {
        visibleEnd = allDates.length - 1; // 展开所有更旧的日期
    }
    
    const visibleDates = allDates.slice(visibleStart, visibleEnd + 1);
    const hasMoreBefore = visibleEnd < allDates.length - 1; // 右边还有更旧的日期
    const hasMoreAfter = visibleStart > 0; // 左边还有更新的日期
    
    let html = '';
    
    // 左边展开按钮（如果有更新的日期且未展开）
    if (hasMoreAfter && !state.expandedLeft) {
        html += `<button class="date-btn expand-btn" data-action="expand-left">...</button>`;
    }
    
    // 可见日期
    html += visibleDates.map(date => {
        const isToday = date === todayStr;
        const isActive = date === state.currentDate;
        
        return `
            <button class="date-btn ${isActive ? 'active' : ''}" 
                    data-date="${date}">
                ${fmtDateLabel(date)}${isToday ? ' 今天' : ''}
            </button>
        `;
    }).join('');
    
    // 右边展开按钮（如果有更旧的日期且未展开）
    if (hasMoreBefore && !state.expandedRight) {
        html += `<button class="date-btn expand-btn" data-action="expand-right">...</button>`;
    }
    
    container.innerHTML = html;
    
    // 日期按钮点击事件
    container.querySelectorAll('.date-btn:not(.expand-btn)').forEach(btn => {
        btn.addEventListener('click', () => {
            state.currentDate = btn.dataset.date;
            renderDateTabs();
            renderMatches();
        });
    });
    
    // 展开按钮点击事件
    container.querySelectorAll('.expand-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.dataset.action;
            if (action === 'expand-left') {
                // 展开所有更新的日期
                state.expandedLeft = true;
            } else if (action === 'expand-right') {
                // 展开所有更旧的日期
                state.expandedRight = true;
            }
            renderDateTabs();
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
            const visibleCount = Math.min(5, footballMatches.length);
            const visibleMatches = footballMatches.slice(0, visibleCount);
            const hiddenMatches = footballMatches.slice(visibleCount);
            
            let html = visibleMatches.map(m => renderMatchCard(m)).join('');
            if (hiddenMatches.length > 0) {
                html += `<div id="football-more-matches" style="display:none;">${hiddenMatches.map(m => renderMatchCard(m)).join('')}</div>`;
                html += `<div id="football-more-btn" style="text-align:center;padding:12px 0;border-top:1px solid rgba(255,255,255,0.08);cursor:pointer;color:#a78bfa;font-size:13px;" onclick="expandMoreMatches('football')">展开更多 (${hiddenMatches.length}场) ▼</div>`;
            }
            footballContainer.innerHTML = html;
            
            // 事件委托：点击比赛卡片展开/收起预测
            if (!footballContainer.dataset.delegated) {
                footballContainer.dataset.delegated = 'true';
                footballContainer.addEventListener('click', function(e) {
                    const card = e.target.closest('.match-card-clickable');
                    if (card && footballContainer.contains(card)) {
                        toggleMatchPredictions(card.dataset.matchId);
                    }
                });
            }
        }
        document.getElementById('football-count-label').textContent = `${footballMatches.length}场`;
    }
    
    const basketballContainer = document.getElementById('view-basketball');
    if (basketballContainer) {
        const basketballMatches = dateMatches.filter(m => m.sport_type === 'basketball');
        if (basketballMatches.length === 0) {
            basketballContainer.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">当天没有篮球赛程</div>';
        } else {
            const visibleCount = Math.min(5, basketballMatches.length);
            const visibleMatches = basketballMatches.slice(0, visibleCount);
            const hiddenMatches = basketballMatches.slice(visibleCount);
            
            let html = visibleMatches.map(m => renderMatchCard(m)).join('');
            if (hiddenMatches.length > 0) {
                html += `<div id="basketball-more-matches" style="display:none;">${hiddenMatches.map(m => renderMatchCard(m)).join('')}</div>`;
                html += `<div id="basketball-more-btn" style="text-align:center;padding:12px 0;border-top:1px solid rgba(255,255,255,0.08);cursor:pointer;color:#a78bfa;font-size:13px;" onclick="expandMoreMatches('basketball')">展开更多 (${hiddenMatches.length}场) ▼</div>`;
            }
            basketballContainer.innerHTML = html;
            
            // 事件委托：点击比赛卡片展开/收起预测
            if (!basketballContainer.dataset.delegated) {
                basketballContainer.dataset.delegated = 'true';
                basketballContainer.addEventListener('click', function(e) {
                    const card = e.target.closest('.match-card-clickable');
                    if (card && basketballContainer.contains(card)) {
                        toggleMatchPredictions(card.dataset.matchId);
                    }
                });
            }
        }
        document.getElementById('basketball-count-label').textContent = `${basketballMatches.length}场`;
    }
    
    document.getElementById('match-count-label').textContent = `${dateMatches.length}场`;
}

// 展开/收起更多比赛
window.expandMoreMatches = function(sport) {
    const moreMatches = document.getElementById(`${sport}-more-matches`);
    const moreBtn = document.getElementById(`${sport}-more-btn`);
    if (moreMatches && moreBtn) {
        const isExpanded = moreMatches.style.display === 'block';
        if (isExpanded) {
            // 收起
            moreMatches.style.display = 'none';
            const hiddenCount = moreMatches.querySelectorAll('.match-card-clickable').length;
            moreBtn.innerHTML = `展开更多 (${hiddenCount}场) ▼`;
        } else {
            // 展开
            moreMatches.style.display = 'block';
            moreBtn.innerHTML = '收起 ▲';
        }
    }
}

// 渲染比赛卡片
function renderMatchCard(match) {
    const matchPredictions = state.predictions.filter(p => p.match_id === match.id);
    const homeTeam = match.home_team || '主队';
    const awayTeam = match.away_team || '客队';
    const matchTime = fmtTime(match.match_time);
    const isDone = isMatchDone(match);
    
    // 构建 badges
    let badges = '';
    
    // 状态badge
    if (match.status === '已取消') {
        badges += `<span class="badge-sm" style="background:rgba(107,114,128,0.2);color:#9ca3af;">已取消</span>`;
    } else if (!isDone && match.status === '未开赛') {
        badges += `<span class="badge-sm status-pending">待比赛</span>`;
    }
    
    // 售卖状态badge（pending显示为"待售"）
    if (match.selling_status === 'pending' && match.status !== '已取消') {
        badges += `<span class="badge-sm" style="background:rgba(245,194,66,0.15);color:#F5C242;">待售</span>`;
    }
    
    // 共识度/分歧度（基于预测）
    if (matchPredictions.length > 0) {
        const rawPredictions = matchPredictions.map(p => p.prediction?.spf || p.prediction?.win_loss).filter(Boolean);
        const predictions = rawPredictions.map(v => v.includes('胜') ? '胜' : v.includes('负') ? '负' : v.includes('平') ? '平' : v).filter(Boolean);
        if (predictions.length > 0) {
            const counts = {};
            predictions.forEach(p => { counts[p] = (counts[p] || 0) + 1; });
            const maxCount = Math.max(...Object.values(counts));
            const consensus = maxCount / predictions.length;
            
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
    
    // 构建赔率显示（已移除胜平负赔率展示）
    const isBasketball = (match.sport_type || 'football') === 'basketball';
    
    // 联赛名称：直接放在time文字前
    const leagueName = (match.metadata && match.metadata.league) || '';
    const leaguePrefix = leagueName ? `[${esc(leagueName)}] ` : '';

    // 让球格式化：正数加+号（已有+号则不加）
    const handicapVal = parseFloat(match.handicap);
    const handicapStr = match.handicap || '';
    const handicapDisplay = !isNaN(handicapVal)
        ? (handicapVal > 0 && !handicapStr.startsWith('+') ? '+' + handicapStr : handicapStr)
        : handicapStr;

    return `
        <div class="view-item match-card-clickable" data-match-id="${match.id}">
            <span class="time">${leaguePrefix}${matchTime}</span>
            ${match.id ? `<a href="/ia2.html?match=${encodeURIComponent(match.id)}" class="match-lottery-id" onclick="event.stopPropagation()">${match.id}</a>` : ''}
            <span class="teams">${esc(homeTeam)} ${isDone && match.home_score != null ? '<span class="score-inline">' + match.home_score + ':' + match.away_score + '</span>' : match.status === '已取消' ? '<span class="score-inline" style="color:#9ca3af;">已取消</span>' : 'vs'} ${esc(awayTeam)}${handicapDisplay ? ' <span class="handicap-tag">' + handicapDisplay + '</span>' : ''}</span>
            <div class="badge-group">
                ${badges}
                ${predCount > 0 ? `<span class="badge-sm" style="background:rgba(139,92,246,0.1);color:#a78bfa;">${predCount}AI预测</span>` : ''}
                <a href="${isBasketball ? '/bb2.html' : '/ia2.html'}?match=${encodeURIComponent(match.id || '')}" class="badge-sm analysis-link" onclick="event.stopPropagation()" style="background:rgba(139,92,246,0.15);color:#a78bfa;text-decoration:none;">AI分析</a>
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
    
    // 判断运动类型
    const sport = (match && match.sport_type) || (predictions[0] && predictions[0].sport_type) || 'football';
    const isBasketball = sport === 'basketball';
    
    // 按总命中数降序排列
    const sorted = [...predictions].sort((a, b) => (b.total_hits || 0) - (a.total_hits || 0));
    
    // 根据运动类型定义字段映射
    const fieldConfig = isBasketball ? {
        // 篮球字段（4维度，无半场）
        col1: { key: 'win_loss', fallbackKey: 'win_loss', hitKey: 'win_loss', label: '胜负' },
        col2: { key: 'handicap_win_loss', fallbackKey: 'handicap_result', hitKey: 'handicap_win_loss', label: '让分' },
        col3: { key: 'score_diff_range', fallbackKey: 'score_diff', hitKey: 'score_diff_range', label: '胜分差' },
        col4: { key: 'total_points', fallbackKey: 'total_points', hitKey: 'total_points', label: '总分' }
    } : {
        // 足球字段
        col1: { key: 'win_loss', fallbackKey: 'spf', hitKey: 'spf', label: '胜平负' },
        col2: { key: 'handicap_win_loss', fallbackKey: 'handicap_spf', hitKey: 'handicap_spf', label: '让球' },
        col3: { key: 'score', hitKey: 'score', label: '比分' },
        col4: { key: 'goals', hitKey: 'goals', label: '进球数' },
        col5: { key: 'half_full', hitKey: 'half_full', label: '半全场' }
    };
    
    // 获取预测值（优先从顶层字段，其次从prediction JSON字段）
    function getPredValue(pred, key, fallbackKey) {
        const prediction = pred.prediction || {};
        const rawKeyMap = {'handicap_win_loss':'handicap_result','score_diff_range':'score_diff'};
        const rawKey = rawKeyMap[key] || key;
        return pred[key] || pred[key+'_pred'] || prediction[key] || prediction[rawKey] || (fallbackKey && (pred[fallbackKey]||prediction[fallbackKey])) || '-';
    }
    
    // 判断命中状态（从hit_status JSON字段）
    function cellClass(pred, hitKey) {
        if (!hitKey) return '';
        const hitStatus = pred.hit_status || {};
        if (hitStatus[hitKey] === undefined || hitStatus[hitKey] === null) return '';
        return hitStatus[hitKey] === true ? 'hit' : 'miss';
    }
    
    return `
        <div class="inline-predictions-table-wrap">
            <table class="inline-predictions-table">
                <thead>
                    <tr>
                        <th>AI</th>
                        <th>${fieldConfig.col1.label}</th>
                        <th>${fieldConfig.col2.label}</th>
                        <th>${fieldConfig.col3.label}</th>
                        <th>${fieldConfig.col4.label}</th>
                        ${!isBasketball ? '<th>' + fieldConfig.col5.label + '</th>' : ''}
                        <th>命中</th>
                    </tr>
                </thead>
                <tbody>
                    ${sorted.map(p => `
                        <tr>
                            <td>${esc(p.ai_name)}</td>
                            <td class="${cellClass(p, fieldConfig.col1.hitKey)}">${getPredValue(p, fieldConfig.col1.key, fieldConfig.col1.fallbackKey)}</td>
                            <td class="${cellClass(p, fieldConfig.col2.hitKey)}">${getPredValue(p, fieldConfig.col2.key, fieldConfig.col2.fallbackKey)}</td>
                            <td class="${cellClass(p, fieldConfig.col3.hitKey)}">${getPredValue(p, fieldConfig.col3.key, fieldConfig.col3.fallbackKey)}</td>
                            <td class="${cellClass(p, fieldConfig.col4.hitKey)}">${getPredValue(p, fieldConfig.col4.key)}</td>
                            ${!isBasketball ? '<td class="' + cellClass(p, fieldConfig.col5.hitKey) + '">' + getPredValue(p, fieldConfig.col5.key) + '</td>' : ''}
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
// 维度配置（按运动类型）
const DIM_CONFIGS = {
    football: {
        'spf': { key: 'spf', label: '胜平负' },
        'let': { key: 'let', label: '让球' },
        'score': { key: 'score', label: '比分' },
        'goals': { key: 'goals', label: '进球' },
        'half': { key: 'half', label: '半全场' }
    },
    basketball: {
        'spf': { key: 'spf', label: '胜负' },
        'let': { key: 'let', label: '让分' },
        'sdr': { key: 'sdr', label: '胜分差' },
        'goals': { key: 'goals', label: '总分' }
    }
};

// 初始化运动类型
if (!state.currentSport) state.currentSport = 'all';

// 渲染维度tab
function renderDimTabs(sport) {
    const container = document.getElementById('rank-tabs');
    if (!container) return;
    const isFootball = sport !== 'basketball';
    const config = isFootball ? DIM_CONFIGS.football : DIM_CONFIGS.basketball;
    let html = '<span class="rank-tab active" data-dim="all" onclick="switchRankTab(\'all\')">总榜</span>';
    Object.entries(config).forEach(function(entry) {
        html += '<span class="rank-tab" data-dim="' + entry[0] + '" onclick="switchRankTab(\'' + entry[0] + '\')">' + entry[1].label + '</span>';
    });
    container.innerHTML = html;
}

// 计算维度命中统计（增量缓存）
function computeDimStats(predictions, matchMap, activeAIs) {
    // 检查缓存是否有效
    const currentPredictionsLength = predictions.length;
    const currentMatchesLength = Object.keys(matchMap).length;
    
    if (dimStatsCache && 
        lastPredictionsLength === currentPredictionsLength && 
        lastMatchesLength === currentMatchesLength) {
        // 缓存有效，直接返回
        return dimStatsCache;
    }
    
    // 缓存无效，重新计算
    const dimStats = {};
    activeAIs.forEach(function(ai) {
        dimStats[ai.ai_name] = { matches:0, spf_t:0,spf_h:0, let_t:0,let_h:0, score_t:0,score_h:0, goals_t:0,goals_h:0, half_t:0,half_h:0, sdr_t:0,sdr_h:0 };
    });

    predictions.forEach(function(p) {
        const ai = p.ai_name;
        if (!dimStats[ai]) return;
        const m = matchMap[p.match_id];
        if (!m) return;
        dimStats[ai].matches++;
        const home = m.home_score, away = m.away_score;
        const sport = m.sport_type || "football";
        const pred = p.prediction || {};

        // 1. 胜平负/胜负
        if (sport === "football" && pred.spf) {
            dimStats[ai].spf_t++;
            var spfActual = home>away ? "主胜" : (home===away ? "平局" : "客胜");
            var spfPred = pred.spf;
            if (spfPred === "胜") spfPred = "主胜";
            else if (spfPred === "平") spfPred = "平局";
            else if (spfPred === "负") spfPred = "客胜";
            if (spfActual === spfPred) dimStats[ai].spf_h++;
        } else if (sport === "basketball" && pred.win_loss) {
            dimStats[ai].spf_t++;
            if ((home>away && pred.win_loss==="胜") || (home<away && pred.win_loss==="负")) dimStats[ai].spf_h++;
        }

        // 2. 让球/让分
        if (sport === "football" && pred.handicap_spf) {
            dimStats[ai].let_t++;
            const hc = parseFloat(m.handicap || 0);
            const adj = home + hc;
            const actual = adj>away ? "胜" : (adj===away ? "平" : "负");
            const predVal = pred.handicap_spf;
            const predNorm = predVal.includes("胜") && !predVal.includes("负") ? "胜" : (predVal.includes("平") ? "平" : "负");
            if (actual === predNorm) dimStats[ai].let_h++;
        } else if (sport === "basketball" && pred.handicap_win_loss) {
            dimStats[ai].let_t++;
            const sl = parseFloat(m.spread_line || 0);
            const adj = home + sl;
            if ((adj>away && pred.handicap_win_loss==="让胜") || (adj<away && pred.handicap_win_loss==="让负")) dimStats[ai].let_h++;
        }

        // 3. 比分
        if (pred.score) {
            dimStats[ai].score_t++;
            if (pred.score === home + "-" + away) dimStats[ai].score_h++;
        }

        // 4. 进球数/总分
        if (sport === "football" && pred.goals != null) {
            dimStats[ai].goals_t++;
            if (parseInt(pred.goals) === home + away) dimStats[ai].goals_h++;
        } else if (sport === "basketball" && pred.total_points) {
            dimStats[ai].goals_t++;
            const tl = parseFloat(m.total_line || 0);
            if (tl && ((home+away>tl && pred.total_points==="大") || (home+away<tl && pred.total_points==="小"))) dimStats[ai].goals_h++;
        }

        // 5. 半全场
        if (sport === "football" && pred.half_full) {
            dimStats[ai].half_t++;
            const hh = m.half_home_score, ha = m.half_away_score;
            if (hh != null && ha != null) {
                const hr = hh>ha ? "胜" : (hh===ha ? "平" : "负");
                const fr = home>away ? "胜" : (home===away ? "平" : "负");
                if (pred.half_full === hr+fr) dimStats[ai].half_h++;
            }
        } else if (sport === "basketball" && pred.score_diff_range) {
            dimStats[ai].sdr_t++;
            const diff = Math.abs(home - away);
            let actualRange;
            if (diff >= 1 && diff <= 5) actualRange = "1-5";
            else if (diff >= 6 && diff <= 10) actualRange = "6-10";
            else if (diff >= 11 && diff <= 15) actualRange = "11-15";
            else if (diff >= 16 && diff <= 20) actualRange = "16-20";
            else if (diff >= 21 && diff <= 25) actualRange = "21-25";
            else if (diff >= 26) actualRange = "26+";
            
            let predRange = (pred.score_diff_range || "").replace("21-25", "21+").replace("21+", "21+");
            if (actualRange === "21-25") actualRange = "21+";
            
            if (actualRange === predRange) dimStats[ai].sdr_h++;
        }
    });
    
    // 更新缓存
    dimStatsCache = dimStats;
    lastPredictionsLength = currentPredictionsLength;
    lastMatchesLength = currentMatchesLength;
    
    return dimStats;
}

function renderRanking() {
    const container = document.getElementById("ranking-list");
    if (!container) return;
    
    // 使用固定AI列表，从state.aiStats中获取统计数据
    const statsMap = {};
    (state.aiStats || []).forEach(ai => {
        if (ai.ai_name && !statsMap[ai.ai_name]) {
            statsMap[ai.ai_name] = ai;
        }
    });
    
    const activeAIs = AI_NAMES.map(name => {
        const stats = statsMap[name] || {};
        return {
            ai_name: name,
            is_active: true,
            rank: stats.rank || 99,
            total_pnl: stats.total_pnl || 0,
            hit_rate: stats.hit_rate || '0%',
            matches: stats.matches || 0,
            let_hit: stats.let_hit || '0%',
            score_hit: stats.score_hit || '0%',
            sport_type: stats.sport_type || 'all'
        };
    });
    
    if (activeAIs.length === 0) {
        container.innerHTML = "<div style=\"padding:20px;text-align:center;color:#94a3b8;\">暂无排行数据</div>";
        return;
    }

    // 建立比赛结果映射
    const matchMap = {};
    (state.allMatches || []).forEach(m => {
        if (m.home_score != null && m.away_score != null && ["已确认","已完成","已结束","已完赛"].includes(m.status)) {
            matchMap[m.id] = m;
        }
    });

    // 按运动类型分组计算（通过match获取sport_type）
    const allPreds = state.predictions || [];
    const getPredSport = function(p) { return (matchMap[p.match_id] || {}).sport_type || p.sport_type || 'football'; };
    const footballPreds = allPreds.filter(p => getPredSport(p) === 'football');
    const basketballPreds = allPreds.filter(p => getPredSport(p) === 'basketball');

    window._dimStatsMap = {
        all: computeDimStats(allPreds, matchMap, activeAIs),
        football: computeDimStats(footballPreds, matchMap, activeAIs),
        basketball: computeDimStats(basketballPreds, matchMap, activeAIs)
    };
    window._activeAIs = activeAIs;

    // 渲染维度tab
    renderDimTabs(state.currentSport);

    // 渲染内容
    renderRankingContent('all');
}

// 切换运动类型
window.switchSport = function(sport) {
    state.currentSport = sport;
    document.querySelectorAll('.sport-tab').forEach(function(tab) {
        tab.classList.toggle('active', tab.dataset.sport === sport);
    });
    renderDimTabs(sport);
    renderRankingContent('all');
};

// 切换维度tab
window.switchRankTab = function(dim) {
    document.querySelectorAll('.rank-tab').forEach(function(tab) {
        tab.classList.toggle('active', tab.dataset.dim === dim);
    });
    renderRankingContent(dim);
};

// 渲染排行内容
function renderRankingContent(dim) {
    const container = document.getElementById("ranking-list");
    if (!container) return;
    const sport = state.currentSport || 'all';
    const dimStats = (window._dimStatsMap || {})[sport] || (window._dimStatsMap || {}).all;
    const activeAIs = window._activeAIs;
    if (!dimStats || !activeAIs) return;

    const medal = function(r) { return r===1?"🥇":r===2?"🥈":r===3?"🥉":r; };
    const th = "padding:5px 3px;font-size:10px;color:#94a3b8;text-align:center;";
    const td = "padding:5px 3px;font-size:12px;text-align:center;";
    const fmtPct = function(h,t) { return t>0 ? (h*100/t).toFixed(0)+"%" : "—"; };

    const isFootball = sport !== 'basketball';
    const dimConfig = isFootball ? DIM_CONFIGS.football : DIM_CONFIGS.basketball;

    if (dim === 'all') {
        // 总榜：按主维度命中率排序
        const sorted = [...activeAIs].sort(function(a, b) {
            const sa = dimStats[a.ai_name], sb = dimStats[b.ai_name];
            const ra = sa.spf_t ? sa.spf_h/sa.spf_t : 0;
            const rb = sb.spf_t ? sb.spf_h/sb.spf_t : 0;
            return rb - ra;
        });

        let html = "<table style=\"width:100%;border-collapse:collapse;\">";
        html += "<thead><tr>";
        html += "<th style=\""+th+"text-align:left;\">排名</th>";
        html += "<th style=\""+th+"text-align:left;\">AI</th>";
        // 总榜列头：根据运动类型显示不同标签
        const mainLabel = isFootball ? '命中率' : '命中率';
        html += "<th style=\""+th+"\">"+mainLabel+"</th>";
        if (isFootball) {
            html += "<th style=\""+th+"\">让球</th>";
            html += "<th style=\""+th+"\">比分</th>";
            html += "<th style=\""+th+"\">进球</th>";
            html += "<th style=\""+th+"\">半全场</th>";
        } else {
            html += "<th style=\""+th+"\">让分</th>";
            html += "<th style=\""+th+"\">胜分差</th>";
            html += "<th style=\""+th+"\">总分</th>";
        }
        html += "</tr></thead><tbody>";

        sorted.forEach(function(ai, i) {
            const d = dimStats[ai.ai_name];
            html += "<tr>";
            html += "<td style=\""+td+"text-align:left;\">"+medal(i+1)+"</td>";
            html += "<td style=\""+td+"text-align:left;font-weight:600;\">"+(ai.ai_name||"")+"</td>";
            html += "<td style=\""+td+"color:#fbbf24;\">"+fmtPct(d.spf_h,d.spf_t)+"</td>";
            if (isFootball) {
                html += "<td style=\""+td+"\">"+fmtPct(d.let_h,d.let_t)+"</td>";
                html += "<td style=\""+td+"\">"+fmtPct(d.score_h,d.score_t)+"</td>";
                html += "<td style=\""+td+"\">"+fmtPct(d.goals_h,d.goals_t)+"</td>";
                html += "<td style=\""+td+"\">"+fmtPct(d.half_h,d.half_t)+"</td>";
            } else {
                html += "<td style=\""+td+"\">"+fmtPct(d.let_h,d.let_t)+"</td>";
                html += "<td style=\""+td+"\">"+fmtPct(d.sdr_h,d.sdr_t)+"</td>";
                html += "<td style=\""+td+"\">"+fmtPct(d.goals_h,d.goals_t)+"</td>";
            }
            html += "</tr>";
        });

        html += "</tbody></table>";
        container.innerHTML = html;
    } else {
        // 单维度榜
        const cfg = dimConfig[dim];
        if (!cfg) return;

        const sorted = [...activeAIs].sort(function(a, b) {
            const sa = dimStats[a.ai_name], sb = dimStats[b.ai_name];
            const ra = sa[cfg.key+'_t'] ? sa[cfg.key+'_h']/sa[cfg.key+'_t'] : 0;
            const rb = sb[cfg.key+'_t'] ? sb[cfg.key+'_h']/sb[cfg.key+'_t'] : 0;
            return rb - ra;
        });

        let html = "<table style=\"width:100%;border-collapse:collapse;\">";
        html += "<thead><tr>";
        html += "<th style=\""+th+"text-align:left;\">排名</th>";
        html += "<th style=\""+th+"text-align:left;\">AI</th>";
        html += "<th style=\""+th+"\">命中场次</th>";
        html += "<th style=\""+th+"\">命中率</th>";
        html += "</tr></thead><tbody>";

        sorted.forEach(function(ai, i) {
            const d = dimStats[ai.ai_name];
            const hits = d[cfg.key+'_h'] || 0;
            const total = d[cfg.key+'_t'] || 0;
            const isFirst = i === 0;
            const highlightStyle = isFirst ? "color:#fbbf24;font-weight:700;" : "";

            html += "<tr>";
            html += "<td style=\""+td+"text-align:left;\">"+medal(i+1)+"</td>";
            html += "<td style=\""+td+"text-align:left;font-weight:600;\">"+(ai.ai_name||"")+"</td>";
            html += "<td style=\""+td+highlightStyle+"\">"+hits+"/"+total+"</td>";
            html += "<td style=\""+td+highlightStyle+"\">"+fmtPct(hits,total)+"</td>";
            html += "</tr>";
        });

        html += "</tbody></table>";
        container.innerHTML = html;
    }
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
        '扣子': '#8b5cf6',
        '混元': '#06b6d4',
        '豆包': '#10b981',
        '文心': '#f59e0b',
        '智谱清言': '#ef4444'
    };
    
    // 使用固定AI列表
    const activeAIs = AI_NAMES.map(name => ({
        ai_name: name,
        rank: 99
    }));
    
    if (activeAIs.length === 0) return;
    container.innerHTML = activeAIs.map(ai => {
        const color = aiColors[ai.ai_name] || '#6b7280';
        return '<div class="ai-logo"><div class="dot" style="background:' + color + ';">' + (ai.ai_name || '?')[0] + '</div>' + (ai.ai_name || '未知') + '</div>';
    }).join('');
}

// ============================================================
// 初始化（支持bfcache恢复）
// ============================================================
async function init() {
    // 先加载AI数据，再渲染Logo
    try {
        state.aiStats = await fetchAIStats();
    } catch (e) {
        console.error('获取AI统计失败:', e);
    }
    renderAILogos();
    loadAll();
}

// 首次加载
document.addEventListener('DOMContentLoaded', init);

// bfcache恢复时重新加载（从其他页面返回时）
window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
        // 页面从bfcache恢复，重新初始化
        console.log('[PageShow] 从bfcache恢复，重新加载数据');
        init();
    }
});
