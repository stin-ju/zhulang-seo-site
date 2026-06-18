import { NavLink, Outlet } from 'react-router-dom';
import { totalMatches, totalConfirmed } from '../lib/data';

const NAV_ITEMS: { to: string; label: string; end?: boolean }[] = [
  { to: '/', label: '排行榜', end: true },
  { to: '/matches', label: '比赛' },
  { to: '/ai', label: 'AI' },
  { to: '/betting', label: '模拟投注' },
];

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-30 backdrop-blur bg-night/75 border-b border-divider">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 h-16 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-3 group">
            <span className="relative inline-flex h-8 w-8 items-center justify-center rounded-md bg-gold-soft border border-gold/40">
              <span className="text-gold font-bold text-base">AI</span>
            </span>
            <span className="text-ink font-semibold tracking-tight">
              AI 赛事预测<span className="text-gold">大竞赛</span>
            </span>
          </NavLink>
          <nav className="flex items-center gap-1 text-sm">
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md transition-colors duration-200 ease-soft ${
                    isActive
                      ? 'text-gold bg-gold-soft border border-gold/30'
                      : 'text-muted hover:text-ink hover:bg-white/5 border border-transparent'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-4 sm:px-6 py-8 sm:py-10">
        <Outlet />
      </main>

      <footer className="border-t border-divider mt-12">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-muted">
          <span>共收录 {totalMatches} 场比赛 · 已确认 {totalConfirmed} 场</span>
          <span className="opacity-70">仅作 AI 能力评测展示。模拟投注每注固定 2 元，与真实投注/赔率/赌博无关。</span>
        </div>
      </footer>
    </div>
  );
}
