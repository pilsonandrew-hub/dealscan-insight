/**
 * Advanced arbitrage calculation engine based on DealerScope v4.6
 */

import { Opportunity, Vehicle, MarketPrice } from '@/types/dealerscope';

interface FeeStructure {
  buyers_premium_pct: number;
  doc_fee: number;
}

interface TransportRate {
  max_miles: number;
  rate_per_mile: number;
}

interface ArbitrageConfig {
  fees: Record<string, FeeStructure>;
  transit_rates: {
    mileage_bands: TransportRate[];
  };
  state_miles_to_ca: Record<string, number>;
}

const DEFAULT_CONFIG: ArbitrageConfig = {
  fees: {
    "GovDeals": { buyers_premium_pct: 12.5, doc_fee: 75 },
    "PublicSurplus": { buyers_premium_pct: 10.0, doc_fee: 50 },
    "Copart": { buyers_premium_pct: 9.5, doc_fee: 89 },
    "IAA": { buyers_premium_pct: 8.5, doc_fee: 95 }
  },
  transit_rates: {
    mileage_bands: [
      { max_miles: 500, rate_per_mile: 2.2 },
      { max_miles: 1000, rate_per_mile: 1.9 },
      { max_miles: 2000, rate_per_mile: 1.6 },
      { max_miles: 99999, rate_per_mile: 1.4 }
    ]
  },
  state_miles_to_ca: {
    "CA": 0, "AZ": 475, "NV": 300, "OR": 600, "WA": 900, "TX": 1400, 
    "CO": 1200, "NM": 900, "UT": 750, "ID": 800, "MT": 1000,
    "AL": 1800, "AR": 1600, "FL": 2000, "GA": 1900, "KY": 1700, 
    "LA": 1500, "MS": 1700, "NC": 2000, "OK": 1400, "SC": 1900, 
    "TN": 1800, "WY": 1000, "VA": 2100, "NY": 2400, "MI": 2000
  }
};

export class ArbitrageCalculator {
  private config: ArbitrageConfig;
  private priceModel: SimpleLinearModel;

  constructor(config: ArbitrageConfig = DEFAULT_CONFIG) {
    this.config = config;
    this.priceModel = new SimpleLinearModel();
  }

