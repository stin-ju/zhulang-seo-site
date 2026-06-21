import { Link, useParams } from 'react-router-dom';
import { useMemo } from 'react';
import { useDocumentMeta, SITE_ORIGIN } from '../lib/useDocumentMeta';
import {
  AI_LIST,
  AI_SHORT,
  DIMENSIONS,
  formatHandicap,
  formatPnl,
  getAiChainHitsForDate,
  getBettingSummary,
  getMatchById,
  isRetiredAi,
  isoToCnDate,
  type AiName,
  type DimensionKey,
  type OddsEntry,
  type Prediction,
} from '../lib/data';

function HitCell({
  hit,
  value,
  isPending,
}: {
  hit: '✅' | '❌' | null;
  value: string | number;
  isPending: boolean;
}) {
  if (isPending || hit === null) {
    return (
      <td className="px-3 py-3 align-middle">
        <div className="rounded-md px-2 py-1.5 text-center text-sm text-ink bg-white/[0.02] border border-divider">
          {String(value)}
        </div>
      </td>
    );
  }
  if (hit === '✅') {
    return (
      <td className="px-3 py-3 align-middle">
        <div className="rounded-md px-2 py-1.5 text-center text-sm font-semibold text-turf bg-turf-soft border border-turf/30 flex items-center justify-center gap-1.5">
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            className="shrink-0"
            aria-hidden
          >
            <path
              d="M2 6.5l2.6 2.5L10 3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="font-mono">{String(value)}</span>
        </div>
      </td>
    );
  }
  return (
    <td className="px-3 py-3 align-middle">
      <div className="rounded-md px-2 py-1.5 text-center text-sm text-miss bg-white/[0.02] border border-divider/70">
        <span className="font-mono">{String(value)}</span>
      </div>
    </td>
  );
}

function SpfCell({ value, hit }: { value: string; hit: boolean | null }) {
  let inner = 'rounded-md px-2 py-1.5 text-center text-sm text-ink bg-white/[0.03] border border-divider';
  if (hit === true) inner = 'rounded-md px-2 py-1.5 text-center text-sm font-semibold text-turf bg-turf-soft border border-turf/40';
  else if (hit === false) inner = 'rounded-md px-2 py-1.5 text-center text-sm text-miss bg-white/[0.03] border border-divider';
  return (
    <td className="px-3 py-3 align-middle">
      <div className={inner}>
        {value}
        {hit === true && <span className="ml-1 text-[10px]">✓</span>}
      </div>
    </td>
  );
}

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

function actualSpfFromScore(score: string | null): '胜' | '平' | '负' | null {
  if (!score) return null;
  const m = /^\s*(\d+)\s*[:：-]\s*(\d+)\s*$/.exec(score);
  if (!m) return null;
  const home = Number(m[1]);
  const away = Number(m[2]);
  if (home > away) return '胜';
  if (home < away) return '负';
  return '平';
}

