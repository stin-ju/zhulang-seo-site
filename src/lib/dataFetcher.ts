import { supabase } from './supabase';
import { AI_RETIRED } from './data';

// ===== Raw data shape (mirrors src/data/data.json) =====
// Reused by src/lib/data.ts so the existing parsing/aggregation logic
// keeps working without changes to the shape it consumes.

export interface RawPrediction {
  ai: string;
  spf: string;
  handicap_spf: string;
  score: string;
  goals: number | string;
  half_full: string;
  hit_handicap: '✅' | '❌' | null;
  hit_score: '✅' | '❌' | null;
  hit_goals: '✅' | '❌' | null;
  hit_half: '✅' | '❌' | null;
  total_hits: number | null;
  analysis?: string;
}

export interface RawOdds {
  win?: number | string;
  draw?: number | string;
  lose?: number | string;
  handicap_win?: number | string;
  handicap_draw?: number | string;
  handicap_lose?: number | string;
  actual_score?: string | null;
  status: '已确认' | '待比赛';
}

export interface RawMatch {
  id: string;
  teams: string;
  time: string;
  handicap: string | number;
  predictions: RawPrediction[];
  odds: RawOdds;
}

export interface RawResource {
  id: string;
  teams: string;
  time: string;
  handicap: string | number;
  score?: string | null;
  result?: string | null;
  status: '已确认' | '待比赛';
}

export interface RawStatsEntry {
  name: string;
  rank: number | null;
  total_pnl: string | number;
  hit_rate: string;
  matches: number;
  let_hit: string;
  score_hit: string;
  retired?: boolean;
  retired_range?: string;
  new?: boolean;
}

export interface RawDimensionStats {
  invest: number;
  hits: number;
  pnl: number;
}

export interface RawBettingSummaryEntry {
  ai: string;
  rank: number;
  dimensions: {
    spf?: RawDimensionStats;
    handicap?: RawDimensionStats;
    score?: RawDimensionStats;
    goals?: RawDimensionStats;
    half_full?: RawDimensionStats;
    chain?: RawDimensionStats;
  };
  total_pnl: number;
  win_rate: string;
  total_matches: number;
}

export interface RawBettingDailyEntry {
  date: string;
  ai: string;
  spf: RawDimensionStats;
  handicap: RawDimensionStats;
  score: RawDimensionStats;
  goals: RawDimensionStats;
  half_full: RawDimensionStats;
  chain?: RawDimensionStats;
  daily_pnl: number;
  win_rate: string;
  rank_change: string;
}

export interface RawChainSelection {
  match_id: string;
  teams: string;
  dimension: string;
  prediction: string;
  hit: boolean | null;
}

export interface RawChainBet {
  type: string;
  selections: RawChainSelection[];
  odds: number;
  hit: boolean | null;
  pnl: number;
}

export interface RawChainAiBets {
  ai: string;
  bets: RawChainBet[];
}

export interface RawChainBetDay {
  date: string;
  matches: string[];
  ai_bets: RawChainAiBets[];
}

export interface RawData {
  matches: RawMatch[];
  resources: RawResource[];
  stats: RawStatsEntry[];
  betting_stats?: {
    summary: RawBettingSummaryEntry[];
    daily: RawBettingDailyEntry[];
  };
  chain_bets?: RawChainBetDay[];
}

// ===== Helpers =====

function ensureAiPrefix(name: string): string {
  if (!name) return name;
  return name.startsWith('AI-') ? name : `AI-${name}`;
}

function stripAiPrefix(name: string): string {
  if (!name) return name;
  return name.startsWith('AI-') ? name.slice(3) : name;
}

function toHitMark(v: unknown): '✅' | '❌' | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'boolean') return v ? '✅' : '❌';
  if (typeof v === 'string') {
    const t = v.trim();
    if (t === '' || t === 'null') return null;
    if (t === '✅' || t === '✓' || t === 'true' || t === '1' || t === 'yes') return '✅';
    if (t === '❌' || t === '✗' || t === 'false' || t === '0' || t === 'no') return '❌';
    return null;
  }
  if (typeof v === 'number') return v > 0 ? '✅' : '❌';
  return null;
}

