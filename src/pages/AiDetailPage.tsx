import { Link, useParams } from 'react-router-dom';
import {
  AI_LIST,
  AI_SHORT,
  DIMENSIONS,
  formatPercent,
  formatPnl,
  formatYuan,
  getAiMatches,
  getAiSummary,
  getChainBetsForAi,
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

function DimBar({ rate, hits, total }: { rate: number; hits: number; total: number }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-muted">
        <span className="font-mono text-ink">{formatPercent(rate)}</span>
        <span>
          {hits} / {total}
        </span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-white/[0.06] overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-turf to-emerald-300"
          style={{ width: `${Math.max(0, Math.min(1, rate)) * 100}%` }}
        />
      </div>
    </div>
  );
}

function MatchStrip({ rows }: { rows: AiMatchRow[] }) {
  // chronological from earliest to latest, left -> right
  const ordered = rows.slice().reverse();
  return (
    <div className="flex gap-1.5">
      {ordered.map(({ match, prediction }) => {
        const hits = prediction?.total_hits ?? null;
        const isPending = match.status === '待比赛';
        let bg = 'bg-white/[0.06]';
        let title = `${match.id} · ${match.teams} · ${isPending ? '待比赛' : '未命中'}`;
        if (!isPending && hits !== null) {
          if (hits >= 3) bg = 'bg-gold';
          else if (hits === 2) bg = 'bg-turf';
          else if (hits === 1) bg = 'bg-turf/40';
          else bg = 'bg-miss';
          title = `${match.id} · ${match.teams} · 命中 ${hits}/4`;
        }
        return (
          <Link
            key={match.id}
            to={`/matches/${encodeURIComponent(match.id)}`}
            title={title}
            className={`h-7 flex-1 rounded-sm ${bg} hover:ring-2 hover:ring-gold/60 transition-shadow`}
          />
        );
      })}
    </div>
  );
}

