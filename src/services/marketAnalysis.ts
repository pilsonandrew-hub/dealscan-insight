import { Opportunity, Vehicle, MarketPrice } from '@/types/dealerscope';
import { supabase } from '@/integrations/supabase/client';

export interface MarketTrend {
  period: string;
  averagePrice: number;
  volume: number;
  priceChange: number;
  demandIndex: number;
}

export interface CompetitiveAnalysis {
  averageMarketPrice: number;
  competitorCount: number;
  pricePosition: 'below' | 'at' | 'above';
  marketShare: number;
  recommendedAction: string;
}

export interface ProfitabilityForecast {
  currentProfit: number;
  projectedProfit30Days: number;
  projectedProfit60Days: number;
  riskFactors: string[];
  opportunityScore: number;
}

export interface AdvancedMarketMetrics {
  liquidityScore: number;
  volatilityIndex: number;
  seasonalMultiplier: number;
  brandStrength: number;
  marketMomentum: 'bullish' | 'bearish' | 'neutral';
}

export class MarketAnalysisEngine {
  private readonly CACHE_DURATION = 30 * 60 * 1000; // 30 minutes
  private marketCache = new Map<string, { data: any; timestamp: number }>();

  constructor() {
    this.initializeMarketData();
  }

  private initializeMarketData(): void {
    // Initialize with current market conditions
    console.log('Market Analysis Engine initialized');
  }

  async analyzeMarketOpportunity(opportunity: Opportunity): Promise<{
    trend: MarketTrend;
    competitive: CompetitiveAnalysis;
    forecast: ProfitabilityForecast;
    metrics: AdvancedMarketMetrics;
  }> {
    const cacheKey = `${opportunity.vehicle.make}-${opportunity.vehicle.model}-${opportunity.vehicle.year}`;
    const cached = this.getCachedData(cacheKey);
    
    if (cached) {
      return cached;
    }

    const [trend, competitive, forecast, metrics] = await Promise.all([
      this.calculateMarketTrend(opportunity),
      this.performCompetitiveAnalysis(opportunity),
      this.generateProfitabilityForecast(opportunity),
      this.calculateAdvancedMetrics(opportunity)
    ]);

    const result = { trend, competitive, forecast, metrics };
    this.setCachedData(cacheKey, result);
    
    return result;
  }

  private async calculateMarketTrend(opportunity: Opportunity): Promise<MarketTrend> {
    try {
      // Fetch historical data for trend analysis
      const { data: historicalSales } = await supabase
        .from('dealer_sales')
        .select('sale_price, sale_date')
        .eq('make', opportunity.vehicle.make)
        .eq('model', opportunity.vehicle.model)
        .gte('year', opportunity.vehicle.year - 2)
        .lte('year', opportunity.vehicle.year + 2)
        .order('sale_date', { ascending: false })
        .limit(100);

      if (!historicalSales || historicalSales.length === 0) {
        return this.getDefaultMarketTrend();
      }

      const recentSales = historicalSales.slice(0, 30);
      const olderSales = historicalSales.slice(30, 60);

      const recentAvg = recentSales.reduce((sum, sale) => sum + Number(sale.sale_price), 0) / recentSales.length;
      const olderAvg = olderSales.length > 0 
        ? olderSales.reduce((sum, sale) => sum + Number(sale.sale_price), 0) / olderSales.length 
        : recentAvg;

      const priceChange = ((recentAvg - olderAvg) / olderAvg) * 100;
      const demandIndex = Math.min(recentSales.length / 10, 1.0); // Normalize to 0-1

      return {
        period: '30-day',
        averagePrice: recentAvg,
        volume: recentSales.length,
        priceChange,
        demandIndex
      };
    } catch (error) {
      console.error('Error calculating market trend:', error);
      return this.getDefaultMarketTrend();
    }
  }