function toBool(v: unknown): boolean {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') {
    const t = v.trim().toLowerCase();
    return t === 'true' || t === '1' || t === 'yes' || t === '✅' || t === '✓';
  }
  if (typeof v === 'number') return v > 0;
  return false;
}

/**
 * 把数据库 boolean 字段安全转换：null / undefined 保留为 null（待定状态）
 * 用于尚未开赛比赛的 hit 字段。
 */
function toBoolOrNull(v: unknown): boolean | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') {
    const t = v.trim().toLowerCase();
    if (t === '' || t === 'null') return null;
    return t === 'true' || t === '1' || t === 'yes' || t === '✅' || t === '✓';
  }
  if (typeof v === 'number') return v > 0;
  return null;
}

function num(v: unknown, fallback = 0): number {
  if (typeof v === 'number') return Number.isFinite(v) ? v : fallback;
  if (typeof v === 'string') {
    const trimmed = v.trim().replace(/^\+/, '');
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : fallback;
  }
  return fallback;
}

// ===== Row types matching DB columns =====

interface DbMatchRow {
  id: string;
  teams: string;
  match_time: string;
  handicap: string | number | null;
  home_score: number | null;
  away_score: number | null;
  status: string | null;
  win_odds: number | string | null;
  draw_odds: number | string | null;
  lose_odds: number | string | null;
  handicap_win_odds: number | string | null;
  handicap_draw_odds: number | string | null;
  handicap_lose_odds: number | string | null;
}

interface DbPredictionRow {
  id: number | string;
  match_id: string;
  ai_name: string;
  spf: string | null;
  handicap_spf: string | null;
  score: string | null;
  goals: number | string | null;
  half_full: string | null;
  hit_handicap: unknown;
  hit_score: unknown;
  hit_goals: unknown;
  hit_half: unknown;
  total_hits: number | null;
  analysis: string | null;
}

interface DbStatsRow {
  id: number | string;
  ai_name: string;
  rank: number | null;
  total_pnl: string | number | null;
  hit_rate: string | null;
  matches: number | null;
  let_hit: string | null;
  score_hit: string | null;
  is_active: boolean | null;
  updated_at?: string | null;
}

interface DbBettingSummaryRow {
  id: number | string;
  ai_name: string;
  rank: number | null;
  spf_invest: number | null;
  spf_hits: number | null;
  spf_pnl: number | null;
  handicap_invest: number | null;
  handicap_hits: number | null;
  handicap_pnl: number | null;
  score_invest: number | null;
  score_hits: number | null;
  score_pnl: number | null;
  goals_invest: number | null;
  goals_hits: number | null;
  goals_pnl: number | null;
  half_full_invest: number | null;
  half_full_hits: number | null;
  half_full_pnl: number | null;
  total_pnl: number | null;
  win_rate: string | null;
  total_matches: number | null;
}

interface DbBettingDailyRow {
  id: number | string;
  match_date: string;
  ai_name: string;
  spf_pnl: number | null;
  handicap_pnl: number | null;
  score_pnl: number | null;
  goals_pnl: number | null;
  half_full_pnl: number | null;
  daily_pnl: number | null;
  win_rate: string | null;
  rank_change: string | null;
}

interface DbChainBetRow {
  id: number | string;
  bet_date: string;
  ai_name: string;
  bet_type: string;
  odds: number | string | null;
  hit: boolean | string | null;
  pnl: number | null;
  selections: unknown;
}

// ===== Reshape DB rows into the JSON shape =====

