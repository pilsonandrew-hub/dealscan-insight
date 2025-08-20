import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";

interface VehicleListing {
  id: string;
  source_site: string;
  listing_url: string;
  year?: number;
  make?: string;
  model?: string;
  trim?: string;
  mileage?: number;
  current_bid?: number;
  location?: string;
  state?: string;
  vin?: string;
  title_status?: string;
  auction_end?: string;
}

interface MarketData {
  avg_price: number;
  low_price: number;
  high_price: number;
  sample_size: number;
  confidence: number;
}

interface DealMetrics {
  estimated_sale_price: number;
  total_cost: number;
  potential_profit: number;
  roi_percentage: number;
  risk_score: number;
  confidence_score: number;
  transportation_cost: number;
  fees_cost: number;
  buyer_premium: number;
  doc_fee: number;
}

// State-based transport cost bands (miles from major hubs)
const TRANSPORT_RATES = {
  // West Coast (low cost states)
  'CA': { rate: 0.85, base: 200 },
  'NV': { rate: 0.90, base: 250 },
  'AZ': { rate: 0.90, base: 250 },
  'OR': { rate: 0.95, base: 300 },
  'WA': { rate: 0.95, base: 300 },
  
  // Rust belt states (higher cost due to condition risk)
  'MI': { rate: 1.25, base: 800 },
  'OH': { rate: 1.20, base: 750 },
  'IL': { rate: 1.15, base: 700 },
  'IN': { rate: 1.20, base: 750 },
  'WI': { rate: 1.25, base: 800 },
  
  // Default for other states
  'DEFAULT': { rate: 1.10, base: 600 }
};

// Fee structures by auction site
const SITE_FEES = {
  'GovDeals': { premium: 0.10, doc_fee: 150 },
  'PublicSurplus': { premium: 0.12, doc_fee: 200 },
  'GSAauctions': { premium: 0.08, doc_fee: 100 },
  'DEFAULT': { premium: 0.10, doc_fee: 150 }
};

// Risk factors for different vehicle attributes
const RISK_FACTORS = {
  age: {
    low: 5,    // < 5 years
    medium: 10, // 5-10 years  
    high: 15   // > 10 years
  },
  mileage: {
    low: 5,     // < 50k miles
    medium: 10, // 50k-100k miles
    high: 20    // > 100k miles
  },
  title_status: {
    clean: 0,
    salvage: 30,
    rebuilt: 15,
    flood: 35,
    lemon: 25
  }
};

class DealScoringEngine {
  private async getMarketData(make: string, model: string, year: number, state?: string): Promise<MarketData> {
    try {
      // First try to get cached market data
      const { data: cached, error } = await supabase
        .from('market_prices')
        .select('*')
        .eq('make', make.toLowerCase())
        .eq('model', model.toLowerCase())
        .eq('year', year)
        .gte('expires_at', new Date().toISOString())
        .order('last_updated', { ascending: false })
        .limit(1)
        .single();

      if (cached && !error) {
        return {
          avg_price: cached.avg_price,
          low_price: cached.low_price,
          high_price: cached.high_price,
          sample_size: cached.sample_size || 10,
          confidence: 0.8
        };
      }

      // If no cached data, use ML estimation based on historical dealer sales
      const { data: sales, error: salesError } = await supabase
        .from('dealer_sales')
        .select('sale_price, mileage, year')
        .eq('make', make.toLowerCase())
        .eq('model', model.toLowerCase())
        .gte('year', year - 2)
        .lte('year', year + 2)
        .order('sale_date', { ascending: false })
        .limit(50);

      if (sales && sales.length > 0) {
        const prices = sales.map(s => s.sale_price).filter(p => p > 0);
        const avgPrice = prices.reduce((sum, p) => sum + p, 0) / prices.length;
        const lowPrice = Math.min(...prices);
        const highPrice = Math.max(...prices);

        // Cache the result
        await supabase.from('market_prices').upsert({
          make: make.toLowerCase(),
          model: model.toLowerCase(),
          year,
          state: state?.toLowerCase() || null,
          avg_price: avgPrice,
          low_price: lowPrice,
          high_price: highPrice,
          sample_size: prices.length,
          source_api: 'dealer_sales_ml',
          expires_at: new Date(Date.now() + 3600000).toISOString() // 1 hour
        });

        return {
          avg_price: avgPrice,
          low_price: lowPrice,
          high_price: highPrice,
          sample_size: prices.length,
          confidence: Math.min(0.9, prices.length / 20) // More samples = higher confidence
        };
      }

      // Fallback: basic estimation model
      const basePrice = this.estimateBasePrice(make, model, year);
      return {
        avg_price: basePrice,
        low_price: basePrice * 0.8,
        high_price: basePrice * 1.2,
        sample_size: 1,
        confidence: 0.3
      };

    } catch (error) {
      console.error('Error getting market data:', error);
      // Fallback estimation
      const basePrice = this.estimateBasePrice(make, model, year);
      return {
        avg_price: basePrice,
        low_price: basePrice * 0.8,
        high_price: basePrice * 1.2,
        sample_size: 1,
        confidence: 0.2
      };
    }
  }

