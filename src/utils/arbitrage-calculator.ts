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
  private priceModel: AdvancedPricePredictionModel;

  constructor(config: ArbitrageConfig = DEFAULT_CONFIG) {
    this.config = config;
    this.priceModel = new AdvancedPricePredictionModel();
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
      risk_score: riskScore,
      transportation_cost: transportationCost,
      fees_cost: buyerPremium + docFee,
      estimated_sale_price: estimatedSalePrice,
      profit_margin: profitMargin,
      source_site: sourceSite,
      current_bid: currentBid,
      vin: vehicle.vin,
      make: vehicle.make,
      model: vehicle.model,
      year: vehicle.year,
      mileage: vehicle.mileage
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
    if (marketPrice) {
      // Use market price as base but adjust with our model's confidence
      const modelPrice = this.priceModel.predict(vehicle.year, vehicle.mileage, vehicle.make, vehicle.model, vehicle.trim);
      const confidence = this.priceModel.getConfidenceScore(vehicle.year, vehicle.mileage, vehicle.make, vehicle.model);
      
      // Weighted average based on confidence
      return (marketPrice.avg_price * (1 - confidence)) + (modelPrice * confidence);
    }
    
    return this.priceModel.predict(vehicle.year, vehicle.mileage, vehicle.make, vehicle.model, vehicle.trim);
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
    let confidence = this.priceModel.getConfidenceScore(vehicle.year, vehicle.mileage, vehicle.make, vehicle.model);

    // Market data availability increases confidence
    if (marketPrice) {
      confidence += 0.2;
      if (marketPrice.sample_size > 10) confidence += 0.05;
      if (marketPrice.sample_size > 50) confidence += 0.05;
      if (marketPrice.sample_size > 100) confidence += 0.05;
      
      // Price consistency check
      const modelPrice = this.priceModel.predict(vehicle.year, vehicle.mileage, vehicle.make, vehicle.model, vehicle.trim);
      const priceVariance = Math.abs(marketPrice.avg_price - modelPrice) / Math.max(marketPrice.avg_price, modelPrice);
      if (priceVariance < 0.1) confidence += 0.1; // Prices align well
      else if (priceVariance > 0.3) confidence -= 0.1; // Large discrepancy
    }

    // Title status impact
    if (vehicle.title_status === 'clean') confidence += 0.05;
    else if (vehicle.title_status === 'salvage') confidence -= 0.2;
    else if (vehicle.title_status === 'flood') confidence -= 0.25;

    return Math.max(0.1, Math.min(0.95, confidence));
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

class AdvancedPricePredictionModel {
  private models: Map<string, any> = new Map();
  private marketFactors: Map<string, number> = new Map();
  private seasonalAdjustments: Map<number, number> = new Map();
  private brandMultipliers: Map<string, number> = new Map();

  constructor() {
    this.initializeMarketFactors();
    this.initializeSeasonalAdjustments();
    this.initializeBrandMultipliers();
  }

  private initializeMarketFactors(): void {
    // Market demand factors by vehicle type
    this.marketFactors.set('luxury', 1.2);
    this.marketFactors.set('suv', 1.15);
    this.marketFactors.set('truck', 1.1);
    this.marketFactors.set('sedan', 0.95);
    this.marketFactors.set('coupe', 0.9);
    this.marketFactors.set('convertible', 1.05);
  }

  private initializeSeasonalAdjustments(): void {
    // Seasonal price adjustments by month
    this.seasonalAdjustments.set(1, 0.95); // January
    this.seasonalAdjustments.set(2, 0.93); // February
    this.seasonalAdjustments.set(3, 1.02); // March
    this.seasonalAdjustments.set(4, 1.05); // April
    this.seasonalAdjustments.set(5, 1.08); // May
    this.seasonalAdjustments.set(6, 1.1);  // June
    this.seasonalAdjustments.set(7, 1.08); // July
    this.seasonalAdjustments.set(8, 1.05); // August
    this.seasonalAdjustments.set(9, 1.02); // September
    this.seasonalAdjustments.set(10, 0.98); // October
    this.seasonalAdjustments.set(11, 0.96); // November
    this.seasonalAdjustments.set(12, 0.94); // December
  }

  private initializeBrandMultipliers(): void {
    // Brand value multipliers
    this.brandMultipliers.set('mercedes-benz', 1.3);
    this.brandMultipliers.set('bmw', 1.25);
    this.brandMultipliers.set('audi', 1.2);
    this.brandMultipliers.set('lexus', 1.15);
    this.brandMultipliers.set('tesla', 1.4);
    this.brandMultipliers.set('porsche', 1.6);
    this.brandMultipliers.set('toyota', 1.1);
    this.brandMultipliers.set('honda', 1.05);
    this.brandMultipliers.set('ford', 0.95);
    this.brandMultipliers.set('chevrolet', 0.9);
    this.brandMultipliers.set('nissan', 0.85);
  }

  predict(year: number, mileage: number, make: string, model: string, trim?: string): number {
    const basePrice = this.calculateBasePrice(year, make, model);
    const ageAdjustment = this.calculateAgeAdjustment(year);
    const mileageAdjustment = this.calculateMileageAdjustment(mileage, year);
    const brandAdjustment = this.calculateBrandAdjustment(make);
    const seasonalAdjustment = this.calculateSeasonalAdjustment();
    const marketAdjustment = this.calculateMarketAdjustment(make, model);
    const conditionAdjustment = this.calculateConditionAdjustment(year, mileage);

    let predictedPrice = basePrice * brandAdjustment * seasonalAdjustment * marketAdjustment;
    predictedPrice += ageAdjustment + mileageAdjustment + conditionAdjustment;

    return Math.max(predictedPrice, 1000);
  }

  private calculateBasePrice(year: number, make: string, model: string): number {
    // Enhanced base price calculation with market intelligence
    const makeLower = make.toLowerCase();
    const modelLower = model.toLowerCase();

    // Luxury brands base prices
    if (['mercedes-benz', 'bmw', 'audi', 'lexus'].includes(makeLower)) {
      return 45000 + (year - 2015) * 2000;
    }

    // Electric vehicles
    if (makeLower === 'tesla' || modelLower.includes('electric') || modelLower.includes('ev')) {
      return 50000 + (year - 2015) * 3000;
    }

    // Performance vehicles
    if (['porsche', 'ferrari', 'lamborghini', 'maserati'].includes(makeLower)) {
      return 80000 + (year - 2015) * 5000;
    }

    // Trucks and SUVs
    if (modelLower.includes('truck') || modelLower.includes('suv') || 
        ['f-150', 'silverado', 'ram', 'sierra'].includes(modelLower)) {
      return 35000 + (year - 2015) * 1500;
    }

    // Standard vehicles
    return 25000 + (year - 2015) * 1000;
  }

  private calculateAgeAdjustment(year: number): number {
    const age = new Date().getFullYear() - year;
    return -age * 1200; // $1200 depreciation per year
  }

  private calculateMileageAdjustment(mileage: number, year: number): number {
    const age = new Date().getFullYear() - year;
    const expectedMileage = age * 12000; // 12k miles per year expected
    const mileageDifference = mileage - expectedMileage;
    return -mileageDifference * 0.2; // $0.20 per mile over/under expected
  }

  private calculateBrandAdjustment(make: string): number {
    return this.brandMultipliers.get(make.toLowerCase()) || 1.0;
  }

  private calculateSeasonalAdjustment(): number {
    const currentMonth = new Date().getMonth() + 1;
    return this.seasonalAdjustments.get(currentMonth) || 1.0;
  }

  private calculateMarketAdjustment(make: string, model: string): number {
    const modelLower = model.toLowerCase();
    
    if (modelLower.includes('suv')) return this.marketFactors.get('suv') || 1.0;
    if (modelLower.includes('truck')) return this.marketFactors.get('truck') || 1.0;
    if (modelLower.includes('convertible')) return this.marketFactors.get('convertible') || 1.0;
    if (modelLower.includes('coupe')) return this.marketFactors.get('coupe') || 1.0;
    
    return this.marketFactors.get('sedan') || 1.0;
  }

  private calculateConditionAdjustment(year: number, mileage: number): number {
    const age = new Date().getFullYear() - year;
    const averageMileagePerYear = mileage / Math.max(age, 1);
    
    // Low mileage bonus
    if (averageMileagePerYear < 8000) return 2000;
    if (averageMileagePerYear < 12000) return 500;
    
    // High mileage penalty
    if (averageMileagePerYear > 20000) return -3000;
    if (averageMileagePerYear > 15000) return -1500;
    
    return 0;
  }

  train(salesData: Array<{year: number, mileage: number, price: number, make: string, model: string}>): void {
    console.log(`Training advanced model with ${salesData.length} data points`);
    
    // Update brand multipliers based on actual sales data
    const brandPerformance = new Map<string, {total: number, count: number}>();
    
    salesData.forEach(sale => {
      const makeLower = sale.make.toLowerCase();
      const existing = brandPerformance.get(makeLower) || {total: 0, count: 0};
      const predicted = this.predict(sale.year, sale.mileage, sale.make, sale.model);
      const actualVsPredicted = sale.price / predicted;
      
      brandPerformance.set(makeLower, {
        total: existing.total + actualVsPredicted,
        count: existing.count + 1
      });
    });

    // Update multipliers based on performance
    brandPerformance.forEach((performance, brand) => {
      const avgMultiplier = performance.total / performance.count;
      const currentMultiplier = this.brandMultipliers.get(brand) || 1.0;
      const updatedMultiplier = (currentMultiplier + avgMultiplier) / 2; // Smooth adjustment
      this.brandMultipliers.set(brand, updatedMultiplier);
    });
  }

  getModelAccuracy(testData: Array<{year: number, mileage: number, price: number, make: string, model: string}>): number {
    if (testData.length === 0) return 0;

    let totalError = 0;
    testData.forEach(test => {
      const predicted = this.predict(test.year, test.mileage, test.make, test.model);
      const error = Math.abs(predicted - test.price) / test.price;
      totalError += error;
    });

    return 1 - (totalError / testData.length); // Return accuracy as percentage
  }

  getConfidenceScore(year: number, mileage: number, make: string, model: string): number {
    const age = new Date().getFullYear() - year;
    let confidence = 0.8; // Base confidence

    // Age factor
    if (age <= 3) confidence += 0.1;
    else if (age <= 7) confidence += 0.05;
    else if (age > 15) confidence -= 0.2;

    // Mileage factor
    const avgMileagePerYear = mileage / Math.max(age, 1);
    if (avgMileagePerYear < 15000) confidence += 0.05;
    else if (avgMileagePerYear > 25000) confidence -= 0.15;

    // Brand factor
    const brandMultiplier = this.brandMultipliers.get(make.toLowerCase()) || 1.0;
    if (brandMultiplier > 1.1) confidence += 0.05; // Popular brands

    return Math.max(0.1, Math.min(0.99, confidence));
  }
}

export const arbitrageCalculator = new ArbitrageCalculator();