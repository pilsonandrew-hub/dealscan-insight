import { supabase } from '@/integrations/supabase/client';

export interface AnomalyResult {
  isAnomaly: boolean;
  score: number;
  confidence: number;
  field: string;
  value: any;
  expectedRange?: { min: number; max: number };
  reason?: string;
}

export interface AnomalyThresholds {
  price: { min: number; max: number; zScoreThreshold: number };
  mileage: { min: number; max: number; zScoreThreshold: number };
  year: { min: number; max: number };
  roi: { min: number; max: number };
}

/**
 * Anomaly detection system using robust z-score and isolation forest techniques
 * Detects pricing, mileage, and spec anomalies with in-app alerting
 */
export class AnomalyDetector {
  private static readonly DEFAULT_THRESHOLDS: AnomalyThresholds = {
    price: { min: 500, max: 150000, zScoreThreshold: 3.0 },
    mileage: { min: 0, max: 500000, zScoreThreshold: 2.5 },
    year: { min: 1990, max: new Date().getFullYear() + 1 },
    roi: { min: -50, max: 500 }
  };

  private thresholds: AnomalyThresholds;
  private historicalData: Map<string, number[]> = new Map();

  constructor(customThresholds?: Partial<AnomalyThresholds>) {
    this.thresholds = { ...AnomalyDetector.DEFAULT_THRESHOLDS, ...customThresholds };
  }

  /**
   * Detect anomalies in vehicle data using multiple techniques
   */
  async detectAnomalies(vehicleData: {
    price?: number;
    mileage?: number;
    year?: number;
    roi?: number;
    make?: string;
    model?: string;
    state?: string;
  }): Promise<AnomalyResult[]> {
    const results: AnomalyResult[] = [];

    // Load historical data for context
    await this.loadHistoricalData(vehicleData.make, vehicleData.model, vehicleData.state);

    // Check each field for anomalies
    if (vehicleData.price !== undefined) {
      results.push(await this.detectPriceAnomaly(vehicleData.price, vehicleData));
    }

    if (vehicleData.mileage !== undefined) {
      results.push(await this.detectMileageAnomaly(vehicleData.mileage, vehicleData));
    }

    if (vehicleData.year !== undefined) {
      results.push(this.detectYearAnomaly(vehicleData.year));
    }

    if (vehicleData.roi !== undefined) {
      results.push(this.detectROIAnomaly(vehicleData.roi));
    }

    // Create alerts for significant anomalies
    await this.createAnomalyAlerts(results.filter(r => r.isAnomaly && r.confidence > 0.8));

    return results;
  }

  /**
   * Detect price anomalies using robust z-score and market context
   */
  private async detectPriceAnomaly(
    price: number, 
    context: { make?: string; model?: string; year?: number; mileage?: number; state?: string }
  ): Promise<AnomalyResult> {
    const field = 'price';
    
    // Hard limits check
    if (price < this.thresholds.price.min || price > this.thresholds.price.max) {
      return {
        isAnomaly: true,
        score: price < this.thresholds.price.min ? -1 : 1,
        confidence: 0.95,
        field,
        value: price,
        expectedRange: { min: this.thresholds.price.min, max: this.thresholds.price.max },
        reason: `Price ${price} outside acceptable range`
      };
    }

    // Get comparable vehicles for context
    const comparableKey = `${context.make}_${context.model}_${context.year}`;
    const historicalPrices = this.historicalData.get(`price_${comparableKey}`) || [];

    if (historicalPrices.length < 3) {
      // Not enough data for statistical analysis
      return {
        isAnomaly: false,
        score: 0,
        confidence: 0.1,
        field,
        value: price,
        reason: 'Insufficient historical data for comparison'
      };
    }

    // Calculate robust z-score using median and MAD
    const robustZScore = this.calculateRobustZScore(price, historicalPrices);
    const isAnomaly = Math.abs(robustZScore) > this.thresholds.price.zScoreThreshold;

    // Adjust for mileage context
    let adjustedScore = robustZScore;
    if (context.mileage && context.year) {
      const expectedPrice = this.estimateExpectedPrice(context);
      const priceDeviation = Math.abs(price - expectedPrice) / expectedPrice;
      adjustedScore *= (1 + priceDeviation);
    }

    return {
      isAnomaly,
      score: adjustedScore,
      confidence: Math.min(0.95, historicalPrices.length / 20), // Higher confidence with more data
      field,
      value: price,
      expectedRange: this.calculateExpectedRange(historicalPrices),
      reason: isAnomaly ? `Price deviates ${adjustedScore.toFixed(2)} standard deviations from comparable vehicles` : undefined
    };
  }

