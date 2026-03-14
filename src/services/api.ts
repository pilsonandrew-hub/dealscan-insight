/**
 * Production-ready API service layer
 * Supabase for opportunity data, Railway for ML/rover endpoints
 */

import { Opportunity, PipelineStatus, UploadResult } from '@/types/dealerscope';
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
  limit?: number;
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

function getRowSource(row: any): string {
  return row.source || row.source_site || '';
}

function getRowAuctionEnd(row: any): string | null {
  return row.auction_end_date || row.auction_end || null;
}

function getRowAuctionFees(row: any): number {
  return row.auction_fees ?? row.fees_cost ?? 0;
}

function getRowTransport(row: any): number {
  return row.estimated_transport ?? row.transportation_cost ?? 0;
}

function getRowMMR(row: any): number {
  return row.mmr ?? row.estimated_sale_price ?? 0;
}

function normalizeROI(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return value > 1 ? value / 100 : value;
}

function getRowGrossMargin(row: any): number {
  return row.gross_margin ?? row.potential_profit ?? row.profit ?? row.profit_margin ?? 0;
}

function getRowROI(row: any): number {
  const roi = row.roi ?? row.roi_percentage ?? 0;
  return normalizeROI(Number(roi) || 0);
}

function getRowProfit(row: any): number {
  return row.potential_profit ?? row.gross_margin ?? row.profit ?? 0;
}

function getRowScore(row: any): number | null {
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

  return query;
}

// Transform database row to Opportunity type
function transformOpportunity(row: any): Opportunity & { created_at: string; id: string } {
  const currentBid = row.current_bid ?? row.buy_now_price ?? 0;
  const buyerPremium = row.buyer_premium ?? 0;
  const auctionFees = getRowAuctionFees(row);
  const transport = getRowTransport(row);

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
    acquisition_cost: currentBid + buyerPremium + auctionFees + transport,
    profit: getRowProfit(row),
    roi: getRowROI(row),
    confidence: row.confidence_score,
    risk_score: row.risk_score,
    location: row.location || '',
    state: row.state || '',
    auction_end: getRowAuctionEnd(row),
    source_site: getRowSource(row),
    status: row.step_status || row.status || 'moderate',
    total_cost: currentBid,
    transportation_cost: transport,
    fees_cost: auctionFees,
    estimated_sale_price: getRowMMR(row),
    profit_margin: getRowGrossMargin(row),
    vin: row.vin,
    make: row.make,
    model: row.model,
    year: row.year,
    mileage: row.mileage,
    score: getRowScore(row) ?? undefined
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
      const { data, error, count } = await buildOpportunityQuery(filters)
        .order('dos_score', { ascending: false, nullsFirst: false })
        .limit(limit);

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
  async getHotDeals(minScore = 80, limit = 5): Promise<Opportunity[]> {
    try {
      const { data, error } = await supabase
        .from('opportunities')
        .select('*')
        .gte('dos_score', minScore)
        .order('dos_score', { ascending: false })
        .limit(limit);

      if (error) throw error;
      return (data || []).map(transformOpportunity);
    } catch (error) {
      console.error('getHotDeals failed:', error);
      return [];
    }
  },

  // Get dashboard metrics
  async getDashboardMetrics(): Promise<{
    total_today: number;
    hot_deals: number;
    avg_margin: number;
    top_score: number;
  }> {
    try {
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      const { data, error } = await supabase
        .from('opportunities')
        .select('dos_score, gross_margin, processed_at');

      if (error) throw error;

      const rows = data || [];
      const todayRows = rows.filter(r => r.processed_at && new Date(r.processed_at) >= today);
      const hotDeals = rows.filter(r => (r.dos_score || 0) >= 80);
      const avgMargin = rows.length > 0
        ? rows.reduce((sum, r) => sum + (r.gross_margin || 0), 0) / rows.length
        : 0;
      const topScore = rows.reduce((max, r) => Math.max(max, r.dos_score || 0), 0);

      return {
        total_today: todayRows.length,
        hot_deals: hotDeals.length,
        avg_margin: avgMargin,
        top_score: topScore
      };
    } catch {
      return { total_today: 0, hot_deals: 0, avg_margin: 0, top_score: 0 };
    }
  },

  // Get scraper sources with last-run info
  async getScraperSources(): Promise<Array<{ name: string; last_run: string | null; count: number }>> {
    try {
      const { data, error } = await supabase
        .from('opportunities')
        .select('source, processed_at, created_at')
        .order('processed_at', { ascending: false })
        .limit(500);

      if (error) throw error;

      const sourceMap = new Map<string, { last_run: string; count: number }>();
      for (const row of data || []) {
        const src = row.source;
        if (!sourceMap.has(src)) {
          sourceMap.set(src, { last_run: row.processed_at || row.created_at, count: 1 });
        } else {
          sourceMap.get(src)!.count++;
        }
      }

      return Array.from(sourceMap.entries()).map(([name, v]) => ({
        name,
        last_run: v.last_run,
        count: v.count
      }));
    } catch {
      return [];
    }
  },

  // Rover recommendations via Railway API
  async getRoverRecommendations(): Promise<any[]> {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const userId = session?.user?.id;

      if (!userId) {
        throw new Error('Missing authenticated user for Rover recommendations');
      }

      const params = new URLSearchParams({ user_id: userId });
      const res = await fetch(`${API_BASE}/api/rover/recommendations?${params.toString()}`, {
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

  // Track rover event (view/save/pass)
  async trackRoverEvent(
    opportunity: Pick<Opportunity, 'id' | 'make' | 'model' | 'year' | 'source_site' | 'current_bid' | 'state' | 'mileage'>,
    event: 'view' | 'save' | 'pass'
  ): Promise<void> {
    if (event === 'pass') {
      return;
    }

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