  private async performCompetitiveAnalysis(opportunity: Opportunity): Promise<CompetitiveAnalysis> {
    try {
      // Get similar opportunities in the market
      const { data: similarOpportunities } = await supabase
        .from('opportunities')
        .select('estimated_sale_price, current_bid')
        .eq('make', opportunity.vehicle.make)
        .eq('model', opportunity.vehicle.model)
        .gte('year', opportunity.vehicle.year - 1)
        .lte('year', opportunity.vehicle.year + 1)
        .eq('is_active', true);

      if (!similarOpportunities || similarOpportunities.length === 0) {
        return this.getDefaultCompetitiveAnalysis(opportunity);
      }

      const prices = similarOpportunities.map(o => Number(o.estimated_sale_price));
      const averageMarketPrice = prices.reduce((sum, price) => sum + price, 0) / prices.length;
      const competitorCount = similarOpportunities.length;

      let pricePosition: 'below' | 'at' | 'above' = 'at';
      const priceDiff = (opportunity.estimated_sale_price - averageMarketPrice) / averageMarketPrice;
      
      if (priceDiff < -0.05) pricePosition = 'below';
      else if (priceDiff > 0.05) pricePosition = 'above';

      const marketShare = 1 / (competitorCount + 1); // Simplified market share

      let recommendedAction = 'Hold current position';
      if (pricePosition === 'below' && opportunity.potential_profit > 0) {
        recommendedAction = 'Strong buy - below market with profit potential';
      } else if (pricePosition === 'above') {
        recommendedAction = 'Caution - priced above market average';
      }

      return {
        averageMarketPrice,
        competitorCount,
        pricePosition,
        marketShare,
        recommendedAction
      };
    } catch (error) {
      console.error('Error performing competitive analysis:', error);
      return this.getDefaultCompetitiveAnalysis(opportunity);
    }
  }

  private async generateProfitabilityForecast(opportunity: Opportunity): Promise<ProfitabilityForecast> {
    const currentProfit = opportunity.potential_profit;
    const riskFactors: string[] = [];

    // Calculate risk factors
    if (opportunity.risk_score > 70) {
      riskFactors.push('High risk score indicates potential issues');
    }

    const age = new Date().getFullYear() - opportunity.vehicle.year;
    if (age > 10) {
      riskFactors.push('Vehicle age may affect resale value');
    }

    if (opportunity.vehicle.mileage && opportunity.vehicle.mileage > 100000) {
      riskFactors.push('High mileage may limit buyer pool');
    }

    if (opportunity.confidence_score < 50) {
      riskFactors.push('Low confidence in price estimation');
    }

    // Seasonal adjustments for projected profits
    const currentMonth = new Date().getMonth() + 1;
    const seasonalMultiplier = this.getSeasonalMultiplier(currentMonth);
    
    const projectedProfit30Days = currentProfit * seasonalMultiplier * 0.95; // Slight depreciation
    const projectedProfit60Days = currentProfit * seasonalMultiplier * 0.90; // More depreciation

    const opportunityScore = this.calculateOpportunityScore(opportunity, riskFactors.length);

    return {
      currentProfit,
      projectedProfit30Days,
      projectedProfit60Days,
      riskFactors,
      opportunityScore
    };
  }

  private async calculateAdvancedMetrics(opportunity: Opportunity): Promise<AdvancedMarketMetrics> {
    const liquidityScore = this.calculateLiquidityScore(opportunity);
    const volatilityIndex = this.calculateVolatilityIndex(opportunity);
    const seasonalMultiplier = this.getSeasonalMultiplier(new Date().getMonth() + 1);
    const brandStrength = this.calculateBrandStrength(opportunity.vehicle.make);
    const marketMomentum = this.determineMarketMomentum(opportunity);

    return {
      liquidityScore,
      volatilityIndex,
      seasonalMultiplier,
      brandStrength,
      marketMomentum
    };
  }

  private calculateLiquidityScore(opportunity: Opportunity): number {
    let score = 0.5; // Base score

    // Popular brands are more liquid
    const popularBrands = ['toyota', 'honda', 'ford', 'chevrolet', 'bmw', 'mercedes-benz'];
    if (popularBrands.includes(opportunity.vehicle.make.toLowerCase())) {
      score += 0.2;
    }

    // Age factor
    const age = new Date().getFullYear() - opportunity.vehicle.year;
    if (age <= 5) score += 0.2;
    else if (age <= 10) score += 0.1;
    else score -= 0.1;

    // Price range factor
    if (opportunity.estimated_sale_price > 50000) {
      score -= 0.1; // Luxury vehicles are less liquid
    } else if (opportunity.estimated_sale_price < 30000) {
      score += 0.1; // Affordable vehicles are more liquid
    }

    return Math.max(0.1, Math.min(1.0, score));
  }

