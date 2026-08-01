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

        // 过滤脏数据：排除RETIRED/TO_DELETE + 去重
        const BLACKLIST = new Set(['RETIRED', 'TO_DELETE']);
        state.predictions = [];
        allMatches.forEach(m => {
            if (m.predictions && m.predictions.length > 0) {
                const valid = m.predictions.filter(p => !BLACKLIST.has(p.ai_name || ''));
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
