<script>
// ============ 动态加载篮球预测（含大小分） ============
(async function loadBasketballPredictions() {
  const AI_LOGOS = {
    '混元': ['#8b5cf6', 'HX'],
    '豆包': ['#ff6b35', 'DB'],
    'DeepSeek': ['#3b82f6', 'DS'],
    'MiniMax': ['#ef4444', 'MM'],
    '扣子（皮皮）': ['#06b6d4', 'KZ'],
    'BetAgent': ['#f59e0b', 'BA'],
    'Grok': ['#10b981', 'GK'],
    '文心': ['#ec4899', 'WX'],
    '智谱清言': ['#6366f1', 'ZP']
  };

  function getAiLogoHtml(aiName) {
    const [color, abbr] = AI_LOGOS[aiName] || ['#6b7280', aiName.slice(0, 2)];
    return `<span class="ai-logo"><span class="dot" style="background:${color}">${abbr}</span><span>${aiName}</span></span>`;
  }

  // Format over/under display
  function formatTotalPoints(totalPoints) {
    if (!totalPoints) return '大小:--';
    return `大小:${totalPoints}`;
  }

  // Format score difference range with win/loss indicator
  function formatScoreDiff(scoreDiff, winLoss) {
    if (!scoreDiff) return '胜分差:--';
    const prefix = winLoss === '主胜' ? '主胜' : winLoss === '客胜' ? '客胜' : '';
    return `胜分差:${prefix}${scoreDiff}`;
  }

  try {
    // Fetch both predictions and matches to get team names
    const [predsResp, matchesResp] = await Promise.all([
      fetch('/api/predictions'),
      fetch('/api/matches')
    ]);
    const predictions = await predsResp.json();
    const matches = await matchesResp.json();

    // Create a map of match_id to teams and match_time
    const matchTeams = {};
    const matchTimes = {};
    matches.forEach(m => {
      matchTeams[m.id] = m.teams;
      matchTimes[m.id] = m.match_time;
    });

    // Get lottery date based on match_time (real date)
    function getLotteryDate(matchId) {
      const matchTime = matchTimes[matchId];
      if (!matchTime) return '未知日期';
      // 直接取日期部分，不转UTC（避免时区导致日期错误）
      const timeStr = matchTime.replace(' ', 'T');
      return timeStr.split('T')[0];
    }

    // Filter for basketball matches
    const basketballPreds = predictions.filter(p => p.sport_type === 'basketball');

    if (basketballPreds.length === 0) {
      document.getElementById('dynamic-predictions').innerHTML = 
        '<div class="text-center text-gray-500 py-8">暂无篮球预测数据</div>';
      return;
    }

    // Group by lottery date
    const byDate = {};
    basketballPreds.forEach(p => {
      const date = getLotteryDate(p.match_id);
      if (!byDate[date]) byDate[date] = {};
      const matchId = p.match_id || 'N/A';
      const teams = matchTeams[matchId] || matchId;
      if (!byDate[date][teams]) byDate[date][teams] = [];
      byDate[date][teams].push(p);
    });

    // Get latest date
    const dates = Object.keys(byDate).sort((a, b) => {
      const da = parseInt(a.replace(/[^0-9]/g, ''));
      const db = parseInt(b.replace(/[^0-9]/g, ''));
      return db - da;
    });
    const latestDate = dates[0];

    // Format date for display
    function formatDate(dateStr) {
      const match = dateStr.match(/(\d+)月(\d+)日/);
      if (match) return `${match[1]}月${match[2]}日`;
      const parts = dateStr.split('-');
      if (parts.length === 3) return `${parseInt(parts[1])}月${parseInt(parts[2])}日`;
      return dateStr;
    }

    // Render predictions for a match
    function renderMatchPredictions(teams, preds) {
      const predsHtml = preds.map(p => {
        const aiName = p.ai_name || 'Unknown';
        const winLoss = p.win_loss || p.spf || '--';
        const handicap = p.handicap_win_loss || p.handicap_spf || '--';
        const totalPoints = formatTotalPoints(p.total_points);
        const scoreDiff = formatScoreDiff(p.score_diff_range, p.win_loss);
        const analysis = p.metadata?.analysis || p.analysis || '';

        // Build prediction summary
        const predSummary = `胜:${winLoss} 让:${handicap} ${totalPoints} ${scoreDiff}`;

        // Parse analysis - show full content
        let analysisText = '';
        if (analysis) {
            if (typeof analysis === 'object' && analysis !== null) {
                // metadata.analysis 已经是对象
                const parts = [];
                if (analysis.core_logic) parts.push('【核心逻辑】' + analysis.core_logic);
                if (analysis.risk) parts.push('【风险提示】' + analysis.risk);
                for (const [key, value] of Object.entries(analysis)) {
                    if (key !== 'core_logic' && key !== 'risk' && value) {
                        parts.push('【' + key + '】' + value);
                    }
                }
                analysisText = parts.join('\n');
            } else if (typeof analysis === 'string') {
                // 先尝试JSON解析
                try {
                    const parsed = JSON.parse(analysis.replace(/'/g, '"'));
                    if (typeof parsed === 'object' && parsed !== null) {
                        // 是JSON对象，结构化显示
                        const parts = [];
                        if (parsed.core_logic) parts.push('【核心逻辑】' + parsed.core_logic);
                        if (parsed.risk) parts.push('【风险提示】' + parsed.risk);
                        for (const [key, value] of Object.entries(parsed)) {
                            if (key !== 'core_logic' && key !== 'risk' && value) {
                                parts.push('【' + key + '】' + value);
                            }
                        }
                        analysisText = parts.join('\n');
                    } else {
                        analysisText = String(parsed);
                    }
                } catch (e) {
                    // 纯文本，markdown转HTML
                    let text = analysis;
                    text = text.replace(/^#{1,4}\s+(.+)$/gm, '<strong>$1</strong>');
                    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
                    text = text.replace(/^\s*[-*]\s+/gm, '• ');
                    text = text.replace(/\n/g, '<br>');
                    text = text.replace(/```json\s*/g, '').replace(/```\s*/g, '');
                    analysisText = text;
                }
            }
        }

        return `
          <div class="rounded-lg bg-elevated/30 border border-border/40 p-3 mb-2">
            <div class="flex items-center gap-2 mb-2">
              ${getAiLogoHtml(aiName)}
              <span class="text-xs font-semibold text-gray-300 bg-elevated/50 px-2 py-0.5 rounded">${predSummary}</span>
            </div>
            ${analysisText ? `<div class="commentary-body text-gray-100 text-sm leading-relaxed"><p>${analysisText}</p></div>` : ''}
          </div>`;
      }).join('');

      const matchId = preds[0]?.match_id || '';
      return `
        <div id="match-${matchId}" class="rounded-lg bg-elevated/50 border border-border/50 p-4 mb-3">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              ${matchId ? `<span class="match-lottery-id">${matchId}</span>` : ''}
              <h4 class="font-semibold">${teams}</h4>
            </div>
          </div>
          <div class="mt-3 space-y-1">
            ${predsHtml}
          </div>
        </div>`;
    }

    // 渲染指定日期的predictions
    function renderPredictionsForDate(date) {
      const dateMatches = byDate[date] || {};
      const matchesHtml = Object.entries(dateMatches).map(([teams, preds]) => 
        renderMatchPredictions(teams, preds)
      ).join('');

      const matchCount = Object.keys(dateMatches).length;
      const dateDisplay = formatDate(date);

      const html = `
        <details open>
          <summary class="flex items-center gap-3 px-4 py-3 hover:bg-elevated/50 transition-colors">
            <span class="chevron text-accent text-sm">▶</span>
            <h3 class="font-semibold">${dateDisplay}</h3>
            <span class="text-xs text-muted">${matchCount}场</span>
          </summary>
          <div class="p-4 pt-0 space-y-4">
            ${matchesHtml}
          </div>
        </details>`;

      document.getElementById('dynamic-predictions').innerHTML = html;
    }

    // 渲染日期标签
    const dates = Object.keys(byDate).sort().reverse();
    const today = new Date();
    const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    let tabsHtml = '';
    let shownCount = 0;
    const MAX_VISIBLE = 7;
    let moreDates = [];

    dates.forEach((date, idx) => {
      const [y, m, d] = date.split('-').map(Number);
      const dt = new Date(y, m - 1, d);
      const label = `${dt.getMonth() + 1}月${dt.getDate()}日 ${weekDays[dt.getDay()]}`;
      const isActive = date === latestDate;

      if (shownCount < MAX_VISIBLE) {
        tabsHtml += `<button class="date-tab${isActive ? ' active' : ''}" onclick="window.switchBasketballDate('${date}')">${label}</button>`;
        shownCount++;
      } else {
        moreDates.push({ date, label });
      }
    });

    if (moreDates.length > 0) {
      tabsHtml += `<button class="date-tab" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'inline-flex':'none';this.textContent=this.textContent.includes('更多')?'收起 ▲':'更多 ▼'">更多 ▼</button>`;
      tabsHtml += `<span style="display:none;gap:6px;flex-wrap:nowrap;">`;
      moreDates.forEach(({ date, label }) => {
        tabsHtml += `<button class="date-tab" onclick="window.switchBasketballDate('${date}')">${label}</button>`;
      });
      tabsHtml += `</span>`;
    }

    document.getElementById('date-bar').innerHTML = tabsHtml;

    // 默认渲染最新日期
    renderPredictionsForDate(latestDate);

    // 挂载切换函数到window
    window.switchBasketballDate = function(date) {
      // 更新tab样式
      document.querySelectorAll('#date-bar .date-tab').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('onclick')?.includes(`'${date}'`)) {
          btn.classList.add('active');
        }
      });
      renderPredictionsForDate(date);
    };
  } catch (err) {
    console.error('Failed to load basketball predictions:', err);
    document.getElementById('dynamic-predictions').innerHTML = 
      '<div class="text-center text-gray-500 py-8">加载失败，请刷新重试</div>';
  }
})();

