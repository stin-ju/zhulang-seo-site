// Data type definitions and helpers for AI prediction dataset.

import rawData from '../data/data.json';

export type AiName =
  | 'AI-豆包'
  | 'AI-DeepSeek'
  | 'AI-扣子（皮皮）'
  | 'AI-文心'
  | 'AI-智谱清言'
  | 'AI-天工'
  | 'AI-MiniMax'
  | 'AI-混元'
  | 'AI-千问'
  | 'AI-Kimi';

// 8 active AIs in the order requested by the product team:
// 豆包 → DeepSeek → 扣子 → 文心 → 智谱 → 天工 → MiniMax → 混元
export const AI_ACTIVE: AiName[] = [
  'AI-豆包',
  'AI-DeepSeek',
  'AI-扣子（皮皮）',
  'AI-文心',
  'AI-智谱清言',
  'AI-天工',
  'AI-MiniMax',
  'AI-混元',
];

// Retired (greyed) AIs displayed at the tail of every list.
export const AI_RETIRED: AiName[] = ['AI-千问', 'AI-Kimi'];

// Canonical display order: 8 active first, then retired at the bottom.
export const AI_LIST: AiName[] = [...AI_ACTIVE, ...AI_RETIRED];

export const AI_SHORT: Record<AiName, string> = {
  'AI-豆包': '豆包',
  'AI-DeepSeek': 'DeepSeek',
  'AI-扣子（皮皮）': '扣子皮皮',
  'AI-文心': '文心',
  'AI-智谱清言': '智谱',
  'AI-天工': '天工',
  'AI-MiniMax': 'MiniMax',
  'AI-混元': '混元',
  'AI-千问': '千问',
  'AI-Kimi': 'Kimi',
};

export const AI_ACCENT: Record<AiName, string> = {
  'AI-豆包': '#60A5FA',
  'AI-DeepSeek': '#818CF8',
  'AI-扣子（皮皮）': '#FB923C',
  'AI-文心': '#F472B6',
  'AI-智谱清言': '#34D399',
  'AI-天工': '#FACC15',
  'AI-MiniMax': '#F87171',
  'AI-混元': '#22D3EE',
  'AI-千问': '#A78BFA',
  'AI-Kimi': '#FBBF24',
};

const RETIRED_SET = new Set<string>(AI_RETIRED);
export function isRetiredAi(ai: string): boolean {
  return RETIRED_SET.has(ai);
}

export type HitMark = '✅' | '❌' | null;

export interface Prediction {
  ai: string;
  spf: string;
  handicap_spf: string;
  score: string;
  goals: string | number;
  half_full: string;
  hit_handicap: HitMark;
  hit_score: HitMark;
  hit_goals: HitMark;
  hit_half: HitMark;
  total_hits: number | null;
  analysis?: string;
}

export interface OddsEntry {
  win: number | string;
  draw: number | string;
  lose: number | string;
  handicap?: string | number;
  handicap_win: number | string;
  handicap_draw: number | string;
  handicap_lose: number | string;
  actual_score: string | null;
  status: '已确认' | '待比赛';
}

export interface MatchEntry {
  id: string;
  teams: string;
  time: string;
  handicap: string | number;
  predictions: Prediction[];
  odds?: OddsEntry;
}

export interface ResourceEntry {
  id: string;
  teams: string;
  time: string;
  handicap: string | number;
  // v9 of the dataset stores the actual score in `result`; older shapes used
  // `score`. Both can be null/undefined for not-yet-played matches.
  score?: string | null;
  result?: string | null;
  status: '已确认' | '待比赛';
}

