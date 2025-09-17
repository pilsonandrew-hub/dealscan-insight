import { supabase } from "@/integrations/supabase/client";
import { logger } from "@/lib/logger";

export interface RoverEvent {
  userId: string;
  event: 'view' | 'click' | 'save' | 'bid' | 'purchase';
  item: DealItem;
  timestamp?: number;
}

export interface DealItem {
  id: string;
  make: string;
  model: string;
  year: number;
  price: number;
  mileage?: number;
  bodyType?: string;
  source?: string;
  sellerId?: string;
  mmr?: number;
  city?: string;
  state?: string;
  vin?: string;
  _score?: number;
  arbitrage_score?: number;
  roi_percentage?: number;
  potential_profit?: number;
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
    purchase: 8
  };

  private decayHalfLife = 72 * 60 * 60 * 1000; // 72 hours in ms

  async trackEvent(event: RoverEvent): Promise<void> {
    try {
      const { data: user } = await supabase.auth.getUser();
      if (!user.user) return;

      const weight = this.eventWeights[event.event];
      const decayedWeight = weight * Math.exp(-Math.log(2) * 
        (Date.now() - (event.timestamp || Date.now())) / this.decayHalfLife);

      // Store event for ML training
      await supabase.from('rover_events').insert({
        user_id: user.user.id,
        event_type: event.event,
        item_data: event.item,
        weight: decayedWeight,
        timestamp: new Date(event.timestamp || Date.now()).toISOString()
      });

      logger.info('Rover event tracked', { event: event.event, item: event.item.id });
    } catch (error) {
      logger.error('Failed to track Rover event', error as Error);
    }
  }

  async getRecommendations(limit = 25): Promise<RoverRecommendations> {
    try {
      const { data: user } = await supabase.auth.getUser();
      if (!user.user) {
        throw new Error('User not authenticated');
      }

      // Check for cached recommendations first
      const { data: cached } = await supabase
        .from('rover_recommendations')
        .select('*')
        .eq('user_id', user.user.id)
        .gt('expires_at', new Date().toISOString())
        .order('created_at', { ascending: false })
        .limit(1)
        .single();

      if (cached) {
        return {
          precomputedAt: new Date(cached.created_at).getTime(),
          items: cached.recommendations.slice(0, limit),
          totalCount: cached.recommendations.length,
          confidence: cached.confidence || 0.8
        };
      }

      // Generate fresh recommendations
      const recommendations = await this.generateRecommendations(user.user.id, limit);
      
      // Cache the results
      await supabase.from('rover_recommendations').insert({
        user_id: user.user.id,
        recommendations: recommendations.items,
        confidence: recommendations.confidence,
        expires_at: new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString() // 4 hours
      });

      return recommendations;
    } catch (error) {
      logger.error('Failed to get Rover recommendations', error as Error);
      throw error;
    }
  }

  private async generateRecommendations(userId: string, limit: number): Promise<RoverRecommendations> {
    try {
      // Get user preferences from past events
      const preferences = await this.getUserPreferences(userId);
      
      // Get available opportunities
      const { data: opportunities } = await supabase
        .from('opportunities')
        .select('*')
        .eq('is_active', true)
        .order('created_at', { ascending: false })
        .limit(500);

      if (!opportunities) {
        return { precomputedAt: null, items: [], totalCount: 0, confidence: 0 };
      }

      // Score and rank opportunities
      const scoredItems = opportunities
        .map(opp => this.scoreOpportunity(opp, preferences))
        .filter(item => item._score && item._score > 0.1)
        .sort((a, b) => (b._score || 0) - (a._score || 0))
        .slice(0, limit);

      const confidence = scoredItems.length > 0 ? 
        Math.min(0.95, 0.5 + (scoredItems[0]._score || 0) * 0.5) : 0;

      return {
        precomputedAt: Date.now(),
        items: scoredItems,
        totalCount: scoredItems.length,
        confidence
      };
    } catch (error) {
      logger.error('Failed to generate recommendations', error as Error);
      return { precomputedAt: null, items: [], totalCount: 0, confidence: 0 };
    }
  }

  private async getUserPreferences(userId: string): Promise<UserPreferences> {
    try {
      const { data: events } = await supabase
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
      events.forEach(event => {
        const item = event.item_data as DealItem;
        const weight = event.weight || 1;

        if (item.make) preferences.makes[item.make] = (preferences.makes[item.make] || 0) + weight;
        if (item.model) preferences.models[item.model] = (preferences.models[item.model] || 0) + weight;
        if (item.bodyType) preferences.bodyTypes[item.bodyType] = (preferences.bodyTypes[item.bodyType] || 0) + weight;
        if (item.state) preferences.states[item.state] = (preferences.states[item.state] || 0) + weight;
      });

      return preferences;
    } catch (error) {
      logger.error('Failed to get user preferences', error as Error);
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
      logger.error('Failed to save Rover intent', error as Error);
    }
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
      logger.error('Failed to get user intents', error as Error);
      return [];
    }
  }
}

export const roverAPI = new RoverAPIService();