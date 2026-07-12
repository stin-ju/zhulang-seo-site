    <script type="module">
        import { fetchAllMatches, fetchPredictions, esc, fmtDate, fmtTime, showError } from './api.202607120838.js';

        async function loadBriefList() {
            const container = document.getElementById('briefList');
            try {
                const matches = await fetchAllMatches('football');
                const matchIds = matches.map(m => m.id);
                const predictions = matchIds.length > 0 ? await fetchPredictions(matchIds, 'football') : [];

                if (matches.length === 0) {
                    container.innerHTML = '<div class="card" style="text-align:center;padding:30px;color:#6b7280;">暂无简报</div>';
                    return;
                }

                // 按日期分组
                const groups = {};
                matches.forEach(m => {
                    const dateKey = m.match_date || (m.match_time ? m.match_time.slice(0, 10) : 'unknown');
                    if (!groups[dateKey]) groups[dateKey] = [];
                    groups[dateKey].push(m);
                });

                const sortedDates = Object.keys(groups).sort().reverse();
                let html = '';
                sortedDates.forEach(dateKey => {
                    const dayMatches = groups[dateKey];
                    const dayPredictions = predictions.filter(p => dayMatches.some(m => m.id === p.match_id));
                    const dateLabel = fmtDate(dateKey);
                    const matchCount = dayMatches.length;
                    const aiCount = new Set(dayPredictions.map(p => p.ai_name)).size;
                    
                    html += `
                        <a href="/brief-${dateKey}.html" class="brief-item">
                            <span class="date">${dateLabel}</span>
                            <span class="title">${matchCount}场比赛 · ${aiCount}个AI预测</span>
                            <span class="arrow">→</span>
                        </a>
                    `;
                });

                container.innerHTML = html || '<div class="card" style="text-align:center;padding:30px;color:#6b7280;">暂无简报</div>';

            } catch (error) {
                console.error('加载简报失败:', error);
                showError('加载简报失败，请刷新页面重试');
            }
        }

        document.addEventListener('DOMContentLoaded', loadBriefList);
    </script>
</body>
