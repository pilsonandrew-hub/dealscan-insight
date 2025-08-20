import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { dealScoringEngine, type VehicleListing, type DealMetrics } from '@/services/dealScoring';
import { toast } from 'sonner';

interface ScoringJob {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  total_listings: number;
  processed_listings: number;
  opportunities_created: number;
  started_at: string;
  completed_at?: string;
  error_message?: string;
}

interface UseDealScoringReturn {
  isScoring: boolean;
  currentJob: ScoringJob | null;
  scoreAllListings: () => Promise<void>;
  scoreSingleListing: (listingId: string) => Promise<DealMetrics | null>;
  cancelScoring: () => void;
  getJobHistory: () => Promise<ScoringJob[]>;
}

export const useDealScoring = (): UseDealScoringReturn => {
  const [isScoring, setIsScoring] = useState(false);
  const [currentJob, setCurrentJob] = useState<ScoringJob | null>(null);
  const [cancelToken, setCancelToken] = useState<AbortController | null>(null);

  // Real-time subscription for job updates
  useEffect(() => {
    if (!currentJob) return;

    const channel = supabase
      .channel('scoring-job-updates')
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'scoring_jobs',
          filter: `id=eq.${currentJob.id}`
        },
        (payload) => {
          setCurrentJob(payload.new as ScoringJob);
          
          if (payload.new.status === 'completed') {
            setIsScoring(false);
            toast.success('Deal scoring completed!', {
              description: `Created ${payload.new.opportunities_created} opportunities from ${payload.new.processed_listings} listings`
            });
          } else if (payload.new.status === 'failed') {
            setIsScoring(false);
            toast.error('Deal scoring failed', {
              description: payload.new.error_message || 'Unknown error occurred'
            });
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [currentJob?.id]);

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
        .is('scored_at', null)
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

      // Create scoring job record
      const job: Partial<ScoringJob> = {
        status: 'processing',
        progress: 0,
        total_listings: listings.length,
        processed_listings: 0,
        opportunities_created: 0,
        started_at: new Date().toISOString()
      };

      const { data: jobData, error: jobError } = await supabase
        .from('scoring_jobs')
        .insert(job)
        .select()
        .single();

      if (jobError) {
        throw jobError;
      }

      setCurrentJob(jobData);
      
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

                // Mark listing as scored
                await supabase
                  .from('public_listings')
                  .update({ 
                    scored_at: new Date().toISOString(),
                    score_metadata: {
                      estimated_sale_price: metrics.estimated_sale_price,
                      roi_percentage: metrics.roi_percentage,
                      risk_score: metrics.risk_score,
                      confidence_score: metrics.confidence_score
                    }
                  })
                  .eq('id', listing.id);
              }
              
              processedCount++;
            } catch (error) {
              console.error(`Error scoring listing ${listing.id}:`, error);
              processedCount++;
            }
          })
        );

        // Update job progress
        const progress = Math.round((processedCount / listings.length) * 100);
        await supabase
          .from('scoring_jobs')
          .update({
            progress,
            processed_listings: processedCount,
            opportunities_created: opportunitiesCreated
          })
          .eq('id', jobData.id);

        // Small delay to prevent overwhelming the system
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      // Complete the job
      const finalStatus = controller.signal.aborted ? 'cancelled' : 'completed';
      await supabase
        .from('scoring_jobs')
        .update({
          status: finalStatus,
          progress: 100,
          processed_listings: processedCount,
          opportunities_created: opportunitiesCreated,
          completed_at: new Date().toISOString()
        })
        .eq('id', jobData.id);

      if (!controller.signal.aborted) {
        toast.success(`Scoring completed! Created ${opportunitiesCreated} opportunities from ${processedCount} listings`);
      }

    } catch (error) {
      console.error('Error during scoring:', error);
      toast.error('Failed to score listings', {
        description: error instanceof Error ? error.message : 'Unknown error'
      });
      
      if (currentJob) {
        await supabase
          .from('scoring_jobs')
          .update({
            status: 'failed',
            error_message: error instanceof Error ? error.message : 'Unknown error',
            completed_at: new Date().toISOString()
          })
          .eq('id', currentJob.id);
      }
    } finally {
      setIsScoring(false);
      setCancelToken(null);
    }
  }, [currentJob]);

  const scoreSingleListing = useCallback(async (listingId: string): Promise<DealMetrics | null> => {
    try {
      const { data: listing, error } = await supabase
        .from('public_listings')
        .select('*')
        .eq('id', listingId)
        .single();

      if (error || !listing) {
        throw new Error('Listing not found');
      }

      const metrics = await dealScoringEngine.scoreDeal(listing);
      
      if (metrics) {
        // Update listing with score metadata
        await supabase
          .from('public_listings')
          .update({ 
            scored_at: new Date().toISOString(),
            score_metadata: {
              estimated_sale_price: metrics.estimated_sale_price,
              roi_percentage: metrics.roi_percentage,
              risk_score: metrics.risk_score,
              confidence_score: metrics.confidence_score
            }
          })
          .eq('id', listingId);

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

  const getJobHistory = useCallback(async (): Promise<ScoringJob[]> => {
    try {
      const { data, error } = await supabase
        .from('scoring_jobs')
        .select('*')
        .order('started_at', { ascending: false })
        .limit(50);

      if (error) {
        throw error;
      }

      return data || [];
    } catch (error) {
      console.error('Error fetching job history:', error);
      return [];
    }
  }, []);

  return {
    isScoring,
    currentJob,
    scoreAllListings,
    scoreSingleListing,
    cancelScoring,
    getJobHistory
  };
};