import { Link } from 'react-router-dom';
import {
  AI_ACTIVE,
  AI_RETIRED,
  AI_SHORT,
  aiSummaries,
  formatPercent,
  formatPnl,
  totalConfirmed,
  totalMatches,
  type AiSummary,
} from '../lib/data';

function PnlBadge({ pnl, size = 'md' }: { pnl: number; size?: 'sm' | 'md' | 'lg' }) {
  const tone =
    pnl > 0 ? 'text-turf' : pnl < 0 ? 'text-rose-300' : 'text-text-secondary';
  const sizeCls =
    size === 'lg'
      ? 'text-2xl font-bold tracking-tight'
      : size === 'sm'
        ? 'text-sm font-semibold tabular-nums'
        : 'text-base font-semibold tabular-nums';
  return (
    <span className={`${sizeCls} ${tone}`} style={{ fontVariantNumeric: 'tabular-nums' }}>
      {formatPnl(pnl)}
    </span>
  );
}

function MedalBadge({ rank, retired }: { rank: number; retired?: boolean }) {
  if (retired) {
    return (
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-elevated text-miss font-semibold text-sm border border-divider">
        ×
      </span>
    );
  }
  if (rank === 1) {
    return (
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-gold text-night font-bold text-lg shadow-gold">
        1
      </span>
    );
  }
  if (rank === 2) {
    return (
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#C0C7D2] text-night font-bold text-base">
        2
      </span>
    );
  }
  if (rank === 3) {
    return (
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#CD7F32] text-night font-bold text-base">
        3
      </span>
    );
  }
  return (
    <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-elevated text-muted font-semibold text-base border border-divider">
      {rank}
    </span>
  );
}

function ChampionCard({ s }: { s: AiSummary }) {
  return (
    <Link
      to={`/ai/${encodeURIComponent(s.ai)}`}
      className="relative overflow-hidden block rounded-2xl border-gold-hairline bg-gradient-to-br from-[#1c2742] to-[#0f1a2e] shadow-gold p-6 sm:p-8 group transition-transform duration-200 ease-soft hover:-translate-y-0.5"
    >
      {/* shimmer */}
      <span
        className="pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 bg-gradient-to-r from-transparent via-gold/25 to-transparent animate-shimmer"
        aria-hidden
      />
      <div className="relative flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <MedalBadge rank={1} />
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-gold/80 mb-1">
              CHAMPION · 现任冠军
            </div>
            <div className="text-2xl sm:text-3xl font-bold text-ink">{AI_SHORT[s.ai]}</div>
            <div className="text-xs text-muted mt-1">{s.ai}</div>
          </div>
        </div>
        <div className="flex items-end gap-6 sm:gap-10">
          <div className="text-right">
            <div className="text-[11px] tracking-widest text-muted">综合命中率</div>
            <div className="font-mono text-4xl sm:text-5xl font-bold text-gold leading-none mt-1">
              {formatPercent(s.hitRate)}
            </div>
            <div className="font-mono text-[11px] text-muted mt-2">
              命中 {s.totalHits} / {s.totalSlots}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] tracking-widest text-muted">模拟盈亏</div>
            <div className="leading-none mt-1">
              <PnlBadge pnl={s.officialPnl} size="lg" />
            </div>
            <div className="font-mono text-[11px] text-muted mt-2">每注 2 元 · 虚拟模拟</div>
          </div>
        </div>
      </div>
    </Link>
  );
}

function RankCard({ s }: { s: AiSummary }) {
  const noConfirmed = s.totalConfirmed === 0;
  return (
    <Link
      to={`/ai/${encodeURIComponent(s.ai)}`}
      className="rounded-xl bg-card-gradient border border-divider hover:border-gold/30 transition-colors duration-200 ease-soft shadow-card p-5 flex items-center gap-4 group"
    >
      <MedalBadge rank={s.rank} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-ink truncate group-hover:text-gold transition-colors">
            {AI_SHORT[s.ai]}
          </span>
          {noConfirmed && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-gold/30 text-gold/80 bg-gold-soft">
              新加入
            </span>
          )}
        </div>
        <div className="text-xs text-muted mt-0.5 truncate">{s.ai}</div>
      </div>
      <div className="text-right">
        <div className="font-mono text-xl font-bold text-ink leading-none">
          {noConfirmed ? '—' : formatPercent(s.hitRate)}
        </div>
        <div className="font-mono text-[11px] text-muted mt-1">
          {noConfirmed ? `参赛 ${s.participatedMatches} 场` : `命中 ${s.totalHits} / ${s.totalSlots}`}
        </div>
        <div className="mt-2 pt-2 border-t border-divider/60 flex items-center justify-end gap-2">
          <span className="text-[10px] tracking-widest text-muted">盈亏</span>
          <PnlBadge pnl={s.officialPnl} size="sm" />
        </div>
      </div>
    </Link>
  );
}

