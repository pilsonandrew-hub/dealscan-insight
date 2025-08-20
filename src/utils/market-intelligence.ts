/**
 * Market Intelligence Engine - Advanced market analysis and prediction system
 */

import { Opportunity, MarketPrice } from '@/types/dealerscope';

interface MarketTrend {
  period: string;
  avgPrice: number;
  volume: number;
  trend: 'up' | 'down' | 'stable';
  seasonalFactor: number;
}

interface VehicleSegment {
  make: string;
  model: string;
  year: number;
  segment: 'economy' | 'midsize' | 'luxury' | 'truck' | 'suv' | 'electric';
  demandScore: number;
  volatility: number;
  liquidityIndex: number;
}

interface CompetitorAnalysis {
  sourceSite: string;
  marketShare: number;
  avgPremium: number;
  qualityScore: number;
  reliabilityIndex: number;
}

interface RegionalInsight {
  state: string;
  demandMultiplier: number;
  seasonalPattern: number[];
  transportAdvantage: number;
  marketSaturation: number;
  economicIndex: number;
}

interface PricePredictor {
  currentPrice: number;
  predictedPrice30d: number;
  predictedPrice60d: number;
  predictedPrice90d: number;
  confidence: number;
  volatilityRange: [number, number];
}

export class MarketIntelligenceEngine {
  private vehicleSegments: Map<string, VehicleSegment> = new Map();
  private marketTrends: Map<string, MarketTrend[]> = new Map();
  private competitorProfiles: Map<string, CompetitorAnalysis> = new Map();
  private regionalInsights: Map<string, RegionalInsight> = new Map();

  constructor() {
    this.initializeMarketData();
  }

  /**
   * Analyze market opportunities with advanced intelligence
   */
  analyzeMarketOpportunity(opportunity: Opportunity): {
    marketScore: number;
    competitivePosition: 'strong' | 'average' | 'weak';
    pricePredictor: PricePredictor;
    recommendedAction: 'buy' | 'watch' | 'skip';
    reasoning: string[];
  } {
    const vehicleKey = `${opportunity.vehicle.make}_${opportunity.vehicle.model}_${opportunity.vehicle.year}`;
    const segment = this.vehicleSegments.get(vehicleKey);
    const regional = this.regionalInsights.get(opportunity.state || 'CA');
    const competitor = this.competitorProfiles.get(opportunity.source_site);

    // Calculate market score
    const marketScore = this.calculateMarketScore(opportunity, segment, regional, competitor);
    
    // Determine competitive position
    const competitivePosition = this.assessCompetitivePosition(opportunity, marketScore);
    
    // Generate price prediction
    const pricePredictor = this.predictPriceMovement(opportunity, segment);
    
    // Make recommendation
    const { action, reasoning } = this.generateRecommendation(
      opportunity, 
      marketScore, 
      competitivePosition, 
      pricePredictor
    );

    return {
      marketScore,
      competitivePosition,
      pricePredictor,
      recommendedAction: action,
      reasoning
    };
  }

  /**
   * Generate market insights dashboard data
   */
  generateMarketInsights(opportunities: Opportunity[]): {
    marketOverview: {
      totalMarketValue: number;
      avgMarketVelocity: number;
      demandTrendIndex: number;
      supplyConstraintIndex: number;
    };
    segmentAnalysis: Array<{
      segment: string;
      opportunities: number;
      avgMargin: number;
      riskLevel: number;
      recommendedAllocation: number;
    }>;
    geographicInsights: Array<{
      region: string;
      opportunities: number;
      transportEfficiency: number;
      marketPenetration: number;
      growthPotential: number;
    }>;
    competitorLandscape: Array<{
      source: string;
      marketShare: number;
      qualityIndex: number;
      pricingStrategy: 'aggressive' | 'premium' | 'balanced';
    }>;
    seasonalFactors: Array<{
      month: string;
      demandMultiplier: number;
      priceInflation: number;
    }>;
  } {
    return {
      marketOverview: this.calculateMarketOverview(opportunities),
      segmentAnalysis: this.analyzeSegments(opportunities),
      geographicInsights: this.analyzeGeographicTrends(opportunities),
      competitorLandscape: this.analyzeCompetitorLandscape(opportunities),
      seasonalFactors: this.calculateSeasonalFactors()
    };
  }

