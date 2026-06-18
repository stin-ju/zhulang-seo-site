import { Link } from 'react-router-dom';
import { matches, formatHandicap, type MatchView } from '../lib/data';

function StatusPill({ status }: { status: MatchView['status'] }) {
  if (status === '已确认') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] bg-turf-soft text-turf border border-turf/30">
        <span className="h-1.5 w-1.5 rounded-full bg-turf" />
        已确认
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] bg-white/5 text-muted border border-divider">
      <span className="h-1.5 w-1.5 rounded-full bg-muted" />
      待比赛
    </span>
  );
}

function MatchCard({ m }: { m: MatchView }) {
  const isDone = m.status === '已确认';
  const [home, away] = m.teams.split(/\s*VS\s*/i);
  return (
    <Link
      to={`/matches/${encodeURIComponent(m.id)}`}
      className={`relative block rounded-xl border bg-card-gradient shadow-card p-5 transition-all duration-200 ease-soft hover:-translate-y-0.5 ${
        isDone
          ? 'border-gold/25 hover:border-gold/55'
          : 'border-divider hover:border-white/15 opacity-90'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-muted">{m.id}</span>
          <span className="text-[11px] text-muted">让球 {formatHandicap(m.handicap)}</span>
        </div>
        <StatusPill status={m.status} />
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="text-right">
          <div className="text-base sm:text-lg font-semibold text-ink truncate">
            {home ?? m.teams}
          </div>
        </div>
        <div className="text-center">
          {isDone && m.actualScore ? (
            <div className="font-mono text-2xl sm:text-3xl font-bold text-gold whitespace-nowrap">
              {m.actualScore.replace(':', ' : ')}
            </div>
          ) : (
            <div className="font-mono text-base text-muted">VS</div>
          )}
        </div>
        <div className="text-left">
          <div className="text-base sm:text-lg font-semibold text-ink truncate">
            {away ?? ''}
          </div>
        </div>
      </div>
      <div className="mt-3 text-[11px] text-muted flex items-center justify-between">
        <span>{m.time}</span>
        <span className="text-gold/80 group-hover:text-gold">查看详情 →</span>
      </div>
    </Link>
  );
}

export default function MatchListPage() {
  const upcoming = matches.filter(m => m.status === '待比赛');
  const confirmed = matches.filter(m => m.status === '已确认');

  return (
    <div className="space-y-10">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-ink">比赛列表</h1>
          <p className="text-muted text-sm mt-1">
            按时间倒序，最新比赛优先展示。点击进入查看 7 个 AI 的对该场比赛的预测对比。
          </p>
        </div>
        <div className="text-xs text-muted">
          共 <span className="font-mono text-ink">{matches.length}</span> 场，已确认{' '}
          <span className="font-mono text-turf">{confirmed.length}</span> 场
        </div>
      </header>

      {upcoming.length > 0 && (
        <section>
          <h2 className="text-sm tracking-[0.18em] uppercase text-muted mb-3">
            待比赛 · Upcoming ({upcoming.length})
          </h2>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            {upcoming.map(m => (
              <MatchCard key={m.id} m={m} />
            ))}
          </div>
        </section>
      )}

      {confirmed.length > 0 && (
        <section>
          <h2 className="text-sm tracking-[0.18em] uppercase text-muted mb-3">
            已确认 · Confirmed ({confirmed.length})
          </h2>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            {confirmed.map(m => (
              <MatchCard key={m.id} m={m} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