function RetiredCard({ s }: { s: AiSummary }) {
  return (
    <Link
      to={`/ai/${encodeURIComponent(s.ai)}`}
      className="rounded-xl border border-divider bg-deep/60 px-5 py-4 flex items-center gap-4 opacity-60 hover:opacity-90 transition-opacity"
    >
      <MedalBadge rank={s.rank} retired />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-miss truncate">{AI_SHORT[s.ai]}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-divider text-miss bg-white/[0.02]">
            已退赛
          </span>
        </div>
        <div className="text-[11px] text-miss/70 mt-0.5 truncate">{s.ai}</div>
      </div>
      <div className="text-right">
        <div className="font-mono text-base font-semibold text-miss leading-none">
          {formatPercent(s.hitRate)}
        </div>
        <div className="font-mono text-[11px] text-miss/70 mt-1">
          命中 {s.totalHits} / {s.totalSlots}
        </div>
        <div className="mt-2 pt-2 border-t border-divider/40 flex items-center justify-end gap-2 opacity-90">
          <span className="text-[10px] tracking-widest text-miss/70">历史盈亏</span>
          <PnlBadge pnl={s.officialPnl} size="sm" />
        </div>
      </div>
    </Link>
  );
}

export default function LeaderboardPage() {
  const activeList = aiSummaries.filter(s => !s.retired);
  const retiredList = aiSummaries.filter(s => s.retired);
  const champion = activeList[0];
  const rest = activeList.slice(1);

  return (
    <div className="space-y-10">
      <section className="text-center pt-2 pb-2 sm:pt-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-gold-soft border border-gold/30 text-gold text-[11px] tracking-[0.22em] uppercase mb-4">
          AI Prediction · Showdown
        </div>
        <h1 className="text-3xl sm:text-5xl font-bold tracking-tight text-ink">
          AI <span className="text-gold">赛事预测</span>大竞赛
        </h1>
        <p className="mt-3 text-sm sm:text-base text-muted max-w-2xl mx-auto">
          {AI_ACTIVE.length} 个活跃 AI（{AI_RETIRED.length} 已退赛），{totalConfirmed} 场已确认比赛，
          4 个预测维度，谁的"足球嗅觉"最敏锐？
        </p>
      </section>

      {champion && <ChampionCard s={champion} />}

      <section>
        <h2 className="text-sm tracking-[0.18em] uppercase text-muted mb-4">梯队榜单 · Lineup</h2>
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {rest.map(s => (
            <RankCard key={s.ai} s={s} />
          ))}
        </div>
      </section>

      {retiredList.length > 0 && (
        <section>
          <h2 className="text-sm tracking-[0.18em] uppercase text-muted mb-4">
            已退赛 · Retired
          </h2>
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {retiredList.map(s => (
              <RetiredCard key={s.ai} s={s} />
            ))}
          </div>
        </section>
      )}

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatBlock label="活跃 AI" value={`${AI_ACTIVE.length}`} unit="个" />
        <StatBlock label="已退赛 AI" value={`${AI_RETIRED.length}`} unit="个" />
        <StatBlock label="收录比赛" value={`${totalMatches}`} unit="场" />
        <StatBlock label="已确认比赛" value={`${totalConfirmed}`} unit="场" />
      </section>
    </div>
  );
}

function StatBlock({
  label,
  value,
  unit,
  hint,
}: {
  label: string;
  value: string;
  unit: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl bg-card-gradient border border-divider px-4 py-4">
      <div className="text-[11px] tracking-widest uppercase text-muted">{label}</div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="font-mono text-3xl font-bold text-ink">{value}</span>
        <span className="text-xs text-muted">{unit}</span>
      </div>
      {hint && <div className="text-[11px] text-muted mt-1 truncate">{hint}</div>}
    </div>
  );
}
