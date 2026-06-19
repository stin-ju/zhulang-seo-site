import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  matches,
  AI_LIST,
  AI_SHORT,
  isRetiredAi,
  formatHandicap,
  type MatchView,
  type Prediction,
} from '../lib/data';

const DIM_LABELS: Array<{
  key: 'spf' | 'handicap_spf' | 'score' | 'goals' | 'half_full';
  label: string;
  hitKey?: 'hit_handicap' | 'hit_score' | 'hit_goals' | 'hit_half';
}> = [
  { key: 'spf', label: '胜平负' },
  { key: 'handicap_spf', label: '让球', hitKey: 'hit_handicap' },
  { key: 'score', label: '比分', hitKey: 'hit_score' },
  { key: 'goals', label: '总进球', hitKey: 'hit_goals' },
  { key: 'half_full', label: '半全场', hitKey: 'hit_half' },
];

function dateOf(time: string): string {
  return time.slice(0, 10);
}

function teamPair(teams: string): { home: string; away: string } {
  const sep = teams.includes('VS') ? 'VS' : teams.includes('vs') ? 'vs' : 'VS';
  const [home = teams, away = ''] = teams.split(sep).map((t) => t.trim());
  return { home, away };
}

export default function MatchListPage() {
  // ---- filters ----
  const [dateFilter, setDateFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | '待比赛' | '已确认'>('all');
  const [search, setSearch] = useState<string>('');

  // ---- derived: all distinct dates ----
  const dates = useMemo(() => {
    const set = new Set<string>();
    for (const m of matches) set.add(dateOf(m.time));
    return Array.from(set);
  }, []);

  // ---- filtered matches (preserves source order = newest first) ----
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return matches.filter((m) => {
      if (dateFilter !== 'all' && dateOf(m.time) !== dateFilter) return false;
      if (statusFilter !== 'all' && m.status !== statusFilter) return false;
      if (q) {
        const hay = `${m.id} ${m.teams}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [dateFilter, statusFilter, search]);

  // ---- expand state: default open the first 2 matches in filtered list ----
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const s = new Set<string>();
    matches.slice(0, 2).forEach((m) => s.add(m.id));
    return s;
  });

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => setExpanded(new Set(filtered.map((m) => m.id)));
  const collapseAll = () => setExpanded(new Set());

  const upcomingCount = matches.filter((m) => m.status === '待比赛').length;
  const confirmedCount = matches.filter((m) => m.status === '已确认').length;

  return (
    <div className="space-y-8">
      <header className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-text-secondary">Matches</p>
          <h1 className="mt-2 text-3xl font-bold text-text-primary md:text-4xl">比赛日程与赛果</h1>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            {matches.length} 场比赛 · {upcomingCount} 待比赛 · {confirmedCount} 已确认。点击 + 展开 8 个 AI 的预测明细。
          </p>
        </div>

        {/* Filter bar */}
        <div className="rounded-xl border border-divider bg-deep/70 p-3 backdrop-blur">
          <div className="flex flex-wrap items-center gap-3">
            {/* Date filter */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-secondary">日期</span>
              <select
                value={dateFilter}
                onChange={(e) => setDateFilter(e.target.value)}
                className="rounded-lg border border-divider bg-elevated/80 px-3 py-1.5 text-sm text-text-primary outline-none transition-colors hover:border-gold/40 focus:border-gold/60"
              >
                <option value="all">全部日期</option>
                {dates.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            {/* Status pills */}
            <div className="flex items-center gap-1.5 rounded-lg border border-divider bg-elevated/80 p-1">
              {(['all', '待比赛', '已确认'] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatusFilter(s)}
                  className={`rounded-md px-3 py-1 text-xs transition-colors ${
                    statusFilter === s
                      ? 'bg-gold/20 text-gold ring-1 ring-gold/40'
                      : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  {s === 'all' ? '全部' : s}
                </button>
              ))}
            </div>

            {/* Search */}
            <div className="flex flex-1 items-center gap-2 min-w-[200px]">
              <span className="text-xs text-text-secondary">搜索</span>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="输入队名或比赛 ID（如 周五029）"
                className="flex-1 rounded-lg border border-divider bg-elevated/80 px-3 py-1.5 text-sm text-text-primary placeholder:text-text-secondary/60 outline-none transition-colors hover:border-gold/40 focus:border-gold/60"
              />
            </div>

            {/* Expand controls */}
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={expandAll}
                className="rounded-md border border-divider bg-elevated/80 px-2.5 py-1 text-xs text-text-secondary transition-colors hover:border-gold/40 hover:text-text-primary"
              >
                全部展开
              </button>
              <button
                type="button"
                onClick={collapseAll}
                className="rounded-md border border-divider bg-elevated/80 px-2.5 py-1 text-xs text-text-secondary transition-colors hover:border-gold/40 hover:text-text-primary"
              >
                全部折叠
              </button>
            </div>
          </div>
          <div className="mt-2 text-xs text-text-secondary">
            匹配 {filtered.length} 场比赛
            {dateFilter !== 'all' || statusFilter !== 'all' || search ? '（已应用筛选）' : ''}
          </div>
        </div>
      </header>

      {/* Match list */}
      <section className="space-y-3">
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-dashed border-divider bg-deep/40 p-8 text-center text-sm text-text-secondary">
            没有匹配的比赛，试试调整筛选条件。
          </div>
        ) : (
          filtered.map((m) => (
            <MatchAccordion key={m.id} match={m} open={expanded.has(m.id)} onToggle={() => toggle(m.id)} />
          ))
        )}
      </section>
    </div>
  );
}

