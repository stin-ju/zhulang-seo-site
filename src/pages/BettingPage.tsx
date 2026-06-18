import { Link } from 'react-router-dom';
import {
  AI_SHORT,
  BETTING_DIMENSIONS,
  bettingDates,
  bettingSummaries,
  formatPnl,
  formatYuan,
  getBettingDailyByDate,
  getBettingTotals,
  type AiName,
  type BettingDimensionKey,
  type BettingSummaryEntry,
} from '../lib/data';

function PnlText({
  value,
  size = 'base',
  showPlus = true,
}: {
  value: number;
  size?: 'sm' | 'base' | 'lg' | 'xl';
  showPlus?: boolean;
}) {
  const cls =
    value > 0
      ? 'text-turf'
      : value < 0
      ? 'text-[#F87171]'
      : 'text-muted';
  const sizeCls =
    size === 'xl'
      ? 'text-3xl sm:text-4xl font-bold'
      : size === 'lg'
      ? 'text-xl font-bold'
      : size === 'sm'
      ? 'text-sm'
      : 'text-base font-semibold';
  const display = value === 0 ? '0.0' : showPlus ? formatPnl(value) : value.toFixed(1);
  return <span className={`font-mono ${cls} ${sizeCls}`}>{display}</span>;
}

function MedalBadge({ rank }: { rank: number }) {
  if (rank === 1) {
    return (
      <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gold text-night font-bold text-sm shadow-gold">
        1
      </span>
    );
  }
  if (rank === 2) {
    return (
      <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#C0C7D2] text-night font-bold text-sm">
        2
      </span>
    );
  }
  if (rank === 3) {
    return (
      <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#CD7F32] text-night font-bold text-sm">
        3
      </span>
    );
  }
  return (
    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-elevated text-muted font-semibold text-sm border border-divider">
      {rank}
    </span>
  );
}

