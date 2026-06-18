// Data type definitions and helpers for AI prediction dataset.

import rawData from '../data/data.json';

export type AiName =
  | 'AI-豆包'
  | 'AI-千问'
  | 'AI-文心'
  | 'AI-智谱清言'
  | 'AI-Kimi'
  | 'AI-混元'
  | 'AI-扣子（皮皮）';

export const AI_LIST: AiName[] = [
  'AI-豆包',
  'AI-千问',
  'AI-文心',
  'AI-智谱清言',
  'AI-Kimi',
  'AI-混元',
  'AI-扣子（皮皮）',
];

export const AI_SHORT: Record<AiName, string> = {
  'AI-豆包': '豆包',
  'AI-千问': '千问',
  'AI-文心': '文心',
  'AI-智谱清言': '智谱',
  'AI-Kimi': 'Kimi',
  'AI-混元': '混元',
  'AI-扣子（皮皮）': '扣子皮皮',
};

export const AI_ACCENT: Record<AiName, string> = {
  'AI-豆包': '#60A5FA',
  'AI-千问': '#A78BFA',
  'AI-文心': '#F472B6',
  'AI-智谱清言': '#34D399',
  'AI-Kimi': '#FBBF24',
  'AI-混元': '#22D3EE',
  'AI-扣子（皮皮）': '#FB923C',
};

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
  win: number;
  draw: number;
  lose: number;
  handicap: string | number;
  handicap_win: number;
  handicap_draw: number;
  handicap_lose: number;
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
  score: string | null;
  status: '已确认' | '待比赛';
}

export interface BettingDimensionStats {
  invest: number;
  hits: number;
  pnl: number;
}

export type BettingDimensionKey = 'spf' | 'handicap' | 'score' | 'goals' | 'half_full';

export interface BettingSummaryEntry {
  ai: string;
  rank: number;
  dimensions: Record<BettingDimensionKey, BettingDimensionStats>;
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
  daily_pnl: number;
  win_rate: string;
  rank_change: string;
}

interface RawData {
  matches: MatchEntry[];
  resources: ResourceEntry[];
  stats: { ai: string; rank: number; total_hits: string; total_matches: number }[];
  betting_stats?: {
    summary: BettingSummaryEntry[];
    daily: BettingDailyEntry[];
  };
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
  return {
    id: m.id,
    teams: m.teams,
    time: m.time,
    handicap: String(m.handicap),
    status: res?.status ?? '待比赛',
    actualScore: res?.score ?? null,
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
  totalSlots: number; // 4 dims × confirmed matches
  hitRate: number; // 0-1
  perDim: Record<DimensionKey, { hits: number; total: number; rate: number }>;
  rank: number;
}

function isHit(mark: HitMark): boolean {
  return mark === '✅';
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
    });
  }

  for (const m of confirmedMatches) {
    for (const p of m.predictions) {
      const summary = map.get(p.ai);
      if (!summary) continue;
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

  const list = Array.from(map.values());
  list.sort((a, b) => b.hitRate - a.hitRate);
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
