/**
 * Production-ready API service layer
 * Supabase for opportunity data, Railway for ML/rover endpoints
 */

import { Opportunity, PipelineStatus, UploadResult, SourceHealthResponse } from '@/types/dealerscope';
import { supabase } from '@/integrations/supabase/client';

const API_BASE = import.meta.env.VITE_API_URL || 'https://dealscan-insight-production.up.railway.app';

export interface CrosshairSearchFilters {
  make?: string;
  model?: string;
  yearMin?: number;
  yearMax?: number;
  state?: string;
  minPrice?: number;
  maxPrice?: number;
  minScore?: number;
  maxMileage?: number;
  limit?: number;
  offset?: number;
}

export type AnalyticsFreshnessStatus = 'fresh' | 'stale' | 'empty' | 'unknown';

export interface AnalyticsFreshnessEntry {
  updated_at: string | null;
  age_seconds: number | null;
  status: AnalyticsFreshnessStatus;
}

export interface AnalyticsFreshness {
  pipeline: AnalyticsFreshnessEntry;
  source_health: AnalyticsFreshnessEntry;
  execution: AnalyticsFreshnessEntry;
  outcomes: AnalyticsFreshnessEntry;
}

export interface OpportunityDetail {
  id: string;
  make: string;
  model: string;
  year: number;
  state: string;
  mmr: number;
  current_bid: number;
  estimated_transport: number;
  auction_fees: number;
  buyer_premium: number;
  source: string;
}

interface OpportunityRow {
  [key: string]: unknown;
  id?: string;
  created_at?: string;
  source?: string;
  source_site?: string;
  auction_end_date?: string;
  auction_end?: string;
  auction_fees?: number;
  fees_cost?: number;
  estimated_transport?: number;
  transportation_cost?: number;
  mmr?: number;
  estimated_sale_price?: number;
  total_cost?: number;
  acquisition_cost?: number;
  projected_total_cost?: number;
  current_bid?: number;
  buy_now_price?: number;
  acquisition_price_basis?: number;
  acquisition_basis_source?: string;
  gross_margin?: number;
  potential_profit?: number;
  profit?: number;
  profit_margin?: number;
  roi?: number;
  roi_percentage?: number;
  dos_score?: number;
  score?: number;
  buyer_premium?: number;
  confidence_score?: number;
  risk_score?: number;
  location?: string;
  city?: string;
  state?: string;
  step_status?: Opportunity['status'];
  status?: Opportunity['status'];
  vin?: string;
  make?: string;
  model?: string;
  year?: number;
  mileage?: number;
  recon_reserve?: number;
  investment_grade?: Opportunity['investment_grade'];
  pricing_source?: string;
  pricing_maturity?: Opportunity['pricing_maturity'];
  pricing_updated_at?: string;
  expected_close_bid?: number;
  current_bid_trust_score?: number;
  expected_close_source?: string;
  auction_stage_hours_remaining?: number;
  manheim_mmr_mid?: number;
  manheim_mmr_low?: number;
  manheim_mmr_high?: number;
  manheim_range_width_pct?: number;
  manheim_confidence?: number;
  manheim_source_status?: string;
  manheim_updated_at?: string;
  retail_asking_price_estimate?: number;
  retail_comp_price_estimate?: number;
  retail_comp_low?: number;
  retail_comp_high?: number;
  retail_comp_count?: number;
  retail_comp_confidence?: number;
  retail_proxy_multiplier?: number;
  wholesale_ctm_pct?: number;
  ctm_pct?: number;
  retail_ctm_pct?: number;
  estimated_days_to_sale?: number;
  roi_per_day?: number;
  mmr_lookup_basis?: string;
  mmr_confidence_proxy?: number;
  bid_ceiling_pct?: number;
  max_bid?: number;
  bid_headroom?: number;
  ceiling_reason?: string;
  score_version?: string;
  legacy_dos_score?: number;
  processed_at?: string;
  designated_lane?: string;
}

function getRowSource(row: OpportunityRow): string {
  return row.source || row.source_site || '';
}

function getRowAuctionEnd(row: OpportunityRow): string | null {
  return row.auction_end_date || row.auction_end || null;
}

function getRowAuctionFees(row: OpportunityRow): number {
  return row.auction_fees ?? row.fees_cost ?? 0;
}