function toOdd(value: number | string | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function spfHitInfo(
  pred: Prediction,
  odds: OddsEntry | undefined,
  actualScore: string | null
): { hit: boolean; pnl: number; odd: number } | null {
  if (!odds || !actualScore) return null;
  const actual = actualSpfFromScore(actualScore);
  if (!actual) return null;
  const map: Record<'胜' | '平' | '负', number | null> = {
    胜: toOdd(odds.win),
    平: toOdd(odds.draw),
    负: toOdd(odds.lose),
  };
  const predSide = pred.spf as '胜' | '平' | '负' | undefined;
  const odd = predSide && predSide in map ? map[predSide] : null;
  if (odd == null) return null;
  const hit = predSide === actual;
  const pnl = hit ? odd * 2 - 2 : -2;
  return { hit, pnl, odd };
}

function handicapHitInfo(
  pred: Prediction,
  odds: OddsEntry | undefined
): { hit: boolean; pnl: number; odd: number } | null {
  if (!odds) return null;
  const map: Record<string, number | null> = {
    让胜: toOdd(odds.handicap_win),
    让平: toOdd(odds.handicap_draw),
    让负: toOdd(odds.handicap_lose),
  };
  const odd = map[pred.handicap_spf] ?? null;
  if (odd == null) return null;
  const hit = pred.hit_handicap === '✅';
  if (pred.hit_handicap === null) return null;
  const pnl = hit ? odd * 2 - 2 : -2;
  return { hit, pnl, odd };
}

function OddsBlock({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string | number;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-md px-3 py-2 border text-center ${
        highlight
          ? 'border-gold/40 bg-gold-soft text-gold'
          : 'border-divider bg-white/[0.02] text-ink'
      }`}
    >
      <div
        className={`text-[10px] uppercase tracking-widest ${
          highlight ? 'text-gold/80' : 'text-muted'
        }`}
      >
        {label}
      </div>
      <div className="font-mono text-lg font-semibold mt-0.5">{value}</div>
    </div>
  );
}

function OddsCard({
  match,
}: {
  match: { handicap: string; actualScore: string | null; status: '已确认' | '待比赛'; odds?: OddsEntry };
}) {
  const odds = match.odds;
  if (!odds) return null;

  const actual = actualSpfFromScore(match.actualScore);
  const handicapStr = formatHandicap(odds.handicap ?? match.handicap);

  return (
    <section className="rounded-2xl border border-divider bg-deep">
      <div className="px-5 py-4 border-b border-divider flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-ink">赔率与赛果</h2>
          <p className="text-xs text-muted mt-0.5">
            模拟下注每注 2 元为虚拟单位，命中按"赔率 × 2"返奖。亮金色表示与实际赛果一致的选项。
          </p>
        </div>
        <Link
          to="/betting"
          className="text-[11px] text-muted hover:text-gold transition-colors"
        >
          模拟盈亏总览 →
        </Link>
      </div>
      <div className="p-5 space-y-5">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] uppercase tracking-widest text-muted">
              胜平负赔率
            </span>
            {actual && (
              <span className="text-[11px] text-muted">
                实际：<span className="text-gold font-semibold">{actual}</span>
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <OddsBlock label="主胜" value={odds.win} highlight={actual === '胜'} />
            <OddsBlock label="平" value={odds.draw} highlight={actual === '平'} />
            <OddsBlock label="客胜" value={odds.lose} highlight={actual === '负'} />
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] uppercase tracking-widest text-muted">
              让球赔率
            </span>
            <span className="text-[11px] text-muted">
              让球 <span className="text-ink font-mono">{handicapStr}</span>
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <OddsBlock label="让胜" value={odds.handicap_win} />
            <OddsBlock label="让平" value={odds.handicap_draw} />
            <OddsBlock label="让负" value={odds.handicap_lose} />
          </div>
        </div>
      </div>
    </section>
  );
}

function BettingChip({
  label,
  hit,
  pnl,
  odd,
  pending,
}: {
  label: string;
  hit: boolean | null;
  pnl: number | null;
  odd: number | null;
  pending: boolean;
}) {
  if (pending || hit === null) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] border border-divider bg-white/[0.02] text-ink">
        <span className="font-sans">{label}</span>
        <span className="text-muted">—</span>
      </span>
    );
  }
  const cls = hit
    ? 'border-turf/30 bg-turf-soft text-turf'
    : 'border-divider bg-white/[0.02] text-miss';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] border font-mono ${cls}`}
    >
      <span className="opacity-80 font-sans">{label}</span>
      <span>{hit ? '中' : '挂'}</span>
      {odd != null && odd > 0 && <span className="opacity-70">@{odd.toFixed(2)}</span>}
      {pnl != null && <span className="font-semibold">{formatPnl(pnl)}</span>}
    </span>
  );
}

