// ============ 动态加载足球预测 ============
(async function loadFootballPredictions() {
  const AI_LOGOS = {
    '混元': ['#8b5cf6', 'HX'],
    '豆包': ['#ff6b35', 'DB'],
    'DeepSeek': ['#3b82f6', 'DS'],
    'MiniMax': ['#ef4444', 'MM'],
    '扣子': ['#06b6d4', 'KZ'],
    '扣子（皮皮）': ['#06b6d4', 'KZ'],
    'BetAgent': ['#f59e0b', 'BA'],
    'Grok': ['#10b981', 'GK'],
    '文心': ['#ec4899', 'WX'],
    '智谱清言': ['#6366f1', 'ZP'],
    'Kimi': ['#1f2937', 'KM'],
    '千问': ['#7c3aed', 'QW'],
    '天工': ['#0891b2', 'TG']
  };

  function getAiLogoHtml(aiName) {
    const [color, abbr] = AI_LOGOS[aiName] || ['#6b7280', aiName.slice(0, 2)];
    return `<span class="ai-logo"><span class="dot" style="background:${color}">${abbr}</span><span>${aiName}</span></span>`;
  }

  function formatPrediction(pred) {
    const parts = [];
    if (pred.spf) parts.push(`胜平负:${pred.spf}`);
    if (pred.handicap_spf) parts.push(`让球:${pred.handicap_spf}`);
    if (pred.score) parts.push(`比分:${pred.score}`);
    if (pred.goals) parts.push(`进球:${pred.goals}`);
    if (pred.half_full) parts.push(`半全:${pred.half_full}`);
    return parts.join(' ');
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    // 直接截取日期部分，不转UTC（避免时区导致日期错误）
    const parts = dateStr.replace(' ', 'T').substring(0, 10).split('-');
    const month = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    return `${month}月${day}日`;
  }

  try {
    const [predsResp, matchesResp] = await Promise.all([
      fetch('/api/predictions'),
      fetch('/api/matches')
    ]);
    const predictions = await predsResp.json();
    const matches = await matchesResp.json();

    // Create a map of match_id to match info
    const matchMap = {};
    matches.forEach(m => {
      matchMap[m.id] = m;
    });

    // Filter for football matches
    const footballPreds = predictions.filter(p => p.sport_type === 'football');

    if (footballPreds.length === 0) {
      document.getElementById('dynamic-predictions').innerHTML = 
        '<div class="text-center text-gray-500 py-8">暂无足球预测数据</div>';
      document.getElementById('today-commentary').innerHTML = 
        '<div class="text-center text-gray-500 py-4">暂无足球总评数据</div>';
      document.getElementById('today-parlay').innerHTML = 
        '<div class="text-center text-gray-500 py-4">暂无足球串关数据</div>';
      return;
    }

    // Get lottery date based on match_time (real date)
    function getLotteryDate(matchId) {
      const match = matchMap[matchId];
      if (!match || !match.match_time) return 'unknown';
      // 直接取日期部分，不转UTC（避免时区导致日期错误）
      const timeStr = match.match_time.replace(' ', 'T');
      return timeStr.split('T')[0];
    }

    // Group predictions by lottery date
    const byDate = {};
    footballPreds.forEach(p => {
      const matchDate = getLotteryDate(p.match_id);
      if (!byDate[matchDate]) byDate[matchDate] = {};
      if (!byDate[matchDate][p.match_id]) byDate[matchDate][p.match_id] = [];
      byDate[matchDate][p.match_id].push(p);
    });

    const dates = Object.keys(byDate).sort().reverse();
    const today = dates[0];

    // Set dates
    document.getElementById('today-date').textContent = formatDate(today);
    document.getElementById('parlay-date').textContent = formatDate(today);

    // Render today's commentary (if available)
    const todayCommentary = document.getElementById('today-commentary');
    todayCommentary.innerHTML = '<div class="text-center text-gray-500 py-4">暂无今日总评数据</div>';

    // Render date tabs
    const dateBar = document.getElementById('date-bar');
    const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    function fmtDateTab(dateStr) {
      const parts = dateStr.split('-');
      const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
      return `${d.getMonth() + 1}月${d.getDate()}日 ${weekDays[d.getDay()]}`;
    }
    const MAX_VISIBLE_TABS = 7;
    let tabsHtml = '';
    dates.forEach((date, idx) => {
      if (idx < MAX_VISIBLE_TABS) {
        tabsHtml += `<span class="date-tab ${date === today ? 'active' : ''}" data-date="${date}" onclick="window.switchAnalysisDate('${date}')">${fmtDateTab(date)}</span>`;
      }
    });
    if (dates.length > MAX_VISIBLE_TABS) {
      tabsHtml += `<span class="date-tab" style="background:rgba(139,92,246,0.04);color:#6b7280;cursor:default;">+${dates.length - MAX_VISIBLE_TABS}天</span>`;
    }
    dateBar.innerHTML = tabsHtml;

    // Expose switch function
    window._analysisByDate = byDate;
    window._analysisMatchMap = matchMap;
    window._analysisAI_LOGOS = AI_LOGOS;
    window._analysisGetAiLogoHtml = getAiLogoHtml;
    window._analysisFormatPrediction = formatPrediction;
    window.switchAnalysisDate = function(date) {
      // Update tab active state
      document.querySelectorAll('#date-bar .date-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.date === date);
      });
      window.renderPredictionsForDate(date);
    };

    // Render predictions for a specific date
    window.renderPredictionsForDate = function(date) {
      const datePreds = window._analysisByDate[date] || {};
      const predictionsContainer = document.getElementById('dynamic-predictions');
      const matchMap = window._analysisMatchMap;
      const getAiLogoHtml = window._analysisGetAiLogoHtml;
      const formatPrediction = window._analysisFormatPrediction;
      
      if (Object.keys(datePreds).length === 0) {
        predictionsContainer.innerHTML = '<div class="text-center text-gray-500 py-8">暂无该日预测数据</div>';
        return;
      }
      
      let html = '<div class="space-y-3">';
      
      Object.entries(datePreds).forEach(([matchId, preds]) => {
        const match = matchMap[matchId];
        const teams = match ? match.teams : matchId;
        
        // 按 ai_name 去重，每个AI只保留第一条预测
        const seen = new Set();
        preds = preds.filter(p => {
          const key = p.ai_name;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        
        html += `
          <div id="analysis-${matchId}" class="rounded-lg bg-elevated/50 border border-border/50 p-4">
            <div class="flex items-center justify-between mb-3">
              <h4 class="font-semibold">${matchId} ${teams}</h4>
              ${match ? `<span class="text-xs text-muted">${formatDate(match.match_time)}</span>` : ''}
            </div>
            <div class="space-y-2">
        `;
        
        preds.forEach(pred => {
          // Parse analysis - show full content
          let analysisText = '';
          const analysis = pred.analysis;
          if (analysis) {
              if (typeof analysis === 'object' && analysis !== null) {
                  // 已经是对象
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
          
          html += `
            <div class="rounded-lg bg-elevated/30 border border-border/40 p-3">
              <div class="flex items-center gap-2 mb-2">
                ${getAiLogoHtml(pred.ai_name)}
                <span class="text-xs font-semibold text-turf bg-turf/10 px-2 py-0.5 rounded">${formatPrediction(pred)}</span>
              </div>
              ${analysisText ? `
                <div class="commentary-body text-gray-300 text-sm leading-relaxed">
                  <p class="analysis-text line-clamp-2" style="white-space: pre-line;">${analysisText}</p>
                  ${analysisText.length > 100 ? `<button class="text-xs text-turf mt-1 hover:underline" onclick="this.previousElementSibling.classList.toggle('line-clamp-2'); this.textContent = this.textContent === '展开全部' ? '收起' : '展开全部'">展开全部</button>` : ''}
                </div>
              ` : ''}
            </div>
          `;
        });
        
        html += '</div></div>';
      });
      
      html += '</div>';
      predictionsContainer.innerHTML = html;
    };

    // Initial render for today
    window.renderPredictionsForDate(today);

    // Render historical commentary
    const histCommentary = document.getElementById('hist-commentary');
    const histDates = dates.slice(1);
    if (histDates.length === 0) {
      histCommentary.innerHTML = '<div class="text-center text-gray-500 py-4">暂无历史总评数据</div>';
      document.getElementById('hist-commentary-count').textContent = '共0天';
    } else {
      document.getElementById('hist-commentary-count').textContent = `共${histDates.length}天`;
      let html = '<div class="space-y-2">';
      histDates.forEach(date => {
        html += `
          <details class="rounded-lg bg-card/50 border border-border/50 overflow-hidden">
            <summary class="flex items-center gap-3 px-4 py-2.5 hover:bg-elevated/50 transition-colors">
              <span class="chevron text-accent text-xs">▶</span>
              <span class="text-sm font-medium">${formatDate(date)}</span>
            </summary>
            <div class="p-3 text-sm text-gray-400">暂无该日总评数据</div>
          </details>
        `;
      });
      html += '</div>';
      histCommentary.innerHTML = html;
    }

    // Render historical parlay
    document.getElementById('hist-parlay').innerHTML = '<div class="text-center text-gray-500 py-4">暂无历史串关数据</div>';
    document.getElementById('hist-parlay-count').textContent = '共0天';

  } catch (err) {
    console.error('加载预测数据失败:', err);
    document.getElementById('dynamic-predictions').innerHTML = 
      '<div class="text-center text-red-500 py-8">加载失败，请刷新重试</div>';
  }
})();



// URL参数定位：跳转到指定比赛分析
(function() {
  const matchId = new URLSearchParams(window.location.search).get('match');
  if (matchId) {
    setTimeout(function() {
      const target = document.getElementById('analysis-' + matchId);
      if (target) {
        target.style.borderLeft = '3px solid #a855f7';
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 500);
  }
})();