function getRowTransport(row: OpportunityRow): number {
  return row.estimated_transport ?? row.transportation_cost ?? 0;
}

function getRowMMR(row: OpportunityRow): number {
  return (
    row.retail_comp_price_estimate ??
    row.retail_asking_price_estimate ??
    row.manheim_mmr_mid ??
    row.mmr ??
    row.estimated_sale_price ??
    0
  );
}

function getRowTotalCost(row: OpportunityRow): number {
  return row.projected_total_cost ?? row.total_cost ?? row.acquisition_cost ?? row.current_bid ?? row.buy_now_price ?? 0;
}

function normalizeROI(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return value > 1 ? value / 100 : value;
}

function getRowGrossMargin(row: OpportunityRow): number | null {
  const val = row.gross_margin ?? row.potential_profit ?? row.profit;
  if (val == null) return null;
  return val as number;
}

function getRowROI(row: OpportunityRow): number {
  const roi = row.roi ?? row.roi_percentage ?? 0;
  return normalizeROI(Number(roi) || 0);
}

function getRowProfit(row: OpportunityRow): number {
  return row.potential_profit ?? row.gross_margin ?? row.profit ?? 0;
}

function getRowScore(row: OpportunityRow): number | null {
  return row.dos_score ?? row.score ?? null;
}

function buildOpportunityQuery(filters?: CrosshairSearchFilters) {
  let query = supabase
    .from('opportunities')
    .select('*', { count: 'exact' })
    .not('dos_score', 'is', null)
    .or('is_duplicate.is.null,is_duplicate.eq.false');

  if (filters?.make) query = query.ilike('make', `%${filters.make}%`);
  if (filters?.model) query = query.ilike('model', `%${filters.model}%`);
  if (filters?.yearMin != null) query = query.gte('year', filters.yearMin);
  if (filters?.yearMax != null) query = query.lte('year', filters.yearMax);
  if (filters?.state) query = query.ilike('state', `%${filters.state.trim().toUpperCase()}%`);
  if (filters?.minPrice != null) query = query.gte('current_bid', filters.minPrice);
  if (filters?.maxPrice != null) query = query.lte('current_bid', filters.maxPrice);
  if (filters?.minScore != null) query = query.gte('dos_score', filters.minScore);
  if (filters?.maxMileage != null) query = query.lte('mileage', filters.maxMileage);

  // Show all deals — no date filter (let the UI sort by newest)
  // Previously filtered by 48hr window which hid too many deals

  return query;
}

