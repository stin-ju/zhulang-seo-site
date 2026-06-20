import './index.css';
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { fetchRawData } from './lib/dataFetcher';
import { initializeData } from './lib/data';

type LoadState =
  | { status: 'loading' }
  | { status: 'ready' }
  | { status: 'error'; message: string };

function Bootstrap() {
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await fetchRawData();
        if (cancelled) return;
        initializeData(raw);
        setState({ status: 'ready' });
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setState({ status: 'error', message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === 'loading') {
    return <BootstrapLoading />;
  }

  if (state.status === 'error') {
    return <BootstrapError message={state.message} />;
  }

  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  );
}

function BootstrapLoading() {
  return (
    <div className="min-h-screen bg-night text-ink flex items-center justify-center">
      <div className="text-center space-y-4">
        <div className="inline-flex h-12 w-12 items-center justify-center">
          <span className="block h-12 w-12 rounded-full border-2 border-gold/30 border-t-gold animate-spin" />
        </div>
        <div className="text-sm text-muted tracking-wide">
          正在从数据库加载赛事与 AI 数据…
        </div>
      </div>
    </div>
  );
}

function BootstrapError({ message }: { message: string }) {
  return (
    <div className="min-h-screen bg-night text-ink flex items-center justify-center px-6">
      <div className="max-w-lg w-full rounded-xl border border-miss/40 bg-bg-deep/80 p-6 space-y-4">
        <div className="text-lg font-semibold text-gold">数据加载失败</div>
        <div className="text-sm text-muted leading-relaxed">
          数据库暂时无法访问，请稍后刷新页面重试。
        </div>
        <pre className="text-[11px] leading-relaxed text-miss whitespace-pre-wrap break-all bg-night/60 border border-divider rounded-lg p-3">
{message}
        </pre>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex items-center justify-center rounded-lg border border-gold/40 bg-gold-soft px-4 py-2 text-sm text-gold hover:bg-gold/15 transition"
        >
          重新加载
        </button>
      </div>
    </div>
  );
}

const root = document.getElementById('app');
if (!root) {
  throw new Error('Root element #app not found');
}

createRoot(root).render(
  <StrictMode>
    <Bootstrap />
  </StrictMode>
);
