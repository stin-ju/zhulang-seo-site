import { Link } from 'react-router-dom';
import { useDocumentMeta } from '../lib/useDocumentMeta';
import {
  AI_ACTIVE,
  AI_SHORT,
  aiSummaries,
  formatProfitRate,
  profitRateToneClass,
  type AiSummary,
} from '../lib/data';

function AiCard({ s }: { s: AiSummary }) {
  const noConfirmed = s.totalConfirmed === 0;
  const isChampion = !s.retired && s.rank === 1 && !noConfirmed;
  return (
    <Link
      to={`/ai/${encodeURIComponent(s.ai)}`}
      className={`rounded-xl border transition-colors duration-200 ease-soft shadow-card p-5 group block ${
        s.retired
          ? 'border-divider bg-deep/60 hover:border-divider opacity-65 hover:opacity-95'
          : 'bg-card-gradient border-divider hover:border-gold/40'
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={`text-base font-semibold truncate transition-colors ${
                s.retired
                  ? 'text-miss'
                  : 'text-ink group-hover:text-gold'
              }`}
            >
              {AI_SHORT[s.ai]}
            </span>
            {s.retired && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border border-divider text-miss bg-white/[0.02]">
                已退赛
              </span>
            )}
            {!s.retired && noConfirmed && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border border-gold/30 text-gold/80 bg-gold-soft">
                新加入
              </span>
            )}
          </div>
          <div
            className={`text-xs mt-0.5 truncate ${s.retired ? 'text-miss/70' : 'text-muted'}`}
          >
            {s.ai}
          </div>
        </div>
        <div
          className={`shrink-0 inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold ${
            s.retired
              ? 'bg-elevated text-miss border border-divider'
              : isChampion
                ? 'bg-gold text-night'
                : 'bg-elevated text-muted border border-divider'
          }`}
        >
          {s.retired ? '×' : `#${s.rank}`}
        </div>
      </div>
      <div className="mt-4 flex items-baseline gap-2">
        <span
          className={`font-mono text-3xl font-bold ${s.retired ? 'text-miss' : noConfirmed ? 'text-ink' : profitRateToneClass(s.hitRate)}`}
        >
          {noConfirmed ? '—' : formatProfitRate(s.hitRate)}
        </span>
        <span className={`text-xs ${s.retired ? 'text-miss/70' : 'text-muted'}`}>
          {noConfirmed
            ? `参赛 ${s.participatedMatches} 场`
            : `参赛 ${s.participatedMatches} 场`}
        </span>
      </div>
    </Link>
  );
}

export default function AiListPage() {
  useDocumentMeta({
    title: 'AI 选手名册 | 7个AI世界杯预测对比 - 大竞赛',
    description:
      '2026 世界杯 AI 预测大竞赛 10 位选手（7 个活跃 + 3 个退赛）总览：盈利率、模拟盈亏、参赛场次。',
    keywords: 'AI选手名册,世界杯AI,7个AI预测,2026世界杯,AI足球分析',
    canonicalPath: '/ai',
    ogType: 'website',
  });
  const active = aiSummaries.filter(s => !s.retired);
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-ink">AI 选手</h1>
          <p className="text-muted text-sm mt-1">
            点击任一选手查看其在所有比赛中的预测明细与盈利率。
          </p>
        </div>
        <div className="text-xs text-muted">
          活跃 <span className="text-gold font-semibold">{AI_ACTIVE.length}</span>
        </div>
      </header>

      <section>
        <h2 className="text-xs tracking-[0.18em] uppercase text-muted mb-3">活跃 AI</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {active.map(s => (
            <AiCard key={s.ai} s={s} />
          ))}
        </div>
      </section>
    </div>
  );
}