  private estimateBasePrice(make: string, model: string, year: number): number {
    // Simple linear depreciation model
    const currentYear = new Date().getFullYear();
    const age = currentYear - year;
    
    // Base prices by make (rough estimates)
    const basePrices = {
      'ford': 35000,
      'chevrolet': 32000,
      'toyota': 38000,
      'honda': 36000,
      'nissan': 30000,
      'jeep': 33000,
      'ram': 45000,
      'gmc': 40000,
      'dodge': 35000
    };
    
    const basePrice = basePrices[make.toLowerCase()] || 30000;
    const depreciation = Math.min(age * 0.12, 0.7); // Max 70% depreciation
    
    return Math.round(basePrice * (1 - depreciation));
  }

  private calculateTransportCost(state: string, estimatedPrice: number): number {
    const rates = TRANSPORT_RATES[state.toUpperCase()] || TRANSPORT_RATES.DEFAULT;
    
    // Base cost + percentage of vehicle value
    const baseCost = rates.base;
    const percentageCost = estimatedPrice * (rates.rate / 100);
    
    return Math.round(baseCost + percentageCost);
  }

  private calculateFees(sourceSite: string, currentBid: number): { premium: number; docFee: number } {
    const fees = SITE_FEES[sourceSite] || SITE_FEES.DEFAULT;
    
    return {
      premium: Math.round(currentBid * fees.premium),
      docFee: fees.doc_fee
    };
  }

  private calculateRiskScore(listing: VehicleListing, marketData: MarketData): number {
    let riskScore = 0;
    const currentYear = new Date().getFullYear();
    
    // Age-based risk
    if (listing.year) {
      const age = currentYear - listing.year;
      if (age < 5) riskScore += RISK_FACTORS.age.low;
      else if (age <= 10) riskScore += RISK_FACTORS.age.medium;
      else riskScore += RISK_FACTORS.age.high;
    }
    
    // Mileage-based risk
    if (listing.mileage) {
      if (listing.mileage < 50000) riskScore += RISK_FACTORS.mileage.low;
      else if (listing.mileage <= 100000) riskScore += RISK_FACTORS.mileage.medium;
      else riskScore += RISK_FACTORS.mileage.high;
    }
    
    // Title status risk
    const titleStatus = listing.title_status?.toLowerCase() || 'clean';
    riskScore += RISK_FACTORS.title_status[titleStatus] || 0;
    
    // Market volatility risk (based on sample size)
    if (marketData.sample_size < 5) riskScore += 15;
    else if (marketData.sample_size < 10) riskScore += 10;
    else if (marketData.sample_size < 20) riskScore += 5;
    
    // Rust state risk
    const rustStates = ['MI', 'OH', 'IL', 'IN', 'WI', 'MN', 'ND', 'SD', 'NE', 'IA'];
    if (listing.state && rustStates.includes(listing.state.toUpperCase())) {
      riskScore += 20;
    }
    
    return Math.min(100, Math.max(0, riskScore));
  }

  private calculateConfidenceScore(listing: VehicleListing, marketData: MarketData): number {
    let confidence = marketData.confidence * 100;
    
    // Reduce confidence for missing data
    if (!listing.mileage) confidence -= 20;
    if (!listing.year) confidence -= 30;
    if (!listing.vin) confidence -= 10;
    if (!listing.title_status) confidence -= 15;
    
    // Boost confidence for good data sources
    if (listing.source_site === 'GSAauctions') confidence += 10;
    if (listing.vin && listing.vin.length === 17) confidence += 10;
    
    return Math.min(100, Math.max(10, confidence));
  }