  /**
   * Advanced opportunity scoring with market intelligence
   */
  scoreOpportunityWithIntelligence(opportunity: Opportunity): {
    baseScore: number;
    marketAdjustedScore: number;
    adjustmentFactors: Record<string, number>;
    riskAdjustedReturn: number;
    timeToSaleEstimate: number;
  } {
    const baseScore = opportunity.score || 0;
    const adjustmentFactors: Record<string, number> = {};

    // Market demand adjustment
    const vehicleKey = `${opportunity.vehicle.make}_${opportunity.vehicle.model}_${opportunity.vehicle.year}`;
    const segment = this.vehicleSegments.get(vehicleKey);
    if (segment) {
      adjustmentFactors.demandScore = (segment.demandScore - 50) / 50; // -1 to 1
      adjustmentFactors.liquidity = (segment.liquidityIndex - 50) / 50;
      adjustmentFactors.volatility = (50 - segment.volatility) / 50; // Lower volatility is better
    }

    // Regional market adjustment
    const regional = this.regionalInsights.get(opportunity.state || 'CA');
    if (regional) {
      adjustmentFactors.regional = (regional.demandMultiplier - 1) / 2; // Normalize around 1.0
      adjustmentFactors.transport = regional.transportAdvantage / 100;
      adjustmentFactors.saturation = (100 - regional.marketSaturation) / 100;
    }

    // Seasonal adjustment
    const currentMonth = new Date().getMonth();
    const seasonalFactor = this.getSeasonalFactor(opportunity.vehicle.make, currentMonth);
    adjustmentFactors.seasonal = (seasonalFactor - 1) / 2;

    // Competitor advantage
    const competitor = this.competitorProfiles.get(opportunity.source_site);
    if (competitor) {
      adjustmentFactors.competitor = (competitor.qualityScore - 50) / 50;
    }

    // Calculate adjusted score
    const totalAdjustment = Object.values(adjustmentFactors).reduce((sum, factor) => sum + factor, 0);
    const marketAdjustedScore = Math.max(0, Math.min(100, baseScore + (totalAdjustment * 10)));

    // Risk-adjusted return calculation
    const riskAdjustedReturn = this.calculateRiskAdjustedReturn(opportunity, adjustmentFactors);

    // Time to sale estimate
    const timeToSaleEstimate = this.estimateTimeToSale(opportunity, segment, regional);

    return {
      baseScore,
      marketAdjustedScore,
      adjustmentFactors,
      riskAdjustedReturn,
      timeToSaleEstimate
    };
  }

  private initializeMarketData(): void {
    // Initialize vehicle segments with market intelligence
    const segments: VehicleSegment[] = [
      { make: 'Ford', model: 'F-150', year: 2020, segment: 'truck', demandScore: 85, volatility: 15, liquidityIndex: 90 },
      { make: 'Chevrolet', model: 'Silverado', year: 2020, segment: 'truck', demandScore: 80, volatility: 18, liquidityIndex: 85 },
      { make: 'Toyota', model: 'Camry', year: 2020, segment: 'midsize', demandScore: 75, volatility: 12, liquidityIndex: 88 },
      { make: 'Honda', model: 'Civic', year: 2020, segment: 'economy', demandScore: 78, volatility: 10, liquidityIndex: 92 },
      { make: 'BMW', model: '3 Series', year: 2020, segment: 'luxury', demandScore: 60, volatility: 35, liquidityIndex: 65 },
      { make: 'Tesla', model: 'Model 3', year: 2020, segment: 'electric', demandScore: 90, volatility: 40, liquidityIndex: 70 }
    ];

    segments.forEach(segment => {
      const key = `${segment.make}_${segment.model}_${segment.year}`;
      this.vehicleSegments.set(key, segment);
    });

    // Initialize regional insights
    const regions: RegionalInsight[] = [
      { 
        state: 'CA', 
        demandMultiplier: 1.2, 
        seasonalPattern: [0.9, 0.95, 1.1, 1.15, 1.2, 1.1, 1.0, 1.0, 1.05, 1.1, 1.0, 0.9],
        transportAdvantage: 0,
        marketSaturation: 65,
        economicIndex: 85
      },
      { 
        state: 'TX', 
        demandMultiplier: 1.1, 
        seasonalPattern: [1.0, 1.0, 1.1, 1.2, 1.25, 1.15, 1.05, 1.0, 1.05, 1.1, 1.0, 0.95],
        transportAdvantage: -25,
        marketSaturation: 45,
        economicIndex: 80
      },
      { 
        state: 'FL', 
        demandMultiplier: 1.05, 
        seasonalPattern: [1.2, 1.15, 1.1, 1.0, 0.9, 0.85, 0.8, 0.85, 0.9, 1.0, 1.1, 1.15],
        transportAdvantage: -35,
        marketSaturation: 55,
        economicIndex: 75
      }
    ];

    regions.forEach(region => {
      this.regionalInsights.set(region.state, region);
    });

    // Initialize competitor profiles
    const competitors: CompetitorAnalysis[] = [
      { sourceSite: 'GovDeals', marketShare: 35, avgPremium: 12.5, qualityScore: 75, reliabilityIndex: 85 },
      { sourceSite: 'PublicSurplus', marketShare: 25, avgPremium: 10.0, qualityScore: 70, reliabilityIndex: 80 },
      { sourceSite: 'Copart', marketShare: 30, avgPremium: 9.5, qualityScore: 85, reliabilityIndex: 90 },
      { sourceSite: 'IAA', marketShare: 10, avgPremium: 8.5, qualityScore: 80, reliabilityIndex: 88 }
    ];

    competitors.forEach(competitor => {
      this.competitorProfiles.set(competitor.sourceSite, competitor);
    });
  }

