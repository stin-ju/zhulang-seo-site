import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useDocumentMeta } from '../lib/useDocumentMeta';
import {
  AI_SHORT,
  BETTING_DIMENSIONS,
  bettingDates,
  bettingSummaries,
  chainBets,
  formatPnl,
  formatYuan,
  getAiDailyBreakdown,
  getBettingDailyByDate,
  getBettingTotals,
  getChainBetTotals,
  isRetiredAi,
  type AiName,
  type BettingDimensionKey,
  type BettingDailyEntry,
  type BettingSummaryEntry,
  type ChainBet,
  type ChainBetSelection,
  type ChainAiBets,
  type ChainBetDay,
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
    (sum, d) => sum + (s.dimensions[d.key]?.invest ?? 0),
    0
  );
  const hitsTotal = BETTING_DIMENSIONS.reduce(
    (sum, d) => sum + (s.dimensions[d.key]?.hits ?? 0),
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
            模拟净收益
          </div>
          <PnlText value={s.total_pnl} size="xl" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mt-6 pt-5 border-t border-gold/15 text-sm">
        <div>
          <div className="text-[11px] text-muted">虚拟投入</div>
          <div className="font-mono text-ink mt-0.5">{formatYuan(investTotal)}</div>
        </div>
        <div>
          <div className="text-[11px] text-muted">综合胜率</div>
          <div className="font-mono text-ink mt-0.5">{s.win_rate}</div>
        </div>
        <div>
          <div className="text-[11px] text-muted">命中次数</div>
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
    (sum, d) => sum + (s.dimensions[d.key]?.invest ?? 0),
    0
  );
  const hitsTotal = BETTING_DIMENSIONS.reduce(
    (sum, d) => sum + (s.dimensions[d.key]?.hits ?? 0),
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
        <span className="text-[11px] uppercase tracking-widest text-muted">模拟净收益</span>
        <PnlText value={s.total_pnl} size="lg" />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[11px] pt-3 border-t border-divider">
        <div>
          <div className="text-muted">虚拟投入</div>
          <div className="font-mono text-ink mt-0.5">{investTotal}</div>
        </div>
        <div>
          <div className="text-muted">胜率</div>
          <div className="font-mono text-ink mt-0.5">{s.win_rate}</div>
        </div>
        <div>
          <div className="text-muted">命中</div>
          <div className="font-mono text-ink mt-0.5">
            {hitsTotal}/{betsTotal}
          </div>
        </div>
      </div>
    </Link>
  );
}

function DailyTimeline() {
  const [showAll, setShowAll] = useState(false);
  const visibleDates = showAll ? bettingDates : bettingDates.slice(0, 1);
  const hasMore = bettingDates.length > 1;
  return (
    <div className="space-y-6">
      {visibleDates.map(date => {
        const rows = getBettingDailyByDate(date).filter(r => !isRetiredAi(r.ai));
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
              {rows.map(r => (
                <DailyRow key={r.ai} entry={r} dayMax={dayMax} />
              ))}
            </div>
          </article>
        );
      })}
      {hasMore && (
        <div className="flex justify-center pt-1">
          <button
            type="button"
            onClick={() => setShowAll(v => !v)}
            className="text-xs px-4 py-1.5 rounded-full border border-divider text-muted hover:text-gold hover:border-gold/40 transition-colors"
          >
            {showAll
              ? `收起（仅显示最新 1 天）`
              : `展开全部（共 ${bettingDates.length} 天，已隐藏 ${bettingDates.length - 1} 天）`}
          </button>
        </div>
      )}
    </div>
  );
}

