import { DealItem, UserPreferences } from "./roverAPI";
import { logger } from "@/lib/logger";

interface MLFeatures {
  vehicle_age: number;
  mileage_normalized: number;
  price_bucket: number;
  make_popularity: number;
  model_demand: number;
  region_factor: number;
  auction_velocity: number;
  mmr_deviation: number;
  historical_roi: number;
  market_trend: number;
}

interface ScoringConfig {
  useRemoteRanker: boolean;
  remoteRankerUrl?: string;
  fallbackToHeuristic: boolean;
  modelVersion: string;
  features: string[];
}

export class RoverMLService {
  private config: ScoringConfig;
  private featureWeights: Record<string, number>;
  private modelCache: Map<string, any>;

  constructor() {
    this.config = {
      useRemoteRanker: false, // Can be configured via environment
      remoteRankerUrl: process.env.ROVER_RANKER_URL,
      fallbackToHeuristic: true,
      modelVersion: "v2.1.3",
      features: [
        "vehicle_age", "mileage_normalized", "price_bucket", "make_popularity",
        "model_demand", "region_factor", "auction_velocity", "mmr_deviation",
        "historical_roi", "market_trend"
      ]
    };

    this.featureWeights = {
      vehicle_age: 0.15,
      mileage_normalized: 0.12,
      price_bucket: 0.10,
      make_popularity: 0.18,
      model_demand: 0.16,
      region_factor: 0.08,
      auction_velocity: 0.06,
      mmr_deviation: 0.20,
      historical_roi: 0.25,
      market_trend: 0.10
    };

    this.modelCache = new Map();
  }

  async scoreOpportunities(
    opportunities: any[], 
    preferences: UserPreferences
  ): Promise<DealItem[]> {
    try {
      if (this.config.useRemoteRanker && this.config.remoteRankerUrl) {
        return await this.scoreWithRemoteRanker(opportunities, preferences);
      } else {
        return await this.scoreWithHeuristicRanker(opportunities, preferences);
      }
    } catch (error) {
      logger.error("ML scoring failed", {
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
        opportunitiesCount: opportunities.length
      });

      if (this.config.fallbackToHeuristic) {
        logger.info("Falling back to heuristic scoring");
        return await this.scoreWithHeuristicRanker(opportunities, preferences);
      }

      throw error;
    }
  }

  private async scoreWithRemoteRanker(
    opportunities: any[], 
    preferences: UserPreferences
  ): Promise<DealItem[]> {
    const features = opportunities.map(opp => this.extractFeatures(opp, preferences));
    
    const payload = {
      preferences: this.serializePreferences(preferences),
      items: features,
      model_version: this.config.modelVersion
    };

    const response = await fetch(`${this.config.remoteRankerUrl}/bulk_score`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(`Remote ranker failed: ${response.status}`);
    }

    const result = await response.json();
    const scores = result.scores || [];

    return opportunities.map((opp, index) => ({
      id: opp.id,
      make: opp.make,
      model: opp.model,
      year: opp.year,
      price: opp.current_bid || opp.estimated_sale_price,
      mileage: opp.mileage,
      source: opp.source_site,
      state: opp.state,
      vin: opp.vin,
      arbitrage_score: opp.score || 0,
      roi_percentage: opp.roi_percentage,
      potential_profit: opp.potential_profit,
      _score: scores[index] || 0,
      _mlFeatures: features[index],
      _modelVersion: this.config.modelVersion
    }));
  }

  private async scoreWithHeuristicRanker(
    opportunities: any[], 
    preferences: UserPreferences
  ): Promise<DealItem[]> {
    return opportunities.map(opp => {
      const features = this.extractFeatures(opp, preferences);
      const score = this.calculateHeuristicScore(features, preferences);

      return {
        id: opp.id,
        make: opp.make,
        model: opp.model,
        year: opp.year,
        price: opp.current_bid || opp.estimated_sale_price,
        mileage: opp.mileage,
        source: opp.source_site,
        state: opp.state,
        vin: opp.vin,
        arbitrage_score: opp.score || 0,
        roi_percentage: opp.roi_percentage,
        potential_profit: opp.potential_profit,
        _score: score,
        _features: features,
        _scoringMethod: "heuristic"
      };
    });
  }

  private extractFeatures(opportunity: any, preferences: UserPreferences): MLFeatures {
    const currentYear = new Date().getFullYear();
    const vehicleAge = currentYear - (opportunity.year || currentYear);
    
    return {
      vehicle_age: Math.min(vehicleAge / 20, 1), // Normalize to 0-1
      mileage_normalized: Math.min((opportunity.mileage || 0) / 200000, 1),
      price_bucket: this.getPriceBucket(opportunity.current_bid || opportunity.estimated_sale_price),
      make_popularity: this.getMakePopularity(opportunity.make, preferences),
      model_demand: this.getModelDemand(opportunity.model, preferences),
      region_factor: this.getRegionFactor(opportunity.state),
      auction_velocity: this.getAuctionVelocity(opportunity),
      mmr_deviation: this.getMMRDeviation(opportunity),
      historical_roi: Math.min((opportunity.roi_percentage || 0) / 100, 1),
      market_trend: this.getMarketTrend(opportunity.make, opportunity.model)
    };
  }

