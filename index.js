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
} from './api.js?v=2026070715';

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
            const visibleCount = Math.min(5, footballMatches.length);
            const visibleMatches = footballMatches.slice(0, visibleCount);
            const hiddenMatches = footballMatches.slice(visibleCount);
            
            let html = visibleMatches.map(m => renderMatchCard(m)).join('');
            if (hiddenMatches.length > 0) {
                html += `<div id="football-more-matches" style="display:none;">${hiddenMatches.map(m => renderMatchCard(m)).join('')}</div>`;
                html += `<div id="football-more-btn" style="text-align:center;padding:12px 0;border-top:1px solid rgba(255,255,255,0.08);cursor:pointer;color:#a78bfa;font-size:13px;" onclick="expandMoreMatches('football')">展开更多 (${hiddenMatches.length}场) ▼</div>`;
            }
            footballContainer.innerHTML = html;
            
            // 绑定所有比赛卡片的点击事件
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
            const visibleCount = Math.min(5, basketballMatches.length);
            const visibleMatches = basketballMatches.slice(0, visibleCount);
            const hiddenMatches = basketballMatches.slice(visibleCount);
            
            let html = visibleMatches.map(m => renderMatchCard(m)).join('');
            if (hiddenMatches.length > 0) {
                html += `<div id="basketball-more-matches" style="display:none;">${hiddenMatches.map(m => renderMatchCard(m)).join('')}</div>`;
                html += `<div id="basketball-more-btn" style="text-align:center;padding:12px 0;border-top:1px solid rgba(255,255,255,0.08);cursor:pointer;color:#a78bfa;font-size:13px;" onclick="expandMoreMatches('basketball')">展开更多 (${hiddenMatches.length}场) ▼</div>`;
            }
            basketballContainer.innerHTML = html;
            
            // 绑定所有比赛卡片的点击事件
            basketballContainer.querySelectorAll('.match-card-clickable').forEach(card => {
                card.addEventListener('click', () => toggleMatchPredictions(card.dataset.matchId));
            });
        }
        document.getElementById('basketball-count-label').textContent = `${basketballMatches.length}场`;
    }
    
    document.getElementById('match-count-label').textContent = `${dateMatches.length}场`;
}

// 展开更多比赛
window.expandMoreMatches = function(sport) {
    const moreMatches = document.getElementById(`${sport}-more-matches`);
    const moreBtn = document.getElementById(`${sport}-more-btn`);
    if (moreMatches) {
        moreMatches.style.display = 'block';
    }
    if (moreBtn) {
        moreBtn.style.display = 'none';
    }
    // 重新绑定展开后卡片的点击事件
    const container = document.getElementById(sport === 'football' ? 'view-football' : 'view-basketball');
    if (container) {
        container.querySelectorAll('.match-card-clickable').forEach(card => {
            card.addEventListener('click', () => toggleMatchPredictions(card.dataset.matchId));
        });
    }
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
        const rawPredictions = matchPredictions.map(p => p.spf || p.win_loss).filter(Boolean);
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
    const container = document.getElementById("ranking-list");
    if (!container) return;
    const activeAIs = (state.aiStats || []).filter(ai => ai.is_active === true);
    if (activeAIs.length === 0) {
        container.innerHTML = "<div style=\"padding:20px;text-align:center;color:#94a3b8;\">暂无排行数据</div>";
        return;
    }

    // 建立比赛结果映射
    const matchMap = {};
    (state.allMatches || []).forEach(m => {
        if (m.home_score != null && m.away_score != null && ["已确认","已完成","已结束"].includes(m.status)) {
            matchMap[m.id] = m;
        }
    });

    // 从predictions计算5维度
    const dimStats = {};
    activeAIs.forEach(ai => {
        dimStats[ai.ai_name] = { matches:0, spf_t:0,spf_h:0, let_t:0,let_h:0, score_t:0,score_h:0, goals_t:0,goals_h:0, half_t:0,half_h:0 };
    });

    (state.predictions || []).forEach(p => {
        const ai = p.ai_name;
        if (!dimStats[ai]) return;
        const m = matchMap[p.match_id];
        if (!m) return;
        dimStats[ai].matches++;
        const home = m.home_score, away = m.away_score;
        const sport = p.sport_type || "football";

        // 1. 胜平负/胜负
        if (sport === "football" && p.spf) {
            dimStats[ai].spf_t++;
            var spfActual = home>away ? "主胜" : (home===away ? "平局" : "客胜");
            var spfPred = p.spf;
            if (spfPred === "胜") spfPred = "主胜";
            else if (spfPred === "平") spfPred = "平局";
            else if (spfPred === "负") spfPred = "客胜";
            if (spfActual === spfPred) dimStats[ai].spf_h++;
        } else if (sport === "basketball" && p.win_loss) {
            dimStats[ai].spf_t++;
            if ((home>away && p.win_loss==="胜") || (home<away && p.win_loss==="负")) dimStats[ai].spf_h++;
        }

        // 2. 让球/让分
        if (sport === "football" && p.handicap_spf) {
            dimStats[ai].let_t++;
            const hc = parseFloat(m.handicap || 0);
            const adj = home + hc;
            const actual = adj>away ? "胜" : (adj===away ? "平" : "负");
            const pred = p.handicap_spf.includes("胜") && !p.handicap_spf.includes("负") ? "胜" : (p.handicap_spf.includes("平") ? "平" : "负");
            if (actual === pred) dimStats[ai].let_h++;
        } else if (sport === "basketball" && p.handicap_win_loss) {
            dimStats[ai].let_t++;
            const sl = parseFloat(m.spread_line || 0);
            const adj = home + sl;
            if ((adj>away && p.handicap_win_loss==="让胜") || (adj<away && p.handicap_win_loss==="让负")) dimStats[ai].let_h++;
        }

        // 3. 比分
        if (p.score) {
            dimStats[ai].score_t++;
            if (p.score === home + "-" + away) dimStats[ai].score_h++;
        }

        // 4. 进球数/总分
        if (sport === "football" && p.goals != null) {
            dimStats[ai].goals_t++;
            if (parseInt(p.goals) === home + away) dimStats[ai].goals_h++;
        } else if (sport === "basketball" && p.total_points) {
            dimStats[ai].goals_t++;
            const tl = parseFloat(m.total_line || 0);
            if (tl && ((home+away>tl && p.total_points==="大") || (home+away<tl && p.total_points==="小"))) dimStats[ai].goals_h++;
        }

        // 5. 半全场
        if (sport === "football" && p.half_full) {
            dimStats[ai].half_t++;
            const hh = m.half_home_score, ha = m.half_away_score;
            if (hh != null && ha != null) {
                const hr = hh>ha ? "胜" : (hh===ha ? "平" : "负");
                const fr = home>away ? "胜" : (home===away ? "平" : "负");
                if (p.half_full === hr+fr) dimStats[ai].half_h++;
            }
        } else if (sport === "basketball" && p.half_win_loss) {
            dimStats[ai].half_t++;
            const hh = m.half_home_score, ha = m.half_away_score;
            if (hh != null && ha != null) {
                if ((hh>ha && p.half_win_loss==="胜") || (hh<ha && p.half_win_loss==="负")) dimStats[ai].half_h++;
            }
        }
    });

    // 存储到全局供tab切换使用
    window._dimStats = dimStats;
    window._activeAIs = activeAIs;

    // 渲染默认总榜
    renderRankingContent('all');
}

