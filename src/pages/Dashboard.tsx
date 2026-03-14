import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  BarChart, Bar, PieChart, Pie, Cell, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip as ReTooltip, ResponsiveContainer, Legend
} from 'recharts';
import { useAuth } from '@/contexts/ModernAuthContext';
import api from '@/services/api';
import { Opportunity } from '@/types/dealerscope';

// ─── Icons (lucide-react is in package.json) ──────────────────────────────────
import {
  LayoutDashboard, Crosshair, Navigation, BarChart2, Settings, Target,
  ExternalLink, RefreshCw, CheckCircle, XCircle, AlertCircle,
  TrendingUp, Car, MapPin, Clock, Star, Filter, ChevronDown,
  ThumbsUp, ThumbsDown, Bookmark, LogOut, User, Wifi, WifiOff
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import SniperScopeDashboard from '@/components/SniperScopeDashboard';

// ─── Types ────────────────────────────────────────────────────────────────────
type Tab = 'dashboard' | 'crosshair' | 'sniper' | 'rover' | 'analytics' | 'settings';

interface ScraperSource {
  name: string;
  last_run: string | null;
  count: number;
}

type DashboardOpportunity = Opportunity & { created_at?: string };

interface RoverRecommendation {
  id?: string;
  opportunity_id?: string;
  make?: string;
  model?: string;
  year?: number;
  mileage?: number;
  current_bid?: number;
  estimated_sale_price?: number;
  score?: number;
  dos_score?: number;
  gross_margin?: number;
  potential_profit?: number;
  profit_margin?: number;
  state?: string;
  source_site?: string;
  auction_end?: string;
  vin?: string;
  total_cost?: number;
  risk_score?: number;
  transportation_cost?: number;
  fees_cost?: number;
  profit?: number;
  roi?: number;
  roi_percentage?: number;
  confidence_score?: number;
  match_pct?: number;
  vehicle?: Partial<Opportunity['vehicle']>;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function dosColor(score: number | null | undefined): string {
  const s = score ?? 0;
  if (s >= 80) return 'bg-emerald-500 text-white';
  if (s >= 65) return 'bg-yellow-500 text-black';
  if (s >= 40) return 'bg-orange-500 text-white';
  return 'bg-gray-600 text-gray-200';
}

function dosLabel(score: number | null | undefined): string {
  const s = score ?? 0;
  if (s >= 80) return 'HOT';
  if (s >= 65) return 'GOOD';
  if (s >= 40) return 'OK';
  return 'COLD';
}

function gradeColor(grade: Opportunity['investment_grade']): string {
  if (grade === 'Platinum') return 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30';
  if (grade === 'Gold') return 'bg-amber-500/15 text-amber-300 border border-amber-500/30';
  if (grade === 'Silver') return 'bg-slate-400/15 text-slate-200 border border-slate-400/30';
  if (grade === 'Bronze') return 'bg-orange-500/15 text-orange-300 border border-orange-500/30';
  return 'bg-gray-700 text-gray-200 border border-gray-600';
}

function fmt$(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `${n.toFixed(1)}%`;
}

function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function timeAgo(s: string | null | undefined): string {
  if (!s) return 'Never';
  const diff = Date.now() - new Date(s).getTime();
  const h = Math.floor(diff / 3600000);
  const m = Math.floor(diff / 60000);
  if (h > 24) return `${Math.floor(h / 24)}d ago`;
  if (h > 0) return `${h}h ago`;
  if (m > 0) return `${m}m ago`;
  return 'Just now';
}

// ─── Deal Card ────────────────────────────────────────────────────────────────
const DealCard = ({
  deal,
  onAction,
  onSendToSniperScope
}: {
  deal: Opportunity;
  onAction?: (deal: Opportunity, action: 'view' | 'save' | 'pass') => void;
  onSendToSniperScope?: (deal: Opportunity) => void;
}) => (
  <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 hover:border-emerald-500/40 transition-colors">
    <div className="flex items-start justify-between mb-3">
      <div>
        <h3 className="font-semibold text-white text-sm">
          {deal.year} {deal.make} {deal.model}
        </h3>
        {deal.mileage && (
          <p className="text-xs text-gray-400 mt-0.5">{deal.mileage.toLocaleString()} mi</p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1">
        <span className={`text-[11px] font-semibold px-2 py-1 rounded-md ${gradeColor(deal.investment_grade)}`}>
          {deal.investment_grade || 'Watch'}
        </span>
        <span className={`text-xs font-bold px-2 py-1 rounded-md ${dosColor(deal.score)}`}>
          {deal.score ?? '—'} {dosLabel(deal.score)}
        </span>
      </div>
    </div>

    <div className="grid grid-cols-2 gap-2 mb-3">
      <div>
        <p className="text-xs text-gray-500">Bid</p>
        <p className="text-sm font-medium text-white">{fmt$(deal.current_bid)}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500">Gross</p>
        <p className={`text-sm font-medium ${(deal.profit_margin || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {deal.profit_margin != null ? fmt$(deal.profit_margin) : '—'}
        </p>
      </div>
      <div>
        <p className="text-xs text-gray-500">Retail CtM</p>
        <p className="text-sm text-gray-300">{fmtPct(deal.retail_ctm_pct)}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500">ROI / Day</p>
        <p className="text-sm text-gray-300">{fmt$(deal.roi_per_day)}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500">Days to Sale</p>
        <p className="text-sm text-gray-300">{deal.estimated_days_to_sale ?? '—'}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500">Headroom</p>
        <p className={`text-sm font-medium ${(deal.bid_headroom || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {fmt$(deal.bid_headroom)}
        </p>
      </div>
      <div>
        <p className="text-xs text-gray-500">Max Bid</p>
        <p className="text-sm text-gray-300">{fmt$(deal.max_bid)}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500">State / Source</p>
        <p className="text-sm text-gray-300 truncate">{[deal.state, deal.source_site].filter(Boolean).join(' • ') || '—'}</p>
      </div>
    </div>

    {deal.auction_end && (
      <div className="flex items-center gap-1 text-xs text-gray-500 mb-3">
        <Clock className="h-3 w-3" />
        <span>Ends {fmtDate(deal.auction_end)}</span>
      </div>
    )}

    <div className="flex items-center gap-2">
      {onSendToSniperScope && deal.id && (
        <button
          onClick={() => onSendToSniperScope(deal)}
          className="flex-1 flex items-center justify-center gap-1 text-xs bg-emerald-600 hover:bg-emerald-500 text-white py-1.5 px-2 rounded-lg transition-colors"
        >
          <Target className="h-3 w-3" />
          Send to SniperScope
        </button>
      )}
      {deal.vin && (
        <a
          href={`https://www.google.com/search?q=${encodeURIComponent(`${deal.year} ${deal.make} ${deal.model} ${deal.vin}`)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 flex items-center justify-center gap-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 py-1.5 px-2 rounded-lg transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
          View
        </a>
      )}
      {onAction && deal.id && (
        <>
          <button
            onClick={() => onAction(deal, 'save')}
            className="flex items-center gap-1 text-xs bg-gray-800 hover:bg-emerald-900/50 text-gray-300 hover:text-emerald-400 py-1.5 px-2 rounded-lg transition-colors"
          >
            <Bookmark className="h-3 w-3" />
          </button>
          <button
            onClick={() => onAction(deal, 'pass')}
            className="flex items-center gap-1 text-xs bg-gray-800 hover:bg-red-900/50 text-gray-300 hover:text-red-400 py-1.5 px-2 rounded-lg transition-colors"
          >
            <ThumbsDown className="h-3 w-3" />
          </button>
        </>
      )}
    </div>
  </div>
);

// ─── Stat Card ────────────────────────────────────────────────────────────────
const StatCard = ({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) => (
  <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
    <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
    <p className={`text-2xl font-bold mt-1 ${accent ? 'text-emerald-400' : 'text-white'}`}>{value}</p>
    {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
  </div>
);

// ─── TAB 1: Dashboard ─────────────────────────────────────────────────────────
const DashboardTab = () => {
  const [metrics, setMetrics] = useState({
    total_today: 0,
    hot_deals: 0,
    platinum_deals: 0,
    avg_margin: 0,
    avg_roi_day: 0,
    top_score: 0
  });
  const [hotDeals, setHotDeals] = useState<Opportunity[]>([]);
  const [sources, setSources] = useState<ScraperSource[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, h, s] = await Promise.all([
        api.getDashboardMetrics(),
        api.getHotDeals(80, 5),
        api.getScraperSources()
      ]);
      setMetrics(m);
      setHotDeals(h);
      setSources(s);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isPipelineLive = sources.some(s => {
    if (!s.last_run) return false;
    return (Date.now() - new Date(s.last_run).getTime()) < 4 * 3600 * 1000;
  });

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">DealerScope</h1>
          <p className="text-sm text-gray-400">Vehicle arbitrage intelligence</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border ${
            isPipelineLive
              ? 'bg-emerald-950 border-emerald-700 text-emerald-400'
              : 'bg-gray-800 border-gray-700 text-gray-400'
          }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${isPipelineLive ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'}`} />
            {isPipelineLive ? 'Pipeline Live' : 'Pipeline Idle'}
          </span>
          <button onClick={load} disabled={loading} className="text-gray-400 hover:text-white transition-colors">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Deals Today" value={metrics.total_today.toString()} />
        <StatCard label="Platinum Deals" value={metrics.platinum_deals.toString()} sub="Grade-first watchlist" accent />
        <StatCard label="Avg ROI / Day" value={fmt$(metrics.avg_roi_day)} />
        <StatCard label="Top Score" value={fmtNum(metrics.top_score, 1)} sub={`${metrics.hot_deals} score ≥ 80`} accent />
      </div>

      {/* Hot Deals */}
      <div>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-3">
          Top Opportunities — Platinum first, then highest score
        </h2>
        {loading ? (
          <div className="text-center py-8 text-gray-500">Loading deals...</div>
        ) : hotDeals.length === 0 ? (
          <div className="text-center py-8 text-gray-500 bg-gray-900 rounded-xl border border-gray-800">
            No high-priority opportunities right now. Pipeline may be between runs.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {hotDeals.map(deal => <DealCard key={deal.id} deal={deal} />)}
          </div>
        )}
      </div>

      {/* Pipeline Status */}
      <div>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-3">
          Scraper Sources
        </h2>
        <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
          {sources.length === 0 && !loading ? (
            <div className="p-4 text-gray-500 text-sm text-center">No source data available</div>
          ) : sources.map(src => {
            const fresh = src.last_run && (Date.now() - new Date(src.last_run).getTime()) < 4 * 3600 * 1000;
            return (
              <div key={src.name} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className={`h-2 w-2 rounded-full ${fresh ? 'bg-emerald-400' : 'bg-gray-600'}`} />
                  <span className="text-sm text-white font-medium">{src.name}</span>
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span>{src.count} deals</span>
                  <span>{timeAgo(src.last_run)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ─── TAB 2: Crosshair ─────────────────────────────────────────────────────────
const CrosshairTab = () => {
  const [filters, setFilters] = useState({
    make: '', model: '',
    yearMin: '', yearMax: '',
    state: '',
    minScore: '',
    minBid: '',
    maxBid: ''
  });
  const [results, setResults] = useState<Opportunity[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  const search = async () => {
    setLoading(true);
    setSearched(true);
    try {
      const { data, total: t } = await api.searchCrosshairOpportunities({
        make: filters.make || undefined,
        model: filters.model || undefined,
        yearMin: filters.yearMin ? parseInt(filters.yearMin) : undefined,
        yearMax: filters.yearMax ? parseInt(filters.yearMax) : undefined,
        state: filters.state || undefined,
        minScore: filters.minScore ? parseInt(filters.minScore) : undefined,
        minPrice: filters.minBid ? parseInt(filters.minBid) : undefined,
        maxPrice: filters.maxBid ? parseInt(filters.maxBid) : undefined,
        limit: 50
      });
      setResults(data);
      setTotal(t);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleSendToSniperScope = (deal: Opportunity) => {
    if (!deal.id) return;
    const next = new URLSearchParams(searchParams);
    next.set('tab', 'sniper');
    next.set('dealId', deal.id);
    setSearchParams(next);
  };

  const inputCls = "w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-emerald-500";
  const labelCls = "block text-xs text-gray-400 mb-1";

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Crosshair</h2>
        <p className="text-sm text-gray-400">Filter and find specific deals</p>
      </div>

      {/* Filter panel */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-4">
          <div>
            <label className={labelCls}>Make</label>
            <input className={inputCls} placeholder="e.g. Ford" value={filters.make}
              onChange={e => setFilters(f => ({ ...f, make: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>Model</label>
            <input className={inputCls} placeholder="e.g. F-150" value={filters.model}
              onChange={e => setFilters(f => ({ ...f, model: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>Year Min</label>
            <input className={inputCls} type="number" placeholder="2015" value={filters.yearMin}
              onChange={e => setFilters(f => ({ ...f, yearMin: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>Year Max</label>
            <input className={inputCls} type="number" placeholder="2024" value={filters.yearMax}
              onChange={e => setFilters(f => ({ ...f, yearMax: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>Min DOS Score</label>
            <input className={inputCls} type="number" placeholder="65" value={filters.minScore}
              onChange={e => setFilters(f => ({ ...f, minScore: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>State</label>
            <input className={inputCls} placeholder="CA" value={filters.state}
              onChange={e => setFilters(f => ({ ...f, state: e.target.value.toUpperCase() }))} />
          </div>
          <div>
            <label className={labelCls}>Bid Min ($)</label>
            <input className={inputCls} type="number" placeholder="5000" value={filters.minBid}
              onChange={e => setFilters(f => ({ ...f, minBid: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>Bid Max ($)</label>
            <input className={inputCls} type="number" placeholder="25000" value={filters.maxBid}
              onChange={e => setFilters(f => ({ ...f, maxBid: e.target.value }))} />
          </div>
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-gray-500">Results are pulled from the live `opportunities` table and ranked by DOS score.</p>
          <button
            onClick={search}
            disabled={loading}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-medium px-6 py-2 rounded-lg transition-colors flex items-center gap-2"
          >
            <Filter className="h-4 w-4" />
            {loading ? 'Searching...' : 'Search Deals'}
          </button>
        </div>
      </div>

      {/* Results */}
      {searched && (
        <div>
          <p className="text-xs text-gray-500 mb-3">{total} results</p>
          {results.length === 0 ? (
            <div className="text-center py-8 text-gray-500 bg-gray-900 rounded-xl border border-gray-800">
              No deals match your filters
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {results.map(deal => (
                <DealCard
                  key={deal.id}
                  deal={deal}
                  onSendToSniperScope={handleSendToSniperScope}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── TAB 3: Rover ─────────────────────────────────────────────────────────────
const RoverTab = () => {
  const [recs, setRecs] = useState<RoverRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionedIds, setActionedIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getRoverRecommendations();
      setRecs(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (deal: Opportunity, action: 'view' | 'save' | 'pass') => {
    await api.trackRoverEvent(deal, action);
    setActionedIds(prev => new Set([...prev, `${deal.id}-${action}`]));
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Rover</h2>
          <p className="text-sm text-gray-400">Personalized recommendations based on your activity</p>
        </div>
        <button onClick={load} disabled={loading} className="text-gray-400 hover:text-white">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading recommendations...</div>
      ) : recs.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center">
          <Navigation className="h-10 w-10 text-gray-600 mx-auto mb-3" />
          <h3 className="text-white font-semibold mb-1">No recommendations yet</h3>
          <p className="text-gray-400 text-sm">
            Browse deals in the Dashboard and Crosshair tabs to train Rover on your preferences.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {recs.map((rec) => {
            const id = rec.id || rec.opportunity_id || Math.random().toString();
            const deal: Opportunity = {
              id,
              make: rec.make || rec.vehicle?.make || '',
              model: rec.model || rec.vehicle?.model || '',
              year: rec.year || rec.vehicle?.year || 0,
              mileage: rec.mileage,
              current_bid: rec.current_bid || 0,
              estimated_sale_price: rec.estimated_sale_price || 0,
              score: rec.score || rec.dos_score,
              profit_margin: rec.gross_margin ?? rec.potential_profit ?? rec.profit_margin ?? 0,
              state: rec.state,
              source_site: rec.source_site || '',
              auction_end: rec.auction_end,
              vin: rec.vin,
              total_cost: rec.total_cost || 0,
              risk_score: rec.risk_score || 0,
              transportation_cost: rec.transportation_cost || 0,
              fees_cost: rec.fees_cost || 0,
              profit: rec.potential_profit || 0,
              expected_price: rec.estimated_sale_price || 0,
              acquisition_cost: rec.total_cost || 0,
              roi: (rec.roi ?? rec.roi_percentage ?? 0) > 1 ? (rec.roi ?? rec.roi_percentage ?? 0) / 100 : (rec.roi ?? rec.roi_percentage ?? 0),
              confidence: rec.confidence_score || 0,
              vehicle: {
                make: rec.make || '',
                model: rec.model || '',
                year: rec.year || 0,
                vin: rec.vin || '',
                mileage: rec.mileage || 0
              }
            };
            return (
              <div key={id} className="relative">
                {rec.match_pct != null && (
                  <div className="absolute -top-2 -right-2 z-10 bg-emerald-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                    {rec.match_pct}% match
                  </div>
                )}
                <DealCard deal={deal} onAction={handleAction} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ─── TAB 4: Analytics ─────────────────────────────────────────────────────────
const AnalyticsTab = () => {
  const [allDeals, setAllDeals] = useState<DashboardOpportunity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.getOpportunities(1, 500);
        setAllDeals(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="p-6 text-center text-gray-500">Loading analytics...</div>;

  // DOS distribution
  const dosBuckets = [
    { range: '0–20', min: 0, max: 20 },
    { range: '20–40', min: 20, max: 40 },
    { range: '40–60', min: 40, max: 60 },
    { range: '60–80', min: 60, max: 80 },
    { range: '80–100', min: 80, max: 100 },
  ];
  const dosHist = dosBuckets.map(b => ({
    range: b.range,
    count: allDeals.filter(d => (d.score || 0) >= b.min && (d.score || 0) < b.max).length
  }));

  // Deals by state (top 10)
  const stateMap: Record<string, number> = {};
  allDeals.forEach(d => { if (d.state) stateMap[d.state] = (stateMap[d.state] || 0) + 1; });
  const stateData = Object.entries(stateMap).sort((a, b) => b[1] - a[1]).slice(0, 10)
    .map(([state, count]) => ({ state, count }));

  // Deals by source
  const srcMap: Record<string, number> = {};
  allDeals.forEach(d => { srcMap[d.source_site] = (srcMap[d.source_site] || 0) + 1; });
  const srcData = Object.entries(srcMap).map(([name, value]) => ({ name, value }));

  // Margin over time (last 14 days)
  const today = new Date();
  const marginByDay: Record<string, number[]> = {};
  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    marginByDay[key] = [];
  }
  allDeals.forEach((d) => {
    if (!d.created_at) return;
    const day = new Date(d.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (marginByDay[day]) marginByDay[day].push(d.profit_margin || 0);
  });
  const marginData = Object.entries(marginByDay).map(([day, vals]) => ({
    day,
    avg_margin: vals.length > 0 ? parseFloat((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1)) : null
  }));

  const COLORS = ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#84cc16'];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Analytics</h2>
        <p className="text-sm text-gray-400">{allDeals.length} active deals analyzed</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* DOS Distribution */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">DOS Score Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={dosHist}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="range" tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <ReTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} />
              <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Deals by State */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Deals by State (Top 10)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={stateData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <YAxis type="category" dataKey="state" tick={{ fill: '#9ca3af', fontSize: 12 }} width={30} />
              <ReTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} />
              <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Deals by Source */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Deals by Source</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={srcData} cx="50%" cy="50%" outerRadius={80} dataKey="value" nameKey="name" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {srcData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <ReTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Margin over time */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Avg Margin — Last 14 Days</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={marginData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="day" tick={{ fill: '#9ca3af', fontSize: 10 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} tickFormatter={(value: number) => fmt$(value)} />
              <ReTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} formatter={(value: number) => [fmt$(value), 'Avg Margin']} />
              <Line type="monotone" dataKey="avg_margin" stroke="#10b981" strokeWidth={2} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Summary stats */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide">Metric</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide">Value</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {[
              ['Total Active Deals', allDeals.length.toString()],
              ['DOS ≥ 80 (Hot)', allDeals.filter(d => (d.score || 0) >= 80).length.toString()],
              ['DOS ≥ 65 (Good+)', allDeals.filter(d => (d.score || 0) >= 65).length.toString()],
              ['Avg DOS Score', allDeals.length ? (allDeals.reduce((s, d) => s + (d.score || 0), 0) / allDeals.length).toFixed(1) : '—'],
              ['Avg Margin', allDeals.length ? fmt$(allDeals.reduce((s, d) => s + (d.profit_margin || 0), 0) / allDeals.length) : '—'],
              ['Unique Sources', Object.keys(srcMap).length.toString()],
              ['Unique States', Object.keys(stateMap).length.toString()],
            ].map(([label, value]) => (
              <tr key={label}>
                <td className="px-4 py-3 text-gray-300">{label}</td>
                <td className="px-4 py-3 text-right text-white font-medium">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ─── TAB 5: Settings ──────────────────────────────────────────────────────────
const SettingsTab = () => {
  const { user, signOut } = useAuth();
  const [railwayStatus, setRailwayStatus] = useState<{ status: string; latency?: number } | null>(null);
  const [supabaseStatus, setSupabaseStatus] = useState<{ status: string; latency?: number } | null>(null);
  const [sources, setSources] = useState<ScraperSource[]>([]);
  const [checking, setChecking] = useState(false);

  const checkConnections = useCallback(async () => {
    setChecking(true);
    // Use allSettled so each check is independent — one failure won't block others
    const [r, s, src] = await Promise.allSettled([
      api.checkRailwayHealth(),
      api.checkSupabaseHealth(),
      api.getScraperSources()
    ]);
    if (r.status === 'fulfilled') setRailwayStatus(r.value);
    else setRailwayStatus({ status: 'error' });
    if (s.status === 'fulfilled') setSupabaseStatus(s.value);
    else setSupabaseStatus({ status: 'error' });
    if (src.status === 'fulfilled') setSources(src.value);
    setChecking(false);
  }, []);

  useEffect(() => { checkConnections(); }, [checkConnections]);

  const StatusBadge = ({ status }: { status: string | null | undefined }) => {
    if (!status) return <span className="text-gray-500 text-xs">—</span>;
    const ok = status === 'healthy';
    return (
      <span className={`flex items-center gap-1 text-xs font-medium ${ok ? 'text-emerald-400' : 'text-red-400'}`}>
        {ok ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
        {ok ? 'Connected' : 'Error'}
      </span>
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Settings</h2>
        <p className="text-sm text-gray-400">System status and configuration</p>
      </div>

      {/* User */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <User className="h-4 w-4" /> Account
        </h3>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-white text-sm">{user?.email}</p>
            <p className="text-gray-500 text-xs mt-0.5">ID: {user?.id?.slice(0, 8)}...</p>
          </div>
          <button
            onClick={() => signOut()}
            className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 bg-red-950/30 hover:bg-red-950/50 px-3 py-1.5 rounded-lg transition-colors"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign Out
          </button>
        </div>
      </div>

      {/* API status */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">Connection Status</h3>
          <button onClick={checkConnections} disabled={checking} className="text-gray-400 hover:text-white">
            <RefreshCw className={`h-4 w-4 ${checking ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white">Railway API</p>
              <p className="text-xs text-gray-500">dealscan-insight-production.up.railway.app</p>
            </div>
            <div className="text-right">
              <StatusBadge status={railwayStatus?.status} />
              {railwayStatus?.latency && <p className="text-xs text-gray-500 mt-0.5">{railwayStatus.latency}ms</p>}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white">Supabase</p>
              <p className="text-xs text-gray-500">lbnxzvqppccajllsqaaw.supabase.co</p>
            </div>
            <div className="text-right">
              <StatusBadge status={supabaseStatus?.status} />
              {supabaseStatus?.latency && <p className="text-xs text-gray-500 mt-0.5">{supabaseStatus.latency}ms</p>}
            </div>
          </div>
        </div>
      </div>

      {/* Scraper sources */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Scraper Sources</h3>
        {sources.length === 0 ? (
          <p className="text-gray-500 text-sm">No source data</p>
        ) : (
          <div className="space-y-2">
            {sources.map(src => {
              const fresh = src.last_run && (Date.now() - new Date(src.last_run).getTime()) < 4 * 3600 * 1000;
              return (
                <div key={src.name} className="flex items-center justify-between py-1">
                  <div className="flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 rounded-full ${fresh ? 'bg-emerald-400' : 'bg-gray-600'}`} />
                    <span className="text-sm text-white">{src.name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{src.count} deals</span>
                    <span>{timeAgo(src.last_run)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Main Dashboard Shell ─────────────────────────────────────────────────────
const TABS: { id: Tab; label: string; Icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { id: 'crosshair', label: 'Crosshair', Icon: Crosshair },
  { id: 'sniper', label: 'SniperScope', Icon: Target },
  { id: 'rover', label: 'Rover', Icon: Navigation },
  { id: 'analytics', label: 'Analytics', Icon: BarChart2 },
  { id: 'settings', label: 'Settings', Icon: Settings },
];

function parseTab(tab: string | null): Tab {
  return TABS.some(({ id }) => id === tab) ? (tab as Tab) : 'dashboard';
}

export default function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseTab(searchParams.get('tab'));

  const navigateToTab = (tab: Tab) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', tab);
    setSearchParams(next);
  };

  const renderTab = () => {
    switch (activeTab) {
      case 'dashboard': return <DashboardTab />;
      case 'crosshair': return <CrosshairTab />;
      case 'sniper': return <SniperScopeDashboard />;
      case 'rover': return <RoverTab />;
      case 'analytics': return <AnalyticsTab />;
      case 'settings': return <SettingsTab />;
    }
  };

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
      {/* Sidebar — desktop */}
      <aside className="hidden md:flex flex-col w-56 bg-gray-900 border-r border-gray-800 shrink-0">
        <div className="px-4 py-5 border-b border-gray-800">
          <h1 className="text-lg font-bold text-white">DealerScope</h1>
          <p className="text-xs text-emerald-400 font-medium mt-0.5">Pro Dashboard</p>
        </div>
        <nav className="flex-1 py-4 px-2 space-y-1">
          {TABS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => navigateToTab(id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === id
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/50'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-600">
          v2.0 · {new Date().getFullYear()}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto pb-20 md:pb-0">
        {renderTab()}
      </main>

      {/* Bottom tab bar — mobile */}
      <nav className="fixed bottom-0 left-0 right-0 md:hidden bg-gray-900 border-t border-gray-800 z-50 overflow-x-auto">
        <div className="flex min-w-max">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => navigateToTab(id)}
            className={`flex flex-col items-center gap-1 py-2 px-3 text-xs transition-colors min-w-[72px] ${
              activeTab === id ? 'text-emerald-400' : 'text-gray-500'
            }`}
          >
            <Icon className="h-5 w-5" />
            <span className="whitespace-nowrap">{label}</span>
          </button>
        ))}
        </div>
      </nav>
    </div>
  );
}