function ChampionCard({ s }: { s: BettingSummaryEntry }) {
  const investTotal = BETTING_DIMENSIONS.reduce(
    (sum, d) => sum + s.dimensions[d.key].invest,
    0
  );
  const hitsTotal = BETTING_DIMENSIONS.reduce(
    (sum, d) => sum + s.dimensions[d.key].hits,
    0
  );
  const betsTotal = investTotal / 2;

  return (
    <Link
      to={`/ai/${encodeURIComponent(s.ai)}`}
      className="relative overflow-hidden block rounded-2xl border-gold-hairline bg-gradient-to-br from-[#1c2742] to-[#0f1a2e] shadow-gold p-6 sm:p-8 group transition-transform duration-200 ease-soft hover:-translate-y-0.5"
    >
      <span
        className="pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 bg-gradient-to-r from-transparent via-gold/25 to-transparent animate-shimmer"
        aria-hidden
      />
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-gold/80">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <path
              d="M7 1l1.5 4 4.2.4-3.2 2.9 1 4.2L7 10.4 3.5 12.5l1-4.2L1.3 5.4 5.5 5z"
              fill="currentColor"
            />
          </svg>
          <span>盈利冠军</span>
        </div>
        <MedalBadge rank={1} />
      </div>
      <div className="flex items-end justify-between gap-6">
        <div className="min-w-0">
          <div className="text-2xl sm:text-3xl font-bold text-ink truncate">
            {AI_SHORT[s.ai as AiName] ?? s.ai}
          </div>
          <div className="text-xs text-muted mt-1 truncate">{s.ai}</div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-[11px] uppercase tracking-widest text-gold/80 mb-0.5">
            总盈亏
          </div>
          <PnlText value={s.total_pnl} size="xl" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mt-6 pt-5 border-t border-gold/15 text-sm">
        <div>
          <div className="text-[11px] text-muted">总投入</div>
          <div className="font-mono text-ink mt-0.5">{formatYuan(investTotal)}</div>
        </div>
        <div>
          <div className="text-[11px] text-muted">综合胜率</div>
          <div className="font-mono text-ink mt-0.5">{s.win_rate}</div>
        </div>
        <div>
          <div className="text-[11px] text-muted">中奖注</div>
          <div className="font-mono text-ink mt-0.5">
            {hitsTotal}
            <span className="text-muted text-xs"> / {betsTotal}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

function StandardCard({ s }: { s: BettingSummaryEntry }) {
  const investTotal = BETTING_DIMENSIONS.reduce(
    (sum, d) => sum + s.dimensions[d.key].invest,
    0
  );
  const hitsTotal = BETTING_DIMENSIONS.reduce(
    (sum, d) => sum + s.dimensions[d.key].hits,
    0
  );
  const betsTotal = investTotal / 2;

  return (
    <Link
      to={`/ai/${encodeURIComponent(s.ai)}`}
      className="block rounded-2xl border border-divider bg-deep p-5 transition-colors duration-200 ease-soft hover:border-gold/30 hover:bg-elevated/50 group"
    >
      <div className="flex items-center gap-3 mb-4">
        <MedalBadge rank={s.rank} />
        <div className="min-w-0 flex-1">
          <div className="text-base font-semibold text-ink truncate group-hover:text-gold transition-colors">
            {AI_SHORT[s.ai as AiName] ?? s.ai}
          </div>
          <div className="text-[11px] text-muted truncate">{s.ai}</div>
        </div>
      </div>
      <div className="flex items-baseline justify-between mb-3">
        <span className="text-[11px] uppercase tracking-widest text-muted">总盈亏</span>
        <PnlText value={s.total_pnl} size="lg" />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[11px] pt-3 border-t border-divider">
        <div>
          <div className="text-muted">投入</div>
          <div className="font-mono text-ink mt-0.5">{investTotal}</div>
        </div>
        <div>
          <div className="text-muted">胜率</div>
          <div className="font-mono text-ink mt-0.5">{s.win_rate}</div>
        </div>
        <div>
          <div className="text-muted">中奖</div>
          <div className="font-mono text-ink mt-0.5">
            {hitsTotal}/{betsTotal}
          </div>
        </div>
      </div>
    </Link>
  );
}

function DimensionTable() {
  const sorted = bettingSummaries;
  const dimMaxAbs: Record<BettingDimensionKey, number> = {
    spf: 0,
    handicap: 0,
    score: 0,
    goals: 0,
    half_full: 0,
  };
  for (const s of sorted) {
    for (const d of BETTING_DIMENSIONS) {
      const a = Math.abs(s.dimensions[d.key].pnl);
      if (a > dimMaxAbs[d.key]) dimMaxAbs[d.key] = a;
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-elevated text-[11px] uppercase tracking-wider text-muted">
            <th className="text-left px-4 py-3 font-medium w-[170px]">AI 模型</th>
            {BETTING_DIMENSIONS.map(d => (
              <th key={d.key} className="text-center px-3 py-3 font-medium">
                {d.label}
              </th>
            ))}
            <th className="text-center px-4 py-3 font-medium w-[120px]">合计</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(s => (
            <tr
              key={s.ai}
              className="border-t border-divider hover:bg-white/[0.02] transition-colors"
            >
              <td className="px-4 py-3 align-middle">
                <Link
                  to={`/ai/${encodeURIComponent(s.ai)}`}
                  className="flex items-center gap-2 group"
                >
                  <MedalBadge rank={s.rank} />
                  <span className="text-ink font-medium group-hover:text-gold transition-colors">
                    {AI_SHORT[s.ai as AiName] ?? s.ai}
                  </span>
                </Link>
              </td>
              {BETTING_DIMENSIONS.map(d => {
                const stat = s.dimensions[d.key];
                const max = dimMaxAbs[d.key] || 1;
                const ratio = Math.min(1, Math.abs(stat.pnl) / max);
                const positive = stat.pnl > 0;
                const negative = stat.pnl < 0;
                return (
                  <td key={d.key} className="px-3 py-3 align-middle">
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-muted font-mono">
                          {stat.hits}/{stat.invest / 2}
                        </span>
                        <PnlText value={stat.pnl} size="sm" />
                      </div>
                      <div className="relative h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                        <div
                          className={`absolute inset-y-0 ${
                            positive
                              ? 'left-1/2 bg-turf/70'
                              : negative
                              ? 'right-1/2 bg-[#F87171]/70'
                              : ''
                          }`}
                          style={{ width: `${ratio * 50}%` }}
                        />
                        <div className="absolute inset-y-0 left-1/2 w-px bg-divider/80" />
                      </div>
                    </div>
                  </td>
                );
              })}
              <td className="px-4 py-3 align-middle text-center">
                <PnlText value={s.total_pnl} size="base" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DailyTimeline() {
  return (
    <div className="space-y-6">
      {bettingDates.map(date => {
        const rows = getBettingDailyByDate(date);
        const dayMax = rows.reduce(
          (m, r) => Math.max(m, Math.abs(r.daily_pnl)),
          1
        );
        return (
          <article key={date} className="rounded-2xl border border-divider bg-deep">
            <header className="px-5 py-3 border-b border-divider flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-gold" />
                <h3 className="text-sm font-semibold text-ink">{date}</h3>
              </div>
              <span className="text-[11px] text-muted">
                当日最佳：
                <span className="text-turf font-mono ml-1">
                  {AI_SHORT[rows[0]?.ai as AiName] ?? rows[0]?.ai}
                </span>
                <span className="text-turf font-mono ml-1">
                  {formatPnl(rows[0]?.daily_pnl ?? 0)}
                </span>
              </span>
            </header>
            <div className="divide-y divide-divider">
              {rows.map(r => {
                const ratio = Math.min(1, Math.abs(r.daily_pnl) / dayMax);
                const positive = r.daily_pnl > 0;
                const negative = r.daily_pnl < 0;
                const investTotal = BETTING_DIMENSIONS.reduce(
                  (sum, d) => sum + r[d.key].invest,
                  0
                );
                return (
                  <div
                    key={r.ai}
                    className="px-5 py-3 grid grid-cols-[140px_1fr_auto] items-center gap-4 hover:bg-white/[0.02] transition-colors"
                  >
                    <Link
                      to={`/ai/${encodeURIComponent(r.ai)}`}
                      className="flex items-center gap-2 min-w-0 group"
                    >
                      <span className="text-ink font-medium truncate group-hover:text-gold transition-colors">
                        {AI_SHORT[r.ai as AiName] ?? r.ai}
                      </span>
                    </Link>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-1/2 w-px bg-divider/70" />
                      <div className="relative h-2 rounded-full bg-white/[0.04] overflow-hidden">
                        {positive && (
                          <div
                            className="absolute inset-y-0 left-1/2 bg-turf/70 rounded-r-full"
                            style={{ width: `${ratio * 50}%` }}
                          />
                        )}
                        {negative && (
                          <div
                            className="absolute inset-y-0 right-1/2 bg-[#F87171]/70 rounded-l-full"
                            style={{ width: `${ratio * 50}%` }}
                          />
                        )}
                      </div>
                      <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted font-mono">
                        <span>投入 {investTotal}</span>
                        <span>胜率 {r.win_rate}</span>
                      </div>
                    </div>
                    <div className="text-right shrink-0 min-w-[80px]">
                      <PnlText value={r.daily_pnl} size="base" />
                      <div className="text-[10px] text-muted mt-0.5">
                        排名变化 {r.rank_change}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export default function BettingPage() {
  const totals = getBettingTotals();
  const champion = bettingSummaries[0];
  const others = bettingSummaries.slice(1);

  return (
    <div className="space-y-10">
      {/* Hero */}
      <header className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-gold" />
          <span className="uppercase tracking-widest">Simulated Betting Arena</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-ink">
          模拟<span className="text-gold">投注</span>盈亏对比
        </h1>
        <p className="text-sm text-muted max-w-2xl leading-relaxed">
          {bettingSummaries.length} 个 AI 在 {totals.totalBets} 注模拟下注（每注固定 2 元、共投入{' '}
          {totals.totalInvest} 元）的真实盈亏复盘。仅作 AI 预测能力评测，与真实投注无关。新加入的
          DeepSeek / 天工 / MiniMax 暂未参与本期投注挑战。
        </p>
      </header>

      {/* KPI strip */}
      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-divider bg-deep px-4 py-4">
          <div className="text-[11px] uppercase tracking-widest text-muted">总投入</div>
          <div className="font-mono text-2xl font-bold text-ink mt-1">
            {totals.totalInvest}
            <span className="text-sm text-muted font-normal"> 元</span>
          </div>
          <div className="text-[11px] text-muted mt-1">{totals.totalBets} 注 × 2 元</div>
        </div>
        <div className="rounded-xl border border-divider bg-deep px-4 py-4">
          <div className="text-[11px] uppercase tracking-widest text-muted">总返奖</div>
          <div className="font-mono text-2xl font-bold text-ink mt-1">
            {totals.totalReturn.toFixed(0)}
            <span className="text-sm text-muted font-normal"> 元</span>
          </div>
          <div className="text-[11px] text-muted mt-1">中奖 {totals.totalHits} 注</div>
        </div>
        <div className="rounded-xl border border-divider bg-deep px-4 py-4">
          <div className="text-[11px] uppercase tracking-widest text-muted">总盈亏</div>
          <div className="mt-1">
            <PnlText value={totals.totalPnl} size="xl" />
            <span className="text-sm text-muted font-normal"> 元</span>
          </div>
          <div className="text-[11px] text-muted mt-1">
            综合命中 {((totals.totalHits / totals.totalBets) * 100).toFixed(1)}%
          </div>
        </div>
        <div className="rounded-xl border-gold-hairline bg-gold-soft px-4 py-4">
          <div className="text-[11px] uppercase tracking-widest text-gold/80">盈利冠军</div>
          <div className="font-bold text-xl text-gold mt-1 truncate">
            {AI_SHORT[champion.ai as AiName] ?? champion.ai}
          </div>
          <div className="text-[11px] text-gold/70 mt-1 font-mono">
            {formatPnl(champion.total_pnl)} 元
          </div>
        </div>
      </section>

      {/* Leaderboard */}
      <section>
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink">投注盈亏排行榜</h2>
          <span className="text-xs text-muted">按总盈亏倒序</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-3">
            <ChampionCard s={champion} />
          </div>
          {others.map(s => (
            <StandardCard key={s.ai} s={s} />
          ))}
        </div>
      </section>

      {/* Per-dimension comparison */}
      <section>
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink">分维度盈亏对比</h2>
          <span className="text-xs text-muted">
            5 个维度：胜平负 / 让球 / 比分 / 总进球 / 半全场
          </span>
        </div>
        <div className="rounded-2xl border border-divider bg-deep overflow-hidden">
          <DimensionTable />
        </div>
        <div className="flex items-center gap-4 text-[11px] text-muted mt-3">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-3 rounded bg-turf/70" /> 盈利
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-3 rounded bg-[#F87171]/70" /> 亏损
          </span>
          <span>条形长度反映该维度上各 AI 间的相对盈亏</span>
        </div>
      </section>

      {/* Daily timeline */}
      <section>
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink">每日盈亏走势</h2>
          <span className="text-xs text-muted">共 {bettingDates.length} 个比赛日</span>
        </div>
        <DailyTimeline />
      </section>
    </div>
  );
}