function buildMatchesAndResources(
  matchRows: DbMatchRow[],
  predictionRows: DbPredictionRow[]
): { matches: RawMatch[]; resources: RawResource[] } {
  const predByMatch = new Map<string, RawPrediction[]>();
  for (const row of predictionRows) {
    const list = predByMatch.get(row.match_id) ?? [];
    list.push({
      ai: ensureAiPrefix(row.ai_name),
      spf: row.spf ?? '',
      handicap_spf: row.handicap_spf ?? '',
      score: row.score ?? '',
      goals: row.goals ?? '',
      half_full: row.half_full ?? '',
      hit_handicap: toHitMark(row.hit_handicap),
      hit_score: toHitMark(row.hit_score),
      hit_goals: toHitMark(row.hit_goals),
      hit_half: toHitMark(row.hit_half),
      total_hits: row.total_hits,
      analysis: row.analysis ?? undefined,
    });
    predByMatch.set(row.match_id, list);
  }

  const matches: RawMatch[] = [];
  const resources: RawResource[] = [];
  for (const m of matchRows) {
    // 数据库实际可能写入：'已确认' / '已结束' / '待比赛'。
    // 前端只区分两态：已结束（含已确认/已结束）→ '已确认'；其它 → '待比赛'。
    const isFinished = m.status === '已确认' || m.status === '已结束';
    const status = (isFinished ? '已确认' : '待比赛') as
      | '已确认'
      | '待比赛';
    const actualScore =
      m.home_score !== null && m.away_score !== null
        ? `${m.home_score}-${m.away_score}`
        : null;

    // DB 中"未开始"等未结算比赛的 predictions.hit_* 可能被错误录入为 false（应为 null），
    // 导致前端 DimCell 把未结算预测渲染为"未命中"暗灰色。
    // 此处兜底：未结束比赛一律把 hit 字段强制置 null，表示"待定"。
    const rawPreds = predByMatch.get(m.id) ?? [];
    const predictions: RawPrediction[] = isFinished
      ? rawPreds
      : rawPreds.map(
          (p) =>
            ({
              ...p,
              hit_handicap: null,
              hit_score: null,
              hit_goals: null,
              hit_half: null,
              total_hits: null,
            }) as RawPrediction,
        );

    matches.push({
      id: m.id,
      teams: m.teams,
      time: m.match_time,
      handicap: m.handicap ?? '',
      predictions,
      odds: {
        win: m.win_odds ?? undefined,
        draw: m.draw_odds ?? undefined,
        lose: m.lose_odds ?? undefined,
        handicap_win: m.handicap_win_odds ?? undefined,
        handicap_draw: m.handicap_draw_odds ?? undefined,
        handicap_lose: m.handicap_lose_odds ?? undefined,
        actual_score: actualScore,
        status,
      },
    });
    resources.push({
      id: m.id,
      teams: m.teams,
      time: m.match_time,
      handicap: m.handicap ?? '',
      result: actualScore,
      status,
    });
  }
  return { matches, resources };
}

function buildStats(rows: DbStatsRow[]): RawStatsEntry[] {
  return rows.map(r => {
    // Frontend retired list overrides DB is_active (e.g. 天工 is active in DB
    // but marked retired on the frontend).
    const isRetiredOnFrontend = AI_RETIRED.some(n => stripAiPrefix(n) === stripAiPrefix(r.ai_name));
    const isActive = r.is_active !== false && !isRetiredOnFrontend; // default true
    const pnl = num(r.total_pnl);
    return {
      name: stripAiPrefix(r.ai_name),
      rank: r.rank,
      total_pnl: pnl,
      hit_rate: r.hit_rate ?? 'N/A',
      matches: r.matches ?? 0,
      let_hit: r.let_hit ?? '0/0(0%)',
      score_hit: r.score_hit ?? '0/0(0%)',
      retired: !isActive,
      // 新加入的活跃 AI（pnl=0 且无让球命中数据）视作 newcomer，让其沉到活跃区底部。
      new:
        isActive &&
        pnl === 0 &&
        (r.let_hit === null || r.let_hit === '' || r.let_hit === '0/0(0%)'),
    };
  });
}