// Raw shape of an entry inside `data.stats[]` (v9):
//   { name, rank, total_pnl, hit_rate, matches, let_hit, score_hit, retired?, retired_range?, new? }
interface RawStatsEntry {
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

export interface BettingDimensionStats {
  invest: number;
  hits: number;
  pnl: number;
}

export type BettingDimensionKey =
  | 'spf'
  | 'handicap'
  | 'score'
  | 'goals'
  | 'half_full'
  | 'chain';

export interface BettingSummaryEntry {
  ai: string;
  rank: number;
  dimensions: Partial<Record<BettingDimensionKey, BettingDimensionStats>>;
  total_pnl: number;
  win_rate: string;
  total_matches: number;
}

export interface BettingDailyEntry {
  date: string;
  ai: string;
  spf: BettingDimensionStats;
  handicap: BettingDimensionStats;
  score: BettingDimensionStats;
  goals: BettingDimensionStats;
  half_full: BettingDimensionStats;
  chain?: BettingDimensionStats;
  daily_pnl: number;
  win_rate: string;
  rank_change: string;
}

export interface ChainBetSelection {
  match_id: string;
  teams: string;
  dimension: string;
  prediction: string;
  hit: boolean;
}

export interface ChainBet {
  type: string;
  selections: ChainBetSelection[];
  odds: number;
  hit: boolean;
  pnl: number;
}

export interface ChainAiBets {
  ai: string;
  bets: ChainBet[];
}

export interface ChainBetDay {
  date: string;
  matches: string[];
  ai_bets: ChainAiBets[];
}

interface RawData {
  matches: MatchEntry[];
  resources: ResourceEntry[];
  stats: RawStatsEntry[];
  betting_stats?: {
    summary: BettingSummaryEntry[];
    daily: BettingDailyEntry[];
  };
  chain_bets?: ChainBetDay[];
}

const data = rawData as RawData;

export interface MatchView {
  id: string;
  teams: string;
  time: string;
  handicap: string;
  status: '已确认' | '待比赛';
  actualScore: string | null;
  predictions: Prediction[];
  odds?: OddsEntry;
}

const resourceMap = new Map<string, ResourceEntry>();
for (const r of data.resources) {
  resourceMap.set(r.id, r);
}

export const matches: MatchView[] = data.matches.map(m => {
  const res = resourceMap.get(m.id);
  const actualScore = res?.result ?? res?.score ?? null;
  return {
    id: m.id,
    teams: m.teams,
    time: m.time,
    handicap: String(m.handicap),
    status: res?.status ?? '待比赛',
    actualScore,
    predictions: m.predictions,
    odds: m.odds,
  };
});

// Sort by time desc (ISO-like string sort works because of YYYY-MM-DD HH:mm)
matches.sort((a, b) => (a.time < b.time ? 1 : a.time > b.time ? -1 : 0));

export const confirmedMatches = matches.filter(m => m.status === '已确认');

const DIMENSION_KEYS = ['hit_handicap', 'hit_score', 'hit_goals', 'hit_half'] as const;
export type DimensionKey = (typeof DIMENSION_KEYS)[number];
export const DIMENSIONS: { key: DimensionKey; label: string }[] = [
  { key: 'hit_handicap', label: '让球胜平负' },
  { key: 'hit_score', label: '全场比分' },
  { key: 'hit_goals', label: '总进球数' },
  { key: 'hit_half', label: '半全场' },
];

export interface AiSummary {
  ai: AiName;
  totalConfirmed: number;
  totalHits: number;
  totalSlots: number; // 4 dims × confirmed matches that have hit data
  hitRate: number; // 0-1, computed from match data (24 matches that have hit data)
  perDim: Record<DimensionKey, { hits: number; total: number; rate: number }>;
  rank: number;
  retired: boolean;
  isNewcomer: boolean;
  participatedMatches: number; // total matches this AI predicted (confirmed + pending)
  // ----- Overlay from data.stats[] (v9 official aggregated numbers) -----
  // These are the headline / rank-driving figures shown on the leaderboard.
  officialRank: number | null; // null = newcomer (not yet ranked)
  officialPnl: number; // parsed from "+51.8" / "-37.0" / "0"
  officialHitRate: number | null; // 0-1 or null when stats says "N/A"
  officialMatches: number;
  officialLetHitText: string; // e.g. "13/28(46%)"
  officialScoreHitText: string; // e.g. "4/28(14%)"
  retiredRange?: string;
}

function isHit(mark: HitMark): boolean {
  return mark === '✅';
}

// stats[] uses bare display names ("混元", "扣子(皮皮)") whereas predictions
// keys use the canonical "AI-…" form (with full-width parens). Map both.
const STATS_NAME_TO_AI: Record<string, AiName> = {
  豆包: 'AI-豆包',
  DeepSeek: 'AI-DeepSeek',
  '扣子(皮皮)': 'AI-扣子（皮皮）',
  '扣子（皮皮）': 'AI-扣子（皮皮）',
  文心: 'AI-文心',
  智谱清言: 'AI-智谱清言',
  天工: 'AI-天工',
  MiniMax: 'AI-MiniMax',
  混元: 'AI-混元',
  千问: 'AI-千问',
  Kimi: 'AI-Kimi',
};

function parseSignedNumber(s: string | number | null | undefined): number {
  if (s === null || s === undefined) return 0;
  if (typeof s === 'number') return Number.isFinite(s) ? s : 0;
  const trimmed = s.trim();
  if (!trimmed) return 0;
  if (trimmed === '0' || trimmed === '+0' || trimmed === '-0') return 0;
  const n = Number(trimmed.replace(/^\+/, ''));
  return Number.isFinite(n) ? n : 0;
}

function parsePercent(s: string): number | null {
  if (!s || s === 'N/A') return null;
  const m = s.match(/(-?\d+(?:\.\d+)?)\s*%/);
  if (!m) return null;
  return Number(m[1]) / 100;
}

export function buildAiSummaries(): AiSummary[] {
  const map = new Map<string, AiSummary>();
  for (const ai of AI_LIST) {
    const perDim: AiSummary['perDim'] = {
      hit_handicap: { hits: 0, total: 0, rate: 0 },
      hit_score: { hits: 0, total: 0, rate: 0 },
      hit_goals: { hits: 0, total: 0, rate: 0 },
      hit_half: { hits: 0, total: 0, rate: 0 },
    };
    map.set(ai, {
      ai,
      totalConfirmed: 0,
      totalHits: 0,
      totalSlots: 0,
      hitRate: 0,
      perDim,
      rank: 0,
      retired: isRetiredAi(ai),
      isNewcomer: false,
      participatedMatches: 0,
      officialRank: null,
      officialPnl: 0,
      officialHitRate: null,
      officialMatches: 0,
      officialLetHitText: '0/0(0%)',
      officialScoreHitText: '0/0(0%)',
      retiredRange: undefined,
    });
  }

  // Count total matches each AI participated in (confirmed + pending).
  for (const m of matches) {
    for (const p of m.predictions) {
      const summary = map.get(p.ai);
      if (!summary) continue;
      summary.participatedMatches += 1;
    }
  }

  // Per-dim hits computed from match data — only the matches with hit_*
  // populated will contribute (newly confirmed 025-028 leave hits as null
  // → they simply don't add to the denominator, keeping the rate honest).
  for (const m of confirmedMatches) {
    for (const p of m.predictions) {
      const summary = map.get(p.ai);
      if (!summary) continue;
      // skip predictions whose hits are not yet recorded
      if (
        p.hit_handicap === null &&
        p.hit_score === null &&
        p.hit_goals === null &&
        p.hit_half === null
      ) {
        continue;
      }
      summary.totalConfirmed += 1;
      for (const k of DIMENSION_KEYS) {
        summary.perDim[k].total += 1;
        if (isHit(p[k])) {
          summary.perDim[k].hits += 1;
          summary.totalHits += 1;
        }
        summary.totalSlots += 1;
      }
    }
  }

  for (const s of map.values()) {
    s.hitRate = s.totalSlots > 0 ? s.totalHits / s.totalSlots : 0;
    for (const k of DIMENSION_KEYS) {
      const d = s.perDim[k];
      d.rate = d.total > 0 ? d.hits / d.total : 0;
    }
  }

  // Overlay v9 official stats from data.stats[].
  for (const raw of data.stats) {
    const ai = STATS_NAME_TO_AI[raw.name];
    if (!ai) continue;
    const summary = map.get(ai);
    if (!summary) continue;
    summary.officialRank = raw.rank;
    summary.officialPnl = parseSignedNumber(raw.total_pnl);
    summary.officialHitRate = parsePercent(raw.hit_rate);
    summary.officialMatches = raw.matches;
    summary.officialLetHitText = raw.let_hit;
    summary.officialScoreHitText = raw.score_hit;
    summary.retired = !!raw.retired || summary.retired;
    summary.retiredRange = raw.retired_range;
    summary.isNewcomer = !!raw.new;

    // Overlay headline numbers used across views to come from the official
    // 28-match aggregate (data.stats), so leaderboard / AI list / AI detail
    // all show the canonical numbers regardless of how many matches have
    // detail-level hit data filled in.
    if (raw.matches > 0) {
      summary.totalConfirmed = raw.matches;
      summary.participatedMatches = raw.matches;
      summary.totalSlots = raw.matches * 4;
      summary.hitRate = summary.officialHitRate ?? 0;
      summary.totalHits = Math.round(summary.totalSlots * summary.hitRate);
    }
  }

  // Ordering: by officialRank ascending. Retired AIs keep their official rank
  // (their final ranking is preserved as a memorial of where they were when
  // they retired) but are styled grey at the view layer. Newcomers
  // (officialRank=null) sink to the very tail.
  const list = Array.from(map.values());
  list.sort((a, b) => {
    if (a.isNewcomer !== b.isNewcomer) return a.isNewcomer ? 1 : -1;
    const ra = a.officialRank ?? 999;
    const rb = b.officialRank ?? 999;
    if (ra !== rb) return ra - rb;
    return b.officialPnl - a.officialPnl;
  });
  list.forEach((s, idx) => {
    s.rank = idx + 1;
  });
  return list;
}

export const aiSummaries: AiSummary[] = buildAiSummaries();

export function getMatchById(id: string): MatchView | undefined {
  return matches.find(m => m.id === id);
}

export function getAiSummary(ai: string): AiSummary | undefined {
  return aiSummaries.find(s => s.ai === ai);
}

export interface AiMatchRow {
  match: MatchView;
  prediction: Prediction | undefined;
}

export function getAiMatches(ai: string): AiMatchRow[] {
  return matches.map(m => ({
    match: m,
    prediction: m.predictions.find(p => p.ai === ai),
  }));
}

export function formatHandicap(h: string | number): string {
  const n = typeof h === 'number' ? h : Number(h);
  if (Number.isFinite(n)) {
    return n > 0 ? `+${n}` : `${n}`;
  }
  return String(h);
}

export function formatPercent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

export const totalMatches = matches.length;
export const totalConfirmed = confirmedMatches.length;

// ===== Betting stats =====

export const BETTING_DIMENSIONS: { key: BettingDimensionKey; label: string }[] = [
  { key: 'spf', label: '胜平负' },
  { key: 'handicap', label: '让球胜平负' },
  { key: 'score', label: '全场比分' },
  { key: 'goals', label: '总进球' },
  { key: 'half_full', label: '半全场' },
  { key: 'chain', label: '串关' },
];

const rawBetting = data.betting_stats;

export const bettingSummaries: BettingSummaryEntry[] = (rawBetting?.summary ?? [])
  .slice()
  .sort((a, b) => b.total_pnl - a.total_pnl)
  .map((s, idx) => ({ ...s, rank: idx + 1 }));

export const bettingDaily: BettingDailyEntry[] = rawBetting?.daily ?? [];

export const bettingDates: string[] = Array.from(
  new Set(bettingDaily.map(d => d.date))
);

// ===== Chain bets (串关推荐) =====
const rawChainBets = (rawData as RawData).chain_bets ?? [];

/** 串关推荐按日期升序（6/17 → 6/18 → 6/19）展示 */
export const chainBets: ChainBetDay[] = [...rawChainBets].sort((a, b) =>
  a.date.localeCompare(b.date)
);

export interface ChainBetTotals {
  totalBets: number;
  totalHits: number;
  totalPnl: number;
  totalInvest: number; // 每注 2 元
  hitRate: number; // 0-1
}

export function getChainBetTotals(): ChainBetTotals {
  let totalBets = 0;
  let totalHits = 0;
  let totalPnl = 0;
  for (const day of chainBets) {
    for (const ai of day.ai_bets) {
      for (const b of ai.bets) {
        totalBets += 1;
        if (b.hit) totalHits += 1;
        totalPnl += b.pnl;
      }
    }
  }
  return {
    totalBets,
    totalHits,
    totalPnl,
    totalInvest: totalBets * 2,
    hitRate: totalBets > 0 ? totalHits / totalBets : 0,
  };
}

export interface AiChainBetsView {
  days: { date: string; matches: string[]; bets: ChainBet[] }[];
  totals: ChainBetTotals;
}

export function getChainBetsForAi(ai: string): AiChainBetsView {
  const days: AiChainBetsView['days'] = [];
  let totalBets = 0;
  let totalHits = 0;
  let totalPnl = 0;
  for (const day of chainBets) {
    const aiEntry = day.ai_bets.find((a) => a.ai === ai);
    if (!aiEntry || aiEntry.bets.length === 0) continue;
    days.push({ date: day.date, matches: day.matches, bets: aiEntry.bets });
    for (const b of aiEntry.bets) {
      totalBets += 1;
      if (b.hit) totalHits += 1;
      totalPnl += b.pnl;
    }
  }
  return {
    days,
    totals: {
      totalBets,
      totalHits,
      totalPnl,
      totalInvest: totalBets * 2,
      hitRate: totalBets > 0 ? totalHits / totalBets : 0,
    },
  };
}

export interface BettingTotals {
  totalInvest: number;
  totalReturn: number;
  totalPnl: number;
  totalHits: number;
  totalBets: number;
}

export function getBettingTotals(): BettingTotals {
  let totalInvest = 0;
  let totalPnl = 0;
  let totalHits = 0;
  let totalBets = 0;
  for (const s of bettingSummaries) {
    for (const dim of BETTING_DIMENSIONS) {
      const stat = s.dimensions[dim.key];
      if (!stat) continue;
      totalInvest += stat.invest;
      totalPnl += stat.pnl;
      totalHits += stat.hits;
      totalBets += stat.invest / 2; // each bet is 2 yuan
    }
  }
  return {
    totalInvest,
    totalReturn: totalInvest + totalPnl,
    totalPnl,
    totalHits,
    totalBets,
  };
}

export function getBettingSummary(ai: string): BettingSummaryEntry | undefined {
  return bettingSummaries.find(s => s.ai === ai);
}

export function getBettingDailyByDate(date: string): BettingDailyEntry[] {
  return bettingDaily
    .filter(d => d.date === date)
    .slice()
    .sort((a, b) => b.daily_pnl - a.daily_pnl);
}

export function formatPnl(pnl: number): string {
  const sign = pnl > 0 ? '+' : pnl < 0 ? '' : '';
  return `${sign}${pnl.toFixed(1)}`;
}

export function formatYuan(value: number): string {
  return `${value.toFixed(0)} 元`;
}