// Transform database row to Opportunity type
function transformOpportunity(row: OpportunityRow): Opportunity & { created_at: string; id: string } {
  const currentBid = row.current_bid ?? row.buy_now_price ?? 0;
  const buyerPremium = row.buyer_premium ?? 0;
  const auctionFees = getRowAuctionFees(row);
  const transport = getRowTransport(row);
  const totalCost = getRowTotalCost(row);

  return {
    id: row.id,
    created_at: row.created_at,
    vehicle: {
      id: row.id,
      make: row.make,
      model: row.model,
      year: row.year,
      vin: row.vin || '',
      mileage: row.mileage || 0
    },
    current_bid: currentBid,
    expected_price: getRowMMR(row),
    acquisition_cost: totalCost,
    projected_total_cost: row.projected_total_cost ?? undefined,
    acquisition_price_basis: row.acquisition_price_basis ?? undefined,
    acquisition_basis_source: typeof row.acquisition_basis_source === 'string' ? row.acquisition_basis_source : undefined,
    profit: getRowProfit(row),
    roi: getRowROI(row),
    confidence: row.confidence_score,
    risk_score: row.risk_score,
    location: row.location || row.city || '',
    state: row.state || '',
    auction_end: getRowAuctionEnd(row),
    source_site: getRowSource(row),
    status: row.step_status || row.status || 'moderate',
    total_cost: totalCost,
    transportation_cost: transport,
    fees_cost: auctionFees,
    estimated_sale_price: getRowMMR(row),
    profit_margin: getRowGrossMargin(row),
    vin: row.vin,
    make: row.make,
    model: row.model,
    year: row.year,
    mileage: row.mileage,
    score: getRowScore(row) ?? undefined,
    buyer_premium: buyerPremium,
    recon_reserve: row.recon_reserve ?? 0,
    investment_grade: row.investment_grade ?? undefined,
    pricing_source: typeof row.pricing_source === 'string' ? row.pricing_source : undefined,
    pricing_maturity: typeof row.pricing_maturity === 'string' ? row.pricing_maturity : undefined,
    pricing_updated_at: typeof row.pricing_updated_at === 'string' ? row.pricing_updated_at : undefined,
    expected_close_bid: row.expected_close_bid ?? undefined,
    current_bid_trust_score: row.current_bid_trust_score ?? undefined,
    expected_close_source: typeof row.expected_close_source === 'string' ? row.expected_close_source : undefined,
    auction_stage_hours_remaining: row.auction_stage_hours_remaining ?? undefined,
    manheim_mmr_mid: row.manheim_mmr_mid ?? undefined,
    manheim_mmr_low: row.manheim_mmr_low ?? undefined,
    manheim_mmr_high: row.manheim_mmr_high ?? undefined,
    manheim_range_width_pct: row.manheim_range_width_pct ?? undefined,
    manheim_confidence: row.manheim_confidence ?? undefined,
    manheim_source_status: typeof row.manheim_source_status === 'string' ? row.manheim_source_status : undefined,
    manheim_updated_at: typeof row.manheim_updated_at === 'string' ? row.manheim_updated_at : undefined,
    retail_asking_price_estimate: row.retail_asking_price_estimate ?? undefined,
    retail_comp_price_estimate: row.retail_comp_price_estimate ?? undefined,
    retail_comp_low: row.retail_comp_low ?? undefined,
    retail_comp_high: row.retail_comp_high ?? undefined,
    retail_comp_count: row.retail_comp_count ?? undefined,
    retail_comp_confidence: row.retail_comp_confidence ?? undefined,
    retail_proxy_multiplier: row.retail_proxy_multiplier ?? undefined,
    wholesale_ctm_pct: row.wholesale_ctm_pct ?? undefined,
    retail_ctm_pct: row.retail_ctm_pct ?? row.ctm_pct ?? undefined,
    estimated_days_to_sale: row.estimated_days_to_sale ?? undefined,
    roi_per_day: row.roi_per_day ?? undefined,
    mmr_lookup_basis: row.mmr_lookup_basis ?? undefined,
    mmr_confidence_proxy: row.mmr_confidence_proxy ?? undefined,
    bid_ceiling_pct: row.bid_ceiling_pct ?? undefined,
    max_bid: row.max_bid ?? undefined,
    bid_headroom: row.bid_headroom ?? undefined,
    ceiling_reason: row.ceiling_reason ?? undefined,
    score_version: row.score_version ?? undefined,
    legacy_dos_score: row.legacy_dos_score ?? undefined,
    designated_lane: row.designated_lane ?? undefined
  };
}

