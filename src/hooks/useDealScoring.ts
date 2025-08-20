import { useState, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { dealScoringEngine, type VehicleListing, type DealMetrics } from '@/services/dealScoring';
import { toast } from 'sonner';

interface ScoringProgress {
  total: number;
  processed: number;
  opportunities: number;
}

interface UseDealScoringReturn {
  isScoring: boolean;
  progress: ScoringProgress | null;
  scoreAllListings: () => Promise<void>;
  scoreSingleListing: (listingId: string) => Promise<DealMetrics | null>;
  cancelScoring: () => void;
}

export const useDealScoring = (): UseDealScoringReturn => {
  const [isScoring, setIsScoring] = useState(false);
  const [progress, setProgress] = useState<ScoringProgress | null>(null);
  const [cancelToken, setCancelToken] = useState<AbortController | null>(null);

  const scoreAllListings = useCallback(async () => {
    try {
      setIsScoring(true);
      
      // Create abort controller for cancellation
      const controller = new AbortController();
      setCancelToken(controller);

      // Get all unscored listings
      const { data: listings, error: fetchError } = await supabase
        .from('public_listings')
        .select('*')
        .eq('is_active', true)
        .order('created_at', { ascending: false })
        .limit(500); // Process in batches

      if (fetchError) {
        throw fetchError;
      }

      if (!listings || listings.length === 0) {
        toast.info('No new listings to score');
        setIsScoring(false);
        return;
      }

      setProgress({
        total: listings.length,
        processed: 0,
        opportunities: 0
      });
      
      let processedCount = 0;
      let opportunitiesCreated = 0;
      const batchSize = 10; // Process in smaller batches to avoid timeouts

      // Process listings in batches
      for (let i = 0; i < listings.length; i += batchSize) {
        if (controller.signal.aborted) {
          break;
        }

        const batch = listings.slice(i, i + batchSize);
        
        await Promise.all(
          batch.map(async (listing) => {
            try {
              const metrics = await dealScoringEngine.scoreDeal(listing);
              
              if (metrics) {
                const created = await dealScoringEngine.createOpportunityIfProfitable(listing, metrics);
                if (created) {
                  opportunitiesCreated++;
                }
              }
              
              processedCount++;
            } catch (error) {
              console.error(`Error scoring listing ${listing.id}:`, error);
              processedCount++;
            }
          })
        );

        // Update progress
        setProgress({
          total: listings.length,
          processed: processedCount,
          opportunities: opportunitiesCreated
        });

        // Small delay to prevent overwhelming the system
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      if (!controller.signal.aborted) {
        toast.success(`Scoring completed! Created ${opportunitiesCreated} opportunities from ${processedCount} listings`);
      }

    } catch (error) {
      console.error('Error during scoring:', error);
      toast.error('Failed to score listings', {
        description: error instanceof Error ? error.message : 'Unknown error'
      });
    } finally {
      setIsScoring(false);
      setProgress(null);
      setCancelToken(null);
    }
  }, []);

  const scoreSingleListing = useCallback(async (listingId: string): Promise<DealMetrics | null> => {
    try {
      const { data: listing, error } = await supabase
        .from('public_listings')
        .select('*')
        .eq('id', listingId)
        .maybeSingle();

      if (error || !listing) {
        throw new Error('Listing not found');
      }

      const metrics = await dealScoringEngine.scoreDeal(listing);
      
      if (metrics) {
        // Create opportunity if profitable
        await dealScoringEngine.createOpportunityIfProfitable(listing, metrics);
      }

      return metrics;
    } catch (error) {
      console.error('Error scoring single listing:', error);
      toast.error('Failed to score listing');
      return null;
    }
  }, []);

  const cancelScoring = useCallback(() => {
    if (cancelToken) {
      cancelToken.abort();
      toast.info('Scoring cancelled');
    }
  }, [cancelToken]);

  return {
    isScoring,
    progress,
    scoreAllListings,
    scoreSingleListing,
    cancelScoring
  };
};