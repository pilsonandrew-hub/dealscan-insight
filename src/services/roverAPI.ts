import { supabase } from "@/integrations/supabase/client";
import { logger } from "@/lib/logger";
import { settings } from "@/config/settings";

const API_BASE = settings.api.baseUrl;

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
  source?: 'personalized' | 'fallback';
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
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      await fetch(`${API_BASE}/api/rover/events`, {
        method: "POST",
        headers,
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
      const token = session?.access_token;
      const userId = session?.user?.id;
      if (!userId) throw new Error("No user session");
      const resp = await fetch(`${API_BASE}/api/rover/recommendations?user_id=${encodeURIComponent(userId)}&limit=${limit}`, {
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

  private mapOpportunityToDealItem(opportunity: any): DealItem {
    return {
      id: opportunity.id,
      make: opportunity.make,
      model: opportunity.model,
      year: opportunity.year,
      price: opportunity.current_bid ?? opportunity.estimated_sale_price ?? 0,
      current_bid: opportunity.current_bid ?? opportunity.estimated_sale_price ?? 0,
      mileage: opportunity.mileage,
      source: opportunity.source_site,
      source_site: opportunity.source_site,
      state: opportunity.state,
      vin: opportunity.vin,
      arbitrage_score: opportunity.dos_score,
      roi_percentage: opportunity.roi_percentage,
      potential_profit: opportunity.potential_profit,
    };
  }

  private async getFallbackRecommendations(limit: number = 25): Promise<RoverRecommendations> {
    const { data: opportunities } = await supabase
      .from('opportunities')
      .select('id,make,model,year,mileage,current_bid,estimated_sale_price,dos_score,state,source_site,vin,roi_percentage,potential_profit,auction_end_date')
      .gte('dos_score', 65)
      .or(`auction_end_date.gt.${new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString()},auction_end_date.is.null`)
      .order('dos_score', { ascending: false })
      .limit(limit);

    const items = (opportunities || []).map((opportunity) => this.mapOpportunityToDealItem(opportunity));
    return {
      precomputedAt: null,
      items,
      totalCount: items.length,
      confidence: 0,
      source: 'fallback',
    };
  }

  async getRecommendationsWithToken(userId: string, token: string, limit: number = 25): Promise<RoverRecommendations & { _debug?: string }> {
    try {
      const resp = await fetch(`${API_BASE}/api/rover/recommendations?user_id=${encodeURIComponent(userId)}&limit=${limit}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        const body = await resp.text();
        const fallback = await this.getFallbackRecommendations(limit);
        return { ...fallback, _debug: `HTTP ${resp.status}: ${body.slice(0,80)}` };
      }
      const data = await resp.json() as RoverRecommendations;
      if ((data.items?.length ?? 0) === 0) {
        const fallback = await this.getFallbackRecommendations(limit);
        return { ...fallback, _debug: `OK 0 items` };
      }
      return { ...data, source: 'personalized', _debug: `OK ${data.items?.length ?? 0} items` };
    } catch (error) {
      const fallback = await this.getFallbackRecommendations(limit);
      return { ...fallback, _debug: `Error: ${String(error).slice(0,80)}` };
    }
  }

  async saveIntent(
    query: any,
    title: string,
    options?: { dosThreshold?: number; telegramChatId?: string }
  ): Promise<void> {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const resp = await fetch(`${API_BASE}/api/saved-searches`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          name: title,
          filters: query || {},
          dos_threshold: options?.dosThreshold ?? 65,
          telegram_chat_id: options?.telegramChatId?.trim() || undefined,
        }),
      });

      if (!resp.ok) {
        throw new Error(`Saved search API error: ${resp.status}`);
      }

      logger.info('Rover intent saved', { title });
    } catch (error) {
      logger.error('Failed to save Rover intent', { 
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined
      });
      throw error;
    }
  }

}

export const roverAPI = new RoverAPIService();
