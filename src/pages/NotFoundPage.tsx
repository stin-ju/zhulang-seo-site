import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="text-center py-24">
      <div className="font-mono text-7xl font-bold text-gold">404</div>
      <p className="mt-4 text-muted">页面不存在</p>
      <Link
        to="/"
        className="inline-block mt-6 px-4 py-2 rounded-md border border-gold/40 text-gold hover:bg-gold-soft transition-colors"
      >
        返回排行榜
      </Link>
    </div>
  );
}