  private calculateHeuristicScore(features: MLFeatures, preferences: UserPreferences): number {
    let score = 0;

    // Weight each feature according to learned importance
    for (const [featureName, weight] of Object.entries(this.featureWeights)) {
      const featureValue = features[featureName as keyof MLFeatures] || 0;
      score += featureValue * weight;
    }

    // Apply preference boosts
    score += this.getPreferenceBoost(features, preferences);

    // Apply recency bonus
    score += this.getRecencyBonus();

    // Apply market conditions
    score += this.getMarketConditionBonus(features);

    return Math.max(0, Math.min(1, score));
  }

  private getPriceBucket(price: number): number {
    if (price < 10000) return 0.2;
    if (price < 20000) return 0.4;
    if (price < 35000) return 0.6;
    if (price < 50000) return 0.8;
    return 1.0;
  }

  private getMakePopularity(make: string, preferences: UserPreferences): number {
    const makeCount = preferences.makes[make] || 0;
    const maxCount = Math.max(...Object.values(preferences.makes), 1);
    return makeCount / maxCount;
  }

  private getModelDemand(model: string, preferences: UserPreferences): number {
    const modelCount = preferences.models[model] || 0;
    const maxCount = Math.max(...Object.values(preferences.models), 1);
    return modelCount / maxCount;
  }

  private getRegionFactor(state: string): number {
    // Simplified region scoring - in production, this would use market data
    const highDemandStates = ['CA', 'TX', 'FL', 'NY', 'IL'];
    return highDemandStates.includes(state || '') ? 0.8 : 0.5;
  }

  private getAuctionVelocity(opportunity: any): number {
    // Simplified velocity calculation
    const createdHoursAgo = opportunity.created_at 
      ? (Date.now() - new Date(opportunity.created_at).getTime()) / (1000 * 60 * 60)
      : 24;
    
    return Math.max(0, Math.min(1, (48 - createdHoursAgo) / 48));
  }

  private getMMRDeviation(opportunity: any): number {
    const currentBid = opportunity.current_bid || opportunity.estimated_sale_price || 0;
    const mmr = opportunity.mmr || currentBid;
    
    if (mmr === 0) return 0.5;
    
    const deviation = (mmr - currentBid) / mmr;
    return Math.max(0, Math.min(1, deviation + 0.5));
  }

  private getMarketTrend(make: string, model: string): number {
    // Simplified trend calculation - in production, this would use actual market data
    const trendingMakes = ['Toyota', 'Honda', 'Tesla', 'Ford'];
    const trendingModels = ['Camry', 'Accord', 'Model 3', 'F-150'];
    
    let trend = 0.5; // Neutral
    if (trendingMakes.includes(make)) trend += 0.2;
    if (trendingModels.includes(model)) trend += 0.2;
    
    return Math.min(1, trend);
  }

  private getPreferenceBoost(features: MLFeatures, preferences: UserPreferences): number {
    // Boost score based on alignment with user preferences
    let boost = 0;
    
    // Price preference alignment
    const preferredPriceRange = preferences.priceRange;
    if (features.price_bucket >= preferredPriceRange[0] / 100000 && 
        features.price_bucket <= preferredPriceRange[1] / 100000) {
      boost += 0.1;
    }
    
    // Mileage preference alignment
    const preferredMileageRange = preferences.mileageRange;
    const actualMileage = features.mileage_normalized * 200000;
    if (actualMileage <= preferredMileageRange[1]) {
      boost += 0.1;
    }
    
    return boost;
  }

  private getRecencyBonus(): number {
    // Slight bonus for recent processing
    return 0.05;
  }

  private getMarketConditionBonus(features: MLFeatures): number {
    // Bonus for favorable market conditions
    let bonus = 0;
    
    if (features.historical_roi > 0.15) bonus += 0.1; // High ROI
    if (features.mmr_deviation > 0.7) bonus += 0.05; // Under MMR
    if (features.auction_velocity > 0.8) bonus += 0.05; // Fresh listing
    
    return bonus;
  }

  private serializePreferences(preferences: UserPreferences): any {
    return {
      makes: preferences.makes,
      models: preferences.models,
      bodyTypes: preferences.bodyTypes,
      priceRange: preferences.priceRange,
      mileageRange: preferences.mileageRange,
      states: preferences.states
    };
  }

  // Public methods for configuration
  setRemoteRanker(url: string, enabled = true) {
    this.config.remoteRankerUrl = url;
    this.config.useRemoteRanker = enabled;
  }

  updateFeatureWeights(weights: Partial<Record<string, number>>) {
    this.featureWeights = { ...this.featureWeights, ...weights };
  }

  getModelInfo() {
    return {
      version: this.config.modelVersion,
      features: this.config.features,
      scoringMethod: this.config.useRemoteRanker ? "remote" : "heuristic",
      lastUpdate: new Date().toISOString()
    };
  }
}

export const roverMLService = new RoverMLService();