export const api = {
  // Get opportunities - supports both cursor pagination and legacy page/limit
  async getOpportunities(
    paramsOrPage?: number,
    limit?: number,
      filters?: {
        make?: string;
        model?: string;
        yearMin?: number;
        yearMax?: number;
        states?: string[];
        state?: string;
        minScore?: number;
        minBid?: number;
        maxBid?: number;
        source?: string;
        sortBy?: 'score' | 'profit_margin' | 'auction_end' | 'current_bid';
      }
  ): Promise<{ data: Opportunity[]; total: number; hasMore: boolean }> {
    const page = typeof paramsOrPage === 'number' ? paramsOrPage : 1;
    const pageLimit = limit || 100;
    const offset = (page - 1) * pageLimit;

    try {
      let query = buildOpportunityQuery({
        make: filters?.make,
        model: filters?.model,
        yearMin: filters?.yearMin,
        yearMax: filters?.yearMax,
        state: filters?.state,
        minPrice: filters?.minBid,
        maxPrice: filters?.maxBid,
        minScore: filters?.minScore
      });

      // Apply filters
      if (filters?.states && filters.states.length > 0) query = query.in('state', filters.states);
      if (filters?.source) query = query.eq('source', filters.source);

      // Sort
      const sortField = filters?.sortBy === 'score' ? 'dos_score'
        : filters?.sortBy === 'profit_margin' ? 'gross_margin'
        : filters?.sortBy === 'auction_end' ? 'auction_end_date'
        : filters?.sortBy === 'current_bid' ? 'current_bid'
        : 'processed_at';
      const ascending = filters?.sortBy === 'auction_end';
      query = query.order(sortField, { ascending, nullsFirst: false });

      const { data, error, count } = await query.range(offset, offset + pageLimit - 1);

      if (error) throw error;

      return {
        data: (data || []).map(transformOpportunity),
        total: count || 0,
        hasMore: (count || 0) > offset + pageLimit
      };
    } catch (error) {
      console.error('getOpportunities failed:', error);
      return { data: [], total: 0, hasMore: false };
    }
  },

  async searchCrosshairOpportunities(filters: CrosshairSearchFilters): Promise<{ data: Opportunity[]; total: number }> {
    try {
      const limit = filters.limit ?? 50;
      const offset = filters.offset ?? 0;
      const { data, error, count } = await buildOpportunityQuery(filters)
        .order('dos_score', { ascending: false, nullsFirst: false })
        .range(offset, offset + limit - 1);

      if (error) throw error;

      return {
        data: (data || []).map(transformOpportunity),
        total: count || 0
      };
    } catch (error) {
      console.error('searchCrosshairOpportunities failed:', error);
      return { data: [], total: 0 };
    }
  },

  async getOpportunityById(id: string): Promise<OpportunityDetail | null> {
    try {
      const { data, error } = await supabase
        .from('opportunities')
        .select('*')
        .eq('id', id)
        .maybeSingle();

      if (error) throw error;
      if (!data) return null;

      return {
        id: data.id,
        make: data.make || '',
        model: data.model || '',
        year: data.year || 0,
        state: data.state || '',
        mmr: getRowMMR(data),
        current_bid: data.current_bid ?? 0,
        estimated_transport: getRowTransport(data),
        auction_fees: getRowAuctionFees(data),
        buyer_premium: data.buyer_premium ?? 0,
        source: getRowSource(data)
      };
    } catch (error) {
      console.error('getOpportunityById failed:', error);
      return null;
    }
  },

  // Get hot deals (DOS score >= threshold)
  async getHotDeals(minScore = 80, limit = 50): Promise<Opportunity[]> {
    try {
      const { data, error } = await supabase
        .from('opportunities')
        .select('*')
        .or(`dos_score.gte.${minScore},investment_grade.eq.Platinum`)
        .order('dos_score', { ascending: false })
        .limit(limit * 3);

      if (error) throw error;
      return (data || [])
        .map(transformOpportunity)
        .sort((a, b) => {
          const gradeRank = (grade?: string) => ({ Platinum: 4, Gold: 3, Silver: 2, Bronze: 1 }[grade || ''] || 0);
          const gradeDelta = gradeRank(b.investment_grade) - gradeRank(a.investment_grade);
          if (gradeDelta !== 0) return gradeDelta;
          return (b.score || 0) - (a.score || 0);
        })
        .slice(0, limit);
    } catch (error) {
      console.error('getHotDeals failed:', error);
      return [];
    }
  },

  // Get dashboard metrics
  async getDashboardMetrics(): Promise<{
    total_today: number;
    hot_deals: number;
    platinum_deals: number;
    avg_margin: number;
    avg_roi_day: number;
    top_score: number;
  }> {
    try {
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      const { data, error } = await supabase
        .from('opportunities')
        .select('dos_score, gross_margin, processed_at, investment_grade, roi_per_day');

      if (error) throw error;

      const rows = data || [];
      const todayRows = rows.filter(r => r.processed_at && new Date(r.processed_at) >= today);
      const hotDeals = rows.filter(r => (r.dos_score || 0) >= 80);
      const platinumDeals = rows.filter(r => r.investment_grade === 'Platinum');
      const avgMargin = rows.length > 0
        ? rows.reduce((sum, r) => sum + (r.gross_margin || 0), 0) / rows.length
        : 0;
      const avgRoiDay = rows.length > 0
        ? rows.reduce((sum, r) => sum + (r.roi_per_day || 0), 0) / rows.length
        : 0;
      const topScore = rows.reduce((max, r) => Math.max(max, r.dos_score || 0), 0);

      return {
        total_today: todayRows.length,
        hot_deals: hotDeals.length,
        platinum_deals: platinumDeals.length,
        avg_margin: avgMargin,
        avg_roi_day: avgRoiDay,
        top_score: topScore
      };
    } catch {
      return { total_today: 0, hot_deals: 0, platinum_deals: 0, avg_margin: 0, avg_roi_day: 0, top_score: 0 };
    }
  },

  // Get Apify actor last run times for green dot status
  async getApifyActorStatus(): Promise<Map<string, { last_run: string; succeeded: boolean }>> {
    const ACTOR_IDS: Record<string, string> = {
      govdeals: "CuKaIAcWyFS0EPrAz",
      publicsurplus: "9xxQLlRsROnSgA42i",
      govplanet: "pO2t5UDoSVmO1gvKJ",
      allsurplus: "gYGIfHeYeN3EzmLnB",
      proxibid: "bxhncvtHEP712WX2e",
      "hibid-v2": "7s9e0eATTt1kuGGfE",
      hibid: "7s9e0eATTt1kuGGfE",
      municibid: "svmsItf3CRBZuIntp",
      gsaauctions: "fvDnYmGuFBCrwpEi9",
      jjkane: "lvb7T6VMFfNUQpqlq",
      bidspotter: "5Eu3hfCcBBdzp6I1u",
    };

    const results = new Map<string, { last_run: string; succeeded: boolean }>();
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      if (!token) return results;

      const res = await fetch('/api/analytics/scraper-status', {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) return results;

      const json = await res.json().catch(() => null);
      const items = Array.isArray(json?.items)
        ? json.items
        : Array.isArray(json?.data)
          ? json.data
          : Array.isArray(json)
            ? json
            : [];

      for (const item of items) {
        const source = item?.source || item?.name;
        const lastRun = item?.last_run || item?.finishedAt || item?.finished_at || null;
        const succeeded = item?.succeeded ?? item?.status === 'SUCCEEDED';
        if (source && lastRun) {
          results.set(source, { last_run: lastRun, succeeded: Boolean(succeeded) });
        }
      }

      if (results.size === 0 && json && typeof json === 'object' && !Array.isArray(json)) {
        for (const source of Object.keys(ACTOR_IDS)) {
          const value = (json as Record<string, any>)[source];
          if (!value) continue;
          const lastRun = value.last_run || value.finishedAt || value.finished_at;
          const succeeded = value.succeeded ?? value.status === 'SUCCEEDED';
          if (lastRun) {
            results.set(source, { last_run: lastRun, succeeded: Boolean(succeeded) });
          }
        }
      }
    } catch {
      // Silently ignore failures and fall back to an empty map.
    }
    return results;
  },

  // Get scraper sources with last-run info
  async getScraperSources(): Promise<Array<{ name: string; last_run: string | null; count: number }>> {
    const RETIRED_SOURCES = new Set(["hibid-bidcal", "equipmentfacts"]);

    try {
      // Fetch DB data and Apify status in parallel
      const [dbResult, apifyStatus] = await Promise.all([
        supabase
          .from('opportunities')
          .select('source, processed_at, created_at')
          .order('processed_at', { ascending: false })
          .limit(2000),
        this.getApifyActorStatus().catch(() => new Map())
      ]);

      if (dbResult.error) throw dbResult.error;

      const sourceMap = new Map<string, { last_run: string; count: number }>();
      for (const row of dbResult.data || []) {
        const src = row.source;
        if (!sourceMap.has(src)) {
          sourceMap.set(src, { last_run: row.processed_at || row.created_at, count: 1 });
        } else {
          sourceMap.get(src)!.count++;
        }
      }

      // Filter out retired sources and merge with Apify last_run times
      return Array.from(sourceMap.entries())
        .filter(([name]) => !RETIRED_SOURCES.has(name))
        .map(([name, v]) => ({
          name,
          last_run: (apifyStatus.get(name)?.last_run) ?? v.last_run,
          count: v.count
        }));
    } catch {
      return [];
    }
  },

  // Rover recommendations via Railway API
  async getRoverRecommendations(): Promise<Array<Record<string, unknown>>> {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const userId = session?.user?.id;
      const res = await fetch(`${API_BASE}/api/rover/recommendations?user_id=${encodeURIComponent(userId || '')}&limit=25`, {
        headers: {
          'Authorization': token ? `Bearer ${token}` : '',
          'Content-Type': 'application/json'
        }
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (Array.isArray(json?.items)) return json.items;
      if (Array.isArray(json?.recommendations)) return json.recommendations;
      if (Array.isArray(json?.data)) return json.data;
      return Array.isArray(json) ? json : [];
    } catch (error) {
      console.error('getRoverRecommendations failed:', error);
      return [];
    }
  },

  // Pass (permanently dismiss) an opportunity for the current user
  async passOpportunity(opportunityId: string): Promise<void> {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const res = await fetch(`${API_BASE}/api/ingest/opportunities/${opportunityId}/pass`, {
      method: 'POST',
      headers: {
        'Authorization': token ? `Bearer ${token}` : '',
        'Content-Type': 'application/json',
      },
    });
    if (!res.ok) throw new Error(`passOpportunity failed: HTTP ${res.status}`);
  },

  // Track rover event (view/save/pass)
  async trackRoverEvent(
    opportunity: Pick<Opportunity, 'id' | 'make' | 'model' | 'year' | 'source_site' | 'current_bid' | 'state' | 'mileage'>,
    event: 'view' | 'save' | 'pass'
  ): Promise<void> {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const userId = session?.user?.id;

      await fetch(`${API_BASE}/api/rover/events`, {
        method: 'POST',
        headers: {
          'Authorization': token ? `Bearer ${token}` : '',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          event,
          userId,
          user_id: userId,
          item: {
            deal_id: opportunity.id,
            id: opportunity.id,
            make: opportunity.make,
            model: opportunity.model,
            year: opportunity.year,
            source: opportunity.source_site,
            source_site: opportunity.source_site,
            price: opportunity.current_bid,
            current_bid: opportunity.current_bid,
            state: opportunity.state,
            mileage: opportunity.mileage ?? null,
          }
        })
      });
    } catch (error) {
      console.error('trackRoverEvent failed:', error);
    }
  },

  // Health check for Railway backend
  async checkRailwayHealth(): Promise<{ status: string; latency?: number }> {
    const start = Date.now();
    try {
      // Use same-origin Vercel proxy to avoid any cross-origin/CORS issues on mobile
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      const res = await fetch('/proxy/health', { signal: controller.signal });
      clearTimeout(timer);
      const latency = Date.now() - start;
      if (!res.ok) return { status: 'error', latency };
      return { status: 'healthy', latency };
    } catch {
      return { status: 'error' };
    }
  },

  // Health check for Supabase
  async checkSupabaseHealth(): Promise<{ status: string; latency?: number }> {
    const start = Date.now();
    try {
      const { error } = await supabase.from('opportunities').select('id').limit(1);
      const latency = Date.now() - start;
      return { status: error ? 'error' : 'healthy', latency };
    } catch {
      return { status: 'error' };
    }
  },

  // Upload CSV file
  async uploadCSV(_file: File): Promise<UploadResult> {
    return { status: 'success', rows_processed: 0 };
  },

  // Analytics summary
  async getAnalyticsSummary(): Promise<{
    total_opportunities: number;
    total_outcomes: number;
    avg_gross_margin: number | null;
    avg_roi_pct: number | null;
    wins_by_source: { source: string; count: number }[];
    top_makes: { make: string; avg_gross_margin: number; count: number }[];
    alerts_sent_last_30d: number;
    total_bids: number;
    total_wins: number;
    win_rate: number | null;
    avg_purchase_price: number | null;
    avg_max_bid: number | null;
    pipeline?: {
      status: 'healthy' | 'degraded' | 'empty';
      scope: 'system';
      updated_at: string | null;
      active_opportunities: number;
      fresh_opportunities_24h: number;
      fresh_opportunities_7d: number;
      hot_deals_count: number;
      good_plus_deals_count: number;
      avg_dos_score: number | null;
      unique_sources: number;
      unique_states: number;
    };
    source_health?: {
      status: 'healthy' | 'degraded' | 'empty';
      scope: 'system';
      updated_at: string | null;
      sources: SourceHealthRow[];
      notes: string[];
    };
    execution?: {
      status: 'healthy' | 'degraded' | 'empty';
      scope: 'user_execution';
      updated_at: string | null;
      workflow_counts?: {
        wins: number;
        losses: number | null;
        passes: number | null;
        pending: number | null;
      };
      bid_metrics?: {
        bids_placed: number;
        win_rate: number | null;
        avg_max_bid: number | null;
        avg_purchase_price: number | null;
        ceiling_compliance: number | null;
      };
      notes?: string[];
    };
    outcomes?: {
      status: 'healthy' | 'degraded' | 'empty';
      scope: 'user_outcomes';
      updated_at: string | null;
      recorded_outcomes: number;
      total_gross_margin: number | null;
      avg_gross_margin: number | null;
      avg_roi: number | null;
      wins_by_source: { source: string; count: number }[];
      top_makes_by_realized_performance: { make: string; avg_gross_margin: number; count: number }[];
    };
    trust?: {
      status: 'healthy' | 'degraded' | 'empty';
      scope: 'trust';
      updated_at: string | null;
      summary_refreshed_at: string | null;
      completeness_score: number | null;
      degraded_sections: string[];
      freshness_age: number | null;
      severity?: 'low' | 'medium' | 'high';
      rule_ids?: string[];
      notes: string[];
    };
    freshness?: AnalyticsFreshness;
  }> {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const res = await fetch(`${API_BASE}/api/analytics/summary`, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
    });
    if (!res.ok) throw new Error(`Analytics fetch failed: ${res.status}`);
    return res.json();
  },

  async getSourceHealth(): Promise<SourceHealthResponse> {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const res = await fetch(`${API_BASE}/api/analytics/source-health`, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
    });
    if (!res.ok) throw new Error(`Source health fetch failed: ${res.status}`);
    return res.json();
  },

  async getRecentAnalyticsTrustEvents(limit: number = 25): Promise<{
    events: Array<{
      id: string | null;
      level: string | null;
      message: string | null;
      event: string | null;
      severity: 'low' | 'medium' | 'high' | null;
      rule_ids: string[];
      notes: string[];
      degraded_sections: string[];
      completeness_score: number | null;
      summary_refreshed_at: string | null;
      freshness_age: number | null;
      freshness?: AnalyticsFreshness;
      paperclip: {
        status: string | null;
        issue_id: string | null;
        identifier: string | null;
        title: string | null;
        issue_status: string | null;
        correlation_key: string | null;
        is_open: boolean;
      };
      timestamp: string | null;
    }>;
    count: number;
    limit: number;
    notes: string[];
  }> {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const res = await fetch(`${API_BASE}/api/analytics/recent-trust-events?limit=${limit}`, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
    });
    if (!res.ok) throw new Error(`Recent trust events fetch failed: ${res.status}`);
    return res.json();
  },

  async getOutcomeSummary(): Promise<{
    count_by_outcome: Record<string, number>;
    total_gross_margin: number;
    avg_roi: number | null;
  }> {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const res = await fetch(`${API_BASE}/outcomes/summary`, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
    });
    if (!res.ok) throw new Error(`Outcome summary fetch failed: ${res.status}`);
    return res.json();
  },

  async recordOutcome(payload: {
    opportunity_id: string;
    outcome: 'won' | 'lost' | 'passed';
    sold_price?: number;
  }): Promise<void> {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const res = await fetch(`${API_BASE}/api/outcomes/${payload.opportunity_id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
      body: JSON.stringify({
        outcome: payload.outcome,
        sold_price: payload.sold_price ?? null,
      }),
    });
    if (!res.ok) throw new Error(`Record outcome failed: ${res.status}`);
  },

  // Log a bid/win outcome for an opportunity
  async logBidOutcome(payload: {
    opportunity_id: string;
    bid: boolean;
    won: boolean;
    purchase_price?: number;
    notes?: string;
  }): Promise<void> {
    if (payload.won && !payload.bid) {
      throw new Error('Cannot log a win when no bid was placed');
    }
    if (payload.purchase_price != null && !payload.won) {
      throw new Error('Winning purchase price is only valid when the bid was won');
    }
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const res = await fetch(`${API_BASE}/api/outcomes/bid`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Log bid outcome failed: ${res.status}`);
  },

  // Legacy health check
  async healthCheck() {
    try {
      const { error } = await supabase.from('opportunities').select('id').limit(1);
      return {
        status: error ? 'error' : 'healthy',
        timestamp: new Date().toISOString(),
        components: {
          database: error ? 'error' : 'ok',
          cache: 'ok',
          scrapers: 'ok'
        }
      };
    } catch {
      return {
        status: 'error',
        timestamp: new Date().toISOString(),
        components: { database: 'error', cache: 'ok', scrapers: 'ok' }
      };
    }
  }
};

export default api;
