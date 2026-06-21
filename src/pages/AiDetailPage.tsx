import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useDocumentMeta, SITE_ORIGIN } from '../lib/useDocumentMeta';
import {
  AI_LIST,
  AI_SHORT,
  DIMENSIONS,
  formatPercent,
  formatPnl,
  formatProfitRate,
  formatYuan,
  getAiMatches,
  getAiSummary,
  getChainBetsForAi,
  isoToCnDate,
  matches as allMatches,
  profitRateToneClass,
  type AiMatchRow,
  type ChainBet,
  type ChainBetSelection,
  type DimensionKey,
  type Prediction,
} from '../lib/data';

function dimValue(p: Prediction, key: DimensionKey): string | number {
  switch (key) {
    case 'hit_handicap':
      return p.handicap_spf;
    case 'hit_score':
      return p.score;
    case 'hit_goals':
      return p.goals;
    case 'hit_half':
      return p.half_full;
  }
}

export default function AiDetailPage() {
  const { name } = useParams<{ name: string }>();
  const decoded = name ? decodeURIComponent(name) : '';
  const summary = getAiSummary(decoded);
  const location = useLocation();

  const aiShort = summary ? AI_SHORT[summary.ai] : '';

  const jsonLd = useMemo(() => {
    if (!summary) return undefined;
    return {
      '@context': 'https://schema.org',
      '@type': 'Person',
      name: AI_SHORT[summary.ai] ?? summary.ai,
      alternateName: summary.ai,
      description: `${aiShort} 在 2026 世界杯 AI 预测大竞赛中的预测分析、盈利率与模拟盈亏明细。当前排名第 ${summary.rank} 名，参赛 ${summary.participatedMatches} 场。`,
      jobTitle: '足球数据分析AI',
      url: `${SITE_ORIGIN}/ai/${encodeURIComponent(summary.ai)}`,
    };
  }, [summary, aiShort]);

  useDocumentMeta({
    title: summary
      ? `${aiShort} 2026世界杯预测分析 | 盈利率与模拟盈亏 - 大竞赛`
      : 'AI 预测分析 | 盈利率与模拟盈亏 - 大竞赛',
    description: summary
      ? `${aiShort} 对 2026 世界杯全部赛事的胜平负、让球、比分、总进球、半全场、串关 6 维度预测分析、盈利率与模拟盈亏明细。`
      : '查看各 AI 在 2026 世界杯赛事中的预测分析、盈利率与模拟盈亏明细。',
    keywords: summary
      ? `${aiShort},${summary.ai},世界杯AI,${aiShort}预测,2026世界杯,AI足球分析`
      : '2026世界杯,AI足球分析,世界杯AI预测',
    canonicalPath: summary ? `/ai/${encodeURIComponent(summary.ai)}` : undefined,
    ogType: 'profile',
    jsonLd,
  });

  useEffect(() => {
    if (!summary) return;
    const hash = location.hash;
    if (!hash || hash.length < 2) return;
    // 等本页所有 section 渲染完
    const id = hash.slice(1);
    const tries = [0, 60, 200, 500];
    tries.forEach((delay) => {
      window.setTimeout(() => {
        const el = document.getElementById(id);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, delay);
    });
  }, [location.hash, summary]);

  if (!summary || !AI_LIST.includes(summary.ai) || summary.retired) {
    return (
      <div className="text-center py-16">
        <div className="text-2xl text-ink">
          {summary?.retired ? '该 AI 选手已退赛' : '未找到该 AI 选手'}
        </div>
        <Link to="/ai" className="inline-block mt-4 text-gold hover:underline">
          ← 返回 AI 列表
        </Link>
      </div>
    );
  }

  const rows = getAiMatches(summary.ai);

  return (
    <article className="space-y-8">
      <h1 className="sr-only">
        {AI_SHORT[summary.ai]} 2026世界杯预测分析 - AI 足球预测盈利率
      </h1>
      <Link
        to="/ai"
        className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink transition-colors"
      >
        ← 返回 AI 列表
      </Link>

      {/* Header card */}
      <section
        className={`rounded-2xl p-6 sm:p-8 border ${
          summary.rank === 1
            ? 'border-gold/40 bg-gradient-to-br from-[#1c2742] to-[#0f1a2e] shadow-gold'
            : 'border-divider bg-card-gradient'
        }`}
      >
        <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-8 items-center">
          <div className="flex items-center gap-5">
            <div
              className={`h-16 w-16 rounded-xl flex items-center justify-center text-2xl font-bold ${
                summary.retired
                  ? 'bg-elevated text-miss border border-divider'
                  : summary.rank === 1
                    ? 'bg-gold text-night'
                    : 'bg-elevated text-ink border border-divider'
              }`}
            >
              {summary.retired ? '×' : `#${summary.rank}`}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs uppercase tracking-[0.18em] text-muted">AI 选手</span>
                {summary.retired && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-divider text-miss bg-white/[0.02]">
                    已退赛
                  </span>
                )}
              </div>
              <div
                className={`text-2xl sm:text-3xl font-bold mt-1 ${
                  summary.retired ? 'text-miss' : 'text-ink'
                }`}
              >
                {AI_SHORT[summary.ai]}
              </div>
              <div
                className={`text-sm ${summary.retired ? 'text-miss/70' : 'text-muted'}`}
              >
                {summary.ai}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-widest text-muted">盈利率</div>
              <div
                className={`font-mono text-4xl sm:text-5xl font-bold mt-1 leading-none ${
                  summary.totalConfirmed === 0
                    ? 'text-ink'
                    : profitRateToneClass(summary.hitRate)
                }`}
              >
                {summary.totalConfirmed === 0 ? '—' : formatProfitRate(summary.hitRate)}
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-widest text-muted">累计盈亏</div>
              <div className="font-mono text-2xl sm:text-3xl mt-1">
                <PnlInline pnl={summary.officialPnl} />
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-widest text-muted">参赛场次</div>
              <div className="font-mono text-2xl sm:text-3xl text-ink mt-1">
                {summary.participatedMatches}
                <span className="text-muted text-base"> / 已确认 {summary.totalConfirmed}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Per-match accordion list */}
      <AiMatchAccordionSection rows={rows} ai={decoded} />

      <AiChainBetsSection ai={decoded} />

      {/* 内链：该 AI 预测过的所有比赛 */}
      {rows.length > 0 && (
        <nav
          aria-label={`${AI_SHORT[summary.ai]} 预测过的比赛`}
          className="rounded-2xl border border-divider bg-deep px-5 py-5 sm:px-7 sm:py-6"
        >
          <h2 className="text-base font-semibold text-ink">预测过的比赛</h2>
          <p className="mt-1 text-xs text-muted">
            点击查看 {AI_SHORT[summary.ai]} 在每场比赛的胜平负 / 让球 / 比分 / 总进球 / 半全场预测与命中情况。
          </p>
          <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((row) => (
              <li key={row.match.id}>
                <Link
                  to={`/matches/${encodeURIComponent(row.match.id)}`}
                  className="block rounded-md border border-divider/70 bg-night/40 px-3 py-2 text-xs text-ink hover:border-gold/40 hover:bg-gold-soft/30 transition-colors"
                >
                  <span className="text-muted mr-2">{isoToCnDate(row.match.time)}</span>
                  {row.match.teams}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </article>
  );
}

function PnlInline({ pnl }: { pnl: number }) {
  const tone = pnl > 0 ? 'text-turf' : pnl < 0 ? 'text-rose-300' : 'text-muted';
  return <span className={tone}>{formatPnl(pnl)}</span>;
}

function AiMatchAccordionSection({ rows, ai }: { rows: AiMatchRow[]; ai: string }) {
  const VISIBLE_BY_DEFAULT = 4;
  const location = useLocation();
  // 当 hash 命中的目标场次落在 VISIBLE_BY_DEFAULT 之外时，自动展开全部
  const initialShowAll = (() => {
    if (!location.hash.startsWith('#match-')) return false;
    const targetId = location.hash.slice(1); // match-周五029
    const idx = rows.findIndex((r) => `match-${encodeURIComponent(r.match.id)}` === targetId);
    return idx >= VISIBLE_BY_DEFAULT;
  })();
  const [showAll, setShowAll] = useState<boolean>(initialShowAll);
  const visibleRows = showAll ? rows : rows.slice(0, VISIBLE_BY_DEFAULT);
  const hiddenCount = Math.max(0, rows.length - VISIBLE_BY_DEFAULT);

  return (
    <section className="rounded-2xl border border-divider bg-deep overflow-hidden">
      <div className="px-5 py-4 border-b border-divider">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink">所有场次预测明细</h2>
            <p className="text-xs text-muted mt-0.5">
              默认仅展示最新 {VISIBLE_BY_DEFAULT} 场，点击底部按钮展开全部 {rows.length} 场。每行点击 +/− 查看维度命中、AI 分析及当日串关。
            </p>
          </div>
          <span className="text-[11px] text-muted">
            当前显示 {visibleRows.length} / {rows.length} 场
          </span>
        </div>
      </div>
      <ul className="divide-y divide-divider/60">
        {visibleRows.map((row, idx) => (
          <AiMatchAccordionItem key={row.match.id} row={row} defaultOpen={idx < VISIBLE_BY_DEFAULT} ai={ai} />
        ))}
      </ul>
      {hiddenCount > 0 && (
        <div className="border-t border-divider/60 px-5 py-3 text-center">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-md border border-divider bg-night/40 px-4 py-1.5 text-xs text-muted transition-colors hover:border-gold/50 hover:text-gold"
          >
            {showAll ? '收起较早场次' : `展开全部场次（还有 ${hiddenCount} 场）`}
          </button>
        </div>
      )}
    </section>
  );
}

function AiMatchAccordionItem({ row, defaultOpen, ai }: { row: AiMatchRow; defaultOpen: boolean; ai: string }) {
  const { match, prediction } = row;
  const location = useLocation();
  const targetHash = `#match-${encodeURIComponent(match.id)}`;
  const [open, setOpen] = useState<boolean>(defaultOpen || location.hash === targetHash);
  const [analysisExpanded, setAnalysisExpanded] = useState<boolean>(false);
  const isPending = match.status === '待比赛';
  const hits = prediction?.total_hits ?? null;
  const analysisText = prediction?.analysis?.trim() ?? '';
  const hasPrediction = prediction !== undefined && prediction !== null;

  useEffect(() => {
    if (location.hash === targetHash) {
      setOpen(true);
      const id = `match-${encodeURIComponent(match.id)}`;
      const el = document.getElementById(id);
      if (el) {
        // 等折叠区渲染完成
        requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }));
      }
    }
  }, [location.hash, targetHash, match.id]);

  return (
    <li id={`match-${encodeURIComponent(match.id)}`} className={`scroll-mt-24 transition-colors ${open ? 'bg-white/[0.03]' : 'hover:bg-white/[0.02]'}`}>
      <button
        type="button"
        onClick={() => hasPrediction && setOpen((v) => !v)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left sm:px-5"
        disabled={!hasPrediction}
      >
        {hasPrediction ? (
          <span
            className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-xs font-bold transition-colors ${
              open
                ? 'border-gold/50 bg-gold/10 text-gold'
                : 'border-divider text-muted'
            }`}
            aria-label={open ? '折叠' : '展开'}
          >
            {open ? '−' : '+'}
          </span>
        ) : (
          <span className="mt-0.5 inline-block h-6 w-6 shrink-0" />
        )}

        {/* Left: match info */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-mono text-[11px] text-muted">{match.id}</span>
            <span className="text-ink">{match.teams}</span>
            {match.actualScore ? (
              <span className="font-mono text-sm font-bold text-gold tabular-nums">
                {match.actualScore.replace(':', '-')}
              </span>
            ) : (
              <span className="text-[11px] text-muted">待比赛</span>
            )}
          </div>
          <div className="mt-0.5 text-[11px] text-muted">{match.time}</div>
        </div>

        {/* Middle: prediction summary (always visible) */}
        {hasPrediction ? (
          <div className="hidden shrink-0 sm:flex sm:flex-col sm:items-end sm:gap-1 text-xs text-muted">
            <span>
              <span className="text-muted">预测：</span>
              <span className="font-medium text-ink">{prediction.spf}</span>
              <span className="mx-1 text-muted/60">·</span>
              <span className="font-mono text-ink tabular-nums">{prediction.score}</span>
            </span>
            <span className="text-[10px] text-muted">
              让球 {prediction.handicap_spf} · 总进球 {prediction.goals} · 半全场 {prediction.half_full}
            </span>
          </div>
        ) : (
          <span className="hidden text-xs text-muted sm:inline">无数据</span>
        )}

        {/* Right: hit count badge */}
        <div className="shrink-0 self-center">
          {!hasPrediction ? (
            <span className="text-xs text-muted">—</span>
          ) : hits === null ? (
            <span className="rounded-md border border-divider px-2 py-1 text-[11px] text-muted">
              {isPending ? '待赛后录入' : '—'}
            </span>
          ) : (
            <span
              className={`inline-flex min-w-[44px] items-center justify-center rounded-md border px-2 py-1 font-mono text-sm font-bold tabular-nums ${
                hits >= 3
                  ? 'border-gold/40 bg-gold-soft text-gold'
                  : hits >= 1
                  ? 'border-turf/30 bg-turf-soft text-turf'
                  : 'border-divider text-miss'
              }`}
            >
              {hits}/4
            </span>
          )}
        </div>
      </button>

      {/* Mobile-only summary line (since md+ summary is in row) */}
      {hasPrediction && (
        <div className="px-4 pb-2 sm:hidden -mt-1">
          <div className="text-[11px] text-muted">
            预测：<span className="text-ink">{prediction.spf}</span>
            <span className="mx-1 text-muted/60">·</span>
            <span className="font-mono text-ink tabular-nums">{prediction.score}</span>
            <span className="mx-1 text-muted/60">·</span>
            让球 {prediction.handicap_spf}
          </div>
        </div>
      )}

      {/* Expanded detail */}
      {open && hasPrediction && (
        <div className="border-t border-divider/60 bg-night/40 px-4 py-4 sm:px-5">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {DIMENSIONS.map((d) => (
              <DimensionPill key={d.key} prediction={prediction} dim={d} isPending={isPending} />
            ))}
          </div>

          <AiMatchInlineChainBets ai={ai} matchTime={match.time} />

          <div className="mt-4 rounded-lg border border-divider/70 bg-deep/60 px-4 py-3">
            <div className="mb-1.5 flex items-center justify-between gap-2 text-xs uppercase tracking-wider text-muted">
              <span className="flex items-center gap-2">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-gold" />
                AI 预测分析
              </span>
              {analysisText.length > 0 && (
                <button
                  type="button"
                  onClick={() => setAnalysisExpanded((v) => !v)}
                  className="rounded-md border border-divider/70 px-2 py-0.5 text-[11px] font-medium normal-case tracking-normal text-muted transition-colors hover:border-gold/60 hover:text-gold"
                >
                  {analysisExpanded ? '收起' : '展开分析'}
                </button>
              )}
            </div>
            {analysisText.length > 0 ? (
              <p
                className={`text-sm leading-relaxed text-ink/90 ${
                  analysisExpanded ? 'whitespace-pre-line' : 'line-clamp-1'
                }`}
                title={!analysisExpanded ? analysisText : undefined}
              >
                {analysisText}
              </p>
            ) : (
              <p className="text-sm text-muted">该 AI 暂未提供本场分析说明，后续补充。</p>
            )}
          </div>

          <div className="mt-3 text-right">
            <Link
              to={`/matches/${encodeURIComponent(match.id)}`}
              className="inline-flex items-center gap-1 text-xs text-muted transition-colors hover:text-gold"
            >
              查看完整命中矩阵 →
            </Link>
          </div>
        </div>
      )}
    </li>
  );
}

function DimensionPill({
  prediction,
  dim,
  isPending,
}: {
  prediction: Prediction;
  dim: { key: DimensionKey; label: string };
  isPending: boolean;
}) {
  const hit = prediction[dim.key];
  const v = dimValue(prediction, dim.key);
  const muted = isPending || hit === null;
  const isHit = hit === '✅';

  let cls = 'border-divider bg-deep/60 text-ink';
  if (muted) cls = 'border-divider/60 bg-deep/40 text-ink';
  else if (isHit) cls = 'border-turf/30 bg-turf-soft text-turf';
  else cls = 'border-divider/60 bg-deep/40 text-miss';

  return (
    <div className={`flex items-center justify-between gap-2 rounded-md border px-3 py-2 ${cls}`}>
      <span className="text-[11px] uppercase tracking-wider text-muted">{dim.label}</span>
      <span className="flex items-center gap-1.5 font-mono text-sm tabular-nums">
        {String(v)}
        {!muted && isHit && (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path
              d="M2 6.5l2.6 2.5L10 3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </span>
    </div>
  );
}

function AiMatchInlineChainBets({ ai, matchTime }: { ai: string; matchTime: string }) {
  const [open, setOpen] = useState(false);
  const cnDate = isoToCnDate(matchTime);
  if (!cnDate) return null;
  const data = getChainBetsForAi(ai);
  const day = data.days.find((d) => d.date === cnDate);

  if (!day || day.bets.length === 0) {
    return (
      <div className="mt-4 rounded-lg border border-divider/60 bg-deep/40 px-4 py-3">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-miss" />
          当日串关方案 · {cnDate}
        </div>
        <div className="mt-1.5 text-[11px] text-muted/80 normal-case tracking-normal">
          暂无串关数据
        </div>
      </div>
    );
  }

  const settled = day.bets.filter((b) => b.hit !== null);
  const hits = day.bets.filter((b) => b.hit === true).length;
  const pnl = settled.reduce((acc, b) => acc + b.pnl, 0);
  const allPending = settled.length === 0;

  return (
    <div className="mt-4 rounded-lg border border-gold/20 bg-gold-soft/20 px-4 py-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full flex-wrap items-center justify-between gap-2 text-left"
      >
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-gold">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-gold" />
          当日串关方案 · {cnDate}
        </div>
        <div className="flex items-center gap-x-4 gap-y-1 text-[11px] text-muted">
          {allPending ? (
            <span className="rounded bg-night/60 px-2 py-0.5 text-muted">待定 · {day.bets.length} 注</span>
          ) : (
            <>
              <span>
                命中 <span className="font-semibold text-turf">{hits}</span> / {settled.length}
              </span>
              <span>
                盈亏{' '}
                <span className={`font-semibold ${pnl >= 0 ? 'text-turf' : 'text-red-400'}`}>
                  {formatPnl(pnl)}
                </span>
              </span>
            </>
          )}
          <span className="text-gold/80">{open ? '收起 ▴' : '展开 ▾'}</span>
        </div>
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {day.bets.map((bet, i) => (
            <AiChainBetCard key={`${bet.type}-${i}`} bet={bet} />
          ))}
        </div>
      )}
    </div>
  );
}

function AiChainBetsSection({ ai }: { ai: string }) {
  const data = getChainBetsForAi(ai);
  const { totals, days } = data;
  const empty = totals.totalBets === 0;
  const shortName = (AI_SHORT as Record<string, string>)[ai] ?? ai.replace(/^AI-/, '');

  // 推算最新比赛日（来自 matches.time 前缀），用于检测是否缺少最新日期的串关数据
  const latestMatchDate = allMatches.reduce((max, m) => {
    const d = isoToCnDate(m.time || '');
    if (!d) return max;
    // 比较时用 ISO 前缀更可靠（'2026-06-20' > '2026-06-19'）
    const iso = (m.time || '').slice(0, 10);
    return iso > max.iso ? { cn: d, iso } : max;
  }, { cn: '', iso: '' }).cn;
  const hasLatestDay = days.some((d) => d.date === latestMatchDate);
  const showPendingPlaceholder = !!latestMatchDate && !hasLatestDay;

  return (
    <section id="chain" className="scroll-mt-24 rounded-xl border border-divider bg-deep px-5 py-6 sm:px-7 sm:py-8">
      <header className="mb-5 flex flex-col gap-3 border-b border-divider/70 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-ink sm:text-xl">串关推荐明细</h2>
          <p className="mt-1 text-xs text-muted sm:text-sm">
            {shortName} 在 2 串 1（稳胆串）/ 3 串 1（均衡串）/ 4 串 1（博高串）三种类型上的逐场推荐与命中情况。
          </p>
        </div>
        {!empty ? (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs sm:text-sm">
            <span className="text-muted">
              推荐 <span className="font-semibold text-ink">{totals.totalBets}</span> 次
            </span>
            <span className="text-muted">
              命中 <span className="font-semibold text-turf">{totals.totalHits}</span> 次
            </span>
            <span className="text-muted">
              命中率 <span className="font-semibold text-ink">{formatPercent(totals.hitRate)}</span>
            </span>
            <span className="text-muted">
              净盈亏{' '}
              <span className={`font-semibold ${totals.totalPnl >= 0 ? 'text-turf' : 'text-red-400'}`}>
                {formatPnl(totals.totalPnl)}
              </span>
            </span>
          </div>
        ) : null}
      </header>

      {empty && !showPendingPlaceholder ? (
        <div className="rounded-lg border border-dashed border-divider bg-night/40 px-5 py-8 text-center text-sm text-muted">
          暂未参与串关追踪
        </div>
      ) : (
        <div className="space-y-3">
          {showPendingPlaceholder ? <AiChainPendingDay date={latestMatchDate} /> : null}
          {days.map((day, idx) => (
            <AiChainDay
              key={day.date}
              day={day}
              defaultOpen={!showPendingPlaceholder && idx === 0}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function AiChainPendingDay({ date }: { date: string }) {
  const display = formatChainDate(date);
  return (
    <article className="rounded-lg border border-dashed border-gold/40 bg-gold-soft/40 px-4 py-4 sm:px-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-6 min-w-[2.25rem] items-center justify-center rounded-full bg-gold/20 px-2 text-[11px] font-semibold uppercase tracking-wide text-gold">
            待生成
          </span>
          <h3 className="text-sm font-semibold text-ink sm:text-base">{display} · 串关预测即将生成</h3>
        </div>
        <span className="text-xs text-muted">系统将在赛前发布该日期的 2 串 1 / 3 串 1 / 4 串 1 推荐</span>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-muted sm:text-sm">
        当前对应日期还未录入串关组合，赛前补充后会自动出现在此处，请稍后再来查看。
      </p>
    </article>
  );
}

function formatChainDate(d: string) {
  if (!d) return '';
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return d;
  return `${parseInt(m[2], 10)}/${parseInt(m[3], 10)}`;
}

interface AiChainDayProps {
  day: { date: string; matches: string[]; bets: ChainBet[] };
  defaultOpen?: boolean;
}

function AiChainDay({ day, defaultOpen = false }: AiChainDayProps) {
  const [open, setOpen] = useState<boolean>(defaultOpen);
  const dayBets = day.bets.length;
  const dayHits = day.bets.filter((b) => b.hit).length;
  const dayPnl = day.bets.reduce((sum, b) => sum + b.pnl, 0);

  return (
    <article
      className={`rounded-lg border bg-night/40 transition-colors ${
        open ? 'border-gold/40 shadow-[0_0_0_1px_rgba(245,194,66,0.15)]' : 'border-divider/70'
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left sm:px-5"
      >
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-base font-bold transition-colors ${
            open ? 'border-gold/50 bg-gold/10 text-gold' : 'border-divider text-muted'
          }`}
          aria-label={open ? '折叠' : '展开'}
        >
          {open ? '−' : '+'}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-base font-semibold text-ink tabular-nums">{day.date}</span>
            {day.matches.length > 0 ? (
              <span className="text-xs text-muted">参考赛事：{day.matches.join('、')}</span>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span>
            推荐 <span className="font-semibold text-ink">{dayBets}</span>
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
      {open && (
        <div className="border-t border-divider/60 px-4 pb-4 pt-3 sm:px-5">
          <div className="grid gap-3 md:grid-cols-3">
            {day.bets.map((bet, i) => (
              <AiChainBetCard key={`${bet.type}-${i}`} bet={bet} />
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

function AiChainBetCard({ bet }: { bet: ChainBet }) {
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
          <div className={`text-sm font-semibold ${hit === true ? 'text-gold' : 'text-muted'}`}>{bet.type}</div>
          <div className="text-[11px] tabular-nums text-muted">
            赔率 {bet.odds.toFixed(2)} × 2 元
          </div>
        </div>
        <span
          className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
            hit === true
              ? 'bg-turf text-night'
              : pending
                ? 'bg-night/60 text-muted border border-divider'
                : 'bg-divider text-muted'
          }`}
          aria-label={hit === true ? '命中' : pending ? '待定' : '未命中'}
        >
          {hit === true ? '✓' : pending ? '○' : '♡'}
        </span>
      </div>

      <ul className="space-y-1.5">
        {bet.selections.map((s, idx) => (
          <AiChainSelectionRow key={idx} selection={s} />
        ))}
      </ul>

      <div className="mt-auto flex items-center justify-between border-t border-divider/60 pt-2 text-xs">
        <span
          className={`rounded px-2 py-0.5 text-[11px] font-medium ${
            hit === true
              ? 'bg-turf-soft text-turf'
              : pending
                ? 'bg-night/60 text-muted'
                : 'bg-night/60 text-muted'
          }`}
        >
          {hit === true ? '命中' : pending ? '○ 待定' : '未中'}
        </span>
        <span
          className={`tabular-nums font-semibold ${
            pending ? 'text-muted' : bet.pnl >= 0 ? 'text-turf' : 'text-red-400'
          }`}
        >
          {pending ? '—' : `${formatPnl(bet.pnl)} (${formatYuan(bet.pnl)})`}
        </span>
      </div>
    </div>
  );
}

function AiChainSelectionRow({ selection }: { selection: ChainBetSelection }) {
  const hit = selection.hit;
  const pending = hit === null;
  const ok = hit === true;
  return (
    <li className="flex items-start gap-2 text-[11px] leading-snug text-muted">
      <span
        className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[10px] font-bold ${
          ok
            ? 'bg-turf-soft text-turf'
            : pending
              ? 'bg-night/60 text-muted'
              : 'bg-night/60 text-muted'
        }`}
        aria-label={ok ? '命中' : pending ? '待定' : '未命中'}
      >
        {ok ? '✓' : pending ? '○' : '♡'}
      </span>
      <span className="flex-1">
        <span className={ok ? 'text-ink' : pending ? 'text-ink/80' : ''}>
          {selection.teams}
        </span>
        <span className="mx-1 text-muted/60">·</span>
        <span className="text-muted">
          {selection.dimension}
          <span className="ml-1 text-ink">{selection.prediction}</span>
        </span>
      </span>
    </li>
  );
}
