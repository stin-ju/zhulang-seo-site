import { Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import LeaderboardPage from './pages/LeaderboardPage';
import MatchListPage from './pages/MatchListPage';
import MatchDetailPage from './pages/MatchDetailPage';
import AiDetailPage from './pages/AiDetailPage';
import AiListPage from './pages/AiListPage';
import BettingPage from './pages/BettingPage';
import NotFoundPage from './pages/NotFoundPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<LeaderboardPage />} />
        <Route path="/matches" element={<MatchListPage />} />
        <Route path="/matches/:id" element={<MatchDetailPage />} />
        <Route path="/ai" element={<AiListPage />} />
        <Route path="/ai/:name" element={<AiDetailPage />} />
        <Route path="/betting" element={<BettingPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