  async scoreDeal(listing: VehicleListing): Promise<DealMetrics | null> {
    try {
      if (!listing.make || !listing.model || !listing.year || !listing.current_bid) {
        console.warn('Insufficient data for scoring:', listing.id);
        return null;
      }

      // Get market data
      const marketData = await this.getMarketData(
        listing.make,
        listing.model,
        listing.year,
        listing.state
      );

      // Adjust market price for mileage
      let estimatedSalePrice = marketData.avg_price;
      if (listing.mileage) {
        const mileageFactor = Math.max(0.4, 1.0 - (listing.mileage / 200000));
        estimatedSalePrice *= mileageFactor;
      }

      // Adjust for title status
      if (listing.title_status && listing.title_status !== 'clean') {
        const titleMultiplier = {
          salvage: 0.6,
          rebuilt: 0.8,
          flood: 0.5,
          lemon: 0.7
        };
        estimatedSalePrice *= titleMultiplier[listing.title_status] || 0.8;
      }

      // Calculate costs
      const fees = this.calculateFees(listing.source_site, listing.current_bid);
      const transportCost = this.calculateTransportCost(listing.state || 'CA', estimatedSalePrice);
      
      const totalCost = listing.current_bid + fees.premium + fees.docFee + transportCost;
      const potentialProfit = estimatedSalePrice - totalCost;
      const roiPercentage = (potentialProfit / totalCost) * 100;

      // Calculate risk and confidence
      const riskScore = this.calculateRiskScore(listing, marketData);
      const confidenceScore = this.calculateConfidenceScore(listing, marketData);

      return {
        estimated_sale_price: Math.round(estimatedSalePrice),
        total_cost: Math.round(totalCost),
        potential_profit: Math.round(potentialProfit),
        roi_percentage: Math.round(roiPercentage * 100) / 100,
        risk_score: riskScore,
        confidence_score: confidenceScore,
        transportation_cost: transportCost,
        fees_cost: fees.premium + fees.docFee,
        buyer_premium: fees.premium,
        doc_fee: fees.docFee
      };

    } catch (error) {
      console.error('Error scoring deal:', error);
      return null;
    }
  }

  async createOpportunityIfProfitable(listing: VehicleListing, metrics: DealMetrics): Promise<boolean> {
    // Profitability thresholds
    const MIN_ROI = 15; // 15% minimum ROI
    const MIN_PROFIT = 3000; // $3k minimum profit
    const MAX_RISK = 70; // Maximum risk score of 70
    const MIN_CONFIDENCE = 40; // Minimum confidence of 40%

    if (
      metrics.roi_percentage >= MIN_ROI &&
      metrics.potential_profit >= MIN_PROFIT &&
      metrics.risk_score <= MAX_RISK &&
      metrics.confidence_score >= MIN_CONFIDENCE
    ) {
      try {
        // Determine status based on metrics
        let status = 'moderate';
        if (metrics.roi_percentage >= 25 && metrics.risk_score <= 40) {
          status = 'hot';
        } else if (metrics.roi_percentage >= 20 && metrics.risk_score <= 50) {
          status = 'good';
        }

        const { error } = await supabase.from('opportunities').insert({
          listing_id: listing.id,
          make: listing.make,
          model: listing.model,
          year: listing.year,
          mileage: listing.mileage,
          vin: listing.vin,
          current_bid: listing.current_bid,
          source_site: listing.source_site,
          location: listing.location,
          state: listing.state,
          auction_end: listing.auction_end,
          estimated_sale_price: metrics.estimated_sale_price,
          total_cost: metrics.total_cost,
          potential_profit: metrics.potential_profit,
          roi_percentage: metrics.roi_percentage,
          risk_score: metrics.risk_score,
          confidence_score: metrics.confidence_score,
          transportation_cost: metrics.transportation_cost,
          fees_cost: metrics.fees_cost,
          buyer_premium: metrics.buyer_premium,
          doc_fee: metrics.doc_fee,
          profit_margin: (metrics.potential_profit / metrics.estimated_sale_price) * 100,
          status,
          is_active: true
        });

        if (error) {
          console.error('Error creating opportunity:', error);
          return false;
        }

        // Show toast notification for hot deals
        if (status === 'hot') {
          toast.success('🔥 Hot Deal Alert!', {
            description: `${listing.year} ${listing.make} ${listing.model} - ${metrics.roi_percentage.toFixed(1)}% ROI, $${metrics.potential_profit.toLocaleString()} profit`,
            duration: 10000
          });
        }

        return true;
      } catch (error) {
        console.error('Error creating opportunity:', error);
        return false;
      }
    }

    return false;
  }
}

export const dealScoringEngine = new DealScoringEngine();
export type { DealMetrics, VehicleListing };