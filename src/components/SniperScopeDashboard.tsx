import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Target, Lock, Trash2, Calculator, Upload, Search, RefreshCw, Crosshair, Clock, DollarSign } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '@/hooks/use-toast';
import { supabase } from '@/integrations/supabase/client';
import api, { type OpportunityDetail } from '@/services/api';

// ─── Types ────────────────────────────────────────────────────────────────────
interface SniperInputs {
  year: string;
  make: string;
  model: string;
  mmr: string;
  source: string;
  buyerPremiumPct: string;
  salesTaxPct: string;
  auctionFees: string;
  titleFees: string;
  transport: string;
  recon: string;
  targetMargin: string;
  state: string;
  currentBid: string;
}

interface SavedTarget {
  id: string;
  vehicle: string;
  mmr: number;
  maxBid: number;
  margin: number;
  roi: number;
  date: string;
  source: string;
  snapshot: {
    buyerPremiumPct: string;
    auctionFees: string;
    titleFees: string;
    transport: string;
    recon: string;
    targetMargin: string;
    state: string;
    salesTaxPct: string;
  };
}

interface OutcomeForm {
  opportunityId: string;
  salePrice: string;
  saleDate: string;
  daysToSale: string;
  notes: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────
const LOW_RUST_STATES: { value: string; label: string; transport: number }[] = [
  { value: 'AL', label: 'Alabama', transport: 625 },
  { value: 'AR', label: 'Arkansas', transport: 550 },
  { value: 'AZ', label: 'Arizona', transport: 350 },
  { value: 'CA', label: 'California', transport: 500 },
  { value: 'CO', label: 'Colorado', transport: 400 },
  { value: 'FL', label: 'Florida', transport: 600 },
  { value: 'GA', label: 'Georgia', transport: 550 },
  { value: 'HI', label: 'Hawaii', transport: 1200 },
  { value: 'LA', label: 'Louisiana', transport: 575 },
  { value: 'MS', label: 'Mississippi', transport: 600 },
  { value: 'NC', label: 'North Carolina', transport: 575 },
  { value: 'NM', label: 'New Mexico', transport: 375 },
  { value: 'NV', label: 'Nevada', transport: 450 },
  { value: 'OK', label: 'Oklahoma', transport: 325 },
  { value: 'OR', label: 'Oregon', transport: 550 },
  { value: 'SC', label: 'South Carolina', transport: 575 },
  { value: 'TN', label: 'Tennessee', transport: 525 },
  { value: 'TX', label: 'Texas', transport: 400 },
  { value: 'UT', label: 'Utah', transport: 425 },
  { value: 'VA', label: 'Virginia', transport: 600 },
  { value: 'WA', label: 'Washington', transport: 575 },
];

const STATE_SALES_TAX: Record<string, number> = {
  AL: 4.0, AR: 6.5, AZ: 5.6, CA: 7.25, CO: 2.9, FL: 6.0,
  GA: 4.0, HI: 4.0, LA: 4.45, MS: 7.0, NC: 4.75, NM: 5.0,
  NV: 6.85, OK: 4.5, OR: 0.0, SC: 6.0, TN: 7.0, TX: 6.25,
  UT: 5.95, VA: 4.3, WA: 6.5,
};

const AUCTION_SOURCES: { value: string; label: string; premium: number; noTax?: boolean }[] = [
  { value: 'govdeals',     label: 'GovDeals',      premium: 10 },
  { value: 'gsaauctions',  label: 'GSAauctions',   premium: 0,    noTax: true },
  { value: 'publicsurplus',label: 'PublicSurplus',  premium: 10 },
  { value: 'hibid',        label: 'HiBid',          premium: 15 },
  { value: 'municibid',    label: 'Municibid',      premium: 10 },
  { value: 'other',        label: 'Other',          premium: 12.5 },
];

const STORAGE_KEY = 'dealerscope_sniper_targets';
const API_BASE = (typeof import.meta !== 'undefined' ? (import.meta as any).env?.VITE_API_URL : '') || 'https://dealscan-insight-production.up.railway.app';

// ─── Active DB Sniper Targets ─────────────────────────────────────────────────
interface LiveTarget {
  id: string;
  status: string;
  max_bid: number;
  created_at: string;
  opportunity?: {
    year?: number;
    make?: string;
    model?: string;
    state?: string;
    source?: string;
    current_bid?: number;
    auction_end_date?: string;
    listing_url?: string;
  };
}

function LiveTargetStatusBadge({ status }: { status: string }) {
  if (status === 'active') return <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-900/60 text-emerald-300 border border-emerald-700/50">Armed 🎯</span>;
  if (status === 'ceiling_exceeded') return <span className="inline-flex text-[11px] font-semibold px-2 py-0.5 rounded-full bg-red-900/60 text-red-300 border border-red-700/50">Ceiling Exceeded ❌</span>;
  if (status === 'expired') return <span className="inline-flex text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">Expired</span>;
  if (status === 'cancelled') return <span className="inline-flex text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">Cancelled</span>;
  return <span className="text-[11px] text-gray-500">{status}</span>;
}

function timeUntil(iso?: string): string {
  if (!iso) return '—';
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return 'Ended';
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function ActiveSniperTargets() {
  const [targets, setTargets] = useState<LiveTarget[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.access_token) { setLoading(false); return; }
      const resp = await fetch(`${API_BASE}/api/sniper/targets`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!resp.ok) return;
      const json = await resp.json();
      setTargets(json.targets || []);
    } catch { /* non-fatal */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <div className="text-center py-4 text-gray-500 text-sm">Loading active targets…</div>;
  if (targets.length === 0) return (
    <div className="text-center py-4 text-gray-600 text-sm">
      No active sniper targets. Arm one from Crosshair or the Dashboard.
    </div>
  );

  return (
    <div className="divide-y divide-gray-800">
      {targets.map(t => {
        const opp = t.opportunity || {};
        const vehicle = [opp.year, opp.make, opp.model].filter(Boolean).join(' ') || 'Unknown vehicle';
        return (
          <div key={t.id} className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-4 py-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-white text-sm font-medium truncate">{vehicle}</span>
                <LiveTargetStatusBadge status={t.status} />
              </div>
              <div className="flex flex-wrap gap-3 text-xs text-gray-400">
                {opp.state && <span className="flex items-center gap-0.5">📍 {opp.state}</span>}
                {opp.source && <span>{opp.source}</span>}
                {opp.auction_end_date && (
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {timeUntil(opp.auction_end_date)}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm">
              {opp.current_bid != null && (
                <div className="text-center">
                  <p className="text-[11px] text-gray-500">Live bid</p>
                  <p className="text-white font-medium">${opp.current_bid.toLocaleString()}</p>
                </div>
              )}
              <div className="text-center">
                <p className="text-[11px] text-gray-500">Your ceiling</p>
                <p className="text-emerald-400 font-semibold">${t.max_bid.toLocaleString()}</p>
              </div>
              {opp.listing_url && (
                <a href={opp.listing_url} target="_blank" rel="noopener noreferrer"
                  className="text-xs text-gray-500 hover:text-emerald-400 underline"
                >
                  View ↗
                </a>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function fmt$(n: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
}

function fmtInput(n: number): string {
  return Number.isFinite(n) ? n.toString() : '';
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function normalizeAuctionSource(source?: string): string {
  const normalized = (source || '').toLowerCase().replace(/[^a-z]/g, '');
  if (normalized.includes('govdeals')) return 'govdeals';
  if (normalized.includes('gsa')) return 'gsaauctions';
  if (normalized.includes('publicsurplus')) return 'publicsurplus';
  if (normalized.includes('hibid')) return 'hibid';
  if (normalized.includes('municibid')) return 'municibid';
  return 'other';
}

const DEFAULT_INPUTS: SniperInputs = {
  year: '', make: '', model: '', mmr: '',
  source: 'other',
  buyerPremiumPct: '12.5',
  salesTaxPct: '5.0',
  auctionFees: '150',
  titleFees: '150',
  transport: '450',
  recon: '500',
  targetMargin: '2500',
  state: '',
  currentBid: '',
};

// ─── SniperScope Calculator ───────────────────────────────────────────────────
export default function SniperScopeDashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();
  const [inputs, setInputs] = useState<SniperInputs>(DEFAULT_INPUTS);
  const [dealIdInput, setDealIdInput] = useState(searchParams.get('dealId') || '');
  const [loadingDeal, setLoadingDeal] = useState(false);
  const [dealError, setDealError] = useState<string | null>(null);
  const [loadedDeal, setLoadedDeal] = useState<OpportunityDetail | null>(null);
  const [savingOutcome, setSavingOutcome] = useState(false);
  const [outcomeForm, setOutcomeForm] = useState<OutcomeForm>({
    opportunityId: searchParams.get('dealId') || '',
    salePrice: '',
    saleDate: '',
    daysToSale: '',
    notes: '',
  });

  const [saved, setSaved] = useState<SavedTarget[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  });

  // ─── Live calculation ──────────────────────────────────────────────────────
  const calc = useMemo(() => {
    const mmr            = parseFloat(inputs.mmr)            || 0;
    const buyerPremiumPct= parseFloat(inputs.buyerPremiumPct)|| 0;
    const salesTaxPct    = parseFloat(inputs.salesTaxPct)    || 0;
    const auctionFees    = parseFloat(inputs.auctionFees)    || 0;
    const titleFees      = parseFloat(inputs.titleFees)      || 0;
    const transport      = parseFloat(inputs.transport)      || 0;
    const recon          = parseFloat(inputs.recon)          || 0;
    const targetMargin   = parseFloat(inputs.targetMargin)   || 0;
    const currentBid     = parseFloat(inputs.currentBid)     || 0;

    // Correct algebraic formula: premium + tax are percentages of maxBid
    const divisor = 1 + buyerPremiumPct / 100 + salesTaxPct / 100;
    const maxBid = divisor > 0
      ? (mmr - auctionFees - titleFees - transport - recon - targetMargin) / divisor
      : 0;

    const buyerPremiumAmount = maxBid * (buyerPremiumPct / 100);
    const salesTaxAmount     = maxBid * (salesTaxPct / 100);
    const allInCost          = maxBid + buyerPremiumAmount + salesTaxAmount + auctionFees + titleFees + transport + recon;
    const estimatedGrossMargin = mmr - allInCost;
    const roi = allInCost > 0 ? (estimatedGrossMargin / allInCost) * 100 : 0;
    const headroom = maxBid - currentBid;

    return {
      mmr, buyerPremiumPct, salesTaxPct, buyerPremiumAmount, salesTaxAmount,
      auctionFees, titleFees, transport, recon, targetMargin,
      maxBid, allInCost, estimatedGrossMargin, roi,
      currentBid, headroom,
    };
  }, [inputs]);

  // ─── Helpers ───────────────────────────────────────────────────────────────
  const set = (key: keyof SniperInputs, value: string) =>
    setInputs(prev => ({ ...prev, [key]: value }));

  const populateFromDeal = (deal: OpportunityDetail) => {
    const stateCode = (deal.state || '').toUpperCase();
    const source = normalizeAuctionSource(deal.source);
    const sourceData = AUCTION_SOURCES.find(entry => entry.value === source);
    const salesTaxPct = sourceData?.noTax ? '0' : (STATE_SALES_TAX[stateCode] ?? parseFloat(DEFAULT_INPUTS.salesTaxPct)).toFixed(2);
    const buyerPremiumPct = deal.current_bid > 0 && deal.buyer_premium > 0
      ? ((deal.buyer_premium / deal.current_bid) * 100).toFixed(2)
      : (sourceData?.premium ?? parseFloat(DEFAULT_INPUTS.buyerPremiumPct)).toString();

    setInputs(prev => ({
      ...prev,
      year: deal.year ? deal.year.toString() : '',
      make: deal.make || '',
      model: deal.model || '',
      mmr: deal.mmr ? fmtInput(deal.mmr) : '',
      source,
      buyerPremiumPct,
      salesTaxPct,
      auctionFees: fmtInput(deal.auction_fees),
      transport: fmtInput(deal.estimated_transport),
      state: stateCode,
      currentBid: fmtInput(deal.current_bid),
    }));
    setLoadedDeal(deal);
    setDealError(null);
  };

  const loadFromDeal = async (id: string, syncUrl = true) => {
    const normalizedId = id.trim();
    if (!normalizedId) {
      setDealError('Enter an opportunity ID to load a deal.');
      return;
    }

    setLoadingDeal(true);
    setDealError(null);

    try {
      const deal = await api.getOpportunityById(normalizedId);
      if (!deal) {
        setLoadedDeal(null);
        setDealError('Deal not found in Supabase.');
        return;
      }

      populateFromDeal(deal);
      setDealIdInput(deal.id);
      setOutcomeForm(prev => ({ ...prev, opportunityId: deal.id }));

      if (syncUrl) {
        const next = new URLSearchParams(searchParams);
        next.set('tab', 'sniper');
        next.set('dealId', deal.id);
        setSearchParams(next);
      }
    } catch (error) {
      console.error(error);
      setLoadedDeal(null);
      setDealError('Failed to load deal from Supabase.');
    } finally {
      setLoadingDeal(false);
    }
  };

  const handleStateChange = (state: string) => {
    const stateData  = LOW_RUST_STATES.find(s => s.value === state);
    const stateTax   = STATE_SALES_TAX[state] ?? 5.0;
    // Don't override salesTax if source is GSA (no tax)
    const sourceData = AUCTION_SOURCES.find(s => s.value === inputs.source);
    setInputs(prev => ({
      ...prev,
      state,
      transport: stateData ? stateData.transport.toString() : prev.transport,
      salesTaxPct: sourceData?.noTax ? '0' : stateTax.toFixed(2),
    }));
  };

  const handleSourceChange = (source: string) => {
    const sourceData = AUCTION_SOURCES.find(s => s.value === source);
    if (!sourceData) return;
    setInputs(prev => {
      const stateTax = STATE_SALES_TAX[prev.state] ?? 5.0;
      return {
        ...prev,
        source,
        buyerPremiumPct: sourceData.premium.toString(),
        salesTaxPct: sourceData.noTax ? '0' : stateTax.toFixed(2),
      };
    });
  };

  const lockTarget = () => {
    if (!inputs.mmr) return;
    const vehicle = [inputs.year, inputs.make, inputs.model].filter(Boolean).join(' ') || 'Unknown Vehicle';
    const sourceLabel = AUCTION_SOURCES.find(s => s.value === inputs.source)?.label ?? inputs.source;
    const entry: SavedTarget = {
      id: Date.now().toString(),
      vehicle,
      mmr: calc.mmr,
      maxBid: calc.maxBid,
      margin: calc.estimatedGrossMargin,
      roi: calc.roi,
      date: new Date().toISOString(),
      source: sourceLabel,
      snapshot: {
        buyerPremiumPct: inputs.buyerPremiumPct,
        auctionFees: inputs.auctionFees,
        titleFees: inputs.titleFees,
        transport: inputs.transport,
        recon: inputs.recon,
        targetMargin: inputs.targetMargin,
        state: inputs.state,
        salesTaxPct: inputs.salesTaxPct,
      },
    };
    const next = [entry, ...saved];
    setSaved(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const deleteTarget = (id: string) => {
    const next = saved.filter(t => t.id !== id);
    setSaved(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const loadTarget = (t: SavedTarget) => {
    const sourceEntry = AUCTION_SOURCES.find(s => s.label === t.source);
    setInputs(prev => ({
      ...prev,
      mmr: t.mmr.toString(),
      source: sourceEntry?.value ?? 'other',
      ...t.snapshot,
      currentBid: '',
    }));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const dealIdParam = searchParams.get('dealId') || '';

  useEffect(() => {
    setDealIdInput(dealIdParam);
    if (dealIdParam) {
      setOutcomeForm(prev => ({ ...prev, opportunityId: dealIdParam }));
    }

    if (dealIdParam && dealIdParam !== loadedDeal?.id) {
      void loadFromDeal(dealIdParam, false);
    }
  }, [dealIdParam, loadedDeal?.id]);

  const setOutcomeField = (key: keyof OutcomeForm, value: string) =>
    setOutcomeForm(prev => ({ ...prev, [key]: value }));

  const handleOutcomeSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const opportunityId = (dealIdParam || outcomeForm.opportunityId).trim();
    if (!opportunityId) {
      toast({
        title: 'Opportunity ID required',
        description: 'Provide an opportunity ID before logging a sale.',
        variant: 'destructive',
      });
      return;
    }

    setSavingOutcome(true);

    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;

      if (!token) {
        throw new Error('You must be signed in to log a sale outcome.');
      }

      const response = await fetch('/api/outcomes', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          opportunity_id: opportunityId,
          sale_price: parseFloat(outcomeForm.salePrice),
          sale_date: outcomeForm.saleDate,
          days_to_sale: parseInt(outcomeForm.daysToSale, 10),
          notes: outcomeForm.notes.trim() || null,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || `Request failed with status ${response.status}`);
      }

      setOutcomeForm(prev => ({
        ...prev,
        opportunityId,
        salePrice: '',
        saleDate: '',
        daysToSale: '',
        notes: '',
      }));

      toast({
        title: 'Sale logged',
        description: 'Outcome saved successfully.',
      });
    } catch (error) {
      console.error('Failed to log outcome:', error);
      toast({
        title: 'Could not log sale',
        description: error instanceof Error ? error.message : 'Unknown error occurred.',
        variant: 'destructive',
      });
    } finally {
      setSavingOutcome(false);
    }
  };

  // ─── Derived UI state ──────────────────────────────────────────────────────
  const hasMMR = Boolean(inputs.mmr);
  const isViable = calc.maxBid > 0;
  const marginShort = isViable && calc.estimatedGrossMargin < calc.targetMargin;

  const maxBidColor  = isViable ? 'text-emerald-400' : 'text-red-400';
  const marginColor  = !hasMMR ? 'text-white'
    : calc.estimatedGrossMargin <= 0 ? 'text-red-400'
    : marginShort ? 'text-yellow-400'
    : 'text-emerald-400';

  const headroomColor = calc.headroom > 1000
    ? 'text-emerald-400 border-emerald-800/60'
    : calc.headroom >= 200
    ? 'text-yellow-400 border-yellow-800/60'
    : 'text-red-400 border-red-800/60 animate-pulse';

  const inputCls = "w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-emerald-500 transition-colors";
  const labelCls = "block text-xs text-gray-400 mb-1";

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Mobile sticky max bid */}
      <div className="sticky top-0 z-10 bg-gray-950 py-2 px-4 xl:hidden border-b border-gray-800 flex justify-between items-center -mx-4 md:-mx-6">
        <span className="text-sm text-gray-400">Max Bid Ceiling</span>
        <span className={`text-2xl font-black ${isViable ? 'text-emerald-400' : 'text-red-400'}`}>
          {hasMMR ? fmt$(calc.maxBid) : '—'}
        </span>
      </div>

      {/* Header */}
      <div className="flex items-center gap-3">
        <Target className="h-6 w-6 text-emerald-400" />
        <div>
          <h2 className="text-xl font-bold text-white">SniperScope</h2>
          <p className="text-sm text-gray-400">Bid execution calculator — find your max bid before you raise your hand</p>
        </div>
      </div>

      {/* ── Active DB Sniper Targets ────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800">
          <Crosshair className="h-4 w-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-gray-200">Active Sniper Targets</h3>
          <span className="text-xs text-gray-500 ml-1">(from database)</span>
        </div>
        <ActiveSniperTargets />
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-gray-200">Load from deal</h3>
        </div>
        <div className="flex flex-col md:flex-row gap-3">
          <input
            type="text"
            className="flex-1 bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-emerald-500 transition-colors"
            placeholder="Opportunity ID"
            value={dealIdInput}
            onChange={e => setDealIdInput(e.target.value)}
          />
          <button
            onClick={() => loadFromDeal(dealIdInput)}
            disabled={loadingDeal}
            className="flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {loadingDeal ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {loadingDeal ? 'Loading...' : 'Load from deal'}
          </button>
        </div>
        {loadedDeal && (
          <p className="text-xs text-gray-400">
            Loaded {loadedDeal.year} {loadedDeal.make} {loadedDeal.model} from {loadedDeal.state || 'unknown state'}.
          </p>
        )}
        {dealError && (
          <p className="text-xs text-red-400">{dealError}</p>
        )}
      </div>

      {/* Viability banners */}
      {hasMMR && !isViable && (
        <div className="bg-red-950/60 border border-red-700 rounded-lg px-4 py-3 text-red-300 font-semibold text-sm">
          ⚠️ DEAL NOT VIABLE — costs exceed MMR at this margin target
        </div>
      )}
      {hasMMR && marginShort && (
        <div className="bg-yellow-950/60 border border-yellow-700 rounded-lg px-4 py-3 text-yellow-300 font-semibold text-sm">
          ⚠️ Margin below target — deal is thin
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* ── INPUT FORM ─────────────────────────────────────────────────────── */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Calculator className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-gray-200">Vehicle & Cost Inputs</h3>
          </div>

          {/* Vehicle */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={labelCls}>Year</label>
              <input type="number" className={inputCls} placeholder="2021" value={inputs.year}
                onChange={e => set('year', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Make</label>
              <input type="text" className={inputCls} placeholder="Ford" value={inputs.make}
                onChange={e => set('make', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Model</label>
              <input type="text" className={inputCls} placeholder="F-150" value={inputs.model}
                onChange={e => set('model', e.target.value)} />
            </div>
          </div>

          {/* MMR */}
          <div>
            <label className={labelCls}>MMR — Market Reference Value ($)</label>
            <input type="number" className={inputCls} placeholder="22000" value={inputs.mmr}
              onChange={e => set('mmr', e.target.value)} />
            <p className="text-xs text-gray-600 mt-1">Manheim Market Report value or your best market estimate</p>
          </div>

          {/* Auction Source */}
          <div>
            <label className={labelCls}>Auction Source</label>
            <select className={inputCls} value={inputs.source} onChange={e => handleSourceChange(e.target.value)}>
              {AUCTION_SOURCES.map(s => (
                <option key={s.value} value={s.value}>{s.label} (premium: {s.premium}%{s.noTax ? ', no tax' : ''})</option>
              ))}
            </select>
          </div>

          {/* Premium + sales tax row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Buyer Premium (%)</label>
              <input type="number" step="0.5" className={inputCls} value={inputs.buyerPremiumPct}
                onChange={e => set('buyerPremiumPct', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Sales Tax (%)</label>
              <input type="number" step="0.01" className={inputCls} value={inputs.salesTaxPct}
                onChange={e => set('salesTaxPct', e.target.value)} />
            </div>
          </div>

          {/* Fees grid */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Auction Fees ($)</label>
              <input type="number" className={inputCls} value={inputs.auctionFees}
                onChange={e => set('auctionFees', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Title & Doc Fees ($)</label>
              <input type="number" className={inputCls} value={inputs.titleFees}
                onChange={e => set('titleFees', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Recon Estimate ($)</label>
              <input type="number" className={inputCls} value={inputs.recon}
                onChange={e => set('recon', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Target Margin ($)</label>
              <input type="number" className={inputCls} value={inputs.targetMargin}
                onChange={e => set('targetMargin', e.target.value)} />
            </div>
          </div>

          {/* State + transport */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Origin State (low-rust)</label>
              <select className={inputCls} value={inputs.state} onChange={e => handleStateChange(e.target.value)}>
                <option value="">— Select state —</option>
                {LOW_RUST_STATES.map(s => (
                  <option key={s.value} value={s.value}>{s.label} ({s.value})</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls}>Transport ($)</label>
              <input type="number" className={inputCls} value={inputs.transport}
                onChange={e => set('transport', e.target.value)} />
            </div>
          </div>

          {/* Current Bid tracker */}
          <div>
            <label className={labelCls}>Current Bid (live) ($)</label>
            <input type="number" className={inputCls} placeholder="Enter live auction price…" value={inputs.currentBid}
              onChange={e => set('currentBid', e.target.value)} />
          </div>
        </div>

        {/* ── CALCULATED OUTPUT ───────────────────────────────────────────────── */}
        <div className="space-y-4">
          {/* Big Max Bid display */}
          <div className={`bg-gray-900 rounded-xl border p-5 text-center ${
            isViable ? 'border-emerald-800/60' : 'border-red-800/60'
          }`}>
            <p className="text-xs text-gray-400 uppercase tracking-widest mb-1">Max Bid Ceiling</p>
            <p className={`text-5xl font-black tracking-tight ${maxBidColor}`}>
              {hasMMR ? fmt$(calc.maxBid) : '—'}
            </p>
          </div>

          {/* Headroom display */}
          {hasMMR && inputs.currentBid && (
            <div className={`bg-gray-900 rounded-xl border p-4 flex items-center justify-between ${headroomColor}`}>
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">Headroom Remaining</p>
                <p className="text-xs text-gray-500">You have {calc.headroom > 0 ? fmt$(calc.headroom) : '—'} left before hitting your ceiling</p>
              </div>
              <span className={`text-2xl font-black ${headroomColor.split(' ')[0]}`}>
                {calc.headroom >= 0 ? fmt$(calc.headroom) : `-${fmt$(Math.abs(calc.headroom))}`}
              </span>
            </div>
          )}

          {/* Summary metrics */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-3 text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">All-In Cost</p>
              <p className="text-lg font-bold text-white">{hasMMR ? fmt$(calc.allInCost) : '—'}</p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-3 text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Est. Gross Margin</p>
              <p className={`text-lg font-bold ${hasMMR ? marginColor : 'text-white'}`}>
                {hasMMR ? fmt$(calc.estimatedGrossMargin) : '—'}
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-3 text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">ROI</p>
              <p className={`text-lg font-bold ${hasMMR ? marginColor : 'text-white'}`}>
                {hasMMR ? `${calc.roi.toFixed(1)}%` : '—'}
              </p>
            </div>
          </div>

          {/* Cost breakdown table */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide">Cost Item</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">MMR (Market Value)</td>
                  <td className="px-4 py-2.5 text-right text-emerald-400 font-medium">{hasMMR ? fmt$(calc.mmr) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Buyer Premium ({inputs.buyerPremiumPct}% of bid)</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{hasMMR ? fmt$(calc.buyerPremiumAmount) : '—'}</td>
                </tr>
                {parseFloat(inputs.salesTaxPct) > 0 && (
                  <tr>
                    <td className="px-4 py-2.5 text-gray-300">Sales Tax ({inputs.salesTaxPct}% of bid)</td>
                    <td className="px-4 py-2.5 text-right text-red-400">-{hasMMR ? fmt$(calc.salesTaxAmount) : '—'}</td>
                  </tr>
                )}
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Auction Fees</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{hasMMR ? fmt$(calc.auctionFees) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Title & Doc Fees</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{hasMMR ? fmt$(calc.titleFees) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Transport</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{hasMMR ? fmt$(calc.transport) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Recon Estimate</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{hasMMR ? fmt$(calc.recon) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Target Margin</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{hasMMR ? fmt$(calc.targetMargin) : '—'}</td>
                </tr>
                <tr className="border-t-2 border-emerald-800/60">
                  <td className="px-4 py-3 font-bold text-white">MAX BID CEILING</td>
                  <td className={`px-4 py-3 text-right font-black text-lg ${maxBidColor}`}>
                    {hasMMR ? fmt$(calc.maxBid) : '—'}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Lock button */}
          <button
            onClick={lockTarget}
            disabled={!hasMMR}
            className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors"
          >
            <Lock className="h-4 w-4" />
            Lock Target
          </button>

          <form onSubmit={handleOutcomeSubmit} className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-200">Log Sale Outcome</h3>
              <p className="text-xs text-gray-400 mt-1">Capture the final result after the unit sells.</p>
            </div>

            {!dealIdParam && (
              <div>
                <label className={labelCls}>Opportunity ID</label>
                <input
                  type="text"
                  className={inputCls}
                  placeholder="Enter opportunity ID"
                  value={outcomeForm.opportunityId}
                  onChange={e => setOutcomeField('opportunityId', e.target.value)}
                />
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Sale Price ($)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  className={inputCls}
                  value={outcomeForm.salePrice}
                  onChange={e => setOutcomeField('salePrice', e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Sale Date</label>
                <input
                  type="date"
                  required
                  className={inputCls}
                  value={outcomeForm.saleDate}
                  onChange={e => setOutcomeField('saleDate', e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Days to Sale</label>
                <input
                  type="number"
                  min="0"
                  required
                  className={inputCls}
                  value={outcomeForm.daysToSale}
                  onChange={e => setOutcomeField('daysToSale', e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className={labelCls}>Notes (optional)</label>
              <textarea
                className={`${inputCls} min-h-24 resize-y`}
                placeholder="Anything notable about the sale outcome"
                value={outcomeForm.notes}
                onChange={e => setOutcomeField('notes', e.target.value)}
              />
            </div>

            <button
              type="submit"
              disabled={savingOutcome}
              className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors"
            >
              {savingOutcome ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}
              {savingOutcome ? 'Saving...' : 'Log Sale'}
            </button>
          </form>
        </div>
      </div>

      {/* ── SAVED TARGETS ────────────────────────────────────────────────────── */}
      {saved.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-3">
            Saved Targets ({saved.length})
          </h3>
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-x-auto">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="border-b border-gray-800">
                  {['Vehicle', 'Source', 'MMR', 'Max Bid', 'Est. Margin', 'ROI', 'Saved', ''].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide last:text-right">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {saved.map(t => {
                  const marginOk = t.margin > 0;
                  return (
                    <tr key={t.id} className="hover:bg-gray-800/50 transition-colors">
                      <td className="px-4 py-3 text-white font-medium">{t.vehicle}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs">{t.source}</td>
                      <td className="px-4 py-3 text-gray-300">{fmt$(t.mmr)}</td>
                      <td className="px-4 py-3 text-emerald-400 font-semibold">{fmt$(t.maxBid)}</td>
                      <td className={`px-4 py-3 font-medium ${marginOk ? 'text-emerald-400' : 'text-red-400'}`}>
                        {fmt$(t.margin)}
                      </td>
                      <td className={`px-4 py-3 ${marginOk ? 'text-emerald-400' : 'text-red-400'}`}>
                        {t.roi.toFixed(1)}%
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(t.date)}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => loadTarget(t)}
                            title="Load into calculator"
                            className="text-gray-500 hover:text-emerald-400 transition-colors"
                          >
                            <Upload className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => deleteTarget(t.id)}
                            title="Delete"
                            className="text-gray-600 hover:text-red-400 transition-colors"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {saved.length === 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-center">
          <Lock className="h-8 w-8 text-gray-700 mx-auto mb-2" />
          <p className="text-gray-500 text-sm">No saved targets yet. Run a calculation and click "Lock Target" to save it.</p>
        </div>
      )}
    </div>
  );
}
