import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useDocumentMeta } from '../lib/useDocumentMeta';
import {
  matches,
  AI_LIST,
  AI_SHORT,
  isRetiredAi,
  formatHandicap,
  formatPnl,
  formatYuan,
  formatPercent,
  isoToCnDate,
  chainBets,
  getChainBetTotals,
  getChainBetsForAi,
  type MatchView,
  type Prediction,
  type ChainBet,
  type ChainBetSelection,
  type ChainAiBets,
  type ChainBetDay,
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
  useDocumentMeta({
    title: '世界杯赛事AI预测对比 | 8个AI胜平负让球分析 - 大竞赛',
    description:
      '逐场对比 8 个 AI 对 2026 世界杯赛事的胜平负、让球、比分、总进球、半全场预测与命中表现，含每日串关推荐与分析逻辑跳转。',
  });
  // ---- top tab ----
  const [tab, setTab] = useState<'matches' | 'chains'>('matches');

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

  // ---- expand state: default open every 待比赛 match, collapse all 已确认 ones ----
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const s = new Set<string>();
    for (const m of matches) {
      if (m.status === '待比赛') s.add(m.id);
    }
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

        {/* Tab switcher */}
        <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-divider bg-deep/70 p-1.5 backdrop-blur">
          {([
            { key: 'matches', label: '比赛日程', sub: `${matches.length} 场` },
            { key: 'chains', label: '串关推荐', sub: `${chainBets.length} 个比赛日` },
          ] as const).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                tab === t.key
                  ? 'bg-gold/15 text-gold ring-1 ring-gold/40 shadow-[0_0_0_1px_rgba(245,194,66,0.15)]'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <span>{t.label}</span>
              <span
                className={`text-[10px] tabular-nums ${
                  tab === t.key ? 'text-gold/80' : 'text-text-secondary/70'
                }`}
              >
                {t.sub}
              </span>
            </button>
          ))}
        </div>

        {tab === 'matches' && (
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
        )}
      </header>

      {tab === 'matches' ? (
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
      ) : (
        <ChainTab />
      )}
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

  const matchDate = isoToCnDate(match.time || '');

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
            <th className="px-2 py-2 text-center font-medium">串关</th>
            <th className="px-2 py-2 text-center font-medium">分析</th>
            <th className="pl-2 py-2 text-center font-medium">命中</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-divider/40">
          {rows.map(({ ai, pred }) => {
            const retired = isRetiredAi(ai);
            const short = AI_SHORT[ai] ?? ai;
            const aiSlug = encodeURIComponent(ai);

            if (!pred) {
              return (
                <tr key={ai} className="text-text-secondary/60">
                  <td className="py-2 pr-3">
                    <span className="font-medium">{short}</span>
                    {retired && (
                      <span className="ml-2 text-[10px] text-text-secondary">已退赛</span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-center text-xs text-text-secondary/50" colSpan={DIM_LABELS.length + 3}>
                    本场未参赛
                  </td>
                </tr>
              );
            }

            const isBest =
              typeof pred.total_hits === 'number' && pred.total_hits > 0 && pred.total_hits === bestHits;

            const hasChainForDay = matchDate
              ? getChainBetsForAi(ai).days.some((d) => d.date === matchDate && d.bets.length > 0)
              : false;

            return (
              <tr key={ai} className={retired ? 'opacity-60' : ''}>
                <td className="py-2 pr-3">
                  <Link
                    to={`/ai/${aiSlug}`}
                    className={`font-medium transition-colors hover:text-gold ${isBest ? 'text-gold' : 'text-text-primary'}`}
                  >
                    {short}
                  </Link>
                  {retired && <span className="ml-2 text-[10px] text-text-secondary">退赛</span>}
                </td>
                {DIM_LABELS.map((d) => (
                  <DimCell key={d.key} pred={pred} dim={d} />
                ))}
                <td className="px-2 py-2 text-center">
                  {retired || !hasChainForDay ? (
                    <span className="text-text-secondary/50">—</span>
                  ) : (
                    <Link
                      to={`/ai/${aiSlug}#chain`}
                      className="inline-flex items-center rounded-md border border-gold/30 bg-gold-soft px-2 py-0.5 text-[11px] font-medium text-gold transition-colors hover:border-gold/60 hover:bg-gold/15"
                    >
                      串关
                    </Link>
                  )}
                </td>
                <td className="px-2 py-2 text-center">
                  {retired ? (
                    <span className="text-text-secondary/50">—</span>
                  ) : (
                    <Link
                      to={`/ai/${aiSlug}#match-${encodeURIComponent(match.id)}`}
                      className="inline-flex items-center rounded-md border border-turf/30 bg-turf-soft px-2 py-0.5 text-[11px] font-medium text-turf transition-colors hover:border-turf/60 hover:bg-turf/15"
                    >
                      详情
                    </Link>
                  )}
                </td>
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

// ===========================================================================
// 串关推荐 Tab
// ===========================================================================

function ChainTab() {
  const totals = getChainBetTotals();
  const days = chainBets; // already sorted desc in data.ts

  if (days.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-divider bg-deep/40 p-8 text-center text-sm text-text-secondary">
        暂无串关推荐数据。
      </section>
    );
  }

  return (
    <section className="space-y-5">
      {/* Totals strip */}
      <div className="grid gap-3 rounded-xl border border-divider bg-deep/70 p-4 backdrop-blur sm:grid-cols-4">
        <ChainStat label="总推荐" value={totals.totalBets.toString()} sub={`${days.length} 个比赛日`} />
        <ChainStat label="命中次数" value={totals.totalHits.toString()} sub={formatPercent(totals.hitRate)} accent="turf" />
        <ChainStat
          label="净盈亏"
          value={formatPnl(totals.totalPnl)}
          sub={formatYuan(totals.totalPnl)}
          accent={totals.totalPnl >= 0 ? 'turf' : 'red'}
        />
        <ChainStat label="虚拟投入" value={`${totals.totalInvest}`} sub="每注 2 元 × 总推荐" />
      </div>

      <div className="space-y-3">
        {days.map((day) => (
          <ChainDayCollapse key={day.date} day={day} />
        ))}
      </div>
    </section>
  );
}

function ChainStat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: 'turf' | 'red';
}) {
  const accentClass = accent === 'turf' ? 'text-turf' : accent === 'red' ? 'text-red-400' : 'text-text-primary';
  return (
    <div className="rounded-lg border border-divider/60 bg-night/40 px-4 py-3">
      <div className="text-xs uppercase tracking-wider text-text-secondary">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${accentClass}`}>{value}</div>
      {sub ? <div className="mt-0.5 text-xs text-text-secondary">{sub}</div> : null}
    </div>
  );
}

function ChainDayCollapse({ day }: { day: ChainBetDay }) {
  // collapse the entire day; default close
  const [openDay, setOpenDay] = useState<boolean>(false);

  const dayBets = day.ai_bets.reduce((sum, ab) => sum + ab.bets.length, 0);
  const dayHits = day.ai_bets.reduce(
    (sum, ab) => sum + ab.bets.filter((b) => b.hit).length,
    0,
  );
  const dayPnl = day.ai_bets.reduce(
    (sum, ab) => sum + ab.bets.reduce((s, b) => s + b.pnl, 0),
    0,
  );

  return (
    <article
      className={`rounded-xl border bg-deep/70 backdrop-blur transition-colors ${
        openDay
          ? 'border-gold/40 shadow-[0_0_0_1px_rgba(245,194,66,0.15)]'
          : 'border-divider hover:border-gold/30'
      }`}
    >
      <button
        type="button"
        onClick={() => setOpenDay((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-base font-bold transition-colors ${
            openDay ? 'border-gold/50 bg-gold/10 text-gold' : 'border-divider text-text-secondary'
          }`}
          aria-label={openDay ? '折叠' : '展开'}
        >
          {openDay ? '−' : '+'}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-base font-semibold text-text-primary tabular-nums sm:text-lg">{day.date}</span>
            {day.matches.length > 0 ? (
              <span className="text-xs text-text-secondary">参考赛事：{day.matches.join('、')}</span>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
          <span>
            参与 <span className="font-semibold text-text-primary">{day.ai_bets.length}</span> AI
          </span>
          <span>
            推荐 <span className="font-semibold text-text-primary">{dayBets}</span>
          </span>
          <span>
            命中 <span className="font-semibold text-turf">{dayHits}</span>
          </span>
          <span>
            盈亏{' '}
            <span className={`font-semibold tabular-nums ${dayPnl >= 0 ? 'text-turf' : 'text-red-400'}`}>
              {formatPnl(dayPnl)}
            </span>
          </span>
        </div>
      </button>

      {openDay && (
        <div className="space-y-2 border-t border-divider/60 bg-night/40 px-4 pb-4 pt-3">
          {day.ai_bets.map((ab) => (
            <ChainAiCollapse key={ab.ai} aiBets={ab} />
          ))}
        </div>
      )}
    </article>
  );
}

function ChainAiCollapse({ aiBets }: { aiBets: ChainAiBets }) {
  const [open, setOpen] = useState<boolean>(false);
  const total = aiBets.bets.length;
  const hits = aiBets.bets.filter((b) => b.hit).length;
  const pnl = aiBets.bets.reduce((sum, b) => sum + b.pnl, 0);
  const retired = isRetiredAi(aiBets.ai);
  const short = (AI_SHORT as Record<string, string>)[aiBets.ai] ?? aiBets.ai.replace(/^AI-/, '');

  return (
    <div
      className={`rounded-lg border bg-night/30 transition-colors ${
        open ? 'border-gold/40' : 'border-divider/70'
      } ${retired ? 'opacity-70' : ''}`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
      >
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-sm font-bold transition-colors ${
            open ? 'border-gold/50 bg-gold/10 text-gold' : 'border-divider text-text-secondary'
          }`}
        >
          {open ? '−' : '+'}
        </span>
        <Link
          to={`/ai/${encodeURIComponent(aiBets.ai)}`}
          onClick={(e) => e.stopPropagation()}
          className="text-sm font-semibold text-text-primary transition-colors hover:text-gold"
        >
          {short}
        </Link>
        {retired && <span className="text-[10px] text-text-secondary">已退赛</span>}

        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
          <span>
            <span className="font-semibold text-turf">{hits}</span>
            <span className="text-text-secondary/70"> / {total}</span>
            <span className="ml-1 text-text-secondary/70">命中</span>
          </span>
          <span className="tabular-nums">
            <span className={`font-semibold ${pnl >= 0 ? 'text-turf' : 'text-red-400'}`}>{formatPnl(pnl)}</span>
            <span className="ml-1 text-text-secondary/70">({formatYuan(pnl)})</span>
          </span>
        </div>
      </button>

      {open && (
        <div className="grid gap-3 border-t border-divider/60 px-3 py-3 md:grid-cols-3">
          {aiBets.bets.map((bet, i) => (
            <ChainBetMiniCard key={`${bet.type}-${i}`} bet={bet} />
          ))}
        </div>
      )}
    </div>
  );
}

function ChainBetMiniCard({ bet }: { bet: ChainBet }) {
  const hit = bet.hit;
  const pending = hit === null;
  return (
    <div
      className={`flex h-full flex-col gap-3 rounded-md border px-3.5 py-3 transition-colors ${
        hit === true
          ? 'border-gold/55 bg-gold-soft/40 shadow-[0_0_0_1px_rgba(245,194,66,0.18)_inset]'
          : 'border-divider bg-night/30'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-0.5">
          <div className={`text-sm font-semibold ${hit === true ? 'text-gold' : 'text-text-secondary'}`}>{bet.type}</div>
          <div className="text-[11px] tabular-nums text-text-secondary">赔率 {bet.odds.toFixed(2)} × 2 元</div>
        </div>
        <span
          className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
            hit === true
              ? 'bg-turf text-night'
              : pending
                ? 'bg-night/60 text-text-secondary border border-divider'
                : 'bg-divider text-text-secondary'
          }`}
          aria-label={hit === true ? '命中' : pending ? '待定' : '未命中'}
        >
          {hit === true ? '✓' : pending ? '○' : '♡'}
        </span>
      </div>

      <ul className="space-y-1.5">
        {bet.selections.map((s, idx) => (
          <ChainSelectionMini key={idx} selection={s} />
        ))}
      </ul>

      <div className="mt-auto flex items-center justify-between border-t border-divider/60 pt-2 text-xs">
        <span
          className={`rounded px-2 py-0.5 text-[11px] font-medium ${
            hit === true ? 'bg-turf-soft text-turf' : 'bg-night/60 text-text-secondary'
          }`}
        >
          {hit === true ? '命中' : pending ? '○ 待定' : '未中'}
        </span>
        <span
          className={`tabular-nums font-semibold ${
            pending ? 'text-text-secondary' : bet.pnl >= 0 ? 'text-turf' : 'text-red-400'
          }`}
        >
          {pending ? '—' : `${formatPnl(bet.pnl)} (${formatYuan(bet.pnl)})`}
        </span>
      </div>
    </div>
  );
}

function ChainSelectionMini({ selection }: { selection: ChainBetSelection }) {
  const hit = selection.hit;
  const pending = hit === null;
  const ok = hit === true;
  return (
    <li className="flex items-start gap-2 text-[11px] leading-snug text-text-secondary">
      <span
        className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[10px] font-bold ${
          ok
            ? 'bg-turf-soft text-turf'
            : pending
              ? 'bg-night/60 text-text-secondary'
              : 'bg-night/60 text-text-secondary'
        }`}
        aria-label={ok ? '命中' : pending ? '待定' : '未命中'}
      >
        {ok ? '✓' : pending ? '○' : '♡'}
      </span>
      <span className="flex-1">
        <span className={ok ? 'text-text-primary' : ''}>{selection.teams}</span>
        <span className="mx-1 text-text-secondary/60">·</span>
        <span className="text-text-secondary">
          {selection.dimension}
          <span className="ml-1 text-text-primary">{selection.prediction}</span>
        </span>
      </span>
    </li>
  );
}
