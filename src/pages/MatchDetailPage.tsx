import { Link, useParams } from 'react-router-dom';
import {
  AI_LIST,
  AI_SHORT,
  DIMENSIONS,
  formatHandicap,
  getMatchById,
  type AiName,
  type DimensionKey,
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
        <div className="rounded-md px-2 py-1.5 text-center text-sm text-muted bg-white/[0.02] border border-divider">
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

function SpfCell({ value }: { value: string }) {
  return (
    <td className="px-3 py-3 align-middle">
      <div className="rounded-md px-2 py-1.5 text-center text-sm text-ink bg-white/[0.03] border border-divider">
        {value}
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

export default function MatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const match = id ? getMatchById(decodeURIComponent(id)) : undefined;

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
  const [home, away] = match.teams.split(/\s*VS\s*/i);

  // Order predictions by AI_LIST
  const predByAi = new Map<string, Prediction>();
  for (const p of match.predictions) predByAi.set(p.ai, p);

  const rows = AI_LIST.map<{ ai: AiName; pred: Prediction | undefined }>(ai => ({
    ai,
    pred: predByAi.get(ai),
  }));

  const bestHits = rows.reduce((max, r) => Math.max(max, r.pred?.total_hits ?? 0), 0);

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

      {/* Prediction matrix */}
      <section className="rounded-2xl border border-divider bg-deep overflow-hidden">
        <div className="px-5 py-4 flex items-center justify-between border-b border-divider">
          <div>
            <h2 className="text-base font-semibold text-ink">7 AI 预测对比</h2>
            <p className="text-xs text-muted mt-0.5">
              {isPending
                ? '本场尚未开赛，暂无命中标记。'
                : '绿色 = 命中实际赛果，灰色 = 未命中。'}
            </p>
          </div>
          {!isPending && (
            <div className="text-xs text-muted">
              本场最佳：<span className="font-mono text-gold">{bestHits} / 4</span>
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
                const hits = pred?.total_hits ?? null;
                const isBest = !isPending && hits !== null && hits === bestHits && hits > 0;
                return (
                  <tr
                    key={ai}
                    className="border-t border-divider hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-4 py-3 align-middle">
                      <Link
                        to={`/ai/${encodeURIComponent(ai)}`}
                        className="flex items-center gap-2 group"
                      >
                        <span className="text-ink font-medium group-hover:text-gold transition-colors">
                          {AI_SHORT[ai]}
                        </span>
                        <span className="text-[11px] text-muted">{ai}</span>
                      </Link>
                    </td>
                    {pred ? (
                      <>
                        <SpfCell value={pred.spf} />
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
                              <span className="text-muted text-sm font-normal"> / 4</span>
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
            return (
              <article
                key={ai}
                className="px-5 py-5 hover:bg-white/[0.02] transition-colors"
              >
                <header className="flex items-center justify-between gap-3 mb-3">
                  <Link
                    to={`/ai/${encodeURIComponent(ai)}`}
                    className="flex items-center gap-2 group min-w-0"
                  >
                    <span
                      className={`inline-flex items-center justify-center h-7 w-7 rounded-full text-[11px] font-bold border ${
                        isBest
                          ? 'border-gold/60 text-gold bg-gold-soft'
                          : 'border-divider text-muted bg-white/[0.03]'
                      }`}
                    >
                      {AI_SHORT[ai].slice(0, 2)}
                    </span>
                    <span className="text-ink font-medium truncate group-hover:text-gold transition-colors">
                      {AI_SHORT[ai]}
                    </span>
                    <span className="text-[11px] text-muted truncate">{ai}</span>
                  </Link>
                  {!isPending && hits !== null && (
                    <span
                      className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] border font-mono ${
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
                </header>
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
    </div>
  );
}