interface MatchAccordionProps {
  match: MatchView;
  open: boolean;
  onToggle: () => void;
}

function MatchAccordion({ match, open, onToggle }: MatchAccordionProps) {
  const isPending = match.status === '待比赛';
  const { home, away } = teamPair(match.teams);
  const hitsByAi = match.predictions.reduce<Record<string, number>>((acc, p) => {
    if (typeof p.total_hits === 'number') acc[p.ai] = p.total_hits;
    return acc;
  }, {});
  const bestHits = Math.max(0, ...Object.values(hitsByAi));
  const summaryHits = match.predictions
    .map((p) => (typeof p.total_hits === 'number' ? p.total_hits : null))
    .filter((v): v is number => v !== null);
  const hasHits = summaryHits.length > 0;

  return (
    <article
      className={`rounded-xl border bg-deep/70 backdrop-blur transition-colors ${
        open ? 'border-gold/40 shadow-[0_0_0_1px_rgba(245,194,66,0.15)]' : 'border-divider hover:border-gold/30'
      }`}
    >
      {/* Summary row (always visible) */}
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        {/* Toggle icon */}
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-base font-bold transition-colors ${
            open ? 'border-gold/50 bg-gold/10 text-gold' : 'border-divider text-text-secondary hover:border-gold/40 hover:text-gold'
          }`}
          aria-label={open ? '折叠' : '展开'}
        >
          {open ? '−' : '+'}
        </span>

        {/* Match ID + status pill */}
        <div className="flex shrink-0 flex-col items-start gap-1">
          <span className="font-mono text-xs text-text-secondary">{match.id}</span>
          <StatusPill status={match.status} />
        </div>

        {/* Teams + score */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h3 className="truncate text-base font-semibold text-text-primary md:text-lg">
              {home} <span className="mx-1 text-text-secondary">VS</span> {away}
            </h3>
            {match.actualScore && (
              <span className="font-mono text-base font-bold text-gold tabular-nums">
                {match.actualScore.replace(':', '-')}
              </span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
            <span className="font-mono tabular-nums">{match.time}</span>
            <span>让球 {formatHandicap(match.handicap)}</span>
            {hasHits && (
              <span>
                最佳命中：<span className="text-turf">{bestHits}</span> / 4
              </span>
            )}
          </div>
        </div>

        {/* View link */}
        <Link
          to={`/matches/${encodeURIComponent(match.id)}`}
          onClick={(e) => e.stopPropagation()}
          className="shrink-0 rounded-md border border-divider px-2.5 py-1 text-xs text-text-secondary transition-colors hover:border-gold/40 hover:text-gold"
        >
          详情 →
        </Link>
      </button>

      {/* Expanded body */}
      {open && (
        <div className="border-t border-divider/70 bg-night/40 px-4 pb-4 pt-3">
          {isPending && (
            <p className="mb-3 text-xs text-text-secondary">
              本场尚未开赛，下方为各 AI 的预测；命中状态待赛后录入。
            </p>
          )}
          {!isPending && !hasHits && (
            <p className="mb-3 text-xs text-text-secondary">
              比赛已确认（实际比分 {match.actualScore}），逐项命中数据待录入，预测内容以灰色展示。
            </p>
          )}
          <PredictionTable match={match} bestHits={bestHits} />
        </div>
      )}
    </article>
  );
}

function StatusPill({ status }: { status: '已确认' | '待比赛' }) {
  if (status === '已确认') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-gold/40 bg-gold/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gold">
        <span className="h-1.5 w-1.5 rounded-full bg-gold" /> 已确认
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-divider bg-elevated/60 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-text-secondary">
      <span className="h-1.5 w-1.5 rounded-full bg-miss" /> 待比赛
    </span>
  );
}

function PredictionTable({ match, bestHits }: { match: MatchView; bestHits: number }) {
  // Build rows: iterate AI_LIST, find matching prediction (some matches may not include all AIs)
  const rows = AI_LIST.map((ai) => {
    const pred = match.predictions.find((p) => p.ai === ai);
    return { ai, pred };
  });

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-divider/60 text-xs text-text-secondary">
            <th className="py-2 pr-3 text-left font-medium">AI 选手</th>
            {DIM_LABELS.map((d) => (
              <th key={d.key} className="px-2 py-2 text-center font-medium">
                {d.label}
              </th>
            ))}
            <th className="pl-2 py-2 text-center font-medium">命中</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-divider/40">
          {rows.map(({ ai, pred }) => {
            const retired = isRetiredAi(ai);
            const short = AI_SHORT[ai] ?? ai;

            if (!pred) {
              return (
                <tr key={ai} className="text-text-secondary/60">
                  <td className="py-2 pr-3">
                    <span className="font-medium">{short}</span>
                    {retired && (
                      <span className="ml-2 text-[10px] text-text-secondary">已退赛</span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-center text-xs text-text-secondary/50" colSpan={DIM_LABELS.length + 1}>
                    本场未参赛
                  </td>
                </tr>
              );
            }

            const isBest =
              typeof pred.total_hits === 'number' && pred.total_hits > 0 && pred.total_hits === bestHits;

            return (
              <tr key={ai} className={retired ? 'opacity-60' : ''}>
                <td className="py-2 pr-3">
                  <Link
                    to={`/ai/${encodeURIComponent(ai)}`}
                    className={`font-medium transition-colors hover:text-gold ${isBest ? 'text-gold' : 'text-text-primary'}`}
                  >
                    {short}
                  </Link>
                  {retired && <span className="ml-2 text-[10px] text-text-secondary">退赛</span>}
                </td>
                {DIM_LABELS.map((d) => (
                  <DimCell key={d.key} pred={pred} dim={d} />
                ))}
                <td className="pl-2 py-2 text-center font-mono tabular-nums">
                  {pred.total_hits === null ? (
                    <span className="text-text-secondary/50">—</span>
                  ) : (
                    <span className={isBest ? 'text-gold font-bold' : 'text-text-primary'}>
                      {pred.total_hits}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DimCell({
  pred,
  dim,
}: {
  pred: Prediction;
  dim: (typeof DIM_LABELS)[number];
}) {
  const value = String(pred[dim.key]);
  const hit = dim.hitKey ? pred[dim.hitKey] : null;
  const isHitTrue = hit === '✅';
  const isMiss = hit === '❌';

  let className = 'text-text-primary';
  if (isHitTrue) className = 'rounded-md bg-turf-soft text-turf font-medium';
  else if (isMiss) className = 'text-miss';
  else if (hit === null) className = 'text-text-secondary/70';

  return (
    <td className="px-2 py-2 text-center">
      <span className={`inline-block min-w-[44px] px-1.5 py-1 ${className}`}>
        {value}
        {isHitTrue && <span className="ml-1 text-[11px]">✓</span>}
      </span>
    </td>
  );
}
