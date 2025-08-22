import { useState, useEffect, useCallback } from 'react';
import { Opportunity } from '@/types/dealerscope';
import { 
  marketAnalysisEngine, 
  MarketTrend, 
  CompetitiveAnalysis, 
  ProfitabilityForecast,
  AdvancedMarketMetrics 
} from '@/services/marketAnalysis';

export interface MarketAnalysisResult {
  trend: MarketTrend;
  competitive: CompetitiveAnalysis;
  forecast: ProfitabilityForecast;
  metrics: AdvancedMarketMetrics;
}

export interface UseMarketAnalysisReturn {
  analysis: MarketAnalysisResult | null;
  isLoading: boolean;
  error: string | null;
  analyzeOpportunity: (opportunity: Opportunity) => Promise<void>;
  clearAnalysis: () => void;
}

export function useMarketAnalysis(): UseMarketAnalysisReturn {
  const [analysis, setAnalysis] = useState<MarketAnalysisResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyzeOpportunity = useCallback(async (opportunity: Opportunity) => {
    if (!opportunity) {
      setError('No opportunity provided for analysis');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await marketAnalysisEngine.analyzeMarketOpportunity(opportunity);
      setAnalysis(result);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to analyze market opportunity';
      setError(errorMessage);
      console.error('Market analysis error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearAnalysis = useCallback(() => {
    setAnalysis(null);
    setError(null);
  }, []);

  return {
    analysis,
    isLoading,
    error,
    analyzeOpportunity,
    clearAnalysis
  };
}

export function useMarketTrends(opportunities: Opportunity[]) {
  const [trends, setTrends] = useState<Record<string, MarketTrend>>({});
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!opportunities.length) return;

    const analyzeTrends = async () => {
      setIsLoading(true);
      const trendData: Record<string, MarketTrend> = {};

      // Group by make-model for trend analysis
      const grouped = opportunities.reduce((acc, opp) => {
        const key = `${opp.vehicle.make}-${opp.vehicle.model}`;
        if (!acc[key]) acc[key] = [];
        acc[key].push(opp);
        return acc;
      }, {} as Record<string, Opportunity[]>);

      // Analyze trends for each group
      for (const [key, opps] of Object.entries(grouped)) {
        try {
          const analysis = await marketAnalysisEngine.analyzeMarketOpportunity(opps[0]);
          trendData[key] = analysis.trend;
        } catch (error) {
          console.error(`Failed to analyze trend for ${key}:`, error);
        }
      }

      setTrends(trendData);
      setIsLoading(false);
    };

    analyzeTrends();
  }, [opportunities]);

  return { trends, isLoading };
}

export function useMarketMetrics(opportunities: Opportunity[]) {
  const [metrics, setMetrics] = useState({
    totalValue: 0,
    averageROI: 0,
    totalProfit: 0,
    riskDistribution: { low: 0, medium: 0, high: 0 },
    topPerformers: [] as Opportunity[],
    marketMomentum: 'neutral' as 'bullish' | 'bearish' | 'neutral'
  });

  useEffect(() => {
    if (!opportunities.length) {
      setMetrics({
        totalValue: 0,
        averageROI: 0,
        totalProfit: 0,
        riskDistribution: { low: 0, medium: 0, high: 0 },
        topPerformers: [],
        marketMomentum: 'neutral'
      });
      return;
    }

    const totalValue = opportunities.reduce((sum, opp) => sum + opp.estimated_sale_price, 0);
    const totalProfit = opportunities.reduce((sum, opp) => sum + opp.potential_profit, 0);
    const averageROI = opportunities.reduce((sum, opp) => sum + opp.roi_percentage, 0) / opportunities.length;

    const riskDistribution = opportunities.reduce((acc, opp) => {
      if (opp.risk_score <= 30) acc.low++;
      else if (opp.risk_score <= 70) acc.medium++;
      else acc.high++;
      return acc;
    }, { low: 0, medium: 0, high: 0 });

    const topPerformers = [...opportunities]
      .sort((a, b) => b.potential_profit - a.potential_profit)
      .slice(0, 5);

    // Simple momentum calculation based on average ROI
    let marketMomentum: 'bullish' | 'bearish' | 'neutral' = 'neutral';
    if (averageROI > 15) marketMomentum = 'bullish';
    else if (averageROI < 5) marketMomentum = 'bearish';

    setMetrics({
      totalValue,
      averageROI,
      totalProfit,
      riskDistribution,
      topPerformers,
      marketMomentum
    });
  }, [opportunities]);

  return metrics;
}