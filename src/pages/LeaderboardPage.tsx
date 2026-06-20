import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useDocumentMeta } from '../lib/useDocumentMeta';
import { supabase } from '../lib/supabase';
import {
  AI_ACTIVE,
  AI_RETIRED,
  AI_SHORT,
  aiSummaries,
  formatProfitRate,
  profitRateToneClass,
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
            <div className="text-[11px] tracking-widest text-muted">盈利率</div>
            <div className={`font-mono text-4xl sm:text-5xl font-bold leading-none mt-1 ${profitRateToneClass(s.hitRate)}`}>
              {formatProfitRate(s.hitRate)}
            </div>
            <div className="font-mono text-[11px] text-muted mt-2">
              参赛 {s.participatedMatches} 场
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
        <div className={`font-mono text-xl font-bold leading-none ${noConfirmed ? 'text-ink' : profitRateToneClass(s.hitRate)}`}>
          {noConfirmed ? '—' : formatProfitRate(s.hitRate)}
        </div>
        <div className="font-mono text-[11px] text-muted mt-1">
          {noConfirmed ? `参赛 ${s.participatedMatches} 场` : `参赛 ${s.participatedMatches} 场`}
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
          {formatProfitRate(s.hitRate)}
        </div>
        <div className="font-mono text-[11px] text-miss/70 mt-1">
          参赛 {s.participatedMatches} 场
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
  useDocumentMeta({
    title: '2026世界杯AI预测大竞赛 | 8个AI足球数据分析对比实验',
    description:
      '8个AI预测2026世界杯全部赛事，含胜平负、让球、比分、总进球、半全场五维度对比分析，AI预测分析逻辑与盈利率排行，足球数据可视化实验。',
  });
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

      <VisitCounter />
    </div>
  );
}

const VISIT_DATE_KEY = 'coze:lastVisitDate';

function todayString(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

async function fetchTotalVisits(): Promise<number | null> {
  const { data, error } = await supabase
    .from('site_visits')
    .select('total_visits')
    .eq('id', 1)
    .maybeSingle();
  if (error || !data) return null;
  const n = Number(data.total_visits);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

async function tryIncrementVisit(): Promise<number | null> {
  // 优先尝试 RPC（如果数据库部署了 increment_site_visit 函数，直接拿到原子结果）。
  const rpc = await supabase.rpc('increment_site_visit');
  if (!rpc.error && rpc.data != null) {
    const n = Number(rpc.data);
    if (Number.isFinite(n) && n >= 0) return n;
  }
  // 降级：先读后写。RLS 若禁止匿名 UPDATE，会失败但不会抛异常，前端继续显示读到的值。
  const current = await fetchTotalVisits();
  if (current === null) {
    // 表里还没有 id=1 的种子行：尝试 insert 一条 total_visits=1。
    const ins = await supabase
      .from('site_visits')
      .insert({ id: 1, total_visits: 1, updated_at: new Date().toISOString() })
      .select('total_visits')
      .maybeSingle();
    if (!ins.error && ins.data) {
      const n = Number(ins.data.total_visits);
      if (Number.isFinite(n) && n >= 0) return n;
    }
    return null;
  }
  const next = current + 1;
  const upd = await supabase
    .from('site_visits')
    .update({ total_visits: next, updated_at: new Date().toISOString() })
    .eq('id', 1)
    .select('total_visits')
    .maybeSingle();
  if (upd.error || !upd.data) {
    // 写失败：依然返回 current，UI 不再做 +1，避免本地虚高。
    return current;
  }
  const n = Number(upd.data.total_visits);
  return Number.isFinite(n) && n >= 0 ? n : current;
}

function VisitCounter() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let lastDate: string | null = null;
      try {
        lastDate =
          typeof window !== 'undefined'
            ? window.localStorage.getItem(VISIT_DATE_KEY)
            : null;
      } catch {
        lastDate = null;
      }
      const today = todayString();
      const isFirstToday = lastDate !== today;

      let total: number | null;
      if (isFirstToday) {
        total = await tryIncrementVisit();
        try {
          if (typeof window !== 'undefined') {
            window.localStorage.setItem(VISIT_DATE_KEY, today);
          }
        } catch {
          // 隐私模式：写入失败也不影响展示。
        }
      } else {
        total = await fetchTotalVisits();
      }

      if (!cancelled) setCount(total);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="rounded-xl border border-divider bg-card-gradient px-5 py-5 sm:px-6 sm:py-6">
      <div className="flex flex-col items-center justify-center gap-2 text-center">
        <span className="text-[11px] tracking-[0.3em] uppercase text-muted">Site Visits</span>
        <p className="flex flex-wrap items-baseline justify-center gap-x-2 gap-y-1 text-sm text-muted">
          <span>本站累计访问次数</span>
          {count === null ? (
            <span className="font-mono text-2xl font-bold text-muted">—</span>
          ) : (
            <span className="font-mono text-3xl font-bold tabular-nums text-gold sm:text-4xl">
              {count.toLocaleString('en-US')}
            </span>
          )}
          <span>次</span>
        </p>
        <span className="text-[11px] text-muted/80">
          数据来自数据库实时计数；同一设备同日多次访问只计 1 次。
        </span>
      </div>
    </section>
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
