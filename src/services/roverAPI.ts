import { supabase } from "@/integrations/supabase/client";
import { logger } from "@/lib/logger";

export interface RoverEvent {
  userId: string;
  event: 'view' | 'click' | 'save' | 'bid' | 'purchase' | 'pass';
  item: DealItem;
  timestamp?: number;
}

export interface DealItem {
  id: string;
  deal_id?: string;
  make: string;
  model: string;
  year: number;
  price: number;
  current_bid?: number;
  mileage?: number;
  bodyType?: string;
  source?: string;
  source_site?: string;
  sellerId?: string;
  mmr?: number;
  city?: string;
  state?: string;
  vin?: string;
  _score?: number;
  arbitrage_score?: number;
  roi_percentage?: number;
  potential_profit?: number;
  why_signals?: string[];
}

export interface RoverRecommendations {
  precomputedAt: number | null;
  items: DealItem[];
  totalCount: number;
  confidence: number;
}

export interface UserPreferences {
  makes: Record<string, number>;
  models: Record<string, number>;
  bodyTypes: Record<string, number>;
  priceRange: [number, number];
  mileageRange: [number, number];
  states: Record<string, number>;
}

class RoverAPIService {
  private eventWeights = {
    view: 0.2,
    click: 1,
    save: 3,
    bid: 5,
    purchase: 8,
    pass: -1.5,
  };

  private decayHalfLife = 72 * 60 * 60 * 1000; // 72 hours in ms

  private buildEventItem(item: DealItem) {
    return {
      deal_id: item.deal_id || item.id,
      id: item.id,
      make: item.make,
      model: item.model,
      year: item.year,
      source: item.source_site || item.source || "",
      source_site: item.source_site || item.source || "",
      price: item.current_bid ?? item.price ?? 0,
      current_bid: item.current_bid ?? item.price ?? 0,
      state: item.state || "",
      mileage: item.mileage ?? null,
    };
  }