  private calculateVolatilityIndex(opportunity: Opportunity): number {
    let volatility = 0.3; // Base volatility

    // Luxury brands are more volatile
    const luxuryBrands = ['bmw', 'mercedes-benz', 'audi', 'lexus', 'porsche'];
    if (luxuryBrands.includes(opportunity.vehicle.make.toLowerCase())) {
      volatility += 0.2;
    }

    // Age factor
    const age = new Date().getFullYear() - opportunity.vehicle.year;
    if (age > 15) volatility += 0.3; // Older cars are more volatile

    // High-performance vehicles
    if (opportunity.vehicle.model.toLowerCase().includes('sport') || 
        opportunity.vehicle.model.toLowerCase().includes('turbo')) {
      volatility += 0.1;
    }

    return Math.max(0.1, Math.min(1.0, volatility));
  }

  private getSeasonalMultiplier(month: number): number {
    const seasonalFactors = {
      1: 0.92,  // January - post-holiday slowdown
      2: 0.90,  // February - winter doldrums
      3: 1.05,  // March - spring recovery
      4: 1.08,  // April - peak spring
      5: 1.12,  // May - peak buying season
      6: 1.15,  // June - summer peak
      7: 1.10,  // July - summer continues
      8: 1.05,  // August - back to school
      9: 1.02,  // September - fall stability
      10: 0.98, // October - pre-winter
      11: 0.95, // November - holiday prep
      12: 0.88  // December - holiday season
    };

    return seasonalFactors[month] || 1.0;
  }

  private calculateBrandStrength(make: string): number {
    const brandStrengths = {
      'toyota': 0.9,
      'honda': 0.85,
      'bmw': 0.8,
      'mercedes-benz': 0.8,
      'audi': 0.75,
      'lexus': 0.75,
      'porsche': 0.85,
      'tesla': 0.7,
      'ford': 0.6,
      'chevrolet': 0.55,
      'nissan': 0.5,
      'hyundai': 0.6,
      'kia': 0.55,
      'volkswagen': 0.65
    };

    return brandStrengths[make.toLowerCase()] || 0.5;
  }

  private determineMarketMomentum(opportunity: Opportunity): 'bullish' | 'bearish' | 'neutral' {
    let momentum = 0;

    // Check if it's a good seasonal period
    const month = new Date().getMonth() + 1;
    const seasonalMultiplier = this.getSeasonalMultiplier(month);
    if (seasonalMultiplier > 1.05) momentum += 1;
    else if (seasonalMultiplier < 0.95) momentum -= 1;

    // Check brand strength
    const brandStrength = this.calculateBrandStrength(opportunity.vehicle.make);
    if (brandStrength > 0.7) momentum += 1;
    else if (brandStrength < 0.5) momentum -= 1;

    // Check profit potential
    const profitMargin = opportunity.potential_profit / opportunity.current_bid;
    if (profitMargin > 0.2) momentum += 1;
    else if (profitMargin < 0.05) momentum -= 1;

    if (momentum > 0) return 'bullish';
    if (momentum < 0) return 'bearish';
    return 'neutral';
  }

  private calculateOpportunityScore(opportunity: Opportunity, riskFactorCount: number): number {
    let score = 50; // Base score

    // Profit potential
    const profitMargin = opportunity.potential_profit / opportunity.current_bid;
    score += profitMargin * 100;

    // Confidence factor
    score += (opportunity.confidence_score - 50) * 0.5;

    // Risk penalty
    score -= riskFactorCount * 10;

    // ROI bonus
    if (opportunity.roi_percentage > 20) score += 15;
    else if (opportunity.roi_percentage > 15) score += 10;
    else if (opportunity.roi_percentage > 10) score += 5;

    return Math.max(0, Math.min(100, score));
  }

  private getDefaultMarketTrend(): MarketTrend {
    return {
      period: '30-day',
      averagePrice: 25000,
      volume: 5,
      priceChange: 0,
      demandIndex: 0.5
    };
  }

  private getDefaultCompetitiveAnalysis(opportunity: Opportunity): CompetitiveAnalysis {
    return {
      averageMarketPrice: opportunity.estimated_sale_price,
      competitorCount: 0,
      pricePosition: 'at',
      marketShare: 1.0,
      recommendedAction: 'Limited market data available'
    };
  }

  private getCachedData(key: string): any {
    const cached = this.marketCache.get(key);
    if (cached && Date.now() - cached.timestamp < this.CACHE_DURATION) {
      return cached.data;
    }
    return null;
  }

  private setCachedData(key: string, data: any): void {
    this.marketCache.set(key, {
      data,
      timestamp: Date.now()
    });
  }
}

export const marketAnalysisEngine = new MarketAnalysisEngine();