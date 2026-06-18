import { Link } from 'react-router-dom';
import { AI_SHORT, aiSummaries, formatPercent } from '../lib/data';

export default function AiListPage() {
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl sm:text-3xl font-bold text-ink">AI 选手</h1>
        <p className="text-muted text-sm mt-1">
          点击任一选手查看其在所有比赛中的预测明细与各维度命中率。
        </p>
      </header>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {aiSummaries.map(s => (
          <Link
            key={s.ai}
            to={`/ai/${encodeURIComponent(s.ai)}`}
            className="rounded-xl bg-card-gradient border border-divider hover:border-gold/40 transition-colors duration-200 ease-soft shadow-card p-5 group"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-base font-semibold text-ink truncate group-hover:text-gold transition-colors">
                  {AI_SHORT[s.ai]}
                </div>
                <div className="text-xs text-muted mt-0.5 truncate">{s.ai}</div>
              </div>
              <div
                className={`shrink-0 inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold ${
                  s.rank === 1
                    ? 'bg-gold text-night'
                    : 'bg-elevated text-muted border border-divider'
                }`}
              >
                #{s.rank}
              </div>
            </div>
            <div className="mt-4 flex items-baseline gap-2">
              <span className="font-mono text-3xl font-bold text-ink">
                {formatPercent(s.hitRate)}
              </span>
              <span className="text-xs text-muted">
                {s.totalHits} / {s.totalSlots} 命中
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