  private calculateMarketScore(
    opportunity: Opportunity, 
    segment?: VehicleSegment, 
    regional?: RegionalInsight, 
    competitor?: CompetitorAnalysis
  ): number {
    let score = 50; // Base score

    // Segment scoring
    if (segment) {
      score += (segment.demandScore - 50) * 0.3;
      score += (segment.liquidityIndex - 50) * 0.2;
      score -= segment.volatility * 0.1;
    }

    // Regional scoring
    if (regional) {
      score += (regional.demandMultiplier - 1) * 25;
      score += regional.transportAdvantage * 0.1;
      score -= regional.marketSaturation * 0.1;
    }

    // Competitor scoring
    if (competitor) {
      score += (competitor.qualityScore - 50) * 0.2;
      score += (competitor.reliabilityIndex - 50) * 0.1;
    }

    return Math.max(0, Math.min(100, score));
  }

  private assessCompetitivePosition(opportunity: Opportunity, marketScore: number): 'strong' | 'average' | 'weak' {
    const roiThreshold = opportunity.roi_percentage > 25;
    const profitThreshold = opportunity.potential_profit > 5000;
    const confidenceThreshold = opportunity.confidence_score > 70;
    
    if (marketScore > 70 && roiThreshold && profitThreshold && confidenceThreshold) {
      return 'strong';
    } else if (marketScore > 50 && (roiThreshold || profitThreshold)) {
      return 'average';
    } else {
      return 'weak';
    }
  }

  private predictPriceMovement(opportunity: Opportunity, segment?: VehicleSegment): PricePredictor {
    const currentPrice = opportunity.estimated_sale_price;
    const volatility = segment?.volatility || 20;
    
    // Simple trend prediction (in production, use ML models)
    const trendFactor = 1 + (Math.random() - 0.5) * 0.1; // ±5% random walk
    const seasonalFactor = this.getSeasonalFactor(opportunity.vehicle.make, new Date().getMonth());
    
    const predicted30d = currentPrice * trendFactor * seasonalFactor;
    const predicted60d = predicted30d * (1 + (Math.random() - 0.5) * 0.15);
    const predicted90d = predicted60d * (1 + (Math.random() - 0.5) * 0.2);
    
    const confidence = Math.max(30, 90 - volatility);
    const volatilityRange: [number, number] = [
      currentPrice * (1 - volatility / 100),
      currentPrice * (1 + volatility / 100)
    ];

    return {
      currentPrice,
      predictedPrice30d: predicted30d,
      predictedPrice60d: predicted60d,
      predictedPrice90d: predicted90d,
      confidence,
      volatilityRange
    };
  }

  private generateRecommendation(
    opportunity: Opportunity,
    marketScore: number,
    position: 'strong' | 'average' | 'weak',
    predictor: PricePredictor
  ): { action: 'buy' | 'watch' | 'skip', reasoning: string[] } {
    const reasoning: string[] = [];
    
    if (position === 'strong' && marketScore > 75 && opportunity.roi_percentage > 20) {
      reasoning.push(`Strong market position with ${marketScore.toFixed(0)} market score`);
      reasoning.push(`High ROI potential of ${opportunity.roi_percentage.toFixed(1)}%`);
      reasoning.push(`Favorable price prediction trend`);
      return { action: 'buy', reasoning };
    }
    
    if (position === 'average' && marketScore > 60) {
      reasoning.push(`Average market conditions with potential upside`);
      reasoning.push(`Consider timing and market trends`);
      return { action: 'watch', reasoning };
    }
    
    reasoning.push(`Weak market position or low ROI potential`);
    reasoning.push(`High risk relative to expected returns`);
    return { action: 'skip', reasoning };
  }

  private calculateMarketOverview(opportunities: Opportunity[]) {
    const totalValue = opportunities.reduce((sum, opp) => sum + opp.estimated_sale_price, 0);
    const avgVelocity = opportunities.length > 0 ? 
      opportunities.reduce((sum, opp) => sum + (opp.confidence_score / 100), 0) / opportunities.length : 0;
    
    return {
      totalMarketValue: totalValue,
      avgMarketVelocity: avgVelocity * 100,
      demandTrendIndex: 75 + Math.random() * 20, // Simulated
      supplyConstraintIndex: 60 + Math.random() * 30 // Simulated
    };
  }

