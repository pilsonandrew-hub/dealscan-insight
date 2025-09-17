import { useState, useEffect, useCallback } from 'react';
import { roverAPI, RoverRecommendations, DealItem } from '@/services/roverAPI';
import { useToast } from '@/hooks/use-toast';

interface UseRoverRecommendationsProps {
  enabled: boolean;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export const useRoverRecommendations = ({ 
  enabled, 
  autoRefresh = true, 
  refreshInterval = 5 * 60 * 1000 // 5 minutes
}: UseRoverRecommendationsProps) => {
  const [recommendations, setRecommendations] = useState<RoverRecommendations | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const { toast } = useToast();

  const fetchRecommendations = useCallback(async (silent = false) => {
    if (!enabled) return;

    try {
      if (!silent) setLoading(true);
      setError(null);

      const recs = await roverAPI.getRecommendations();
      setRecommendations(recs);
      setLastUpdate(Date.now());

      if (!silent && recs.items.length > 0) {
        toast({
          title: "Rover updated",
          description: `Found ${recs.items.length} premium opportunities`,
        });
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load recommendations';
      setError(errorMessage);
      
      if (!silent) {
        toast({
          title: "Failed to update Rover",
          description: errorMessage,
          variant: "destructive"
        });
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [enabled, toast]);

  // Track item interactions
  const trackInteraction = useCallback(async (item: DealItem, eventType: 'view' | 'click' | 'save' | 'bid') => {
    try {
      await roverAPI.trackEvent({
        userId: 'current_user',
        event: eventType,
        item
      });

      // Refresh recommendations after significant interactions
      if (eventType === 'save' || eventType === 'bid') {
        setTimeout(() => fetchRecommendations(true), 1000);
      }
    } catch (error) {
      console.error('Failed to track interaction:', error);
    }
  }, [fetchRecommendations]);

  // Initial load
  useEffect(() => {
    if (enabled) {
      fetchRecommendations();
    }
  }, [enabled, fetchRecommendations]);

  // Auto refresh
  useEffect(() => {
    if (!enabled || !autoRefresh) return;

    const interval = setInterval(() => {
      fetchRecommendations(true);
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [enabled, autoRefresh, refreshInterval, fetchRecommendations]);

  const refresh = useCallback(() => {
    fetchRecommendations();
  }, [fetchRecommendations]);

  return {
    recommendations,
    loading,
    error,
    lastUpdate,
    refresh,
    trackInteraction,
    isStale: lastUpdate ? (Date.now() - lastUpdate > refreshInterval) : false
  };
};