  calculateOpportunity(
    vehicle: Vehicle, 
    currentBid: number, 
    sourceSite: string,
    location: string,
    state: string,
    marketPrice?: MarketPrice
  ): Opportunity {
    // Calculate all costs
    const buyerPremium = this.calculateBuyerPremium(currentBid, sourceSite);
    const docFee = this.getDocFee(sourceSite);
    const transportationCost = this.calculateTransportCost(state);
    const totalCost = currentBid + buyerPremium + docFee + transportationCost;

    // Estimate sale price using multiple methods
    const estimatedSalePrice = this.estimateSalePrice(vehicle, marketPrice);
    
    // Calculate profitability metrics
    const potentialProfit = estimatedSalePrice - totalCost;
    const roiPercentage = totalCost > 0 ? (potentialProfit / totalCost) * 100 : 0;
    const profitMargin = estimatedSalePrice > 0 ? (potentialProfit / estimatedSalePrice) * 100 : 0;

    // Calculate risk and confidence scores
    const riskScore = this.calculateRiskScore(vehicle, marketPrice, currentBid);
    const confidenceScore = this.calculateConfidenceScore(vehicle, marketPrice, currentBid);

    // Determine status based on multiple factors
    const status = this.determineOpportunityStatus(potentialProfit, roiPercentage, riskScore, confidenceScore);

    return {
      id: `opp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      vehicle,
      expected_price: estimatedSalePrice,
      acquisition_cost: totalCost,
      profit: potentialProfit,
      roi: roiPercentage,
      confidence: confidenceScore,
      location,
      state,
      status,
      score: this.calculateOpportunityScore(potentialProfit, roiPercentage, riskScore, confidenceScore),
      market_price: marketPrice,
      total_cost: totalCost,
      potential_profit: potentialProfit,
      roi_percentage: roiPercentage,
      risk_score: riskScore,
      confidence_score: confidenceScore,
      transportation_cost: transportationCost,
      fees_cost: buyerPremium + docFee,
      estimated_sale_price: estimatedSalePrice,
      profit_margin: profitMargin,
      source_site: sourceSite,
      current_bid: currentBid
    };
  }

  private calculateBuyerPremium(currentBid: number, sourceSite: string): number {
    const feeStructure = this.config.fees[sourceSite] || this.config.fees["GovDeals"];
    return currentBid * (feeStructure.buyers_premium_pct / 100);
  }

  private getDocFee(sourceSite: string): number {
    const feeStructure = this.config.fees[sourceSite] || this.config.fees["GovDeals"];
    return feeStructure.doc_fee;
  }

  private calculateTransportCost(state: string): number {
    const distance = this.config.state_miles_to_ca[state] || 1000;
    
    for (const band of this.config.transit_rates.mileage_bands) {
      if (distance <= band.max_miles) {
        return distance * band.rate_per_mile;
      }
    }
    
    const lastBand = this.config.transit_rates.mileage_bands[this.config.transit_rates.mileage_bands.length - 1];
    return distance * lastBand.rate_per_mile;
  }

  private estimateSalePrice(vehicle: Vehicle, marketPrice?: MarketPrice): number {
    let basePrice = 25000; // Default fallback

    if (marketPrice) {
      // Use market data as primary source
      const marketMedian = (marketPrice.avg_price + marketPrice.low_price + marketPrice.high_price) / 3;
      basePrice = marketMedian;
    } else {
      // Fallback to ML estimation
      basePrice = this.priceModel.predict(vehicle.year, vehicle.mileage);
    }

    // Apply mileage factor
    const mileageFactor = Math.max(0.3, 1.0 - (vehicle.mileage / 200000));
    
    // Apply age factor
    const currentYear = new Date().getFullYear();
    const ageFactor = Math.max(0.4, 1.0 - ((currentYear - vehicle.year) * 0.03));
    
    // Apply title status factor
    const titleFactor = this.getTitleStatusFactor(vehicle.title_status);
    
    // Conservative pricing for arbitrage (95% of estimated value)
    return basePrice * mileageFactor * ageFactor * titleFactor * 0.95;
  }

  private getTitleStatusFactor(titleStatus?: string): number {
    const factors: Record<string, number> = {
      "clean": 1.0,
      "rebuilt": 0.75,
      "salvage": 0.6,
      "flood": 0.5,
      "lemon": 0.45
    };
    return factors[titleStatus || "clean"] || 0.8;
  }

  private calculateRiskScore(vehicle: Vehicle, marketPrice?: MarketPrice, currentBid?: number): number {
    const riskFactors: number[] = [];
    
    // Age risk (older vehicles are riskier)
    const currentYear = new Date().getFullYear();
    const ageRisk = Math.min(50, (currentYear - vehicle.year) * 3);
    riskFactors.push(ageRisk);
    
    // Mileage risk
    const mileageRisk = Math.min(40, vehicle.mileage / 5000);
    riskFactors.push(mileageRisk);
    
    // Market volatility risk
    if (marketPrice) {
      const priceRange = marketPrice.high_price - marketPrice.low_price;
      const volatilityRisk = (priceRange / marketPrice.avg_price) * 50;
      riskFactors.push(Math.min(30, volatilityRisk));
      
      // Sample size risk (fewer data points = higher risk)
      const sampleRisk = Math.max(0, 30 - marketPrice.sample_size / 5);
      riskFactors.push(sampleRisk);
    } else {
      riskFactors.push(25); // Default risk for no market data
    }
    
    // Title status risk
    const titleRisk = vehicle.title_status === "clean" ? 0 : 
                     vehicle.title_status === "rebuilt" ? 15 :
                     vehicle.title_status === "salvage" ? 35 : 20;
    riskFactors.push(titleRisk);
    
    return Math.min(100, riskFactors.reduce((sum, risk) => sum + risk, 0) / riskFactors.length);
  }

  private calculateConfidenceScore(vehicle: Vehicle, marketPrice?: MarketPrice, currentBid?: number): number {
    const confidenceFactors: number[] = [];
    
    // Market data confidence
    if (marketPrice) {
      if (marketPrice.sample_size > 100) confidenceFactors.push(95);
      else if (marketPrice.sample_size > 50) confidenceFactors.push(80);
      else if (marketPrice.sample_size > 20) confidenceFactors.push(65);
      else confidenceFactors.push(40);
    } else {
      confidenceFactors.push(30); // Low confidence without market data
    }
    
    // Data completeness confidence
    let completeness = 0;
    if (vehicle.vin && vehicle.vin.length === 17) completeness += 25;
    if (vehicle.photo_url) completeness += 20;
    if (vehicle.description && vehicle.description.length > 50) completeness += 25;
    if (vehicle.trim) completeness += 15;
    if (vehicle.title_status) completeness += 15;
    confidenceFactors.push(completeness);
    
    // Bid position confidence (lower bids = higher confidence)
    if (marketPrice && currentBid) {
      if (currentBid < marketPrice.low_price * 0.7) confidenceFactors.push(95);
      else if (currentBid < marketPrice.avg_price * 0.8) confidenceFactors.push(80);
      else if (currentBid < marketPrice.avg_price) confidenceFactors.push(65);
      else confidenceFactors.push(35);
    }
    
    return confidenceFactors.reduce((sum, factor) => sum + factor, 0) / confidenceFactors.length;
  }

  private determineOpportunityStatus(
    profit: number, 
    roi: number, 
    risk: number, 
    confidence: number
  ): "hot" | "good" | "moderate" {
    if (profit > 5000 && roi > 25 && confidence > 70 && risk < 30) return "hot";
    if (profit > 2500 && roi > 15 && confidence > 50 && risk < 50) return "good";
    return "moderate";
  }

  private calculateOpportunityScore(
    profit: number,
    roi: number,
    risk: number,
    confidence: number
  ): number {
    // Weighted scoring algorithm
    const profitScore = Math.min(40, profit / 250); // Max 40 points for $10k+ profit
    const roiScore = Math.min(30, roi); // Max 30 points for 30%+ ROI
    const confidenceBonus = confidence / 5; // Up to 20 points for confidence
    const riskPenalty = risk / 2; // Up to 50 point penalty for high risk
    
    return Math.max(0, Math.min(100, profitScore + roiScore + confidenceBonus - riskPenalty));
  }
}

// Simple linear regression model for price prediction
class SimpleLinearModel {
  private yearCoeff = -1000;
  private mileageCoeff = -0.12;
  private intercept = 2050000; // Base price for year 2025, 0 miles

  predict(year: number, mileage: number): number {
    const predicted = this.intercept + (this.yearCoeff * (2025 - year)) + (this.mileageCoeff * mileage);
    return Math.max(5000, predicted); // Minimum $5k value
  }

  // In a real implementation, this would train on historical sales data
  train(salesData: Array<{year: number, mileage: number, price: number}>): void {
    if (salesData.length < 10) return;
    
    // Simple calculation of coefficients (in production, use proper ML library)
    const avgYear = salesData.reduce((sum, d) => sum + d.year, 0) / salesData.length;
    const avgMileage = salesData.reduce((sum, d) => sum + d.mileage, 0) / salesData.length;
    const avgPrice = salesData.reduce((sum, d) => sum + d.price, 0) / salesData.length;
    
    let yearVariance = 0, mileageVariance = 0, yearPriceCovar = 0, mileagePriceCovar = 0;
    
    salesData.forEach(d => {
      const yearDiff = d.year - avgYear;
      const mileageDiff = d.mileage - avgMileage;
      const priceDiff = d.price - avgPrice;
      
      yearVariance += yearDiff * yearDiff;
      mileageVariance += mileageDiff * mileageDiff;
      yearPriceCovar += yearDiff * priceDiff;
      mileagePriceCovar += mileageDiff * priceDiff;
    });
    
    this.yearCoeff = yearVariance > 0 ? yearPriceCovar / yearVariance : -1000;
    this.mileageCoeff = mileageVariance > 0 ? mileagePriceCovar / mileageVariance : -0.12;
    this.intercept = avgPrice - (this.yearCoeff * avgYear) - (this.mileageCoeff * avgMileage);
  }
}

export const arbitrageCalculator = new ArbitrageCalculator();