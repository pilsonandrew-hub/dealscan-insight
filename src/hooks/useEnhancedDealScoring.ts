/**
 * Enhanced deal scoring with ML predictions and user feedback
 */

import { useState, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { Opportunity } from '@/types/dealerscope';

interface MLPrediction {
  predicted_prices: {
    p10: number;
    p50: number;
    p90: number;
  };
  days_to_sell: number;
  confidence_interval: number;
  deal_rationale: string;
  risk_factors: string[];
  market_position: "below" | "market" | "above";
}

interface ScoringProgress {
  total: number;
  processed: number;
  currentStage: string;
  estimatedTimeRemaining: number;
}

export function useEnhancedDealScoring() {
  const [isScoring, setIsScoring] = useState(false);
  const [progress, setProgress] = useState<ScoringProgress | null>(null);

  const runMLPrediction = useCallback(async (opportunity: Opportunity): Promise<MLPrediction> => {
    // Enhanced ML scoring logic
    const basePrice = opportunity.current_bid || 0;
    const year = opportunity.year;
    const mileage = opportunity.mileage || 0;
    
    // Simulate sophisticated ML model with multiple factors
    const ageDepreciation = Math.max(0, (2024 - year) * 0.08);
    const mileageFactor = Math.min(1, mileage / 200000);
    const marketAdjustment = Math.random() * 0.4 - 0.2; // ±20% market variance
    
    const predictedMedian = basePrice * (1 - ageDepreciation - mileageFactor * 0.3) * (1 + marketAdjustment);
    const variance = predictedMedian * 0.15; // 15% price variance
    
    const prediction: MLPrediction = {
      predicted_prices: {
        p10: predictedMedian - variance,
        p50: predictedMedian,
        p90: predictedMedian + variance
      },
      days_to_sell: Math.max(15, 90 - (opportunity.confidence * 0.6)),
      confidence_interval: 85 + Math.random() * 10,
      deal_rationale: generateDealRationale(opportunity, predictedMedian),
      risk_factors: assessRiskFactors(opportunity),
      market_position: predictedMedian > basePrice * 1.1 ? "below" : 
                      predictedMedian < basePrice * 0.9 ? "above" : "market"
    };

    return prediction;
  }, []);

  const generateDealRationale = useCallback((opportunity: Opportunity, predictedPrice: number): string => {
    const profit = predictedPrice - opportunity.total_cost;
    const reasons = [];

    if (profit > 5000) reasons.push("High profit potential");
    if (opportunity.mileage && opportunity.mileage < 100000) reasons.push("Low mileage");
    if (opportunity.year > 2018) reasons.push("Recent model year");
    if (opportunity.confidence > 80) reasons.push("High confidence score");
    if (opportunity.risk_score < 30) reasons.push("Low risk");

    return reasons.length > 0 
      ? `Strong deal: ${reasons.join(", ")}.`
      : "Standard market opportunity with typical risk profile.";
  }, []);

  const assessRiskFactors = useCallback((opportunity: Opportunity): string[] => {
    const factors = [];

    if (opportunity.mileage && opportunity.mileage > 150000) factors.push("High mileage");
    if (opportunity.year < 2015) factors.push("Older model");
    if (opportunity.risk_score > 70) factors.push("High risk score");
    if (opportunity.confidence < 60) factors.push("Low confidence prediction");

    return factors;
  }, []);

  const scoreOpportunityWithML = useCallback(async (opportunity: Opportunity): Promise<Opportunity> => {
    const mlPrediction = await runMLPrediction(opportunity);
    
    // Calculate enhanced metrics
    const bidCap = mlPrediction.predicted_prices.p10 * 0.85; // Conservative bid cap
    const enhancedProfit = mlPrediction.predicted_prices.p50 - opportunity.total_cost;
    const enhancedROI = (enhancedProfit / opportunity.total_cost) * 100;

    return {
      ...opportunity,
      predicted_prices: mlPrediction.predicted_prices,
      days_to_sell: mlPrediction.days_to_sell,
      deal_rationale: mlPrediction.deal_rationale,
      bid_cap: bidCap,
      market_position: mlPrediction.market_position,
      profit: enhancedProfit,
      roi: enhancedROI,
      confidence: mlPrediction.confidence_interval,
      last_updated: new Date().toISOString()
    };
  }, [runMLPrediction]);

  const batchScoreOpportunities = useCallback(async (opportunities: Opportunity[]): Promise<Opportunity[]> => {
    setIsScoring(true);
    setProgress({
      total: opportunities.length,
      processed: 0,
      currentStage: "Initializing ML models...",
      estimatedTimeRemaining: opportunities.length * 2 // ~2 seconds per opportunity
    });

    const scoredOpportunities: Opportunity[] = [];

    for (let i = 0; i < opportunities.length; i++) {
      setProgress(prev => prev ? {
        ...prev,
        processed: i,
        currentStage: `Analyzing ${opportunities[i].make} ${opportunities[i].model}...`,
        estimatedTimeRemaining: (opportunities.length - i) * 2
      } : null);

      const scored = await scoreOpportunityWithML(opportunities[i]);
      scoredOpportunities.push(scored);

      // Simulate processing time
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    setProgress(prev => prev ? {
      ...prev,
      processed: opportunities.length,
      currentStage: "Complete",
      estimatedTimeRemaining: 0
    } : null);

    setIsScoring(false);
    return scoredOpportunities;
  }, [scoreOpportunityWithML]);

  const recordUserFeedback = useCallback(async (
    opportunityId: string, 
    action: "saved" | "ignored" | "viewed"
  ) => {
    try {
      const { error } = await supabase
        .from('opportunities')
        .update({ 
          user_sentiment: action === "saved" ? "interested" : "ignored",
          status: action === "saved" ? "flagged" : "read"
        })
        .eq('id', opportunityId);

      if (error) throw error;

      // In a real implementation, this would feed into a personalization model
      console.log(`Recorded user feedback: ${action} for opportunity ${opportunityId}`);
    } catch (error) {
      console.error('Error recording user feedback:', error);
    }
  }, []);

  return {
    isScoring,
    progress,
    scoreOpportunityWithML,
    batchScoreOpportunities,
    recordUserFeedback,
    runMLPrediction
  };
}