  private analyzeSegments(opportunities: Opportunity[]) {
    const segments = new Map<string, Opportunity[]>();
    
    opportunities.forEach(opp => {
      const key = opp.vehicle.make;
      if (!segments.has(key)) segments.set(key, []);
      segments.get(key)!.push(opp);
    });
    
    return Array.from(segments.entries()).map(([segment, opps]) => ({
      segment,
      opportunities: opps.length,
      avgMargin: opps.reduce((sum, opp) => sum + opp.profit_margin, 0) / opps.length,
      riskLevel: opps.reduce((sum, opp) => sum + opp.risk_score, 0) / opps.length,
      recommendedAllocation: Math.min(40, Math.max(5, (opps.length / opportunities.length) * 100))
    }));
  }

  private analyzeGeographicTrends(opportunities: Opportunity[]) {
    const regions = new Map<string, Opportunity[]>();
    
    opportunities.forEach(opp => {
      const key = opp.state || 'Unknown';
      if (!regions.has(key)) regions.set(key, []);
      regions.get(key)!.push(opp);
    });
    
    return Array.from(regions.entries()).map(([region, opps]) => ({
      region,
      opportunities: opps.length,
      transportEfficiency: 100 - (opps.reduce((sum, opp) => sum + opp.transportation_cost, 0) / opps.length / 100),
      marketPenetration: (opps.length / opportunities.length) * 100,
      growthPotential: 60 + Math.random() * 40 // Simulated
    }));
  }

  private analyzeCompetitorLandscape(opportunities: Opportunity[]) {
    const sources = new Map<string, number>();
    
    opportunities.forEach(opp => {
      sources.set(opp.source_site, (sources.get(opp.source_site) || 0) + 1);
    });
    
    return Array.from(sources.entries()).map(([source, count]) => {
      const competitor = this.competitorProfiles.get(source);
      const strategy: 'aggressive' | 'premium' | 'balanced' = 
        competitor?.avgPremium > 10 ? 'premium' : 
        competitor?.avgPremium < 8 ? 'aggressive' : 'balanced';
      
      return {
        source,
        marketShare: (count / opportunities.length) * 100,
        qualityIndex: competitor?.qualityScore || 50,
        pricingStrategy: strategy
      };
    });
  }

  private calculateSeasonalFactors() {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    
    return months.map((month, index) => ({
      month,
      demandMultiplier: 0.9 + Math.sin(index * Math.PI / 6) * 0.2,
      priceInflation: 1.0 + Math.cos(index * Math.PI / 4) * 0.1
    }));
  }

  private getSeasonalFactor(make: string, month: number): number {
    // Seasonal patterns vary by vehicle type
    const truckPattern = [0.9, 0.95, 1.1, 1.2, 1.25, 1.15, 1.05, 1.0, 1.05, 1.1, 1.0, 0.9];
    const carPattern = [1.0, 1.0, 1.1, 1.15, 1.2, 1.1, 1.0, 1.0, 1.05, 1.1, 1.0, 0.95];
    
    const istruck = ['Ford', 'Chevrolet', 'Ram', 'GMC'].includes(make);
    const pattern = istruck ? truckPattern : carPattern;
    
    return pattern[month] || 1.0;
  }

  private calculateRiskAdjustedReturn(opportunity: Opportunity, adjustmentFactors: Record<string, number>): number {
    const baseReturn = opportunity.roi_percentage;
    const riskFactor = opportunity.risk_score / 100;
    const marketRisk = Math.abs(Object.values(adjustmentFactors).reduce((sum, factor) => sum + factor, 0)) / 10;
    
    const totalRisk = Math.min(0.9, riskFactor + marketRisk);
    return baseReturn * (1 - totalRisk);
  }

  private estimateTimeToSale(opportunity: Opportunity, segment?: VehicleSegment, regional?: RegionalInsight): number {
    let baseDays = 45; // Base estimate
    
    if (segment) {
      baseDays -= (segment.liquidityIndex - 50) / 5; // Higher liquidity = faster sale
      baseDays += segment.volatility / 10; // Higher volatility = longer time
    }
    
    if (regional) {
      baseDays /= regional.demandMultiplier; // Higher demand = faster sale
    }
    
    // Price competitiveness factor
    if (opportunity.current_bid < opportunity.estimated_sale_price * 0.8) {
      baseDays -= 10; // Great deal sells faster
    }
    
    return Math.max(7, Math.min(90, baseDays));
  }
}

export const marketIntelligence = new MarketIntelligenceEngine();