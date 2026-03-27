import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { SniperButton } from '@/components/SniperButton';
import {
  BarChart, Bar, PieChart, Pie, Cell, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip as ReTooltip, ResponsiveContainer, Legend
} from 'recharts';
import { useAuth } from '@/contexts/ModernAuthContext';
import api from '@/services/api';
import { Opportunity } from '@/types/dealerscope';
import { supabase } from '@/integrations/supabase/client';
import { OutcomeModal } from '@/components/OutcomeModal';
import { Button } from '@/components/ui/button';

// ─── Icons (lucide-react is in package.json) ──────────────────────────────────
import {
  LayoutDashboard, Crosshair, Navigation, BarChart2, Settings, Target,
  ExternalLink, RefreshCw, CheckCircle, XCircle, AlertCircle,
  TrendingUp, Car, MapPin, Clock, Star, Filter, ChevronDown,
  ThumbsUp, ThumbsDown, Bookmark, LogOut, User, Wifi, WifiOff, ScanSearch
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import SniperScopeDashboard from '@/components/SniperScopeDashboard';
import { ReconPanel } from '@/components/ReconPanel';
import { roverAPI } from '@/services/roverAPI';
import { OnboardingFlow } from '@/components/OnboardingFlow';
import LaneBadge from '@/components/LaneBadge';

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
  why_signals?: string[];
  // Pricing / scoring fields used by DealCard
  roi_per_day?: number;
  retail_ctm_pct?: number;
  estimated_days_to_sale?: number;
  max_bid?: number;
  pricing_source?: string;
  manheim_mmr_mid?: number;
  manheim_mmr_low?: number;
  manheim_mmr_high?: number;
  pricing_updated_at?: string;
  investment_grade?: string;
  listing_url?: string;
  designated_lane?: 'premium' | 'standard' | 'unassigned' | 'rejected';
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

function fmtConfidence(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `${Math.round(n * 100)}%`;
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

function getAuctionStatus(auction_end: string | null | undefined): 'live' | 'closing_soon' | 'closed' {
  if (!auction_end) return 'live';
  const end = new Date(auction_end).getTime();
  const now = Date.now();
  if (end <= now) return 'closed';
  if (end - now < 4 * 60 * 60 * 1000) return 'closing_soon';
  return 'live';
}

function pricingSourceLabel(source: string | null | undefined): string {
  if (source === 'retail_market_cache') return 'Retail comps';
  if (source === 'dealer_sales_history') return 'Dealer sales';
  if (source === 'mmr_proxy') return 'MMR proxy';
  return source || 'Unknown';
}

function manheimSourceLabel(source: Opportunity['manheim_source_status']): string {
  if (source === 'live') return 'Live Manheim';
  if (source === 'fallback') return 'Proxy fallback';
  if (source === 'unavailable') return 'Unavailable';
  return 'Unknown';
}

// ─── Deal Card ────────────────────────────────────────────────────────────────
const DealCard = ({
  deal,
  onAction,
  onSendToSniperScope,
  whySignals,
}: {
  deal: Opportunity;
  onAction?: (deal: Opportunity, action: 'view' | 'save' | 'pass') => void;
  onSendToSniperScope?: (deal: Opportunity) => void;
  whySignals?: string[];
}) => {
  const [showWhy, setShowWhy] = React.useState(false);
  const [outcomeOpen, setOutcomeOpen] = React.useState(false);
  const auctionStatus = getAuctionStatus(deal.auction_end);
  return (
  <div className={`bg-gray-900 rounded-xl border border-gray-800 p-4 hover:border-emerald-500/40 transition-colors${auctionStatus === 'closed' ? ' opacity-60' : ''}`}>
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
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${
          auctionStatus === 'live' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
          auctionStatus === 'closing_soon' ? 'bg-orange-500/20 text-orange-400 border-orange-500/30' :
          'bg-gray-600/30 text-gray-400 border-gray-600/30'
        }`}>
          {auctionStatus === 'live' ? 'LIVE' : auctionStatus === 'closing_soon' ? 'CLOSING SOON' : 'CLOSED'}
        </span>
        <span className={`text-[11px] font-semibold px-2 py-1 rounded-md ${gradeColor(deal.investment_grade)}`}>
          {deal.investment_grade || 'Watch'}
        </span>
        <LaneBadge lane={deal.designated_lane} size="sm" />
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

    <div className="mb-3 rounded-lg border border-gray-800 bg-gray-950/60 p-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <p className="text-xs text-gray-500">Pricing Source</p>
          <p className="text-sm text-gray-300">{pricingSourceLabel(deal.pricing_source)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Comp Signal</p>
          <p className="text-sm text-gray-300">
            {deal.retail_comp_count
              ? `${deal.retail_comp_count} comps • ${fmtConfidence(deal.retail_comp_confidence)}`
              : 'Proxy fallback'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Wholesale Source</p>
          <p className="text-sm text-gray-300">{manheimSourceLabel(deal.manheim_source_status)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">MMR Confidence</p>
          <p className="text-sm text-gray-300">{fmtConfidence(deal.manheim_confidence)}</p>
        </div>
        <div className="col-span-2">
          <p className="text-xs text-gray-500">Retail Band</p>
          <p className="text-sm text-gray-300">
            {deal.retail_comp_low != null && deal.retail_comp_high != null
              ? `${fmt$(deal.retail_comp_low)} - ${fmt$(deal.retail_comp_high)}`
              : fmt$(deal.retail_asking_price_estimate)}
          </p>
        </div>
        <div className="col-span-2">
          <p className="text-xs text-gray-500">MMR Band</p>
          <p className="text-sm text-gray-300">
            {deal.manheim_mmr_low != null && deal.manheim_mmr_mid != null && deal.manheim_mmr_high != null
              ? `${fmt$(deal.manheim_mmr_low)} - ${fmt$(deal.manheim_mmr_mid)} - ${fmt$(deal.manheim_mmr_high)}`
              : fmt$(deal.manheim_mmr_mid ?? deal.expected_price)}
          </p>
        </div>
        <div className="col-span-2">
          <p className="text-xs text-gray-500">MMR Range Width</p>
          <p className="text-sm text-gray-300">{fmtPct(deal.manheim_range_width_pct)}</p>
        </div>
      </div>
      {deal.pricing_updated_at && deal.pricing_source && deal.pricing_source !== 'mmr_proxy' && (
        <p className="mt-2 text-[11px] text-gray-500">Pricing updated {timeAgo(deal.pricing_updated_at)}</p>
      )}
      {deal.manheim_updated_at && deal.manheim_source_status === 'live' && (
        <p className="mt-1 text-[11px] text-gray-500">Manheim updated {timeAgo(deal.manheim_updated_at)}</p>
      )}
    </div>

    {deal.auction_end && (
      <div className="flex items-center gap-1 text-xs text-gray-500 mb-3">
        <Clock className="h-3 w-3" />
        <span>Ends {fmtDate(deal.auction_end)}</span>
      </div>
    )}

    {/* Why this deal? tooltip */}
    {whySignals && whySignals.length > 0 && (
      <div className="mb-3 relative">
        <button
          onClick={() => setShowWhy(v => !v)}
          className="flex items-center gap-1 text-xs text-emerald-400/80 hover:text-emerald-300 transition-colors"
        >
          <Star className="h-3 w-3" />
          Why this deal?
        </button>
        {showWhy && (
          <div className="mt-1 bg-gray-800 border border-gray-700 rounded-lg p-2.5 text-xs text-gray-300 space-y-1">
            {whySignals.map((s, i) => <div key={i} className="flex items-start gap-1.5"><span className="text-emerald-400 shrink-0">•</span><span>{s}</span></div>)}
          </div>
        )}
      </div>
    )}

    <div className="flex flex-wrap items-center gap-2">
      {deal.id && (
        <SniperButton
          opportunity={{ id: deal.id, year: deal.year, make: deal.make, model: deal.model, current_bid: deal.current_bid }}
          className="flex-1 min-w-[120px]"
        />
      )}
      {deal.id && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="flex-1 min-w-[120px]"
          onClick={() => setOutcomeOpen(true)}
        >
          Record Outcome
        </Button>
      )}
      {deal.listing_url ? (
        <a
          href={deal.listing_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 py-1.5 px-2 rounded-lg transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
          Listing
        </a>
      ) : deal.id ? (
        <Link
          to={`/deal/${deal.id}`}
          className="flex items-center justify-center gap-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 py-1.5 px-2 rounded-lg transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
          Detail
        </Link>
      ) : null}
      {onSendToSniperScope && deal.id && (
        <button
          onClick={() => onSendToSniperScope(deal)}
          className="flex items-center justify-center gap-1 text-xs bg-emerald-600 hover:bg-emerald-500 text-white py-1.5 px-2 rounded-lg transition-colors"
        >
          <Target className="h-3 w-3" />
          Scope
        </button>
      )}
      {deal.vin && (
        <a
          href={`https://www.google.com/search?q=${encodeURIComponent(`${deal.year} ${deal.make} ${deal.model} ${deal.vin}`)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 py-1.5 px-2 rounded-lg transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
          VIN
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
    {deal.id && (
      <OutcomeModal
        open={outcomeOpen}
        onOpenChange={setOutcomeOpen}
        opportunity={{ id: deal.id, year: deal.year, make: deal.make, model: deal.model, current_bid: deal.current_bid }}
      />
    )}
  </div>
  );
};

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
  const { session } = useAuth();
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
  const [passedIds, setPassedIds] = useState<Set<string>>(new Set());
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set());
  const [laneFilter, setLaneFilter] = useState<'all' | 'premium' | 'standard'>('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, h, s] = await Promise.all([
        api.getDashboardMetrics(),
        api.getHotDeals(80, 50),
        api.getScraperSources()
      ]);
      setMetrics(m);

      // Filter out already-passed deals on reload
      const userId = session?.user?.id;
      if (userId && h.length > 0) {
        const { data: passes } = await supabase
          .from('user_passes')
          .select('opportunity_id')
          .eq('user_id', userId);
        if (passes && passes.length > 0) {
          const passed = new Set(passes.map((p: { opportunity_id: string }) => p.opportunity_id));
          setPassedIds(passed);
          setHotDeals(h.filter(d => !passed.has(d.id!)));
        } else {
          setHotDeals(h);
        }
      } else {
        setHotDeals(h);
      }

      setSources(s);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => { load(); }, [load]);

  const handleDashboardAction = async (deal: Opportunity, action: 'view' | 'save' | 'pass') => {
    if (action !== 'pass' || !deal.id) return;
    // Animate out immediately
    setFadingIds(prev => new Set([...prev, deal.id!]));
    // Remove card after fade
    setTimeout(() => {
      setHotDeals(prev => prev.filter(d => d.id !== deal.id));
      setPassedIds(prev => new Set([...prev, deal.id!]));
    }, 300);
    // Persist to backend (non-blocking)
    api.passOpportunity(deal.id).catch(console.error);
  };

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
          <>
          {(() => {
            const standardCount = hotDeals.filter(d => !passedIds.has(d.id!) && d.designated_lane === 'standard').length;
            const STANDARD_CAP = 10;
            if (standardCount >= STANDARD_CAP) {
              return (
                <div className="mb-4 flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-900/40 border border-amber-600/50 text-amber-300 text-xs font-medium">
                  ⚠️ Standard lane cap reached ({standardCount}/{STANDARD_CAP} units). Review existing Standard deals before adding more to avoid capital tie-up.
                </div>
              );
            }
            if (standardCount >= 7) {
              return (
                <div className="mb-4 flex items-center gap-2 px-3 py-2 rounded-lg bg-yellow-900/30 border border-yellow-700/40 text-yellow-400 text-xs">
                  📦 {standardCount}/{STANDARD_CAP} Standard lane slots used — approaching cap.
                </div>
              );
            }
            return null;
          })()}
          {/* Lane filter toggle */}
          <div className="flex gap-2 mb-4">
            {(['all', 'premium', 'standard'] as const).map(l => (
              <button
                key={l}
                onClick={() => setLaneFilter(l)}
                className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors ${
                  laneFilter === l
                    ? l === 'premium' ? 'bg-emerald-600 text-white border-emerald-600'
                      : l === 'standard' ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-900 border-gray-300'
                    : 'bg-transparent text-gray-400 border-gray-600 hover:border-gray-400'
                }`}
              >
                {l === 'all' ? 'All' : l === 'premium' ? '⭐ Premium' : '📦 Standard'}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {hotDeals.filter(d => !passedIds.has(d.id!) && (laneFilter === 'all' || d.designated_lane === laneFilter)).map(deal => (
              <div
                key={deal.id}
                className={`transition-all duration-300 ${fadingIds.has(deal.id!) ? 'opacity-0 scale-95' : 'opacity-100 scale-100'}`}
              >
                <DealCard deal={deal} onAction={handleDashboardAction} />
              </div>
            ))}
          </div>
          </>
        )}
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
  const [loadingMore, setLoadingMore] = useState(false);
  const [searched, setSearched] = useState(false);
  const [page, setPage] = useState(1);
  const [searchParams, setSearchParams] = useSearchParams();

  const buildFilters = (lim: number, offset = 0) => ({
    make: filters.make || undefined,
    model: filters.model || undefined,
    yearMin: filters.yearMin ? parseInt(filters.yearMin) : undefined,
    yearMax: filters.yearMax ? parseInt(filters.yearMax) : undefined,
    state: filters.state || undefined,
    minScore: filters.minScore ? parseInt(filters.minScore) : undefined,
    minPrice: filters.minBid ? parseInt(filters.minBid) : undefined,
    maxPrice: filters.maxBid ? parseInt(filters.maxBid) : undefined,
    limit: lim,
    offset,
  });

  const search = async () => {
    setLoading(true);
    setSearched(true);
    setPage(1);
    try {
      const { data, total: t } = await api.searchCrosshairOpportunities(buildFilters(50));
      setResults(data);
      setTotal(t);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const offset = results.length;
      const { data } = await api.searchCrosshairOpportunities(buildFilters(50, offset));
      setResults(prev => [...prev, ...data]);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingMore(false);
    }
  };

  const resetFilters = () => {
    setFilters({ make: '', model: '', yearMin: '', yearMax: '', state: '', minScore: '', minBid: '', maxBid: '' });
    setResults([]);
    setTotal(0);
    setSearched(false);
    setPage(1);
  };

  const handleSendToSniperScope = (deal: Opportunity) => {
    if (!deal.id) return;
    const next = new URLSearchParams(searchParams);
    next.set('tab', 'sniper');
    next.set('dealId', deal.id);
    setSearchParams(next);
  };

  const handleCrosshairAction = async (deal: Opportunity, action: 'view' | 'save' | 'pass') => {
    if (action === 'pass' || action === 'view') return;
    // Fire Rover save event (non-blocking)
    const { data: { session } } = await supabase.auth.getSession();
    const userId = session?.user?.id;
    if (!userId) return;
    roverAPI.trackEvent({
      userId,
      event: 'save',
      item: {
        id: deal.id || '',
        make: deal.make,
        model: deal.model,
        year: deal.year,
        price: deal.current_bid ?? 0,
        source: deal.source_site,
        source_site: deal.source_site,
        state: deal.state,
        mileage: deal.mileage,
      },
    });
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
          <div className="flex items-center gap-2">
            <button
              onClick={resetFilters}
              className="text-xs text-gray-400 hover:text-gray-200 px-3 py-2 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors"
            >
              Reset
            </button>
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
      </div>

      {/* Loading state */}
      {loading && (
        <div className="text-center py-10 text-gray-400 flex flex-col items-center gap-3">
          <RefreshCw className="h-6 w-6 animate-spin text-emerald-500" />
          <span className="text-sm">Searching deals…</span>
        </div>
      )}

      {/* Results */}
      {!loading && searched && (
        <div>
          {/* Result count + filter summary */}
          {total > 0 && (
            <div className="mb-3 bg-emerald-950/30 border border-emerald-800/40 rounded-lg px-4 py-2 flex items-center gap-2 text-sm text-emerald-300">
              <Filter className="h-3.5 w-3.5 shrink-0" />
              <span>
                Showing <strong>{results.length}</strong> of <strong>{total}</strong> deals
                {[
                  filters.make && filters.make,
                  filters.model && filters.model,
                  filters.state && filters.state,
                  filters.yearMin && `${filters.yearMin}+`,
                  filters.minBid && `≥$${parseInt(filters.minBid).toLocaleString()}`,
                  filters.maxBid && `≤$${parseInt(filters.maxBid).toLocaleString()}`,
                ].filter(Boolean).length > 0 && (
                  <> matching: {[
                    filters.make,
                    filters.model,
                    filters.state,
                    filters.yearMin && `${filters.yearMin}+`,
                    filters.minBid && `≥$${parseInt(filters.minBid).toLocaleString()}`,
                    filters.maxBid && `≤$${parseInt(filters.maxBid).toLocaleString()}`,
                  ].filter(Boolean).join(', ')}</>
                )}
                {' '}— sorted by DOS score
              </span>
            </div>
          )}
          {results.length === 0 ? (
            <div className="text-center py-8 text-gray-500 bg-gray-900 rounded-xl border border-gray-800">
              No deals match your filters
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {results.map(deal => (
                  <DealCard
                    key={deal.id}
                    deal={deal}
                    onSendToSniperScope={handleSendToSniperScope}
                    onAction={handleCrosshairAction}
                  />
                ))}
              </div>
              {results.length < total && (
                <div className="mt-6 text-center">
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-200 text-sm px-6 py-2 rounded-lg border border-gray-700 transition-colors flex items-center gap-2 mx-auto"
                  >
                    {loadingMore ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}
                    {loadingMore ? 'Loading…' : `Load more (${total - results.length} remaining)`}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};

// ─── TAB 3: Rover ─────────────────────────────────────────────────────────────
const RoverTab = () => {
  const { user, session, loading: authLoading } = useAuth();
  const [recs, setRecs] = useState<RoverRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [isFallback, setIsFallback] = useState(false);
  const [actionedIds, setActionedIds] = useState<Set<string>>(new Set());
  const [roverDebug, setRoverDebug] = useState<string>('');
  const [roverMode, setRoverMode] = useState<'ai' | 'manual'>(() =>
    (localStorage.getItem('rover_mode') as 'ai' | 'manual') || 'ai'
  );

  const load = useCallback(async () => {
    const token = session?.access_token;
    if (!user || !token) { setRoverDebug('No user session'); setLoading(false); return; }
    setLoading(true);
    setIsFallback(false);

    // ── Manual mode: skip AI, query Supabase directly ────────────────────────
    if (roverMode === 'manual') {
      try {
        const { data: manualDeals } = await supabase
          .from('opportunities')
          .select('id,make,model,year,mileage,current_bid,estimated_sale_price,dos_score,gross_margin,potential_profit,profit_margin,state,source_site,auction_end:auction_end_date,vin,total_cost,risk_score,transportation_cost,fees_cost,roi,roi_percentage,confidence_score,roi_per_day,retail_ctm_pct,estimated_days_to_sale,max_bid,pricing_source,manheim_mmr_mid,manheim_mmr_low,manheim_mmr_high,pricing_updated_at,investment_grade,listing_url,designated_lane')
          .gte('dos_score', 65)
          .order('dos_score', { ascending: false })
          .limit(25);
        if (manualDeals && manualDeals.length > 0) {
          const mapped: RoverRecommendation[] = manualDeals.map((d: any) => ({
            id: d.id, make: d.make, model: d.model, year: d.year, mileage: d.mileage,
            current_bid: d.current_bid, estimated_sale_price: d.estimated_sale_price,
            score: d.dos_score, dos_score: d.dos_score, gross_margin: d.gross_margin,
            potential_profit: d.potential_profit, profit_margin: d.profit_margin,
            state: d.state, source_site: d.source_site, auction_end: d.auction_end,
            listing_url: d.listing_url, vin: d.vin, total_cost: d.total_cost,
            risk_score: d.risk_score, transportation_cost: d.transportation_cost,
            fees_cost: d.fees_cost, roi: d.roi, roi_percentage: d.roi_percentage,
            confidence_score: d.confidence_score, roi_per_day: d.roi_per_day,
            retail_ctm_pct: d.retail_ctm_pct, estimated_days_to_sale: d.estimated_days_to_sale,
            max_bid: d.max_bid, pricing_source: d.pricing_source,
            manheim_mmr_mid: d.manheim_mmr_mid, manheim_mmr_low: d.manheim_mmr_low,
            manheim_mmr_high: d.manheim_mmr_high, pricing_updated_at: d.pricing_updated_at,
            investment_grade: d.investment_grade, designated_lane: d.designated_lane,
          }));
          setRecs(mapped);
        } else {
          setRecs([]);
        }
      } catch (e) {
        console.error('RoverTab manual load error:', e);
      } finally {
        setLoading(false);
      }
      return;
    }

    // ── AI mode ──────────────────────────────────────────────────────────────
    setRoverDebug(`Loading for user: ${user.id.slice(0,8)}...`);
    try {
      const result = await roverAPI.getRecommendationsWithToken(user.id, token, 25);
      const items = result?.items ?? [];
      setRoverDebug((result as any)._debug || `API returned ${items.length} items`);

      if (items.length > 0) {
        // Map DealItem → RoverRecommendation; preserve why_signals from backend
        const mapped: RoverRecommendation[] = items.map((item: any) => ({
          id: item.id,
          make: item.make,
          model: item.model,
          year: item.year,
          mileage: item.mileage,
          current_bid: item.current_bid ?? item.price,
          estimated_sale_price: item.estimated_sale_price ?? item.price,
          score: item._score != null ? (item._score <= 1 ? item._score * 100 : item._score) : item.arbitrage_score,
          dos_score: item.dos_score ?? item.arbitrage_score,
          potential_profit: item.potential_profit,
          roi_percentage: item.roi_percentage,
          investment_grade: item.investment_grade,
          state: item.state,
          source_site: item.source_site ?? item.source,
          vin: item.vin,
          why_signals: item.why_signals ?? [],
        }));
        setRecs(mapped);
      } else {
        // Cold-start fallback: query Supabase for top DOS score deals
        const { data: fallbackDeals } = await supabase
          .from('opportunities')
          .select('id,make,model,year,mileage,current_bid,estimated_sale_price,dos_score,gross_margin,potential_profit,profit_margin,state,source_site,auction_end:auction_end_date,vin,total_cost,risk_score,transportation_cost,fees_cost,roi,roi_percentage,confidence_score,roi_per_day,retail_ctm_pct,estimated_days_to_sale,max_bid,pricing_source,manheim_mmr_mid,manheim_mmr_low,manheim_mmr_high,pricing_updated_at,investment_grade,listing_url,designated_lane')
          .gte('dos_score', 65)
          .or(`auction_end_date.gt.${new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString()},auction_end_date.is.null`)
          .order('dos_score', { ascending: false })
          .limit(25);

        if (fallbackDeals && fallbackDeals.length > 0) {
          const mapped: RoverRecommendation[] = fallbackDeals.map((d: any) => ({
            id: d.id,
            make: d.make,
            model: d.model,
            year: d.year,
            mileage: d.mileage,
            current_bid: d.current_bid,
            estimated_sale_price: d.estimated_sale_price,
            score: d.dos_score,
            dos_score: d.dos_score,
            gross_margin: d.gross_margin,
            potential_profit: d.potential_profit,
            profit_margin: d.profit_margin,
            state: d.state,
            source_site: d.source_site,
            auction_end: d.auction_end,
            listing_url: d.listing_url,
            vin: d.vin,
            total_cost: d.total_cost,
            risk_score: d.risk_score,
            transportation_cost: d.transportation_cost,
            fees_cost: d.fees_cost,
            roi: d.roi,
            roi_percentage: d.roi_percentage,
            confidence_score: d.confidence_score,
            roi_per_day: d.roi_per_day,
            retail_ctm_pct: d.retail_ctm_pct,
            estimated_days_to_sale: d.estimated_days_to_sale,
            max_bid: d.max_bid,
            pricing_source: d.pricing_source,
            manheim_mmr_mid: d.manheim_mmr_mid,
            manheim_mmr_low: d.manheim_mmr_low,
            manheim_mmr_high: d.manheim_mmr_high,
            pricing_updated_at: d.pricing_updated_at,
            investment_grade: d.investment_grade, designated_lane: d.designated_lane,
          }));
          setRecs(mapped);
          setIsFallback(true);
        } else {
          setRecs([]);
        }
      }
    } catch (e) {
      console.error('RoverTab load error:', e);
      // On error, still try the Supabase fallback
      try {
        const { data: fallbackDeals } = await supabase
          .from('opportunities')
          .select('id,make,model,year,mileage,current_bid,estimated_sale_price,dos_score,gross_margin,potential_profit,profit_margin,state,source_site,auction_end:auction_end_date,vin,total_cost,risk_score,transportation_cost,fees_cost,roi,roi_percentage,confidence_score,roi_per_day,retail_ctm_pct,estimated_days_to_sale,max_bid,pricing_source,manheim_mmr_mid,manheim_mmr_low,manheim_mmr_high,pricing_updated_at,investment_grade,listing_url,designated_lane')
          .gte('dos_score', 65)
          .or(`auction_end_date.gt.${new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString()},auction_end_date.is.null`)
          .order('dos_score', { ascending: false })
          .limit(25);
        if (fallbackDeals && fallbackDeals.length > 0) {
          const mapped: RoverRecommendation[] = fallbackDeals.map((d: any) => ({
            id: d.id, make: d.make, model: d.model, year: d.year, mileage: d.mileage,
            current_bid: d.current_bid, estimated_sale_price: d.estimated_sale_price,
            score: d.dos_score, dos_score: d.dos_score, potential_profit: d.potential_profit,
            state: d.state, source_site: d.source_site, vin: d.vin,
            roi_per_day: d.roi_per_day, retail_ctm_pct: d.retail_ctm_pct,
            estimated_days_to_sale: d.estimated_days_to_sale, max_bid: d.max_bid,
            pricing_source: d.pricing_source, manheim_mmr_mid: d.manheim_mmr_mid,
            manheim_mmr_low: d.manheim_mmr_low, manheim_mmr_high: d.manheim_mmr_high,
            pricing_updated_at: d.pricing_updated_at, investment_grade: d.investment_grade, designated_lane: d.designated_lane,
          }));
          setRecs(mapped);
          setIsFallback(true);
        }
      } catch (fallbackErr) {
        console.error('RoverTab fallback also failed:', fallbackErr);
      }
    } finally {
      setLoading(false);
    }
  }, [user, session, authLoading, roverMode]);

  // Only fire after auth has fully initialized
  useEffect(() => {
    if (!authLoading) { load(); }
  }, [load, authLoading]);

  const handleAction = async (deal: Opportunity, action: 'view' | 'save' | 'pass') => {
    await api.trackRoverEvent(deal, action);
    setActionedIds(prev => new Set([...prev, `${deal.id}-${action}`]));
    // Refresh recommendations after save or pass so the ranking reflects the new signal
    if (action === 'save' || action === 'pass') {
      load();
    }
  };

  const handleModeChange = (mode: 'ai' | 'manual') => {
    localStorage.setItem('rover_mode', mode);
    setRoverMode(mode);
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Rover</h2>
          <p className="text-sm text-gray-400">
            {roverMode === 'manual'
              ? 'Sorted by DOS Score'
              : isFallback
              ? 'Top Deals — Training Rover — interact with deals to personalize'
              : 'Personalized recommendations based on your activity'}
          </p>
        </div>
        <button onClick={load} disabled={loading} className="text-gray-400 hover:text-white">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Mode toggle */}
      <div className="flex items-center gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
        <button
          onClick={() => handleModeChange('ai')}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            roverMode === 'ai'
              ? 'bg-emerald-600 text-white'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          🤖 AI Personalized
        </button>
        <button
          onClick={() => handleModeChange('manual')}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            roverMode === 'manual'
              ? 'bg-emerald-600 text-white'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          📊 Manual (DOS Sorted)
        </button>
      </div>

      {roverMode === 'ai' && isFallback && (
        <div className="bg-blue-900/30 border border-blue-700/50 rounded-lg px-4 py-3 text-sm text-blue-300 flex items-center gap-2">
          <Navigation className="h-4 w-4 flex-shrink-0" />
          <span>Training Rover — interact with deals to personalize your recommendations over time.</span>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading recommendations...</div>
      ) : recs.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center">
          <Navigation className="h-10 w-10 text-gray-600 mx-auto mb-3" />
          <h3 className="text-white font-semibold mb-1">No recommendations yet</h3>
          <p className="text-gray-400 text-sm">
            Browse deals in the Dashboard and Crosshair tabs to train Rover on your preferences.
          </p>
          {roverDebug && <p className="text-yellow-500 text-xs mt-3 font-mono">{roverDebug}</p>}
        </div>
      ) : (
        (() => {
          // Helper: map rec → Opportunity for DealCard
          const recToDeal = (rec: RoverRecommendation): Opportunity => ({
            id: rec.id || rec.opportunity_id || '',
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
            listing_url: rec.listing_url,
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
            roi_per_day: rec.roi_per_day,
            retail_ctm_pct: rec.retail_ctm_pct,
            estimated_days_to_sale: rec.estimated_days_to_sale,
            max_bid: rec.max_bid,
            pricing_source: rec.pricing_source,
            manheim_mmr_mid: rec.manheim_mmr_mid,
            manheim_mmr_low: rec.manheim_mmr_low,
            manheim_mmr_high: rec.manheim_mmr_high,
            pricing_updated_at: rec.pricing_updated_at,
            investment_grade: rec.investment_grade as Opportunity['investment_grade'],
            vehicle: { make: rec.make || '', model: rec.model || '', year: rec.year || 0, vin: rec.vin || '', mileage: rec.mileage || 0 },
          });

          // Manual mode: flat grid sorted by DOS score, no why-signals
          if (roverMode === 'manual') {
            return (
              <div className="space-y-4">
                <p className="text-xs text-gray-400 uppercase tracking-wide font-medium">📊 Sorted by DOS Score</p>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {recs.map(rec => {
                    const id = rec.id || rec.opportunity_id || Math.random().toString();
                    return (
                      <div key={id}>
                        <DealCard deal={{ ...recToDeal(rec), id }} onAction={handleAction} />
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          }

          // Infer body type from model name for cold-start categorization
          const inferType = (model = ''): 'truck' | 'suv' | 'other' => {
            const m = model.toLowerCase();
            if (/f-?150|f-?250|f-?350|silverado|sierra|ram\s*1500|ram\s*2500|tacoma|tundra|ranger|frontier|titan|colorado|canyon/.test(m)) return 'truck';
            if (/explorer|tahoe|suburban|expedition|yukon|highlander|pilot|pathfinder|4runner|sequoia|armada|traverse|equinox|cr-?v|rav4|escape|tucson|sorento|telluride|cx-?5|cx-?9|outback|forester|rogue|murano|durango|grand cherokee|wrangler|defender/.test(m)) return 'suv';
            return 'other';
          };

          // Cold start: show categorized deal buckets
          if (isFallback) {
            const trucks = recs.filter(r => inferType(r.model) === 'truck').slice(0, 6);
            const suvs   = recs.filter(r => inferType(r.model) === 'suv').slice(0, 6);
            const bestVal = [...recs].sort((a, b) => (b.potential_profit ?? 0) - (a.potential_profit ?? 0)).slice(0, 6);
            const buckets = [
              { label: '🚛 Top Trucks', items: trucks },
              { label: '🚙 Top SUVs', items: suvs },
              { label: '💰 Best Value', items: bestVal },
            ].filter(b => b.items.length > 0);

            return (
              <div className="space-y-8">
                {buckets.map(bucket => (
                  <div key={bucket.label}>
                    <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-3">{bucket.label}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                      {bucket.items.map(rec => {
                        const id = rec.id || rec.opportunity_id || Math.random().toString();
                        return (
                          <div key={id} className="relative">
                            {rec.match_pct != null && (
                              <div className="absolute -top-2 -right-2 z-10 bg-emerald-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                                {rec.match_pct}% match
                              </div>
                            )}
                            <DealCard deal={{ ...recToDeal(rec), id }} onAction={handleAction} whySignals={rec.why_signals} />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            );
          }

          // Personalized: flat grid with why-signals tooltip
          return (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {recs.map((rec) => {
                const id = rec.id || rec.opportunity_id || Math.random().toString();
                return (
                  <div key={id} className="relative">
                    {rec.match_pct != null && (
                      <div className="absolute -top-2 -right-2 z-10 bg-emerald-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                        {rec.match_pct}% match
                      </div>
                    )}
                    <DealCard deal={{ ...recToDeal(rec), id }} onAction={handleAction} whySignals={rec.why_signals} />
                  </div>
                );
              })}
            </div>
          );
        })()
      )}
    </div>
  );
};

// ─── TAB 4: Analytics ─────────────────────────────────────────────────────────
interface AnalyticsSummary {
  total_opportunities: number;
  total_outcomes: number;
  avg_gross_margin: number | null;
  avg_roi_pct: number | null;
  wins_by_source: { source: string; count: number }[];
  top_makes: { make: string; avg_dos_score: number; count: number }[];
  alerts_sent_last_30d: number;
  total_bids: number;
  total_wins: number;
  win_rate: number | null;
  avg_purchase_price: number | null;
  avg_max_bid: number | null;
}

interface BidOutcomeSummary {
  count_by_outcome: Record<string, number>;
  total_gross_margin: number;
  avg_roi: number | null;
}

interface LogOutcomeForm {
  bid: boolean;
  won: boolean;
  purchase_price: string;
  notes: string;
}

const LogOutcomeModal = ({
  deal,
  onClose,
  onSaved,
}: {
  deal: DashboardOpportunity;
  onClose: () => void;
  onSaved: () => void;
}) => {
  const [form, setForm] = React.useState<LogOutcomeForm>({ bid: false, won: false, purchase_price: '', notes: '' });
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.logBidOutcome({
        opportunity_id: deal.id!,
        bid: form.bid,
        won: form.won,
        purchase_price: form.won && form.purchase_price ? parseFloat(form.purchase_price) : undefined,
        notes: form.notes || undefined,
      });
      onSaved();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
        <h3 className="text-white font-semibold text-base mb-1">Log Outcome</h3>
        <p className="text-gray-400 text-xs mb-5">{deal.year} {deal.make} {deal.model} — Max Bid {fmt$(deal.max_bid)}</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Bid toggle */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-300">Did you bid?</span>
            <div className="flex gap-2">
              {([true, false] as const).map(v => (
                <button key={String(v)} type="button"
                  onClick={() => setForm(f => ({ ...f, bid: v, won: v ? f.won : false }))}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                    form.bid === v
                      ? v ? 'bg-emerald-600 border-emerald-500 text-white' : 'bg-red-600/80 border-red-500 text-white'
                      : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500'
                  }`}>
                  {v ? 'Yes' : 'No'}
                </button>
              ))}
            </div>
          </div>

          {/* Won toggle — only shown if bid */}
          {form.bid && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-300">Did you win?</span>
              <div className="flex gap-2">
                {([true, false] as const).map(v => (
                  <button key={String(v)} type="button"
                    onClick={() => setForm(f => ({ ...f, won: v }))}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                      form.won === v
                        ? v ? 'bg-emerald-600 border-emerald-500 text-white' : 'bg-red-600/80 border-red-500 text-white'
                        : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500'
                    }`}>
                    {v ? 'Yes' : 'No'}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Purchase price — only shown if won */}
          {form.bid && form.won && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Final Purchase Price</label>
              <input
                type="number"
                min={0}
                step={100}
                placeholder="e.g. 14500"
                value={form.purchase_price}
                onChange={e => setForm(f => ({ ...f, purchase_price: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-emerald-500"
              />
            </div>
          )}

          {/* Notes */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Notes (optional)</label>
            <textarea
              rows={2}
              placeholder="Any context..."
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-emerald-500 resize-none"
            />
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-400 text-sm hover:border-gray-500 transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold transition-colors disabled:opacity-50">
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

interface ReconActivity {
  totalEvaluated: number;
  avgMaxBid: number | null;
  tightestDeal: { year?: number; make?: string; model?: string; max_bid?: number } | null;
  topSegment: string | null;
}

const AnalyticsTab = () => {
  const { session } = useAuth();
  const [allDeals, setAllDeals] = useState<DashboardOpportunity[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [bidSummary, setBidSummary] = useState<BidOutcomeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [bidSummaryLoading, setBidSummaryLoading] = useState(true);
  const [logDeal, setLogDeal] = useState<DashboardOpportunity | null>(null);
  const [reconActivity, setReconActivity] = useState<ReconActivity | null>(null);
  const [reconLoading, setReconLoading] = useState(true);

  const fetchReconActivity = useCallback(async () => {
    const userId = session?.user?.id;
    if (!userId) { setReconLoading(false); return; }
    try {
      const { data } = await supabase
        .from('recon_evaluations')
        .select('id, make, model, year, max_bid, verdict')
        .eq('user_id', userId);
      if (!data || data.length === 0) {
        setReconActivity({ totalEvaluated: 0, avgMaxBid: null, tightestDeal: null, topSegment: null });
        return;
      }
      const totalEvaluated = data.length;
      const bids = data.map((d: any) => d.max_bid).filter((b: any) => b != null) as number[];
      const avgMaxBid = bids.length > 0 ? bids.reduce((a: number, b: number) => a + b, 0) / bids.length : null;
      const nonPass = data.filter((d: any) => d.verdict !== 'PASS' && d.max_bid != null);
      const tightestDeal = nonPass.length > 0
        ? nonPass.sort((a: any, b: any) => (b.max_bid || 0) - (a.max_bid || 0))[0]
        : null;
      const makeCount: Record<string, number> = {};
      data.forEach((d: any) => { if (d.make) makeCount[d.make] = (makeCount[d.make] || 0) + 1; });
      const topSegment = Object.entries(makeCount).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
      setReconActivity({ totalEvaluated, avgMaxBid, tightestDeal, topSegment });
    } catch (e) {
      console.error('[Analytics] recon activity fetch error:', e);
    } finally {
      setReconLoading(false);
    }
  }, [session]);

  const fetchSummary = useCallback(async () => {
    try {
      const data = await api.getAnalyticsSummary();
      setSummary(data);
    } catch (e) {
      console.error('[Analytics] summary fetch error:', e);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  const fetchBidSummary = useCallback(async () => {
    try {
      const data = await api.getOutcomeSummary();
      setBidSummary(data);
    } catch (e) {
      console.error('[Analytics] bid outcome summary fetch error:', e);
    } finally {
      setBidSummaryLoading(false);
    }
  }, []);

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

  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchBidSummary(); }, [fetchBidSummary]);
  useEffect(() => { fetchReconActivity(); }, [fetchReconActivity]);

  if (loading) return <div className="p-6 text-center text-gray-500">Loading analytics...</div>;

  // ── Render summary section ─────────────────────────────────────────────────
  const SummarySection = () => {
    if (summaryLoading) return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-gray-900 rounded-xl border border-gray-800 p-4 animate-pulse">
            <div className="h-3 w-24 bg-gray-700 rounded mb-3" />
            <div className="h-7 w-16 bg-gray-700 rounded" />
          </div>
        ))}
      </div>
    );
    if (!summary) return null;
    return (
      <div className="space-y-4">
        {/* Top KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Total Opportunities"
            value={summary.total_opportunities.toLocaleString()}
            sub="All-time pipeline"
          />
          <StatCard
            label="Bids Placed"
            value={summary.total_bids.toLocaleString()}
            sub={`${summary.total_wins} win${summary.total_wins !== 1 ? 's' : ''}`}
            accent={summary.total_bids > 0}
          />
          <StatCard
            label="Win Rate"
            value={summary.win_rate != null ? `${summary.win_rate}%` : '—'}
            sub={summary.total_bids > 0 ? `${summary.total_wins} / ${summary.total_bids} bids` : 'No bids logged'}
            accent={summary.win_rate != null && summary.win_rate > 0}
          />
          <StatCard
            label="Avg Purchase vs Ceiling"
            value={summary.avg_purchase_price != null ? fmt$(summary.avg_purchase_price) : '—'}
            sub={summary.avg_max_bid != null ? `ceiling ${fmt$(summary.avg_max_bid)}` : 'No wins logged'}
            accent={
              summary.avg_purchase_price != null &&
              summary.avg_max_bid != null &&
              summary.avg_purchase_price <= summary.avg_max_bid
            }
          />
        </div>

        {/* Second KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Recorded Outcomes"
            value={summary.total_outcomes.toLocaleString()}
            sub="Closed deals tracked"
            accent
          />
          <StatCard
            label="Avg Gross Margin"
            value={summary.avg_gross_margin != null ? fmt$(summary.avg_gross_margin) : '—'}
            sub="From closed outcomes"
            accent={summary.avg_gross_margin != null && summary.avg_gross_margin > 0}
          />
          <StatCard
            label="Avg ROI %"
            value={summary.avg_roi_pct != null ? fmtPct(summary.avg_roi_pct) : '—'}
            sub="From closed outcomes"
            accent={summary.avg_roi_pct != null && summary.avg_roi_pct > 0}
          />
          <StatCard
            label="Alerts (30d)"
            value={summary.alerts_sent_last_30d.toLocaleString()}
            sub="Hot deal notifications"
          />
        </div>

        {/* Third row — source breakdown + top makes */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Wins by source */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">Wins by Source</p>
            {summary.wins_by_source.length === 0 ? (
              <p className="text-sm text-gray-500">No outcome data yet</p>
            ) : (
              <div className="space-y-1.5">
                {summary.wins_by_source.map(({ source, count }) => (
                  <div key={source} className="flex items-center justify-between text-sm">
                    <span className="text-gray-300 truncate">{source}</span>
                    <span className="text-white font-medium ml-2 shrink-0">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Top makes */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">Top Makes by DOS Score</p>
            {summary.top_makes.length === 0 ? (
              <p className="text-sm text-gray-500">No data yet</p>
            ) : (
              <div className="space-y-1.5">
                {summary.top_makes.map(({ make, avg_dos_score, count }) => (
                  <div key={make} className="flex items-center justify-between text-sm">
                    <span className="text-gray-300">{make}</span>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-semibold ${dosColor(avg_dos_score)}`}>
                        {avg_dos_score}
                      </span>
                      <span className="text-gray-500 text-xs">{count}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

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

      <div className="space-y-3">
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Bid Outcomes</p>
        {bidSummaryLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-gray-900 rounded-xl border border-gray-800 p-4 animate-pulse">
                <div className="h-3 w-24 bg-gray-700 rounded mb-3" />
                <div className="h-7 w-16 bg-gray-700 rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Won"
                value={(bidSummary?.count_by_outcome?.won ?? 0).toLocaleString()}
                sub="Closed wins"
                accent={(bidSummary?.count_by_outcome?.won ?? 0) > 0}
              />
              <StatCard
                label="Lost"
                value={(bidSummary?.count_by_outcome?.lost ?? 0).toLocaleString()}
                sub="Lost bids"
              />
              <StatCard
                label="Passed"
                value={(bidSummary?.count_by_outcome?.passed ?? 0).toLocaleString()}
                sub="Intentional passes"
              />
              <StatCard
                label="Pending"
                value={(bidSummary?.count_by_outcome?.pending ?? 0).toLocaleString()}
                sub="Still open"
              />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <StatCard
                label="Total Gross Margin"
                value={bidSummary ? fmt$(bidSummary.total_gross_margin) : '—'}
                sub="From dealer_sales"
                accent={!!bidSummary && bidSummary.total_gross_margin > 0}
              />
              <StatCard
                label="Avg ROI"
                value={bidSummary?.avg_roi != null ? fmtPct(bidSummary.avg_roi) : '—'}
                sub="Across recorded outcomes"
                accent={bidSummary?.avg_roi != null && bidSummary.avg_roi > 0}
              />
            </div>
          </div>
        )}
      </div>

      {/* ── Recon Activity layer ── */}
      <div className="space-y-3">
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Recon Activity</p>
        {reconLoading ? (
          <div className="grid grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-gray-900 rounded-xl border border-gray-800 p-4 animate-pulse">
                <div className="h-3 w-24 bg-gray-700 rounded mb-3" />
                <div className="h-7 w-16 bg-gray-700 rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <StatCard
              label="Vehicles Evaluated"
              value={(reconActivity?.totalEvaluated ?? 0).toLocaleString()}
              sub="All-time recon runs"
              accent={(reconActivity?.totalEvaluated ?? 0) > 0}
            />
            <StatCard
              label="Avg Max Bid"
              value={reconActivity?.avgMaxBid != null ? fmt$(reconActivity.avgMaxBid) : '—'}
              sub="Across all evaluations"
              accent={reconActivity?.avgMaxBid != null}
            />
            <StatCard
              label="Tightest Deal"
              value={reconActivity?.tightestDeal
                ? `${reconActivity.tightestDeal.year ?? ''} ${reconActivity.tightestDeal.make ?? ''} ${reconActivity.tightestDeal.model ?? ''}`.trim()
                : '—'}
              sub={reconActivity?.tightestDeal?.max_bid != null ? `Max bid ${fmt$(reconActivity.tightestDeal.max_bid)}` : 'Highest non-pass bid'}
            />
            <StatCard
              label="Top Segment"
              value={reconActivity?.topSegment ?? '—'}
              sub="Most evaluated make"
              accent={!!reconActivity?.topSegment}
            />
          </div>
        )}
      </div>

      {/* ── Real outcome KPIs from dealer_sales / alert_log ── */}
      <SummarySection />

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

      {/* ── Deal cards with Log Outcome ── */}
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Active Deals — Log Your Bid Results</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {allDeals.slice(0, 30).map(deal => (
            <div key={deal.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white truncate">
                    {deal.year} {deal.make} {deal.model}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {deal.mileage ? `${deal.mileage.toLocaleString()} mi · ` : ''}{deal.source_site}
                  </p>
                </div>
                <span className={`text-xs font-bold px-2 py-1 rounded-md shrink-0 ${dosColor(deal.score)}`}>
                  {deal.score ?? '—'}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>Bid: <span className="text-white font-medium">{fmt$(deal.current_bid)}</span></span>
                <span>Max: <span className="text-emerald-400 font-medium">{fmt$(deal.max_bid)}</span></span>
                <span>Margin: <span className={`font-medium ${(deal.profit_margin || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fmt$(deal.profit_margin)}</span></span>
              </div>
              <button
                onClick={() => deal.id ? setLogDeal(deal) : undefined}
                className="mt-1 w-full py-1.5 rounded-lg bg-gray-800 hover:bg-emerald-600/20 border border-gray-700 hover:border-emerald-500/50 text-xs font-medium text-gray-300 hover:text-emerald-400 transition-colors"
              >
                Log Outcome
              </button>
            </div>
          ))}
        </div>
        {allDeals.length > 30 && (
          <p className="text-xs text-gray-500 mt-3 text-center">Showing top 30 deals. Use filters in the Dashboard tab to narrow results.</p>
        )}
      </div>

      {/* Modal */}
      {logDeal && (
        <LogOutcomeModal
          deal={logDeal}
          onClose={() => setLogDeal(null)}
          onSaved={() => { fetchSummary(); }}
        />
      )}
    </div>
  );
};

// ─── TAB 5: Settings ──────────────────────────────────────────────────────────
const SettingsTab = () => {
  const { user, signOut } = useAuth();
  const [railwayStatus, setRailwayStatus] = useState<{ status: string; latency?: number } | null>(null);
  const [supabaseStatus, setSupabaseStatus] = useState<{ status: string; latency?: number } | null>(null);
  const [checking, setChecking] = useState(false);

  const checkConnections = useCallback(async () => {
    setChecking(true);
    const [r, s] = await Promise.allSettled([
      api.checkRailwayHealth(),
      api.checkSupabaseHealth()
    ]);
    if (r.status === 'fulfilled') setRailwayStatus(r.value);
    else setRailwayStatus({ status: 'error' });
    if (s.status === 'fulfilled') setSupabaseStatus(s.value);
    else setSupabaseStatus({ status: 'error' });
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
    </div>
  );
};

// ─── Main Dashboard Shell ─────────────────────────────────────────────────────
const TABS: { id: Tab; label: string; Icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { id: 'crosshair', label: 'Crosshair', Icon: Crosshair },
  { id: 'sniper', label: 'Sniper', Icon: Target },
  { id: 'rover', label: 'Rover', Icon: Navigation },
  { id: 'recon', label: 'Recon', Icon: ScanSearch },
  { id: 'analytics', label: 'Analytics', Icon: BarChart2 },
  { id: 'settings', label: 'Settings', Icon: Settings },
];

function parseTab(tab: string | null): Tab {
  return TABS.some(({ id }) => id === tab) ? (tab as Tab) : 'dashboard';
}

export default function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseTab(searchParams.get('tab'));
  const [showOnboarding, setShowOnboarding] = useState(
    !localStorage.getItem('onboarding_completed')
  );

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
      case 'recon': return <ReconPanel />;
      case 'analytics': return <AnalyticsTab />;
      case 'settings': return <SettingsTab />;
    }
  };

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
      {showOnboarding && (
        <OnboardingFlow onComplete={() => setShowOnboarding(false)} />
      )}
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
      <main className="flex-1 overflow-y-auto pb-nav-safe md:pb-0">
        {renderTab()}
      </main>

      {/* Bottom tab bar — mobile */}
      <nav className="fixed bottom-0 left-0 right-0 md:hidden bg-gray-900 border-t border-gray-800 z-50 overflow-x-auto pb-safe">
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