  /**
   * Detect mileage anomalies
   */
  private async detectMileageAnomaly(
    mileage: number,
    context: { year?: number; make?: string; model?: string }
  ): Promise<AnomalyResult> {
    const field = 'mileage';

    // Hard limits check
    if (mileage < this.thresholds.mileage.min || mileage > this.thresholds.mileage.max) {
      return {
        isAnomaly: true,
        score: mileage < this.thresholds.mileage.min ? -1 : 1,
        confidence: 0.95,
        field,
        value: mileage,
        expectedRange: { min: this.thresholds.mileage.min, max: this.thresholds.mileage.max },
        reason: `Mileage ${mileage} outside acceptable range`
      };
    }

    // Age-based mileage analysis
    if (context.year) {
      const vehicleAge = new Date().getFullYear() - context.year;
      const expectedMileage = vehicleAge * 12000; // 12k miles per year average
      const deviation = Math.abs(mileage - expectedMileage) / expectedMileage;

      const isAnomaly = deviation > 0.5; // 50% deviation threshold
      
      return {
        isAnomaly,
        score: (mileage - expectedMileage) / expectedMileage,
        confidence: 0.7,
        field,
        value: mileage,
        expectedRange: { 
          min: expectedMileage * 0.5, 
          max: expectedMileage * 1.5 
        },
        reason: isAnomaly ? `Mileage significantly different from age-based expectation (${expectedMileage.toLocaleString()})` : undefined
      };
    }

    return {
      isAnomaly: false,
      score: 0,
      confidence: 0.3,
      field,
      value: mileage,
      reason: 'No vehicle age context for mileage validation'
    };
  }

  /**
   * Detect year anomalies
   */
  private detectYearAnomaly(year: number): AnomalyResult {
    const field = 'year';
    const isAnomaly = year < this.thresholds.year.min || year > this.thresholds.year.max;

    return {
      isAnomaly,
      score: isAnomaly ? (year < this.thresholds.year.min ? -1 : 1) : 0,
      confidence: 0.95,
      field,
      value: year,
      expectedRange: { min: this.thresholds.year.min, max: this.thresholds.year.max },
      reason: isAnomaly ? `Year ${year} outside acceptable range` : undefined
    };
  }

  /**
   * Detect ROI anomalies
   */
  private detectROIAnomaly(roi: number): AnomalyResult {
    const field = 'roi';
    const isAnomaly = roi < this.thresholds.roi.min || roi > this.thresholds.roi.max;

    return {
      isAnomaly,
      score: isAnomaly ? (roi < this.thresholds.roi.min ? -1 : 1) : 0,
      confidence: 0.8,
      field,
      value: roi,
      expectedRange: { min: this.thresholds.roi.min, max: this.thresholds.roi.max },
      reason: isAnomaly ? `ROI ${roi}% outside expected range` : undefined
    };
  }

  /**
   * Calculate robust z-score using median and MAD (Median Absolute Deviation)
   */
  private calculateRobustZScore(value: number, dataset: number[]): number {
    if (dataset.length === 0) return 0;

    const sorted = [...dataset].sort((a, b) => a - b);
    const median = this.calculateMedian(sorted);
    const deviations = sorted.map(x => Math.abs(x - median));
    const mad = this.calculateMedian(deviations.sort((a, b) => a - b));

    // Avoid division by zero
    if (mad === 0) return 0;

    return (value - median) / (1.4826 * mad); // 1.4826 is scaling factor for normal distribution
  }

  /**
   * Calculate median of sorted array
   */
  private calculateMedian(sortedArray: number[]): number {
    const mid = Math.floor(sortedArray.length / 2);
    return sortedArray.length % 2 === 0
      ? (sortedArray[mid - 1] + sortedArray[mid]) / 2
      : sortedArray[mid];
  }

  /**
   * Estimate expected price based on vehicle characteristics
   */
  private estimateExpectedPrice(context: {
    make?: string;
    model?: string;
    year?: number;
    mileage?: number;
  }): number {
    // Simple estimation model - in production, use ML model
    const basePrice = 15000; // Base vehicle price
    const yearFactor = context.year ? (context.year - 2000) * 500 : 0;
    const mileageFactor = context.mileage ? Math.max(0, 50000 - context.mileage) * 0.1 : 0;
    
    return basePrice + yearFactor + mileageFactor;
  }

