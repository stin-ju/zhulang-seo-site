import { Link, useParams } from 'react-router-dom';
import {
  AI_LIST,
  AI_SHORT,
  DIMENSIONS,
  formatPercent,
  getAiMatches,
  getAiSummary,
  type AiMatchRow,
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
                summary.rank === 1
                  ? 'bg-gold text-night'
                  : 'bg-elevated text-ink border border-divider'
              }`}
            >
              #{summary.rank}
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-muted">AI 选手</div>
              <div className="text-2xl sm:text-3xl font-bold text-ink mt-1">
                {AI_SHORT[summary.ai]}
              </div>
              <div className="text-sm text-muted">{summary.ai}</div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-widest text-muted">综合命中率</div>
              <div
                className={`font-mono text-4xl sm:text-5xl font-bold mt-1 leading-none ${
                  summary.rank === 1 ? 'text-gold' : 'text-ink'
                }`}
              >
                {formatPercent(summary.hitRate)}
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
              <div className="text-[11px] uppercase tracking-widest text-muted">已确认场次</div>
              <div className="font-mono text-2xl sm:text-3xl text-ink mt-1">
                {summary.totalConfirmed}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Per-dimension stats */}
      <section className="rounded-2xl border border-divider bg-deep p-5 sm:p-6">
        <h2 className="text-base font-semibold text-ink">各维度命中率</h2>
        <p className="text-xs text-muted mt-1">基于 {summary.totalConfirmed} 场已确认比赛统计。</p>
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