function buildBettingSummary(
  rows: DbBettingSummaryRow[],
  chainBetsByAi: Map<string, RawDimensionStats>
): RawBettingSummaryEntry[] {
  return rows.map(r => {
    const ai = ensureAiPrefix(r.ai_name);
    const chain = chainBetsByAi.get(ai);
    return {
      ai,
      rank: r.rank ?? 0,
      dimensions: {
        spf: { invest: num(r.spf_invest), hits: num(r.spf_hits), pnl: num(r.spf_pnl) },
        handicap: {
          invest: num(r.handicap_invest),
          hits: num(r.handicap_hits),
          pnl: num(r.handicap_pnl),
        },
        score: {
          invest: num(r.score_invest),
          hits: num(r.score_hits),
          pnl: num(r.score_pnl),
        },
        goals: {
          invest: num(r.goals_invest),
          hits: num(r.goals_hits),
          pnl: num(r.goals_pnl),
        },
        half_full: {
          invest: num(r.half_full_invest),
          hits: num(r.half_full_hits),
          pnl: num(r.half_full_pnl),
        },
        ...(chain ? { chain } : {}),
      },
      total_pnl: num(r.total_pnl),
      win_rate: r.win_rate ?? '0%',
      total_matches: r.total_matches ?? 0,
    };
  });
}

function buildBettingDaily(rows: DbBettingDailyRow[]): RawBettingDailyEntry[] {
  return rows.map(r => ({
    date: r.match_date,
    ai: ensureAiPrefix(r.ai_name),
    spf: { invest: 0, hits: 0, pnl: num(r.spf_pnl) },
    handicap: { invest: 0, hits: 0, pnl: num(r.handicap_pnl) },
    score: { invest: 0, hits: 0, pnl: num(r.score_pnl) },
    goals: { invest: 0, hits: 0, pnl: num(r.goals_pnl) },
    half_full: { invest: 0, hits: 0, pnl: num(r.half_full_pnl) },
    daily_pnl: num(r.daily_pnl),
    win_rate: r.win_rate ?? '0%',
    rank_change: r.rank_change ?? '—',
  }));
}

function buildChainBets(
  rows: DbChainBetRow[],
  matchRows: DbMatchRow[] = []
): {
  days: RawChainBetDay[];
  chainPerAi: Map<string, RawDimensionStats>;
} {
  // group by date → ai
  const dateMap = new Map<string, Map<string, RawChainBet[]>>();
  const matchesPerDate = new Map<string, Set<string>>();
  const perAi = new Map<string, RawDimensionStats>();
  // match_id → teams，用于补齐 selections 中缺失的 teams 字段
  const teamsById = new Map<string, string>();
  for (const m of matchRows) {
    if (m.id && m.teams) teamsById.set(m.id, m.teams);
  }

  for (const row of rows) {
    const ai = ensureAiPrefix(row.ai_name);
    const selectionsRaw = Array.isArray(row.selections)
      ? (row.selections as unknown[])
      : [];
    const selections: RawChainSelection[] = selectionsRaw.map(s => {
      const obj = (s ?? {}) as Record<string, unknown>;
      const matchId = String(obj.match_id ?? '');
      // 兼容两种字段命名：dimension/prediction（历史数据）与 dim/pick（v12 新数据）
      const dimension = String(obj.dimension ?? obj.dim ?? '');
      const prediction = String(obj.prediction ?? obj.pick ?? '');
      const teams = String(obj.teams ?? teamsById.get(matchId) ?? '');
      return {
        match_id: matchId,
        teams,
        dimension,
        prediction,
        hit: toBoolOrNull(obj.hit),
      };
    });

    const bet: RawChainBet = {
      type: row.bet_type,
      selections,
      odds: num(row.odds),
      hit: toBoolOrNull(row.hit),
      pnl: num(row.pnl),
    };

    let aiMap = dateMap.get(row.bet_date);
    if (!aiMap) {
      aiMap = new Map();
      dateMap.set(row.bet_date, aiMap);
    }
    const list = aiMap.get(ai) ?? [];
    list.push(bet);
    aiMap.set(ai, list);

    let mset = matchesPerDate.get(row.bet_date);
    if (!mset) {
      mset = new Set();
      matchesPerDate.set(row.bet_date, mset);
    }
    for (const sel of selections) {
      if (sel.match_id) mset.add(sel.match_id);
    }

    // accumulate chain summary per AI
    const acc = perAi.get(ai) ?? { invest: 0, hits: 0, pnl: 0 };
    acc.invest += 2; // 每注 2 元
    if (bet.hit) acc.hits += 1;
    acc.pnl += bet.pnl;
    perAi.set(ai, acc);
  }

  const days: RawChainBetDay[] = [];
  for (const [date, aiMap] of dateMap) {
    const ai_bets: RawChainAiBets[] = [];
    for (const [ai, bets] of aiMap) {
      ai_bets.push({ ai, bets });
    }
    days.push({
      date,
      matches: Array.from(matchesPerDate.get(date) ?? []),
      ai_bets,
    });
  }

  // sort each day's bets by type for stable rendering (2串1 → 3串1 → 4串1)
  for (const d of days) {
    for (const a of d.ai_bets) {
      a.bets.sort((x, y) => x.type.localeCompare(y.type, 'zh-Hans-CN'));
    }
  }
  // sort dates ascending; the consumer in data.ts will reverse to descending
  days.sort((a, b) => a.date.localeCompare(b.date));

  return { days, chainPerAi: perAi };
}