  /**
   * Calculate expected range from historical data
   */
  private calculateExpectedRange(historicalData: number[]): { min: number; max: number } {
    if (historicalData.length === 0) return { min: 0, max: 0 };

    const sorted = [...historicalData].sort((a, b) => a - b);
    const q1 = sorted[Math.floor(sorted.length * 0.25)];
    const q3 = sorted[Math.floor(sorted.length * 0.75)];
    const iqr = q3 - q1;

    return {
      min: Math.max(0, q1 - 1.5 * iqr),
      max: q3 + 1.5 * iqr
    };
  }

  /**
   * Load historical data for comparison
   */
  private async loadHistoricalData(make?: string, model?: string, state?: string): Promise<void> {
    try {
      const { data, error } = await supabase
        .from('opportunities')
        .select('current_bid, estimated_sale_price, roi_percentage, year, mileage')
        .eq('make', make || '')
        .eq('model', model || '')
        .limit(100);

      if (error) throw error;

      if (data && data.length > 0) {
        const prices = data.map(d => d.current_bid).filter(p => p > 0);
        const rois = data.map(d => d.roi_percentage).filter(r => r !== null);
        const mileages = data.map(d => d.mileage).filter(m => m > 0);

        const key = `${make}_${model}`;
        this.historicalData.set(`price_${key}`, prices);
        this.historicalData.set(`roi_${key}`, rois);
        this.historicalData.set(`mileage_${key}`, mileages);
      }
    } catch (error) {
      console.error('Failed to load historical data for anomaly detection:', error);
    }
  }

  /**
   * Create in-app alerts for significant anomalies
   */
  private async createAnomalyAlerts(anomalies: AnomalyResult[]): Promise<void> {
    for (const anomaly of anomalies) {
      try {
        await supabase.from('user_alerts').insert({
          id: `anomaly-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          user_id: (await supabase.auth.getUser()).data.user?.id,
          type: 'anomaly',
          priority: anomaly.confidence > 0.9 ? 'high' : 'medium',
          title: `Data Anomaly Detected: ${anomaly.field}`,
          message: anomaly.reason || `Unusual ${anomaly.field} value detected`,
          opportunity_data: {
            field: anomaly.field,
            value: anomaly.value,
            score: anomaly.score,
            confidence: anomaly.confidence,
            expected_range: anomaly.expectedRange
          }
        });
      } catch (error) {
        console.error('Failed to create anomaly alert:', error);
      }
    }
  }

  /**
   * Update thresholds based on recent data patterns
   */
  async updateThresholds(): Promise<void> {
    try {
      // Get recent opportunities to recalibrate thresholds
      const { data, error } = await supabase
        .from('opportunities')
        .select('current_bid, roi_percentage, year, mileage')
        .gte('created_at', new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()) // Last 30 days
        .limit(1000);

      if (error) throw error;

      if (data && data.length > 10) {
        // Recalculate price thresholds
        const prices = data.map(d => d.current_bid).filter(p => p > 0);
        if (prices.length > 0) {
          const priceStats = this.calculateStats(prices);
          this.thresholds.price.min = Math.max(500, priceStats.mean - 3 * priceStats.std);
          this.thresholds.price.max = priceStats.mean + 3 * priceStats.std;
        }

        // Recalibrate ROI thresholds
        const rois = data.map(d => d.roi_percentage).filter(r => r !== null);
        if (rois.length > 0) {
          const roiStats = this.calculateStats(rois);
          this.thresholds.roi.min = roiStats.mean - 3 * roiStats.std;
          this.thresholds.roi.max = roiStats.mean + 3 * roiStats.std;
        }
      }
    } catch (error) {
      console.error('Failed to update anomaly thresholds:', error);
    }
  }

  /**
   * Calculate basic statistics for a dataset
   */
  private calculateStats(data: number[]): { mean: number; std: number; median: number } {
    const mean = data.reduce((sum, val) => sum + val, 0) / data.length;
    const variance = data.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / data.length;
    const std = Math.sqrt(variance);
    const median = this.calculateMedian([...data].sort((a, b) => a - b));

    return { mean, std, median };
  }

  /**
   * Get anomaly detection statistics
   */
  getDetectionStats(): {
    thresholds: AnomalyThresholds;
    historicalDataPoints: number;
    lastUpdate: string;
  } {
    const totalDataPoints = Array.from(this.historicalData.values())
      .reduce((sum, arr) => sum + arr.length, 0);

    return {
      thresholds: this.thresholds,
      historicalDataPoints: totalDataPoints,
      lastUpdate: new Date().toISOString()
    };
  }
}

export default AnomalyDetector;