// ============ 动态加载篮球串关推荐 ============
(async function loadBasketballParlayData() {
  const AI_LOGOS = {
    '混元': ['#8b5cf6', 'HX'],
    '豆包': ['#ff6b35', 'DB'],
    'DeepSeek': ['#3b82f6', 'DS'],
    'MiniMax': ['#ef4444', 'MM'],
    '扣子（皮皮）': ['#06b6d4', 'KZ'],
    'BetAgent': ['#f59e0b', 'BA'],
    'Grok': ['#10b981', 'GK'],
    '文心': ['#ec4899', 'WX'],
    '智谱清言': ['#6366f1', 'ZP']
  };

  function getAiLogoHtml(aiName) {
    const [color, abbr] = AI_LOGOS[aiName] || ['#6b7280', aiName.slice(0, 2)];
    return `<span class="ai-logo"><span class="dot" style="background:${color}">${abbr}</span><span>${aiName}</span></span>`;
  }

  // Format match date for display (e.g., "周四001 6/29")
  function formatMatchLabel(matchId, matchTime) {
    if (!matchTime) return matchId;
    // 直接截取日期部分，不转UTC（避免时区导致日期错误）
    const dateStr = matchTime.replace(' ', 'T').substring(0, 10);
    const parts = dateStr.split('-');
    const month = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    return `${matchId} ${month}/${day}`;
  }

  function renderSelection(sel, matchesMap) {
    const matchId = sel.match_id;
    const match = matchesMap[matchId];
    const teams = match?.teams || 'N/A';
    const prediction = sel.prediction || 'N/A';
    const hit = sel.hit;
    if (teams === 'N/A' || !teams) return '';
    
    const hitClass = hit === true ? 'text-win' : (hit === false ? 'text-lose' : 'text-gray-400');
    const hitIcon = hit === true ? '✓' : (hit === false ? '✗' : '');
    const matchLabel = formatMatchLabel(matchId, match?.match_time);
    
    return `<div class="flex justify-between items-center">
      <span class="text-gray-400 text-xs">${matchLabel}</span>
      <span class="${hitClass}">${prediction} ${hitIcon}</span>
    </div>
    <div class="text-gray-300 text-xs mb-1">${teams}</div>`;
  }

  function renderCard(record, matchesMap) {
    const betType = record.bet_type || '';
    const odds = record.odds || 1.0;
    const selections = (record.selections || []).filter(s => {
      const match = matchesMap[s.match_id];
      return match && match.sport_type === 'basketball';
    });
    
    if (selections.length < 2) return '';

    const hitCount = selections.filter(s => s.hit === true).length;
    const total = selections.filter(s => s.hit !== null && s.hit !== undefined).length;
    
    let statusHtml;
    if (total > 0) {
      if (hitCount === total) statusHtml = `<span class="text-xs text-win">✓全中 ${hitCount}</span>`;
      else if (hitCount === 0) statusHtml = `<span class="text-xs text-lose">✗未中 ${hitCount}</span>`;
      else statusHtml = `<span class="text-xs text-yellow-400">◐中${hitCount} ${hitCount}/${total}</span>`;
    } else {
      statusHtml = '<span class="text-xs text-gray-500">待确认</span>';
    }

    const selectionsHtml = selections.map(s => renderSelection(s, matchesMap)).join('');
    if (!selectionsHtml) return '';

    return `
    <div class="rounded-lg bg-elevated/30 border border-border/40 p-3">
      <div class="flex justify-between items-center mb-2">
        <span class="text-xs font-medium text-gray-400">${betType}</span>
        ${statusHtml}
      </div>
      <div class="text-sm font-semibold text-accent mb-2">赔率 ${odds}</div>
      <div class="text-xs space-y-2">
        ${selectionsHtml}
      </div>
    </div>`;
  }

  function renderAiParlay(aiName, records, matchesMap) {
    const cardsHtml = records.map(r => renderCard(r, matchesMap)).join('');
    if (!cardsHtml) return '';
    return `
    <div class="mb-4">
      <div class="flex items-center gap-2 mb-2">
        ${getAiLogoHtml(aiName)}
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        ${cardsHtml}
      </div>
    </div>`;
  }

  function renderDateSection(date, records, matchesMap) {
    const byAi = {};
    records.forEach(r => {
      if (!byAi[r.ai_name]) byAi[r.ai_name] = [];
      byAi[r.ai_name].push(r);
    });

    const aiOrder = ['DeepSeek', '豆包', 'MiniMax', '混元', '扣子（皮皮）', 'BetAgent', 'Grok', '文心', '智谱清言'];
    const sortedAis = Object.keys(byAi).sort((a, b) => {
      const ia = aiOrder.indexOf(a);
      const ib = aiOrder.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    const aiHtml = sortedAis.map(ai => renderAiParlay(ai, byAi[ai], matchesMap)).join('');
    if (!aiHtml) return '';

    return `
    <div class="mb-4 border-b border-border/30 pb-4">
      <h4 class="text-sm font-semibold text-gray-400 mb-3">${date}</h4>
      ${aiHtml}
    </div>`;
  }

  try {
    // Fetch both chain_bets and matches data
    const [chainBetsResp, matchesResp] = await Promise.all([
      fetch('/api/chain_bets'),
      fetch('/api/matches')
    ]);
    const chainBetsData = await chainBetsResp.json();
    const matchesData = await matchesResp.json();

    // Create a lookup map for matches by match_id
    const matchesMap = {};
    matchesData.forEach(m => {
      matchesMap[m.id] = m;
    });

    // Filter for basketball matches (check sport_type from matches table)
    const basketballData = chainBetsData.filter(r => {
      const sels = r.selections || [];
      return sels.some(s => {
        const match = matchesMap[s.match_id];
        return match && match.sport_type === 'basketball';
      });
    });

    if (basketballData.length === 0) {
      const todayEl = document.getElementById('today-basketball-parlay');
      if (todayEl) {
        todayEl.innerHTML = '<div class="text-center text-gray-500 py-4">暂无篮球串关数据</div>';
      }
      return;
    }

    // Filter valid records and deduplicate
    const validData = basketballData.filter(r => {
      const sels = (r.selections || []).filter(s => {
        const match = matchesMap[s.match_id];
        return match && match.sport_type === 'basketball';
      });
      return sels.length >= 2;
    });

    const grouped = {};
    validData.forEach(r => {
      const key = `${r.bet_date}|${r.ai_name}|${r.bet_type}`;
      const validCount = (r.selections || []).filter(s => {
        const match = matchesMap[s.match_id];
        return match && match.sport_type === 'basketball';
      }).length;
      if (!grouped[key] || validCount > grouped[key]._validCount) {
        grouped[key] = { ...r, _validCount: validCount };
      }
    });
    const deduped = Object.values(grouped);

    // Group by date
    const byDate = {};
    deduped.forEach(r => {
      if (!byDate[r.bet_date]) byDate[r.bet_date] = [];
      byDate[r.bet_date].push(r);
    });

    const dates = Object.keys(byDate).sort((a, b) => {
      const da = parseInt(a.replace('月', '').replace('日', ''));
      const db = parseInt(b.replace('月', '').replace('日', ''));
      return db - da;
    });

    // Split into today and historical
    const today = dates[0];
    const histDates = dates.slice(1);

    // Render today's basketball parlay
    if (byDate[today]) {
      const todayHtml = renderDateSection(today, byDate[today], matchesMap);
      const todayEl = document.getElementById('today-basketball-parlay');
      if (todayEl && todayHtml) {
        todayEl.innerHTML = todayHtml;
      }
    }

    // Render historical basketball parlay
    if (histDates.length > 0) {
      let histHtml = '';
      histDates.slice(0, 5).forEach(date => {
        histHtml += renderDateSection(date, byDate[date], matchesMap);
      });
      const histEl = document.getElementById('hist-basketball-parlay');
      if (histEl && histHtml) {
        histEl.innerHTML = histHtml;
      }
    }
  } catch (err) {
    console.error('Failed to load basketball parlay data:', err);
    const todayEl = document.getElementById('today-basketball-parlay');
    if (todayEl) {
      todayEl.innerHTML = '<div class="text-center text-red-400 py-4">加载篮球串关数据失败</div>';
    }
  }
})();
</script>

<!-- 引入公共API模块 -->
<script type="module">
    import { fetchMatches, fetchPredictions, fetchAIStats, esc, fmtDate, fmtTime, showError, getCachedData, setCachedData } from './api.202607141528.js';
    
    // 将函数暴露到全局作用域供页面使用
    window.fetchMatches = fetchMatches;
    window.fetchPredictions = fetchPredictions;
    window.fetchAIStats = fetchAIStats;
    window.esc = esc;
    window.fmtDate = fmtDate;
    window.fmtTime = fmtTime;
    window.showError = showError;
    window.getCachedData = getCachedData;
    window.setCachedData = setCachedData;

    // URL参数定位：支持 ?match=xxx 跳转到指定比赛
    const urlParams = new URLSearchParams(window.location.search);
    const targetMatchId = urlParams.get('match');
    if (targetMatchId) {
      setTimeout(() => {
        const el = document.getElementById('match-' + targetMatchId);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.style.borderLeft = '4px solid #8b5cf6';
          el.style.paddingLeft = '12px';
          el.style.transition = 'all 0.3s ease';
        }
      }, 500);
    }
</script>
</body>