export default function BettingPage() {
  useDocumentMeta({
    title: 'AI预测模拟盈亏对比 | 串关与单注数据 - 大竞赛',
    description:
      '8 个 AI 在 2026 世界杯模拟盈亏排行榜，每日总盈亏与胜率走势对比。',
  });
  const totals = getBettingTotals();
  const activeSummaries = bettingSummaries.filter(s => !isRetiredAi(s.ai));
  const champion = activeSummaries[0];
  const others = activeSummaries.slice(1);

  return (
    <div className="space-y-10">
      {/* Hero */}
      <header className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-gold" />
          <span className="uppercase tracking-widest">AI Forecast Scoreboard</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-ink">
          AI <span className="text-gold">模拟盈亏</span>对比
        </h1>
        <p className="text-sm text-muted max-w-2xl leading-relaxed">
          {bettingSummaries.length} 个 AI 在 {totals.totalBets} 次模拟下注（每次按 2 元为虚拟计算单位、累计虚拟投入{' '}
          {totals.totalInvest} 元）下的预测命中复盘。所有数据仅作 AI 预测能力评测使用，与任何真实彩票/投注无关。新加入的
          DeepSeek / 天工 / MiniMax 暂未参与本期模拟盈亏统计。
        </p>
      </header>

      {/* KPI strip */}
      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-divider bg-deep px-4 py-4">
          <div className="text-[11px] uppercase tracking-widest text-muted">虚拟投入</div>
          <div className="font-mono text-2xl font-bold text-ink mt-1">
            {totals.totalInvest}
            <span className="text-sm text-muted font-normal"> 元</span>
          </div>
          <div className="text-[11px] text-muted mt-1">{totals.totalBets} 次 × 2 元单位</div>
        </div>
        <div className="rounded-xl border border-divider bg-deep px-4 py-4">
          <div className="text-[11px] uppercase tracking-widest text-muted">虚拟返奖</div>
          <div className="font-mono text-2xl font-bold text-ink mt-1">
            {totals.totalReturn.toFixed(0)}
            <span className="text-sm text-muted font-normal"> 元</span>
          </div>
          <div className="text-[11px] text-muted mt-1">命中 {totals.totalHits} 次</div>
        </div>
        <div className="rounded-xl border border-divider bg-deep px-4 py-4">
          <div className="text-[11px] uppercase tracking-widest text-muted">模拟净收益</div>
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
          <h2 className="text-lg font-semibold text-ink">模拟盈亏排行榜</h2>
          <span className="text-xs text-muted">按模拟净收益倒序</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {champion ? (
            <div className="lg:col-span-3">
              <ChampionCard s={champion} />
            </div>
          ) : null}
          {others.map(s => (
            <StandardCard key={s.ai} s={s} />
          ))}
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

      {/* Chain bets recommendations */}
      <section>
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink">串关推荐明细</h2>
          <span className="text-xs text-muted">共 {chainBets.length} 个比赛日 · 7 AI × 3 串关组合</span>
        </div>
        <ChainBetsSection />
      </section>

      {/* Disclaimer */}
      <section
        role="note"
        aria-label="免责声明"
        className="rounded-2xl border-l-4 border-gold bg-gold-soft/40 px-5 py-4"
      >
        <div className="flex items-center gap-2 text-gold mb-2">
          <span className="inline-block h-2 w-2 rounded-full bg-gold" />
          <span className="text-xs uppercase tracking-widest font-semibold">免责声明</span>
        </div>
        <p className="text-[13px] leading-[1.7] text-ink/85">
          本站所有数据仅用于AI预测能力对比研究，每注2元为虚拟模拟计算单位，与任何真实彩票投注无关。足球赛事临场变量极多，赛果存在高度不确定性，请理性观赛、远离非法购彩。
        </p>
      </section>
    </div>
  );
}

// ===== Daily row（可点击展开维度详情）=====
const DAILY_DIMENSIONS = [
  { key: 'spf' as const, label: '胜平负' },
  { key: 'handicap' as const, label: '让球' },
  { key: 'score' as const, label: '比分' },
  { key: 'goals' as const, label: '总进球' },
  { key: 'half_full' as const, label: '半全场' },
  { key: 'chain' as const, label: '串关' },
];