export default function AiDetailPage() {
  const { name } = useParams<{ name: string }>();
  const decoded = name ? decodeURIComponent(name) : '';
  const summary = getAiSummary(decoded);

  if (!summary || !AI_LIST.includes(summary.ai)) {
    return (
      <div className="text-center py-16">
        <div className="text-2xl text-ink">未找到该 AI 选手</div>
        <Link to="/ai" className="inline-block mt-4 text-gold hover:underline">
          ← 返回 AI 列表
        </Link>
      </div>
    );
  }

  const rows = getAiMatches(summary.ai);
  const confirmedRows = rows.filter(r => r.match.status === '已确认');

  return (
    <div className="space-y-8">
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
              <div className="text-[11px] uppercase tracking-widest text-muted">综合命中率</div>
              <div
                className={`font-mono text-4xl sm:text-5xl font-bold mt-1 leading-none ${
                  summary.retired
                    ? 'text-miss'
                    : summary.rank === 1
                      ? 'text-gold'
                      : 'text-ink'
                }`}
              >
                {summary.totalConfirmed === 0 ? '—' : formatPercent(summary.hitRate)}
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-widest text-muted">命中 / 预测</div>
              <div className="font-mono text-2xl sm:text-3xl text-ink mt-1">
                {summary.totalHits}
                <span className="text-muted text-base"> / {summary.totalSlots}</span>
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

      {/* Per-dimension stats */}
      <section className="rounded-2xl border border-divider bg-deep p-5 sm:p-6">
        <h2 className="text-base font-semibold text-ink">各维度命中率</h2>
        <p className="text-xs text-muted mt-1">
          基于 {summary.totalConfirmed} 场已确认比赛
          {(() => {
            const dimTotal = Math.max(
              ...Object.values(summary.perDim).map(d => d.total)
            );
            const gap = summary.totalConfirmed - dimTotal;
            return gap > 0
              ? `（其中 ${gap} 场逐项命中数据待录入，仅汇总赔率/胜率不受影响）`
              : '统计';
          })()}
          。
        </p>
        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-5">
          {DIMENSIONS.map(d => {
            const stat = summary.perDim[d.key];
            return (
              <div key={d.key}>
                <div className="text-sm text-ink mb-1">{d.label}</div>
                <DimBar rate={stat.rate} hits={stat.hits} total={stat.total} />
              </div>
            );
          })}
        </div>
      </section>

      {/* Strip */}
      {confirmedRows.length > 0 && (
        <section className="rounded-2xl border border-divider bg-deep p-5 sm:p-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-base font-semibold text-ink">已确认场次命中分布</h2>
            <div className="flex items-center gap-3 text-[11px] text-muted">
              <Legend className="bg-gold" label="3+" />
              <Legend className="bg-turf" label="2" />
              <Legend className="bg-turf/40" label="1" />
              <Legend className="bg-miss" label="0" />
            </div>
          </div>
          <MatchStrip rows={confirmedRows} />
          <div className="mt-2 flex justify-between text-[11px] text-muted">
            <span>较早</span>
            <span>较新</span>
          </div>
        </section>
      )}

      {/* Per-match table */}
      <section className="rounded-2xl border border-divider bg-deep overflow-hidden">
        <div className="px-5 py-4 border-b border-divider">
          <h2 className="text-base font-semibold text-ink">所有场次预测明细</h2>
          <p className="text-xs text-muted mt-0.5">绿色 = 命中实际赛果 · 灰色 = 未命中。</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-elevated text-[11px] uppercase tracking-wider text-muted">
                <th className="text-left px-4 py-3 font-medium">比赛</th>
                <th className="text-center px-3 py-3 font-medium">胜平负</th>
                {DIMENSIONS.map(d => (
                  <th key={d.key} className="text-center px-3 py-3 font-medium">
                    {d.label}
                  </th>
                ))}
                <th className="text-center px-4 py-3 font-medium">命中</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ match, prediction }) => {
                const isPending = match.status === '待比赛';
                const hits = prediction?.total_hits ?? null;
                return (
                  <tr
                    key={match.id}
                    className="border-t border-divider hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-4 py-3 align-middle">
                      <Link
                        to={`/matches/${encodeURIComponent(match.id)}`}
                        className="block group"
                      >
                        <div className="text-ink group-hover:text-gold transition-colors">
                          {match.teams}
                        </div>
                        <div className="text-[11px] text-muted mt-0.5">
                          {match.id} · {match.time}
                          {match.actualScore ? ` · ${match.actualScore}` : ' · 待比赛'}
                        </div>
                      </Link>
                    </td>
                    {prediction ? (
                      <>
                        <td className="px-3 py-3 align-middle text-center text-ink">
                          {prediction.spf}
                        </td>
                        {DIMENSIONS.map(d => {
                          const hit = prediction[d.key];
                          const v = dimValue(prediction, d.key);
                          if (isPending || hit === null) {
                            return (
                              <td
                                key={d.key}
                                className="px-3 py-3 align-middle text-center text-muted"
                              >
                                {String(v)}
                              </td>
                            );
                          }
                          if (hit === '✅') {
                            return (
                              <td key={d.key} className="px-3 py-3 align-middle">
                                <div className="rounded-md mx-auto inline-flex items-center gap-1.5 px-2 py-1 text-turf bg-turf-soft border border-turf/30">
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
                                  <span className="font-mono">{String(v)}</span>
                                </div>
                              </td>
                            );
                          }
                          return (
                            <td
                              key={d.key}
                              className="px-3 py-3 align-middle text-center text-miss font-mono"
                            >
                              {String(v)}
                            </td>
                          );
                        })}
                        <td className="px-4 py-3 align-middle text-center">
                          {hits === null ? (
                            <span className="text-muted text-xs">—</span>
                          ) : (
                            <span
                              className={`font-mono font-bold ${
                                hits >= 3 ? 'text-gold' : hits >= 1 ? 'text-turf' : 'text-miss'
                              }`}
                            >
                              {hits}/4
                            </span>
                          )}
                        </td>
                      </>
                    ) : (
                      <td colSpan={6} className="px-4 py-3 text-center text-muted">
                        无数据
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <AiChainBetsSection ai={decoded} />
    </div>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-2.5 w-2.5 rounded-sm ${className}`} />
      <span>{label}</span>
    </span>
  );
}

function AiChainBetsSection({ ai }: { ai: string }) {
  const data = getChainBetsForAi(ai);
  const { totals, days } = data;
  const empty = totals.totalBets === 0;
  const shortName = (AI_SHORT as Record<string, string>)[ai] ?? ai.replace(/^AI-/, '');

  return (
    <section className="rounded-xl border border-divider bg-deep px-5 py-6 sm:px-7 sm:py-8">
      <header className="mb-5 flex flex-col gap-3 border-b border-divider/70 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-text-primary sm:text-xl">串关推荐明细</h2>
          <p className="mt-1 text-xs text-text-secondary sm:text-sm">
            {shortName} 在 2 串 1（稳胆串）/ 3 串 1（均衡串）/ 4 串 1（博高串）三种类型上的逐场推荐与命中情况。
          </p>
        </div>
        {!empty ? (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs sm:text-sm">
            <span className="text-text-secondary">
              推荐 <span className="font-semibold text-text-primary">{totals.totalBets}</span> 次
            </span>
            <span className="text-text-secondary">
              命中 <span className="font-semibold text-turf">{totals.totalHits}</span> 次
            </span>
            <span className="text-text-secondary">
              命中率 <span className="font-semibold text-text-primary">{formatPercent(totals.hitRate)}</span>
            </span>
            <span className="text-text-secondary">
              净盈亏{' '}
              <span className={`font-semibold ${totals.totalPnl >= 0 ? 'text-turf' : 'text-red-400'}`}>
                {formatPnl(totals.totalPnl)}
              </span>
            </span>
          </div>
        ) : null}
      </header>

      {empty ? (
        <div className="rounded-lg border border-dashed border-divider bg-night/40 px-5 py-8 text-center text-sm text-text-secondary">
          暂未参与串关追踪
        </div>
      ) : (
        <div className="space-y-5">
          {days.map((day) => (
            <article key={day.date} className="rounded-lg border border-divider/70 bg-night/40 px-4 py-4 sm:px-5 sm:py-5">
              <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-divider/60 pb-2">
                <span className="text-base font-semibold text-text-primary tabular-nums">{day.date}</span>
                {day.matches.length > 0 ? (
                  <span className="text-xs text-text-secondary">参考赛事：{day.matches.join('、')}</span>
                ) : null}
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {day.bets.map((bet, i) => (
                  <AiChainBetCard key={`${bet.type}-${i}`} bet={bet} />
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function AiChainBetCard({ bet }: { bet: ChainBet }) {
  const hit = bet.hit;
  return (
    <div
      className={`flex h-full flex-col gap-3 rounded-md border px-3.5 py-3 transition-colors ${
        hit
          ? 'border-gold/55 bg-gold-soft/40 shadow-[0_0_0_1px_rgba(245,194,66,0.18)_inset]'
          : 'border-divider bg-night/30'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-0.5">
          <div className={`text-sm font-semibold ${hit ? 'text-gold' : 'text-text-secondary'}`}>{bet.type}</div>
          <div className="text-[11px] tabular-nums text-text-secondary">
            赔率 {bet.odds.toFixed(2)} × 2 元
          </div>
        </div>
        <span
          className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
            hit ? 'bg-turf text-night' : 'bg-divider text-text-secondary'
          }`}
        >
          {hit ? '✓' : '✗'}
        </span>
      </div>

      <ul className="space-y-1.5">
        {bet.selections.map((s, idx) => (
          <AiChainSelectionRow key={idx} selection={s} />
        ))}
      </ul>

      <div className="mt-auto flex items-center justify-between border-t border-divider/60 pt-2 text-xs">
        <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${hit ? 'bg-turf-soft text-turf' : 'bg-night/60 text-text-secondary'}`}>
          {hit ? '命中' : '未中'}
        </span>
        <span className={`tabular-nums font-semibold ${bet.pnl >= 0 ? 'text-turf' : 'text-red-400'}`}>
          {formatPnl(bet.pnl)} ({formatYuan(bet.pnl)})
        </span>
      </div>
    </div>
  );
}

function AiChainSelectionRow({ selection }: { selection: ChainBetSelection }) {
  const ok = selection.hit === true;
  return (
    <li className="flex items-start gap-2 text-[11px] leading-snug text-text-secondary">
      <span
        className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[10px] font-bold ${
          ok ? 'bg-turf-soft text-turf' : 'bg-night/60 text-text-secondary line-through decoration-divider'
        }`}
      >
        {ok ? '✓' : '✗'}
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