// 切换排行tab
window.switchRankTab = function(dim) {
    // 更新tab样式
    document.querySelectorAll('.rank-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.dim === dim);
    });
    // 渲染对应维度内容
    renderRankingContent(dim);
};

// 渲染排行内容
function renderRankingContent(dim) {
    const container = document.getElementById("ranking-list");
    if (!container) return;
    const dimStats = window._dimStats;
    const activeAIs = window._activeAIs;
    if (!dimStats || !activeAIs) return;

    const medal = (r) => r===1?"🥇":r===2?"🥈":r===3?"🥉":r;
    const th = "padding:5px 3px;font-size:10px;color:#94a3b8;text-align:center;";
    const td = "padding:5px 3px;font-size:12px;text-align:center;";
    const fmtPct = (h,t) => t>0 ? (h*100/t).toFixed(0)+"%" : "—";

    // 维度配置
    const dimConfig = {
        'spf': { key: 'spf', label: '胜平负' },
        'let': { key: 'let', label: '让球' },
        'score': { key: 'score', label: '比分' },
        'goals': { key: 'goals', label: '进球' },
        'half': { key: 'half', label: '半全场' }
    };

    if (dim === 'all') {
        // 总榜：按命中率排序，显示5列
        const sorted = [...activeAIs].sort((a, b) => {
            const sa = dimStats[a.ai_name], sb = dimStats[b.ai_name];
            const ra = sa.spf_t ? sa.spf_h/sa.spf_t : 0;
            const rb = sb.spf_t ? sb.spf_h/sb.spf_t : 0;
            return rb - ra;
        });

        let html = "<table style=\"width:100%;border-collapse:collapse;\">";
        html += "<thead><tr>";
        html += "<th style=\""+th+"text-align:left;\">排名</th>";
        html += "<th style=\""+th+"text-align:left;\">AI</th>";
        html += "<th style=\""+th+"\">命中率</th>";
        html += "<th style=\""+th+"\">让球</th>";
        html += "<th style=\""+th+"\">比分</th>";
        html += "<th style=\""+th+"\">进球</th>";
        html += "<th style=\""+th+"\">半全场</th>";
        html += "</tr></thead><tbody>";

        sorted.forEach((ai, i) => {
            const d = dimStats[ai.ai_name];
            html += "<tr>";
            html += "<td style=\""+td+"text-align:left;\">"+medal(i+1)+"</td>";
            html += "<td style=\""+td+"text-align:left;font-weight:600;\">"+(ai.ai_name||"")+"</td>";
            html += "<td style=\""+td+"color:#fbbf24;\">"+fmtPct(d.spf_h,d.spf_t)+"</td>";
            html += "<td style=\""+td+"\">"+fmtPct(d.let_h,d.let_t)+"</td>";
            html += "<td style=\""+td+"\">"+fmtPct(d.score_h,d.score_t)+"</td>";
            html += "<td style=\""+td+"\">"+fmtPct(d.goals_h,d.goals_t)+"</td>";
            html += "<td style=\""+td+"\">"+fmtPct(d.half_h,d.half_t)+"</td>";
            html += "</tr>";
        });

        html += "</tbody></table>";
        container.innerHTML = html;
    } else {
        // 单维度榜
        const cfg = dimConfig[dim];
        if (!cfg) return;

        const sorted = [...activeAIs].sort((a, b) => {
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

        sorted.forEach((ai, i) => {
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
