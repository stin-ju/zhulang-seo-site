    <script>
        // 备用数据（静态嵌入）
        window.MATCH_DATA = []; // 保留作为fallback，实际数据从API动态获取
        window.MATCH_DATA.forEach(m => {
            // 兼容 ' VS ' 和 'VS' 两种格式
            const teams = m.teams || '';
            const match = teams.match(/^(.+?)\s*VS\s*(.+)$/);
            if (match) {
                m.home_team = match[1].trim();
                m.away_team = match[2].trim();
            } else {
                m.home_team = teams;
                m.away_team = '';
            }
            m.sport = m.sport_type;
        });

        // 从API加载所有在售比赛
        async function loadMatches() {
            try {
                const resp = await fetch('/api/matches');
                const data = await resp.json();
                const now = new Date();
                // 过滤：只保留在售且未结束的比赛
                // 1. status 不是"已确认"（容错：反向排除）
                // 2. selling_status 是 "on_sale"
                // 3. 当前时间 < match_time - 25分钟（体彩规则：开赛前25分钟停售）
                const availableMatches = data.filter(m => {
                    if (m.status === '已确认') return false;
                    if (m.selling_status !== 'on_sale') return false;
                    // 时间容错：如果当前时间已超过开赛前25分钟，视为停售
                    if (m.match_time) {
                        const matchStart = new Date(m.match_time);
                        const cutoff = new Date(matchStart.getTime() - 25 * 60 * 1000);
                        if (now >= cutoff) return false;
                    }
                    return true;
                });
                // 处理队伍名称和sport字段
                availableMatches.forEach(m => {
                    // 兼容 ' VS ' 和 'VS' 两种格式
                    const teams = m.teams || '';
                    const match = teams.match(/^(.+?)\s*VS\s*(.+)$/);
                    if (match) {
                        m.home_team = match[1].trim();
                        m.away_team = match[2].trim();
                    } else {
                        m.home_team = teams;
                        m.away_team = '';
                    }
                    m.sport = m.sport_type;
                });
                state.matches = availableMatches;
                renderMatches();
                console.log('✅ 从API加载', availableMatches.length, '场在售比赛');
            } catch (e) {
                console.warn('API加载失败，使用备用数据:', e);
                // fallback也过滤selling_status
                state.matches = (window.MATCH_DATA || []).filter(m => 
                    m.selling_status === 'on_sale'
                );
                state.matches.forEach(m => { m.sport = m.sport_type; });
                renderMatches();
            }
        }

        // 配置
        const FOOTBALL_PLAYS = [
            { key: 'spf', label: '胜平负', maxPass: 8 },
            { key: 'rqspf', label: '让球胜平负', maxPass: 8 },
            { key: 'bf', label: '比分', maxPass: 4 },
            { key: 'jqs', label: '总进球', maxPass: 6 },
            { key: 'bqc', label: '半全场', maxPass: 4 }
        ];
        const BASKETBALL_PLAYS = [
            { key: 'winlose', label: '胜负', maxPass: 8 },
            { key: 'spread', label: '让分胜负', maxPass: 8 },
            { key: 'total', label: '大小分', maxPass: 8 },
            { key: 'scorediff', label: '胜分差', maxPass: 4 }
        ];

        // 过关方式配置（省略详细内容，保持原有逻辑）
        const PASS_SUBS = {
            '2x1': [{ m: 2 }], '3x1': [{ m: 3 }], '3x3': [{ m: 2 }], '3x4': [{ m: 2 }, { m: 3 }],
            '4x1': [{ m: 4 }], '4x4': [{ m: 3 }], '4x5': [{ m: 3 }, { m: 4 }], '4x11': [{ m: 2 }, { m: 3 }, { m: 4 }],
            '5x1': [{ m: 5 }], '5x5': [{ m: 4 }], '5x10': [{ m: 3 }], '5x16': [{ m: 3 }, { m: 4 }, { m: 5 }],
            '5x20': [{ m: 2 }], '5x26': [{ m: 2 }, { m: 3 }, { m: 4 }, { m: 5 }],
            '单关(2场)': [{ m: 1 }], '单关(3场)': [{ m: 1 }], '单关(4场)': [{ m: 1 }], '单关(5场)': [{ m: 1 }]
        };
        const PASS_TOTAL = {
            '2x1': 1, '3x1': 1, '3x3': 3, '3x4': 4, '4x1': 1, '4x4': 4, '4x5': 5, '4x11': 11,
            '5x1': 1, '5x5': 5, '5x10': 10, '5x16': 16, '5x20': 20, '5x26': 26,
            '单关(2场)': 2, '单关(3场)': 3, '单关(4场)': 4, '单关(5场)': 5
        };
        const PASS_OPTIONS = {
            2: ['2x1', '单关(2场)'], 3: ['3x1', '3x3', '3x4', '单关(3场)'],
            4: ['4x1', '4x4', '4x5', '4x11', '单关(4场)'], 5: ['5x1', '5x5', '5x10', '5x16', '5x20', '5x26', '单关(5场)']
        };
        const SCORE_DIFF_OPTIONS = [
            '主胜1-5', '主胜6-10', '主胜11-15', '主胜16-20', '主胜21-25', '主胜26+',
            '客胜1-5', '客胜6-10', '客胜11-15', '客胜16-20', '客胜21-25', '客胜26+'
        ];

        // 组合算法
        function getCombinations(arr, k) {
            if (k === 0) return [[]];
            if (arr.length === 0 || k > arr.length) return [];
            const result = [];
            const [first, ...rest] = arr;
            for (const combo of getCombinations(rest, k - 1)) result.push([first, ...combo]);
            for (const combo of getCombinations(rest, k)) result.push(combo);
            return result;
        }

        // 状态
        const state = {
            matches: window.MATCH_DATA || [],
            selections: [], passType: '', currentSport: 'football', currentPlay: 'spf',
            danMatchIds: [], detailOpen: false, multiplier: 1,
        };

        // DOM 引用
        const $ = id => document.getElementById(id);
        const matchList = $('matchList'), matchCount = $('matchCount'), betList = $('betList');
        const passGrid = $('passGrid'), passSection = $('passSection'), passHint = $('passHint');
        const clearAllBtn = $('clearAllBtn'), selCount = $('selCount');
        const betCount = $('betCount'), betAmount = $('betAmount'), bonusAmount = $('bonusAmount');
        const calcHint = $('calcHint'), amountBreakdown = $('amountBreakdown');
        const detailContent = $('detailContent');
        const playTabs = $('playTabs'), multiplierInput = $('multiplierInput');
        const panelSelCount = $('panelSelCount');

        // 比分三排分类
        function categorizeScores(oddsList) {
            const win = [], draw = [], lose = [];
            // 支持连字符(1-0)和冒号(1:0)两种格式
            const winOrder = ['1-0','2-0','2-1','3-0','3-1','3-2','4-0','4-1','4-2','5-0','5-1','5-2','胜其它'];
            const drawOrder = ['0-0','1-1','2-2','3-3','平其它'];
            const loseOrder = ['0-1','0-2','1-2','0-3','1-3','2-3','0-4','1-4','2-4','0-5','1-5','2-5','负其它'];
            
            oddsList.forEach(o => {
                if (winOrder.includes(o.type)) win.push(o);
                else if (drawOrder.includes(o.type)) draw.push(o);
                else if (loseOrder.includes(o.type)) lose.push(o);
            });
            
            // Sort by predefined order
            win.sort((a, b) => winOrder.indexOf(a.type) - winOrder.indexOf(b.type));
            draw.sort((a, b) => drawOrder.indexOf(a.type) - drawOrder.indexOf(b.type));
            lose.sort((a, b) => loseOrder.indexOf(a.type) - loseOrder.indexOf(b.type));
            
            return { win, draw, lose };
        }

        // 篮球赔率映射
        function getOddsMapForMatch(match, sport, playKey) {
            if (sport === 'football') {
                const map = {
                    'spf': [
                        { type: 'win', label: '胜', value: match.win_odds },
                        { type: 'draw', label: '平', value: match.draw_odds },
                        { type: 'lose', label: '负', value: match.lose_odds },
                    ],
                    'rqspf': [
                        { type: 'hwin', label: '让胜', value: match.handicap_win_odds },
                        { type: 'hdraw', label: '让平', value: match.handicap_draw_odds },
                        { type: 'hlose', label: '让负', value: match.handicap_lose_odds },
                    ],
                    'bf': Object.keys(match.score_odds || {}).map(k => ({ type: k, label: k, value: match.score_odds[k] })),
                    'jqs': Object.keys(match.goals_odds || {}).map(k => ({ type: k, label: k, value: match.goals_odds[k] })),
                    'bqc': Object.keys(match.half_full_odds || {}).map(k => ({ type: k, label: k, value: match.half_full_odds[k] })),
                };
                return map[playKey] || map['spf'];
            }
            
            // 篮球赔率映射
            const spreadOdds = match.spread_odds || {};
            const totalOdds = match.goals_odds || {};  // 大小分赔率存在 goals_odds
            const scoreDiffOdds = match.score_diff_odds || {};
            
            const map = {
                'winlose': [
                    { type: 'bwin', label: '主胜', value: match.win_odds },
                    { type: 'blose', label: '客胜', value: match.lose_odds },
                ],
                'spread': [
                    { type: 'bspread_win', label: '让分主胜', value: spreadOdds.win || spreadOdds.over },
                    { type: 'bspread_lose', label: '让分客胜', value: spreadOdds.lose || spreadOdds.under },
                ],
                'total': [
                    { type: 'bover', label: '大分', value: totalOdds.over },
                    { type: 'bunder', label: '小分', value: totalOdds.under },
                ],
                'scorediff': Object.keys(scoreDiffOdds).length > 0 
                    ? Object.keys(scoreDiffOdds).map(k => ({ type: k, label: k, value: scoreDiffOdds[k] }))
                    : SCORE_DIFF_OPTIONS.map(k => ({ type: k, label: k, value: null })),
            };
            return map[playKey] || map['winlose'];
        }

        function getHandicap(match, sport) {
            if (sport === 'football') return match.handicap;
            const spreadOdds = match.spread_odds || {};
            return spreadOdds.handicap || null;
        }

        function getTotalLine(match) {
            const totalOdds = match.goals_odds || {};
            return totalOdds.line || match.total_points_odds || null;
        }

        function getSelectedPlayForMatch(matchId) {
            const sel = state.selections.find(s => s.matchId === matchId);
            return sel ? sel.playKey : null;
        }

        function getMaxPassForSelections() {
            if (state.selections.length === 0) return 8;
            const plays = state.selections.map(s => s.playKey);
            const uniquePlays = [...new Set(plays)];
            const allPlays = [...FOOTBALL_PLAYS, ...BASKETBALL_PLAYS];
            let maxPass = 8;
            for (const playKey of uniquePlays) {
                const playConfig = allPlays.find(p => p.key === playKey);
                if (playConfig && playConfig.maxPass < maxPass) maxPass = playConfig.maxPass;
            }
            return maxPass;
        }

        function isMixPass() {
            if (state.selections.length < 2) return false;
            const plays = state.selections.map(s => s.playKey);
            return [...new Set(plays)].length > 1;
        }

        // 渲染函数
        function renderPlayTabs() {
            const plays = state.currentSport === 'football' ? FOOTBALL_PLAYS : BASKETBALL_PLAYS;
            let html = '';
            plays.forEach(p => {
                const active = p.key === state.currentPlay ? 'active' : '';
                const hasSelected = state.selections.some(s => s.playKey === p.key);
                html += `<button class="play-tab ${active}" data-play="${p.key}">${p.label} <span class="max-tag">${p.maxPass}关</span>${hasSelected ? ' <span class="check">✓</span>' : ''}</button>`;
            });
            playTabs.innerHTML = html;
            playTabs.querySelectorAll('.play-tab').forEach(btn => {
                btn.addEventListener('click', () => {
                    playTabs.querySelectorAll('.play-tab').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    state.currentPlay = btn.dataset.play;
                    renderMatches();
                });
            });
        }

        function renderMatches() {
            const data = state.matches.filter(m => m.sport === state.currentSport);
            if (!data.length) {
                matchList.innerHTML = '<div style="text-align:center;color:#9ca3af;padding:20px 0;">暂无赛事</div>';
                matchCount.textContent = '0 场';
                return;
            }
            matchCount.textContent = data.length + ' 场';
            let html = '';
            data.forEach(m => {
                const isDan = state.danMatchIds.includes(m.id);
                const selectedPlay = getSelectedPlayForMatch(m.id);
                const play = (state.currentSport === 'football' ? FOOTBALL_PLAYS : BASKETBALL_PLAYS).find(p => p.key === state.currentPlay);
                if (!play) return;
                const oddsList = getOddsMapForMatch(m, state.currentSport, state.currentPlay);
                const validOdds = oddsList.filter(o => o.value && o.value > 0);
                if (!validOdds.length) {
                    html += `<div class="match-item" style="color:#9ca3af;text-align:center;padding:8px 0;">${m.home_team} VS ${m.away_team} - 无${play.label}数据</div>`;
                    return;
                }
                // 检查该场比赛已选的玩法（支持容错：同玩法可多选）
                const matchSelections = state.selections.filter(s => s.matchId === m.id);
                const selectedPlays = [...new Set(matchSelections.map(s => s.playKey))];
                const isSelectedPlay = selectedPlays.includes(state.currentPlay);
                const isDisabled = selectedPlays.length > 0 && !selectedPlays.includes(state.currentPlay);
                const isScoreDiff = state.currentPlay === 'scorediff';
                const isScorePlay = state.currentPlay === 'bf';
                const handicap = getHandicap(m, state.currentSport);
                const totalLine = state.currentSport === 'basketball' ? getTotalLine(m) : null;
                
                // Format match time
                const matchTime = m.match_time || '';
                const timeDisplay = matchTime ? matchTime.substring(5, 16).replace('T', ' ') : '';
                
                // 检查某个选项是否已选中
                const isOptionSelected = (type) => state.selections.some(s => s.matchId === m.id && s.type === type);
                
                // Generate odds HTML
                let oddsHtml = '';
                if (isScorePlay) {
                    // 比分三排布局
                    const { win, draw, lose } = categorizeScores(validOdds);
                    const renderScoreRow = (label, rowClass, items) => {
                        if (!items.length) return '';
                        return `<div class="score-row ${rowClass}">
                            <span class="row-label">${label}</span>
                            <div class="row-options">
                                ${items.map(o => {
                                    // 将连字符格式(1-0)转换为冒号格式(1:0)显示
                                    const displayLabel = o.label.includes('-') ? o.label.replace('-', ':') : o.label;
                                    return `
                                    <button class="odds-btn ${isOptionSelected(o.type) ? 'selected' : ''} ${isDisabled ? 'disabled' : ''}"
                                            data-matchid="${m.id}" data-play="${state.currentPlay}" data-type="${o.type}" 
                                            data-odds="${o.value || 0}" data-label="${displayLabel}">
                                        <span class="label">${displayLabel}</span>
                                        <span class="value">${o.value || '-'}</span>
                                    </button>
                                `}).join('')}
                            </div>
                        </div>`;
                    };
                    oddsHtml = `<div class="score-rows">
                        ${renderScoreRow('胜', 'win-row', win)}
                        ${renderScoreRow('平', 'draw-row', draw)}
                        ${renderScoreRow('负', 'lose-row', lose)}
                    </div>`;
                } else {
                    oddsHtml = `<div class="odds-group ${isScoreDiff ? 'score-diff' : ''}">
                        ${validOdds.map(o => `
                            <button class="odds-btn ${isOptionSelected(o.type) ? 'selected' : ''} ${isDisabled ? 'disabled' : ''}"
                                    data-matchid="${m.id}" data-play="${state.currentPlay}" data-type="${o.type}" 
                                    data-odds="${o.value || 0}" data-label="${o.label}">
                                <span class="label">${o.label}</span>
                                <span class="value">${o.value || '-'}</span>
                            </button>
                        `).join('')}
                    </div>`;
                }
                
                html += `
                    <div class="match-item" data-matchid="${m.id}">
                        <div class="match-header" data-matchid="${m.id}">
                            <div class="match-meta">
                                <span class="match-id">${m.id}</span>
                                <span class="match-time">${timeDisplay}</span>
                            </div>
                            <button class="collapse-btn" data-matchid="${m.id}">▼</button>
                        </div>
                        <div class="match-body" data-matchid="${m.id}">
                            <div class="teams-row">
                                <button class="star-btn ${isDan ? 'active' : ''}" data-matchid="${m.id}" title="设胆">${isDan ? '★' : '☆'}</button>
                                ${m.home_team} <span class="vs">VS</span> ${m.away_team}
                            </div>
                            <div class="tags-row">
                                ${handicap ? `<span class="handicap-label">让${handicap}</span>` : ''}
                                ${totalLine ? `<span class="handicap-label">总分${totalLine}</span>` : ''}
                                ${selectedPlay ? `<span class="selected-play-label">已选 ${play.label}</span>` : ''}
                            </div>
                            <div class="play-row">
                                <span class="play-label">${play.label}</span>
                                ${oddsHtml}
                            </div>
                        </div>
                    </div>
                `;
            });
            matchList.innerHTML = html;
            
            // Collapse/expand handlers
            matchList.querySelectorAll('.match-header').forEach(header => {
                header.addEventListener('click', (e) => {
                    // Don't toggle if clicking on odds button or star button
                    if (e.target.closest('.odds-btn') || e.target.closest('.star-btn')) return;
                    const matchId = header.dataset.matchid;
                    const body = matchList.querySelector(`.match-body[data-matchid="${matchId}"]`);
                    const btn = header.querySelector('.collapse-btn');
                    if (body && btn) {
                        body.classList.toggle('hidden');
                        btn.classList.toggle('collapsed');
                    }
                });
            });
            
            // Star button handlers
            matchList.querySelectorAll('.star-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const mid = btn.dataset.matchid;
                    if (state.danMatchIds.includes(mid)) {
                        state.danMatchIds = state.danMatchIds.filter(id => id !== mid);
                    } else {
                        state.danMatchIds.push(mid);
                    }
                    renderMatches();
                    renderBetSlip();
                });
            });
            
            // Odds button handlers
            matchList.querySelectorAll('.odds-btn:not(.disabled)').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const matchId = btn.dataset.matchid;
                    const playKey = btn.dataset.play;
                    const type = btn.dataset.type;
                    const odds = parseFloat(btn.dataset.odds);
                    const label = btn.dataset.label || type;
                    if (isNaN(odds) || odds <= 0) return;
                    toggleSelection(matchId, playKey, type, odds, label);
                });
            });
        }

        function toggleSelection(matchId, playKey, type, odds, label) {
            // 检查是否已存在相同选择
            const existingIdx = state.selections.findIndex(s => s.matchId === matchId && s.type === type && s.playKey === playKey);
            if (existingIdx >= 0) {
                // 取消选择
                state.selections.splice(existingIdx, 1);
                if (state.danMatchIds.includes(matchId)) state.danMatchIds = state.danMatchIds.filter(id => id !== matchId);
                renderMatches(); renderBetSlip(); renderPlayTabs();
                return;
            }
            
            // 检查是否已存在同场比赛的其他选择
            const existingForMatch = state.selections.filter(s => s.matchId === matchId);
            if (existingForMatch.length > 0) {
                // 如果已有选择，检查是否同一种玩法
                const existingPlay = existingForMatch[0].playKey;
                if (existingPlay !== playKey) {
                    // 不同玩法，替换（同一场只能选一种玩法）
                    state.selections = state.selections.filter(s => s.matchId !== matchId);
                    if (state.danMatchIds.includes(matchId)) state.danMatchIds = state.danMatchIds.filter(id => id !== matchId);
                }
                // 同玩法不同选项，允许添加（容错模式）
            }
            
            state.selections.push({ matchId, playKey, type, odds, label, sport: state.currentSport });
            renderMatches(); renderBetSlip(); renderPlayTabs();
        }

        function renderBetSlip() {
            const groups = {};
            state.selections.forEach(s => {
                if (!groups[s.matchId]) groups[s.matchId] = [];
                groups[s.matchId].push(s);
            });
            const count = Object.keys(groups).length;
            selCount.textContent = count;
            if (panelSelCount) panelSelCount.textContent = count;
            
            if (!state.selections.length) {
                betList.innerHTML = '<div class="panel-empty">点击赔率添加</div>';
                passSection.style.display = 'none';
                updateResult();
                return;
            }
            const allPlays = [...FOOTBALL_PLAYS, ...BASKETBALL_PLAYS];
            let html = '<div class="panel-bet-list">';
            Object.keys(groups).forEach(mid => {
                const items = groups[mid];
                const match = state.matches.find(m => m.id === mid);
                const label = match ? `${match.home_team} VS ${match.away_team}` : mid;
                const isDan = state.danMatchIds.includes(mid);
                const tags = items.map(s => {
                    const play = allPlays.find(p => p.key === s.playKey);
                    return `${s.label} ${s.odds}${play ? ' ('+play.label+')' : ''}`;
                }).join('、');
                html += `<div class="panel-bet-item">
                    <span class="dan-star ${isDan ? 'active' : ''}" data-matchid="${mid}" title="设胆">${isDan ? '★' : '☆'}</span>
                    <span class="match-name">${label}</span>
                    <span class="bet-info">${tags}</span>
                    <span class="del-btn" data-matchid="${mid}">✕</span>
                </div>`;
            });
            html += '</div>';
            html += '<div class="panel-hint">💡 点击 ☆ 可设为胆码（必选），支持多选</div>';
            betList.innerHTML = html;
            
            // 设胆点击
            betList.querySelectorAll('.dan-star').forEach(btn => {
                btn.addEventListener('click', () => {
                    const mid = btn.dataset.matchid;
                    if (state.danMatchIds.includes(mid)) {
                        state.danMatchIds = state.danMatchIds.filter(id => id !== mid);
                    } else {
                        state.danMatchIds.push(mid);
                    }
                    renderBetSlip();
                    renderMatches();
                });
            });
            
            // 删除点击
            betList.querySelectorAll('.del-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const mid = btn.dataset.matchid;
                    state.selections = state.selections.filter(s => s.matchId !== mid);
                    if (state.danMatchIds.includes(mid)) state.danMatchIds = state.danMatchIds.filter(id => id !== mid);
                    renderBetSlip(); renderMatches(); renderPlayTabs(); updateResult();
                });
            });
            renderPassOptions();
            updateResult();
        }

        function renderPassOptions() {
            const groups = {};
            state.selections.forEach(s => {
                if (!groups[s.matchId]) groups[s.matchId] = [];
                groups[s.matchId].push(s);
            });
            const count = Object.keys(groups).length;
            if (count < 2) {
                passGrid.innerHTML = '<span style="color:#9ca3af;font-size:12px;">至少选2场比赛</span>';
                passSection.style.display = 'block';
                passHint.textContent = '';
                return;
            }
            const maxPass = getMaxPassForSelections();
            const effectiveCount = Math.min(count, maxPass);
            let options = effectiveCount >= 2 ? (PASS_OPTIONS[effectiveCount] || []) : [];
            if (!options.length) {
                passGrid.innerHTML = '<span style="color:#9ca3af;font-size:12px;">请选择更多比赛</span>';
                passSection.style.display = 'block';
                passHint.textContent = '';
                return;
            }
            if (!state.passType || !options.includes(state.passType)) state.passType = options[0];
            let html = '';
            options.forEach(p => {
                html += `<button class="pass-btn ${p === state.passType ? 'active' : ''}" data-pass="${p}">${p}</button>`;
            });
            passGrid.innerHTML = html;
            passSection.style.display = 'block';
            passGrid.querySelectorAll('.pass-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    state.passType = btn.dataset.pass;
                    renderPassOptions(); updateResult();
                });
            });
            passHint.textContent = effectiveCount < count ? `⚠️ 最高 ${maxPass} 关，已选 ${count} 场，超出部分忽略` : `已选 ${count} 场，最高 ${maxPass} 关`;
            passHint.style.color = effectiveCount < count ? '#f59e0b' : '#6b7280';
        }

        function updateResult() {
            const sel = state.selections;
            if (sel.length < 2) {
                betCount.textContent = '0';
                betAmount.textContent = '0.00 元';
                amountBreakdown.textContent = '每注 2 元 × 0 注 × ' + state.multiplier + ' 倍';
                bonusAmount.innerHTML = '0.00 <span class="unit">元</span>';
                calcHint.textContent = '请选择至少 2 场比赛';
                detailContent.innerHTML = '';
                detailContent.classList.remove('open');
                return;
            }
            
            // 按比赛分组，支持容错（同一场多个选项）
            const matchGroups = {};
            sel.forEach(s => {
                if (!matchGroups[s.matchId]) matchGroups[s.matchId] = [];
                matchGroups[s.matchId].push(s);
            });
            
            const matchIds = Object.keys(matchGroups);
            const totalMatches = matchIds.length;
            
            // 检查是否有容错（某场比赛有多个选项）
            const hasRongCuo = Object.values(matchGroups).some(group => group.length > 1);
            
            const subs = PASS_SUBS[state.passType] || [{ m: 0 }];
            let totalPrize = 0, maxPrize = 0, detailRows = [], actualBets = 0;
            
            // 设胆处理：胆码必须包含在所有组合中
            const danIds = state.danMatchIds.filter(id => matchIds.includes(id));
            const hasDan = danIds.length > 0;
            const otherIds = matchIds.filter(id => !danIds.includes(id));
            const danCount = danIds.length;
            
            for (const sub of subs) {
                const subM = sub.m;
                if (totalMatches < subM) continue;
                
                // 生成比赛组合（胆码必须包含）
                let matchCombos;
                if (hasDan) {
                    // 有胆码：从其他比赛中选 subM-danCount 场，加上所有胆码
                    const needOthers = subM - danCount;
                    if (needOthers > otherIds.length || needOthers < 0) continue;
                    const otherCombos = getCombinations(otherIds, needOthers);
                    matchCombos = otherCombos.map(combo => [...danIds, ...combo]);
                } else {
                    matchCombos = getCombinations(matchIds, subM);
                }
                
                for (const matchCombo of matchCombos) {
                    if (hasRongCuo) {
                        // 容错模式：每场比赛的多个选项都要组合
                        // 生成所有选项组合
                        const selectionCombos = matchCombo.reduce((acc, mid) => {
                            const selections = matchGroups[mid];
                            if (acc.length === 0) {
                                return selections.map(s => [s]);
                            }
                            const newCombos = [];
                            acc.forEach(existing => {
                                selections.forEach(s => {
                                    newCombos.push([...existing, s]);
                                });
                            });
                            return newCombos;
                        }, []);
                        
                        for (const combo of selectionCombos) {
                            let comboOdds = 1, comboLabel = '';
                            for (const s of combo) {
                                comboOdds *= s.odds;
                                const match = state.matches.find(m => m.id === s.matchId);
                                comboLabel += `${match ? match.home_team : s.matchId}(${s.label}) `;
                            }
                            if (comboLabel) {
                                const prize = comboOdds * 2 * state.multiplier;
                                totalPrize += prize;
                                if (prize > maxPrize) maxPrize = prize;
                                actualBets++;
                                detailRows.push({ combo: comboLabel.trim(), odds: comboOdds, prize: prize.toFixed(2) });
                            }
                        }
                    } else {
                        // 普通模式：每场一个选项
                        let comboOdds = 1, comboLabel = '';
                        for (const id of matchCombo) {
                            const s = matchGroups[id][0];
                            comboOdds *= s.odds;
                            const match = state.matches.find(m => m.id === id);
                            comboLabel += `${match ? match.home_team : id}(${s.label}) `;
                        }
                        if (comboLabel) {
                            const prize = comboOdds * 2 * state.multiplier;
                            totalPrize += prize;
                            if (prize > maxPrize) maxPrize = prize;
                            actualBets++;
                            detailRows.push({ combo: comboLabel.trim(), odds: comboOdds, prize: prize.toFixed(2) });
                        }
                    }
                }
            }
            
            const displayBets = actualBets > 0 ? actualBets : 0;
            const perBet = 2, multiplier = state.multiplier || 1;
            const totalAmount = perBet * multiplier * displayBets;
            betCount.textContent = displayBets;
            betAmount.textContent = totalAmount.toFixed(2) + ' 元';
            amountBreakdown.textContent = `每注 ${perBet} 元 × ${displayBets} 注 × ${multiplier} 倍`;
            // 理论最高奖金：无容错时=所有注数总和，有容错时=单版本最高
            const displayPrize = hasRongCuo ? maxPrize : totalPrize;
            bonusAmount.innerHTML = `${displayPrize.toFixed(2)} <span class="unit">元</span>`;
            calcHint.textContent = `${totalMatches} 场比赛${hasRongCuo ? ' · 容错' : ''} · ${state.passType || '未选择'}`;
            if (detailRows.length > 0) {
                let detailHtml = '';
                detailRows.slice(0, 20).forEach((row, i) => {
                    detailHtml += `<div class="detail-item"><span class="combo">第${i+1}注：${row.combo}</span><span class="prize">${row.prize} 元</span></div>`;
                });
                if (detailRows.length > 20) detailHtml += `<div class="detail-item" style="text-align:center;color:#9ca3af;">... 共 ${detailRows.length} 注</div>`;
                detailContent.innerHTML = detailHtml;
            } else {
                detailContent.innerHTML = '<div style="padding:4px;color:#9ca3af;text-align:center;">暂无明细</div>';
            }
        }

        // 事件绑定
        const danBtn = document.getElementById('danBtn');
        const slipPanel = document.getElementById('slipPanel');
        const detailModal = document.getElementById('detailModal');
        const detailBtn = document.getElementById('detailBtn');
        const closeDetail = document.getElementById('closeDetail');
        const multMinus = document.getElementById('multMinus');
        const multPlus = document.getElementById('multPlus');

        // 选单面板展开/收起
        danBtn.addEventListener('click', () => {
            slipPanel.classList.toggle('open');
            danBtn.querySelector('.arrow').textContent = slipPanel.classList.contains('open') ? '▼' : '▲';
        });

        // 清空选单
        clearAllBtn.addEventListener('click', () => {
            state.selections = []; state.danMatchIds = [];
            renderMatches(); renderBetSlip(); renderPlayTabs();
        });

        // 奖金详情弹窗
        detailBtn.addEventListener('click', () => {
            detailModal.style.display = 'flex';
        });
        closeDetail.addEventListener('click', () => {
            detailModal.style.display = 'none';
        });
        detailModal.addEventListener('click', (e) => {
            if (e.target === detailModal) detailModal.style.display = 'none';
        });

        // 过关方式切换
        document.querySelectorAll('.pass-type-options button').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.pass-type-options button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                // 这里可以添加M串N和自由过关的切换逻辑
            });
        });

        // 倍数控制
        multMinus.addEventListener('click', () => {
            let val = parseInt(multiplierInput.value) || 1;
            if (val > 1) {
                multiplierInput.value = val - 1;
                state.multiplier = val - 1;
                updateResult();
            }
        });
        multPlus.addEventListener('click', () => {
            let val = parseInt(multiplierInput.value) || 1;
            if (val < 50) {
                multiplierInput.value = val + 1;
                state.multiplier = val + 1;
                updateResult();
            }
        });

        document.querySelectorAll('#sportTabs .tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('#sportTabs .tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                state.currentSport = tab.dataset.sport;
                state.currentPlay = state.currentSport === 'football' ? 'spf' : 'winlose';
                state.selections = []; state.danMatchIds = []; state.multiplier = 1;
                multiplierInput.value = 1;
                renderPlayTabs(); renderMatches(); renderBetSlip();
            });
        });

        multiplierInput.addEventListener('input', () => {
            let val = parseInt(multiplierInput.value) || 1;
            if (val < 1) val = 1;
            if (val > 50) val = 50;
            state.multiplier = val;
            updateResult();
        });

        // 初始化
        renderPlayTabs();
        renderMatches();
        renderBetSlip();
        // 从API加载在售比赛数据
        loadMatches();
        console.log('✅ 竞彩计算器已加载');
    </script>

    <!-- 引入公共API模块 -->
    <script type="module">
        import { fetchMatches, fetchPredictions, fetchAIStats, esc, fmtDate, fmtTime, showError, getCachedData, setCachedData } from './api.2026070720.js';
        
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
    </script>
</body>
