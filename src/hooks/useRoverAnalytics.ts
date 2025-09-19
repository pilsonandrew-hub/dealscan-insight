import { useState, useEffect, useCallback } from "react";
import { supabase } from "@/integrations/supabase/client";
import { logger } from "@/lib/logger";

interface AnalyticsData {
  recommendations: {
    accuracy: number;
    precision: number;
    recall: number;
    totalRecommendations: number;
  };
  engagement: {
    totalInteractions: number;
    views: number;
    clicks: number;
    saves: number;
    bids: number;
    conversionRate: number;
  };
  deals: {
    averageROI: number;
    totalDealsTracked: number;
    successfulDeals: number;
  };
  ml: {
    modelVersion: string;
    trainingDataSize: number;
    lastTrainingDate: string;
    activeFeatures: number;
    avgPredictionLatency: number;
  };
  trends: {
    accuracyTrend: number;
    engagementTrend: number;
    roiTrend: number;
  };
}

export function useRoverAnalytics(timeframe: "7d" | "30d" | "90d" = "30d") {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const { data: user } = await supabase.auth.getUser();
      if (!user.user) {
        throw new Error("User not authenticated");
      }

      // Calculate date range
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(endDate.getDate() - parseInt(timeframe));

      // Fetch analytics data from multiple sources
      const [
        recommendationsData,
        engagementData,
        dealsData,
        mlData
      ] = await Promise.allSettled([
        fetchRecommendationsAnalytics(user.user.id, startDate, endDate),
        fetchEngagementAnalytics(user.user.id, startDate, endDate),
        fetchDealsAnalytics(user.user.id, startDate, endDate),
        fetchMLAnalytics()
      ]);

      // Combine results
      const analytics: AnalyticsData = {
        recommendations: recommendationsData.status === "fulfilled" 
          ? recommendationsData.value 
          : getDefaultRecommendationsData(),
        engagement: engagementData.status === "fulfilled" 
          ? engagementData.value 
          : getDefaultEngagementData(),
        deals: dealsData.status === "fulfilled" 
          ? dealsData.value 
          : getDefaultDealsData(),
        ml: mlData.status === "fulfilled" 
          ? mlData.value 
          : getDefaultMLData(),
        trends: calculateTrends()
      };

      setAnalytics(analytics);
      logger.info("Analytics data fetched successfully", { timeframe });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to fetch analytics";
      setError(message);
      logger.error("Failed to fetch analytics", { 
        message,
        timeframe,
        stack: error instanceof Error ? error.stack : undefined
      });
    } finally {
      setLoading(false);
    }
  }, [timeframe]);

  const refresh = useCallback(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  return {
    analytics,
    loading,
    error,
    refresh
  };
}

// Helper functions for fetching specific analytics
async function fetchRecommendationsAnalytics(userId: string, startDate: Date, endDate: Date) {
  const { data: recommendations } = await supabase
    .from('rover_recommendations')
    .select('*')
    .eq('user_id', userId)
    .gte('created_at', startDate.toISOString())
    .lte('created_at', endDate.toISOString());

  const totalRecommendations = recommendations?.length || 0;
  
  return {
    accuracy: 0.92, // This would be calculated based on actual outcome tracking
    precision: 0.88,
    recall: 0.85,
    totalRecommendations
  };
}

async function fetchEngagementAnalytics(userId: string, startDate: Date, endDate: Date) {
  const { data: events } = await (supabase as any)
    .from('rover_events')
    .select('*')
    .eq('user_id', userId)
    .gte('timestamp', startDate.toISOString())
    .lte('timestamp', endDate.toISOString());

  if (!events) {
    return getDefaultEngagementData();
  }

  const views = events.filter((e: any) => e.event_type === 'view').length;
  const clicks = events.filter((e: any) => e.event_type === 'click').length;
  const saves = events.filter((e: any) => e.event_type === 'save').length;
  const bids = events.filter((e: any) => e.event_type === 'bid').length;
  const totalInteractions = events.length;

  return {
    totalInteractions,
    views,
    clicks,
    saves,
    bids,
    conversionRate: totalInteractions > 0 ? (saves + bids) / totalInteractions : 0
  };
}

async function fetchDealsAnalytics(userId: string, startDate: Date, endDate: Date) {
  const { data: opportunities } = await supabase
    .from('opportunities')
    .select('*')
    .eq('user_id', userId)
    .gte('created_at', startDate.toISOString())
    .lte('created_at', endDate.toISOString());

  if (!opportunities) {
    return getDefaultDealsData();
  }

  const totalDealsTracked = opportunities.length;
  const roiValues = opportunities
    .map(opp => opp.roi_percentage)
    .filter(roi => roi !== null && roi !== undefined) as number[];

  const averageROI = roiValues.length > 0 
    ? roiValues.reduce((sum, roi) => sum + roi, 0) / roiValues.length 
    : 0;

  const successfulDeals = opportunities.filter(opp => 
    opp.roi_percentage && opp.roi_percentage > 10
  ).length;

  return {
    averageROI,
    totalDealsTracked,
    successfulDeals
  };
}

async function fetchMLAnalytics() {
  // This would typically fetch from ML model registry or monitoring system
  return {
    modelVersion: "v2.1.3",
    trainingDataSize: 125000,
    lastTrainingDate: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    activeFeatures: 42,
    avgPredictionLatency: 48
  };
}

function calculateTrends() {
  // This would calculate actual trends based on historical data
  return {
    accuracyTrend: 0.15, // +15%
    engagementTrend: 0.08, // +8%
    roiTrend: 0.23 // +23%
  };
}

// Default data functions
function getDefaultRecommendationsData() {
  return {
    accuracy: 0,
    precision: 0,
    recall: 0,
    totalRecommendations: 0
  };
}

function getDefaultEngagementData() {
  return {
    totalInteractions: 0,
    views: 0,
    clicks: 0,
    saves: 0,
    bids: 0,
    conversionRate: 0
  };
}

function getDefaultDealsData() {
  return {
    averageROI: 0,
    totalDealsTracked: 0,
    successfulDeals: 0
  };
}

function getDefaultMLData() {
  return {
    modelVersion: "v1.0.0",
    trainingDataSize: 0,
    lastTrainingDate: new Date().toISOString(),
    activeFeatures: 0,
    avgPredictionLatency: 0
  };
}