export default function MatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const match = id ? getMatchById(decodeURIComponent(id)) : undefined;

  const [homeName, awayName] = match
    ? match.teams.split(/\s*VS\s*/i)
    : ['', ''];

  const jsonLd = useMemo(() => {
    if (!match) return undefined;
    const homeT = homeName || match.teams;
    const awayT = awayName || '';
    return {
      '@context': 'https://schema.org',
      '@type': 'SportsEvent',
      name: `${homeT}VS${awayT}`,
      sport: 'Soccer',
      startDate: match.time,
      eventStatus:
        match.status === '待比赛'
          ? 'https://schema.org/EventScheduled'
          : 'https://schema.org/EventScheduled',
      homeTeam: {
        '@type': 'SportsTeam',
        name: homeT,
      },
      awayTeam: {
        '@type': 'SportsTeam',
        name: awayT,
      },
      location: {
        '@type': 'Place',
        name: '2026 FIFA World Cup',
      },
      url: match
        ? `${SITE_ORIGIN}/matches/${encodeURIComponent(match.id)}`
        : undefined,
    };
  }, [match, homeName, awayName]);

  const seoTitle = match
    ? `2026世界杯 ${homeName}vs${awayName} AI预测分析 | 8个AI命中矩阵`
    : '比赛预测对比 | 8个AI命中矩阵 - 大竞赛';
  const seoDescription = match
    ? `2026 世界杯 ${homeName} VS ${awayName}：8 个 AI 的胜平负、让球、比分、总进球、半全场预测命中矩阵与分析逻辑。`
    : '8 个 AI 对世界杯赛事的胜平负、让球、比分、总进球、半全场预测命中矩阵。';

  useDocumentMeta({
    title: seoTitle,
    description: seoDescription,
    keywords: match
      ? `2026世界杯,${homeName}vs${awayName},世界杯${homeName},世界杯预测,AI足球分析`
      : '2026世界杯,世界杯预测,AI足球分析',
    canonicalPath: match
      ? `/matches/${encodeURIComponent(match.id)}`
      : undefined,
    ogType: 'article',
    jsonLd,
  });

  if (!match) {
    return (
      <div className="text-center py-16">
        <div className="text-2xl text-ink">未找到该比赛</div>
        <Link to="/matches" className="inline-block mt-4 text-gold hover:underline">
          ← 返回比赛列表
        </Link>
      </div>
    );
  }

  const isPending = match.status === '待比赛';
  const home = homeName;
  const away = awayName;

  // Order predictions by AI_LIST
  const predByAi = new Map<string, Prediction>();
  for (const p of match.predictions) predByAi.set(p.ai, p);

  const rows = AI_LIST.map<{ ai: AiName; pred: Prediction | undefined }>(ai => ({
    ai,
    pred: predByAi.get(ai),
  }));

  const matchCnDate = isoToCnDate(match.time);
  const chainHitsByAi = new Map<AiName, number>();
  for (const ai of AI_LIST) {
    chainHitsByAi.set(ai, matchCnDate ? getAiChainHitsForDate(ai, matchCnDate) : 0);
  }
  const totalHitsByAi = new Map<AiName, number>();
  for (const r of rows) {
    const base = r.pred?.total_hits ?? 0;
    totalHitsByAi.set(r.ai, base + (chainHitsByAi.get(r.ai) ?? 0));
  }
  const bestHits = Array.from(totalHitsByAi.values()).reduce((max, v) => Math.max(max, v), 0);

  return (
    <div className="space-y-8">
      <Link
        to="/matches"
        className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink transition-colors"
      >
        ← 返回比赛列表
      </Link>

      {/* Banner */}
      <section
        className={`relative overflow-hidden rounded-2xl p-6 sm:p-8 border ${
          isPending
            ? 'border-divider bg-card-gradient'
            : 'border-gold/30 bg-gradient-to-br from-[#1c2742] to-[#0f1a2e] shadow-gold'
        }`}
      >
        <h1 className="sr-only">
          2026世界杯 {home}vs{away} AI预测分析
        </h1>
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-muted">
            <span className="font-mono">{match.id}</span>
            <span>·</span>
            <span>{match.time}</span>
            <span>·</span>
            <span>让球 {formatHandicap(match.handicap)}</span>
          </div>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] border ${
              isPending
                ? 'bg-white/5 text-muted border-divider'
                : 'bg-turf-soft text-turf border-turf/30'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${isPending ? 'bg-muted' : 'bg-turf'}`}
            />
            {match.status}
          </span>
        </div>
        <div className="mt-6 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <div className="text-right">
            <div className="text-2xl sm:text-3xl font-bold text-ink truncate">{home}</div>
            <div className="text-[11px] text-muted mt-1">主队</div>
          </div>
          <div className="text-center">
            {isPending || !match.actualScore ? (
              <div className="font-mono text-3xl sm:text-4xl text-muted">VS</div>
            ) : (
              <div>
                <div className="text-[11px] tracking-widest uppercase text-gold/80 mb-1">
                  实际比分
                </div>
                <div className="font-mono text-5xl sm:text-6xl font-bold text-gold leading-none">
                  {match.actualScore.replace(':', ' : ')}
                </div>
              </div>
            )}
          </div>
          <div className="text-left">
            <div className="text-2xl sm:text-3xl font-bold text-ink truncate">{away}</div>
            <div className="text-[11px] text-muted mt-1">客队</div>
          </div>
        </div>
      </section>

      {/* Odds & actual */}
      <OddsCard match={match} />

      {/* Prediction matrix */}
      <section className="rounded-2xl border border-divider bg-deep overflow-hidden">
        <div className="px-5 py-4 flex items-center justify-between border-b border-divider">
          <div>
            <h2 className="text-base font-semibold text-ink">10 AI 预测对比</h2>
            <p className="text-xs text-muted mt-0.5">
              {isPending
                ? '本场尚未开赛，暂无命中标记。'
                : bestHits === 0 && !rows.some(r => r.pred?.total_hits != null)
                ? '比赛已确认，逐项命中数据待录入，预测内容以灰色展示。'
                : '绿色 = 命中实际赛果，灰色 = 未命中。'}
            </p>
          </div>
          {!isPending && rows.some(r => r.pred?.total_hits != null) && (
            <div className="text-xs text-muted">
              本场最佳：<span className="font-mono text-gold">{bestHits} / 8</span>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-elevated text-[11px] uppercase tracking-wider text-muted">
                <th className="text-left px-4 py-3 font-medium w-[180px]">AI 模型</th>
                <th className="text-center px-3 py-3 font-medium">胜平负</th>
                {DIMENSIONS.map(d => (
                  <th key={d.key} className="text-center px-3 py-3 font-medium">
                    {d.label}
                  </th>
                ))}
                <th className="text-center px-4 py-3 font-medium w-[110px]">命中数</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ ai, pred }) => {
                const baseHits = pred?.total_hits ?? null;
                const combinedHits = baseHits === null ? null : (totalHitsByAi.get(ai) ?? baseHits);
                const hits = combinedHits;
                const isBest = !isPending && hits !== null && hits === bestHits && hits > 0;
                const retired = isRetiredAi(ai);
                return (
                  <tr
                    key={ai}
                    className={`border-t border-divider hover:bg-white/[0.02] transition-colors ${
                      retired ? 'opacity-60' : ''
                    }`}
                  >
                    <td className="px-4 py-3 align-middle">
                      <Link
                        to={`/ai/${encodeURIComponent(ai)}`}
                        className="flex items-center gap-2 group"
                      >
                        <span
                          className={`font-medium transition-colors ${
                            retired
                              ? 'text-miss group-hover:text-miss/90'
                              : 'text-ink group-hover:text-gold'
                          }`}
                        >
                          {AI_SHORT[ai]}
                        </span>
                        {retired && (
                          <span className="text-[10px] px-1 py-0.5 rounded border border-divider text-miss bg-white/[0.02]">
                            退赛
                          </span>
                        )}
                        <span className={`text-[11px] ${retired ? 'text-miss/70' : 'text-muted'}`}>
                          {ai}
                        </span>
                      </Link>
                    </td>
                    {pred ? (
                      <>
                        <SpfCell
                          value={pred.spf}
                          hit={isPending ? null : (spfHitInfo(pred, match.odds, match.actualScore)?.hit ?? null)}
                        />
                        {DIMENSIONS.map(d => (
                          <HitCell
                            key={d.key}
                            hit={pred[d.key]}
                            value={dimValue(pred, d.key)}
                            isPending={isPending}
                          />
                        ))}
                        <td className="px-4 py-3 align-middle text-center">
                          {hits === null ? (
                            <span className="text-muted">—</span>
                          ) : (
                            <span
                              className={`font-mono text-lg font-bold ${
                                isBest ? 'text-gold' : hits > 0 ? 'text-ink' : 'text-miss'
                              }`}
                            >
                              {hits}
                              <span className="text-muted text-sm font-normal"> / 8</span>
                            </span>
                          )}
                        </td>
                      </>
                    ) : (
                      <td colSpan={6} className="px-4 py-3 text-center text-muted text-xs">
                        {retired ? '已退赛 · 未参与本场预测' : '本场未参赛'}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* AI prediction analysis */}
      <section className="rounded-2xl border border-divider bg-deep overflow-hidden">
        <div className="px-5 py-4 border-b border-divider flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink">AI 预测分析</h2>
            <p className="text-xs text-muted mt-0.5">
              各模型给出的预测推理逻辑原文
            </p>
          </div>
          <span className="text-[11px] text-muted">
            共 {rows.filter(r => r.pred?.analysis).length} 份分析
          </span>
        </div>
        <div className="divide-y divide-divider">
          {rows.map(({ ai, pred }) => {
            const analysis = pred?.analysis?.trim() ?? '';
            const hits = pred?.total_hits ?? null;
            const isBest = !isPending && hits !== null && hits === bestHits && hits > 0;
            const spfInfo = pred ? spfHitInfo(pred, match.odds, match.actualScore) : null;
            const handicapInfo = pred ? handicapHitInfo(pred, match.odds) : null;
            const aiBetting = getBettingSummary(ai);
            const retired = isRetiredAi(ai);
            return (
              <article
                key={ai}
                className={`px-5 py-5 hover:bg-white/[0.02] transition-colors ${
                  retired ? 'opacity-65' : ''
                }`}
              >
                <header className="flex items-center justify-between gap-3 mb-3">
                  <Link
                    to={`/ai/${encodeURIComponent(ai)}`}
                    className="flex items-center gap-2 group min-w-0"
                  >
                    <span
                      className={`inline-flex items-center justify-center h-7 w-7 rounded-full text-[11px] font-bold border ${
                        retired
                          ? 'border-divider text-miss bg-white/[0.02]'
                          : isBest
                            ? 'border-gold/60 text-gold bg-gold-soft'
                            : 'border-divider text-muted bg-white/[0.03]'
                      }`}
                    >
                      {AI_SHORT[ai].slice(0, 2)}
                    </span>
                    <span
                      className={`font-medium truncate transition-colors ${
                        retired
                          ? 'text-miss group-hover:text-miss/90'
                          : 'text-ink group-hover:text-gold'
                      }`}
                    >
                      {AI_SHORT[ai]}
                    </span>
                    {retired && (
                      <span className="text-[10px] px-1 py-0.5 rounded border border-divider text-miss bg-white/[0.02] shrink-0">
                        退赛
                      </span>
                    )}
                    <span
                      className={`text-[11px] truncate ${
                        retired ? 'text-miss/70' : 'text-muted'
                      }`}
                    >
                      {ai}
                    </span>
                  </Link>
                  <div className="flex items-center gap-2 shrink-0">
                    {aiBetting && (
                      <Link
                        to="/betting"
                        title="查看模拟盈亏总览"
                        className="hidden sm:inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] border border-divider bg-white/[0.02] text-muted hover:text-gold hover:border-gold/30 transition-colors font-mono"
                      >
                        <span className="font-sans">盈亏 #{aiBetting.rank}</span>
                        <span
                          className={
                            aiBetting.total_pnl > 0
                              ? 'text-turf'
                              : aiBetting.total_pnl < 0
                              ? 'text-[#F87171]'
                              : 'text-muted'
                          }
                        >
                          {formatPnl(aiBetting.total_pnl)}
                        </span>
                      </Link>
                    )}
                    {!isPending && hits !== null && (
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] border font-mono ${
                          isBest
                            ? 'border-gold/40 text-gold bg-gold-soft'
                            : hits > 0
                            ? 'border-turf/30 text-turf bg-turf-soft'
                            : 'border-divider text-miss bg-white/[0.02]'
                        }`}
                      >
                        命中 {hits} / 4
                      </span>
                    )}
                  </div>
                </header>
                {pred && !isPending && (spfInfo || handicapInfo) && (
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    <BettingChip
                      label="胜平负"
                      hit={spfInfo?.hit ?? null}
                      pnl={spfInfo?.pnl ?? null}
                      odd={spfInfo?.odd ?? null}
                      pending={isPending}
                    />
                    <BettingChip
                      label="让球"
                      hit={handicapInfo?.hit ?? null}
                      pnl={handicapInfo?.pnl ?? null}
                      odd={handicapInfo?.odd ?? null}
                      pending={isPending}
                    />
                    <BettingChip
                      label="比分"
                      hit={pred.hit_score === '✅'}
                      pnl={pred.hit_score === null ? null : pred.hit_score === '✅' ? null : -2}
                      odd={null}
                      pending={isPending}
                    />
                    <BettingChip
                      label="总进球"
                      hit={pred.hit_goals === '✅'}
                      pnl={pred.hit_goals === null ? null : pred.hit_goals === '✅' ? null : -2}
                      odd={null}
                      pending={isPending}
                    />
                    <BettingChip
                      label="半全场"
                      hit={pred.hit_half === '✅'}
                      pnl={pred.hit_half === null ? null : pred.hit_half === '✅' ? null : -2}
                      odd={null}
                      pending={isPending}
                    />
                  </div>
                )}
                {pred ? (
                  analysis ? (
                    <p className="text-[14px] leading-[1.7] text-ink/85 whitespace-pre-wrap">
                      {analysis}
                    </p>
                  ) : (
                    <p className="text-[13px] leading-relaxed text-muted italic">
                      该模型未提供分析逻辑文本。
                    </p>
                  )
                ) : (
                  <p className="text-[13px] leading-relaxed text-muted italic">
                    无该模型的本场预测数据。
                  </p>
                )}
              </article>
            );
          })}
        </div>
      </section>

      {/* 相关 AI 分析 内链区块 */}
      <nav
        aria-label="相关 AI 分析"
        className="rounded-2xl border border-divider bg-deep p-5"
      >
        <h2 className="text-base font-semibold text-ink mb-1">相关 AI 分析</h2>
        <p className="text-xs text-muted mb-3">
          深入了解每个 AI 的整体预测能力与历史命中表现
        </p>
        <ul className="flex flex-wrap gap-2">
          {AI_LIST.map((ai) => (
            <li key={ai}>
              <Link
                to={`/ai/${encodeURIComponent(ai)}`}
                className="inline-flex items-center rounded-full border border-divider bg-white/[0.02] px-3 py-1 text-xs text-ink transition-colors hover:border-gold/40 hover:text-gold"
                title={`查看 ${AI_SHORT[ai]} 的 2026 世界杯预测分析`}
              >
                {AI_SHORT[ai]} 预测分析
              </Link>
            </li>
          ))}
        </ul>
      </nav>

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