  async trackEvent(event: RoverEvent): Promise<void> {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "https://dealscan-insight-production.up.railway.app";
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      await fetch(`${apiUrl}/api/rover/events`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          event: event.event,
          userId: event.userId,
          user_id: event.userId,
          item: this.buildEventItem(event.item),
        }),
      });
    } catch (error) {
      // Fire and forget - don't block UX on tracking failures
      logger.warn("Rover event tracking failed", { message: String(error) });
    }
  }

  async getRecommendations(limit: number = 25): Promise<RoverRecommendations> {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const user = session?.user;
      const token = session?.access_token;
      if (!user) return { precomputedAt: null, items: [], totalCount: 0, confidence: 0 };

      const apiUrl = import.meta.env.VITE_API_URL || "https://dealscan-insight-production.up.railway.app";
      const resp = await fetch(`${apiUrl}/api/rover/recommendations?user_id=${user.id}&limit=${limit}`, {
        headers: {
          Authorization: token ? `Bearer ${token}` : "",
        },
      });

      if (!resp.ok) throw new Error(`Rover API error: ${resp.status}`);

      const data = await resp.json();
      return data as RoverRecommendations;
    } catch (error) {
      logger.error("Rover recommendations failed", { message: String(error) });
      // Fallback: return empty with cold start indicator
      return { precomputedAt: null, items: [], totalCount: 0, confidence: 0 };
    }
  }

  async getRecommendationsWithToken(userId: string, token: string, limit: number = 25): Promise<RoverRecommendations & { _debug?: string }> {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "https://dealscan-insight-production.up.railway.app";
      const resp = await fetch(`${apiUrl}/api/rover/recommendations?user_id=${userId}&limit=${limit}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        const body = await resp.text();
        return { precomputedAt: null, items: [], totalCount: 0, confidence: 0, _debug: `HTTP ${resp.status}: ${body.slice(0,80)}` };
      }
      const data = await resp.json() as RoverRecommendations;
      return { ...data, _debug: `OK ${data.items?.length ?? 0} items` };
    } catch (error) {
      return { precomputedAt: null, items: [], totalCount: 0, confidence: 0, _debug: `Error: ${String(error).slice(0,80)}` };
    }
  }

  private async generateRecommendations(userId: string, limit: number): Promise<RoverRecommendations> {
    try {
      // Get user preferences from past events
      const preferences = await this.getUserPreferences(userId);
      
      // Get available opportunities - use ML service for scoring
      const { data: opportunities } = await supabase
        .from('opportunities')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(500);

      if (!opportunities) {
        return { precomputedAt: null, items: [], totalCount: 0, confidence: 0 };
      }

      // Use ML service for enhanced scoring
      const { roverMLService } = await import('./roverMLService');
      const scoredItems = await roverMLService.scoreOpportunities(opportunities, preferences);

      // Filter and sort
      const finalItems = scoredItems
        .filter(item => item._score && item._score > 0.1)
        .sort((a, b) => (b._score || 0) - (a._score || 0))
        .slice(0, limit);

      const confidence = finalItems.length > 0 ? 
        Math.min(0.95, 0.5 + (finalItems[0]._score || 0) * 0.5) : 0;

      // Record metrics
      const { roverMetrics } = await import('./roverMetrics');
      roverMetrics.recordMLScoringLatency(Date.now() - performance.now());

      return {
        precomputedAt: Date.now(),
        items: finalItems,
        totalCount: finalItems.length,
        confidence
      };
    } catch (error) {
      logger.error('Failed to generate recommendations', { 
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined
      });
      return { precomputedAt: null, items: [], totalCount: 0, confidence: 0 };
    }
  }

  private async getUserPreferences(userId: string): Promise<UserPreferences> {
    try {
      const { data: events } = await (supabase as any)
        .from('rover_events')
        .select('*')
        .eq('user_id', userId)
        .gt('timestamp', new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()) // Last 30 days
        .order('timestamp', { ascending: false });

      const preferences: UserPreferences = {
        makes: {},
        models: {},
        bodyTypes: {},
        priceRange: [0, 100000],
        mileageRange: [0, 200000],
        states: {}
      };

      if (!events || events.length === 0) {
        return preferences;
      }

      // Aggregate preferences with decay
      events.forEach((event: any) => {
        const item = event.item_data as DealItem;
        const weight = event.weight || 1;

        if (item.make) preferences.makes[item.make] = (preferences.makes[item.make] || 0) + weight;
        if (item.model) preferences.models[item.model] = (preferences.models[item.model] || 0) + weight;
        if (item.bodyType) preferences.bodyTypes[item.bodyType] = (preferences.bodyTypes[item.bodyType] || 0) + weight;
        if (item.state) preferences.states[item.state] = (preferences.states[item.state] || 0) + weight;
      });

      return preferences;
    } catch (error) {
      logger.error('Failed to get user preferences', { 
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined
      });
      return {
        makes: {},
        models: {},
        bodyTypes: {},
        priceRange: [0, 100000],
        mileageRange: [0, 200000],
        states: {}
      };
    }
  }

  private scoreOpportunity(opportunity: any, preferences: UserPreferences): DealItem {
    let score = 0;
    
    const item: DealItem = {
      id: opportunity.id,
      make: opportunity.make,
      model: opportunity.model,
      year: opportunity.year,
      price: opportunity.current_bid || opportunity.estimated_sale_price,
      mileage: opportunity.mileage,
      source: opportunity.source_site,
      state: opportunity.state,
      vin: opportunity.vin,
      arbitrage_score: opportunity.score || 0,
      roi_percentage: opportunity.roi_percentage,
      potential_profit: opportunity.potential_profit
    };

    // Base arbitrage score
    if (opportunity.roi_percentage) {
      score += Math.min(1, opportunity.roi_percentage / 50) * 0.4;
    }

    // Preference matching
    if (item.make && preferences.makes[item.make]) {
      score += Math.min(0.3, preferences.makes[item.make] / 10);
    }

    if (item.model && preferences.models[item.model]) {
      score += Math.min(0.2, preferences.models[item.model] / 10);
    }

    if (item.state && preferences.states[item.state]) {
      score += Math.min(0.1, preferences.states[item.state] / 5);
    }

    // Recency bonus
    const daysSinceCreated = (Date.now() - new Date(opportunity.created_at).getTime()) / (24 * 60 * 60 * 1000);
    if (daysSinceCreated < 1) score += 0.1;
    else if (daysSinceCreated < 3) score += 0.05;

    item._score = Math.min(1, score);
    return item;
  }

  async saveIntent(query: any, title: string): Promise<void> {
    try {
      const { data: user } = await supabase.auth.getUser();
      if (!user.user) return;

      await supabase.from('crosshair_intents').insert({
        user_id: user.user.id,
        title,
        canonical_query: query,
        search_options: {},
        notify_on_first_match: true,
        is_active: true
      });

      logger.info('Rover intent saved', { title });
    } catch (error) {
      logger.error('Failed to save Rover intent', { 
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined
      });
    }
  }

  async createIntent(params: { title: string; make?: string; model?: string; year?: number }): Promise<void> {
    const { error } = await supabase
      .from("crosshair_intents")
      .insert({
        title: params.title,
        make: params.make,
        model: params.model,
        year: params.year,
        user_id: supabase.auth.getUser().user.id,
        is_active: true,
        created_at: new Date().toISOString()
      });
    if (error) throw error;
  }

  async getUserIntents(): Promise<any[]> {
    try {
      const { data: user } = await supabase.auth.getUser();
      if (!user.user) return [];

      const { data: intents } = await supabase
        .from('crosshair_intents')
        .select('*')
        .eq('user_id', user.user.id)
        .eq('is_active', true)
        .order('created_at', { ascending: false });

      return intents || [];
    } catch (error) {
      logger.error('Failed to get user intents', { 
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined
      });
      return [];
    }
  }
}

export const roverAPI = new RoverAPIService();