function DailyRow({ entry, dayMax }: { entry: BettingDailyEntry; dayMax: number }) {
  const [open, setOpen] = useState(false);
  const ratio = Math.min(1, Math.abs(entry.daily_pnl) / dayMax);
  const positive = entry.daily_pnl > 0;
  const negative = entry.daily_pnl < 0;
  const breakdown = getAiDailyBreakdown(entry.ai, entry.date);
  return (
    <div className="hover:bg-white/[0.02] transition-colors">
      <div className="px-5 py-3 grid grid-cols-[140px_1fr_auto] items-center gap-4">
        <Link
          to={`/ai/${encodeURIComponent(entry.ai)}`}
          className="flex items-center gap-2 min-w-0 group"
        >
          <span className="text-ink font-medium truncate group-hover:text-gold transition-colors">
            {AI_SHORT[entry.ai as AiName] ?? entry.ai}
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
          <div className="mt-1.5 flex items-center justify-end text-[11px] text-muted font-mono">
            <span>胜率 {entry.win_rate}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          className="text-right shrink-0 min-w-[80px] flex items-center gap-1 justify-end group"
          aria-expanded={open}
          aria-label={open ? '收起详情' : '查看详情'}
        >
          <PnlText value={entry.daily_pnl} size="base" />
          <span className="text-[10px] text-muted group-hover:text-gold transition-colors">
            {open ? '▴' : '▾'}
          </span>
        </button>
      </div>
      {open && (
        <div className="bg-night/40 border-t border-divider/60 px-5 py-3">
          <div className="text-[11px] uppercase tracking-wider text-muted mb-2">
            维度盈亏拆解
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {DAILY_DIMENSIONS.map(dim => {
              const cell = entry[dim.key];
              const live = breakdown[dim.key];
              const invest = live?.invest ?? cell?.invest ?? 0;
              const hits = live?.hits ?? cell?.hits ?? 0;
              // 串关 pnl 优先使用 chainBets 实时累加，因为 betting_daily 表没有 chain_pnl 字段
              const pnl = dim.key === 'chain' ? (live?.pnl ?? 0) : (cell?.pnl ?? 0);
              const empty = invest === 0 && pnl === 0;
              return (
                <div
                  key={dim.key}
                  className="rounded-md border border-divider/60 bg-deep/40 px-3 py-2 flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="text-xs text-ink">{dim.label}</div>
                    <div className="text-[11px] text-muted font-mono">
                      投 {invest} · 中 {hits}
                    </div>
                  </div>
                  {empty ? (
                    <span className="text-xs text-muted">—</span>
                  ) : (
                    <PnlText value={pnl} size="sm" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ===== Chain bets section =====
function ChainBetsSection() {
  const totals = getChainBetTotals();
  // 过滤退赛 AI 后的天数
  const days = chainBets
    .map((d) => ({ ...d, ai_bets: d.ai_bets.filter((ab) => !isRetiredAi(ab.ai)) }))
    .filter((d) => d.ai_bets.length > 0);
  const [showAll, setShowAll] = useState(false);
  const visibleDays = showAll ? days : days.slice(0, 1);
  const hasMore = days.length > 1;
  return (
    <div className="space-y-5">
      {/* KPI top */}
      <div className="rounded-xl bg-deep ring-1 ring-divider px-5 py-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
          <ChainStat label="总推荐" value={totals.totalBets.toString()} sub={`${chainBets.length} 个比赛日`} />
          <ChainStat
            label="命中"
            value={totals.totalHits.toString()}
            sub={`${totals.totalBets - totals.totalHits} 未中`}
          />
          <ChainStat
            label="命中率"
            value={`${(totals.hitRate * 100).toFixed(1)}%`}
            tone={totals.hitRate >= 0.3 ? 'turf' : 'gold'}
          />
          <ChainStat
            label="模拟净收益"
            value={(totals.totalPnl >= 0 ? '+' : '') + totals.totalPnl.toFixed(2)}
            sub={`虚拟投入 ${totals.totalInvest.toFixed(0)} 元`}
            tone={totals.totalPnl >= 0 ? 'turf' : 'miss'}
          />
        </div>
      </div>

      {/* Day cards */}
      {visibleDays.map((day, idx) => (
        <ChainDayCard key={day.date} day={day} defaultOpen={idx === 0} />
      ))}

      {hasMore && (
        <div className="flex justify-center pt-1">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="text-xs px-4 py-1.5 rounded-full border border-divider text-muted hover:text-gold hover:border-gold/40 transition-colors"
          >
            {showAll
              ? `收起（仅显示最新 1 天）`
              : `展开全部（共 ${days.length} 天，已隐藏 ${days.length - 1} 天）`}
          </button>
        </div>
      )}
    </div>
  );
}

function ChainStat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'turf' | 'gold' | 'miss';
}) {
  const toneCls = tone === 'turf' ? 'text-turf' : tone === 'gold' ? 'text-gold' : tone === 'miss' ? 'text-miss' : 'text-ink';
  return (
    <div>
      <div className="text-[11px] uppercase tracking-widest text-muted mb-1">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${toneCls}`}>{value}</div>
      {sub ? <div className="text-[11px] text-muted mt-1">{sub}</div> : null}
    </div>
  );
}

function ChainDayCard({ day, defaultOpen = false }: { day: ChainBetDay; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const dayBets = day.ai_bets.flatMap((ab) => ab.bets);
  const dayHits = dayBets.filter((b) => b.hit).length;
  const dayPnl = dayBets.reduce((s, b) => s + b.pnl, 0);

  return (
    <div className="rounded-xl bg-deep ring-1 ring-divider overflow-hidden">
      {/* Day header (clickable) */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-baseline justify-between px-5 py-3 bg-elevated/40 border-b border-divider hover:bg-elevated/60 transition-colors text-left"
        aria-expanded={open}
      >
        <div className="flex items-baseline gap-3">
          <h3 className="text-base font-semibold text-ink">{day.date}</h3>
          <span className="text-xs text-muted">{day.matches.length} 场比赛</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted">命中</span>
          <span className="font-semibold text-ink tabular-nums">
            {dayHits}/{dayBets.length}
          </span>
          <span className={`font-semibold tabular-nums ${dayPnl >= 0 ? 'text-turf' : 'text-miss'}`}>
            {dayPnl >= 0 ? '+' : ''}
            {dayPnl.toFixed(2)}
          </span>
          <span className="text-muted ml-1">{open ? '收起 ▴' : '展开 ▾'}</span>
        </div>
      </button>

      {open && (
        <>
          {/* Match list strip */}
          <div className="px-5 py-2 text-[11px] text-muted border-b border-divider/50 flex flex-wrap gap-x-3 gap-y-1">
            <span className="text-muted">本日比赛：</span>
            {day.matches.map((mid) => (
              <span key={mid} className="tabular-nums text-ink/70">
                {mid}
              </span>
            ))}
          </div>

          {/* AI bet rows */}
          <div className="divide-y divide-divider">
            {day.ai_bets.map((ab) => (
              <AiChainBets key={ab.ai} aiBets={ab} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function AiChainBets({ aiBets }: { aiBets: ChainAiBets }) {
  const aiKey = aiBets.ai;
  const display = aiKey.startsWith('AI-') ? aiKey.slice(3) : aiKey;

  return (
    <div className="px-5 py-4">
      <div className="flex items-baseline justify-between mb-3">
        <Link to={`/ai/${encodeURIComponent(aiKey)}`} className="text-sm font-semibold text-ink hover:text-gold transition-colors">
          {display}
        </Link>
        <span className="text-[11px] text-muted">
          {aiBets.bets.filter((b) => b.hit).length}/{aiBets.bets.length} 命中
        </span>
      </div>
      <div className="grid md:grid-cols-3 gap-3">
        {aiBets.bets.map((bet, i) => (
          <ChainBetCard key={i} bet={bet} />
        ))}
      </div>
    </div>
  );
}

function ChainBetCard({ bet }: { bet: ChainBet }) {
  const hit = bet.hit;
  const pending = hit === null;
  const ringCls = hit === true ? 'ring-turf/60 bg-turf-soft/50' : 'ring-divider bg-night/40';
  const pnlCls = pending ? 'text-muted' : bet.pnl >= 0 ? 'text-turf' : 'text-miss';

  return (
    <div className={`rounded-lg ring-1 ${ringCls} p-3 space-y-2`}>
      {/* Header: type + odds + result */}
      <div className="flex items-center justify-between">
        <span className={`text-[11px] font-semibold tracking-wider px-2 py-0.5 rounded ${hit === true ? 'bg-turf/15 text-turf' : 'bg-divider/40 text-muted'}`}>
          {bet.type}
        </span>
        <span className="text-[11px] tabular-nums text-muted">@ {bet.odds.toFixed(2)}</span>
      </div>

      {/* Selections */}
      <div className="space-y-1">
        {bet.selections.map((sel, i) => (
          <ChainSelectionLine key={i} sel={sel} />
        ))}
      </div>

      {/* Footer: result + pnl */}
      <div className="flex items-center justify-between pt-1.5 border-t border-divider/50">
        <span className={`text-[11px] font-semibold ${hit === true ? 'text-turf' : 'text-miss'}`}>
          {hit === true ? '✓ 命中' : pending ? '○ 待定' : '♡ 未中'}
        </span>
        <span className={`text-sm font-bold tabular-nums ${pnlCls}`}>
          {pending ? '—' : `${bet.pnl >= 0 ? '+' : ''}${bet.pnl.toFixed(2)}`}
        </span>
      </div>
    </div>
  );
}

function ChainSelectionLine({ sel }: { sel: ChainBetSelection }) {
  const hitMark = sel.hit;
  const pending = hitMark === null;
  const teams = sel.teams;
  const dim = sel.dimension;
  const pred = sel.prediction;

  return (
    <div className="flex items-baseline justify-between gap-2 text-[12px]">
      <div className="min-w-0 flex-1 truncate text-ink/85">
        <span className="text-muted text-[10px] mr-1">{sel.match_id}</span>
        <span className="truncate">{teams}</span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-muted text-[10px]">{dim}</span>
        <span className="font-semibold text-ink tabular-nums">{pred}</span>
        <span className={hitMark === true ? 'text-turf' : pending ? 'text-muted' : 'text-miss'}>
          {hitMark === true ? '✓' : pending ? '○' : '♡'}
        </span>
      </div>
    </div>
  );
}