// ===== Public entry =====

/** 并行查询 6 张表并重塑成 src/data/data.json 的形态。 */
export async function fetchRawData(): Promise<RawData> {
  const [
    matchesRes,
    predictionsRes,
    statsRes,
    summaryRes,
    dailyRes,
    chainRes,
  ] = await Promise.all([
    supabase
      .from('matches')
      .select(
        'id, teams, match_time, handicap, home_score, away_score, status, win_odds, draw_odds, lose_odds, handicap_win_odds, handicap_draw_odds, handicap_lose_odds'
      ),
    supabase
      .from('predictions')
      .select(
        'id, match_id, ai_name, spf, handicap_spf, score, goals, half_full, hit_handicap, hit_score, hit_goals, hit_half, total_hits, analysis'
      ),
    supabase
      .from('ai_stats')
      .select(
        'id, ai_name, rank, total_pnl, hit_rate, matches, let_hit, score_hit, is_active'
      ),
    supabase
      .from('betting_summary')
      .select(
        'id, ai_name, rank, spf_invest, spf_hits, spf_pnl, handicap_invest, handicap_hits, handicap_pnl, score_invest, score_hits, score_pnl, goals_invest, goals_hits, goals_pnl, half_full_invest, half_full_hits, half_full_pnl, total_pnl, win_rate, total_matches'
      ),
    supabase
      .from('betting_daily')
      .select(
        'id, match_date, ai_name, spf_pnl, handicap_pnl, score_pnl, goals_pnl, half_full_pnl, daily_pnl, win_rate, rank_change'
      ),
    supabase
      .from('chain_bets')
      .select('id, bet_date, ai_name, bet_type, odds, hit, pnl, selections'),
  ]);

  const errors = [
    matchesRes.error,
    predictionsRes.error,
    statsRes.error,
    summaryRes.error,
    dailyRes.error,
    chainRes.error,
  ].filter(e => e !== null);

  if (errors.length > 0) {
    throw new Error(
      `Supabase 查询失败：${errors.map(e => e?.message ?? '未知错误').join('; ')}`
    );
  }

  const matchRows = (matchesRes.data ?? []) as DbMatchRow[];
  const predictionRows = (predictionsRes.data ?? []) as DbPredictionRow[];
  const statsRows = (statsRes.data ?? []) as DbStatsRow[];
  const summaryRows = (summaryRes.data ?? []) as DbBettingSummaryRow[];
  const dailyRows = (dailyRes.data ?? []) as DbBettingDailyRow[];
  const chainRows = (chainRes.data ?? []) as DbChainBetRow[];

  // matches & resources need to follow the JSON source ordering convention:
  // newest match-day first, within a day ascending by match id.
  // Sort match rows by match_time desc then id asc.
  matchRows.sort((a, b) => {
    if (a.match_time !== b.match_time) {
      return b.match_time.localeCompare(a.match_time);
    }
    return a.id.localeCompare(b.id);
  });

  const { matches, resources } = buildMatchesAndResources(
    matchRows,
    predictionRows
  );
  const stats = buildStats(statsRows);
  const { days: chainDays, chainPerAi } = buildChainBets(chainRows, matchRows);
  const summary = buildBettingSummary(summaryRows, chainPerAi);
  const daily = buildBettingDaily(dailyRows);

  return {
    matches,
    resources,
    stats,
    betting_stats: { summary, daily },
    chain_bets: chainDays,
  };
}
