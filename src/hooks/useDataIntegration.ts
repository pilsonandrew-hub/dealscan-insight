import { useState, useCallback, useEffect } from 'react';
import { manheimAPI } from '@/services/manheimAPI';
import { govAuctionScraper } from '@/services/govAuctionScraper';
import { supabase } from '@/integrations/supabase/client';
import { useToast } from '@/hooks/use-toast';

export interface IntegrationStatus {
  manheim: {
    connected: boolean;
    lastSync: string | null;
    status: string;
  };
  scrapers: {
    running: boolean;
    lastRun: string | null;
    availableScrapers: number;
  };
  database: {
    connected: boolean;
    recordCount: number;
    lastUpdate: string | null;
  };
}

export interface DataSyncResult {
  success: boolean;
  recordsProcessed: number;
  opportunitiesCreated: number;
  errors: string[];
  duration: number;
}

export function useDataIntegration() {
  const [status, setStatus] = useState<IntegrationStatus>({
    manheim: { connected: false, lastSync: null, status: 'disconnected' },
    scrapers: { running: false, lastRun: null, availableScrapers: 0 },
    database: { connected: false, recordCount: 0, lastUpdate: null }
  });
  
  const [isLoading, setIsLoading] = useState(false);
  const [syncInProgress, setSyncInProgress] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    checkIntegrationStatus();
    
    // Refresh status every 30 seconds
    const interval = setInterval(checkIntegrationStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const checkIntegrationStatus = useCallback(async () => {
    try {
      // Check Manheim API status
      const manheimConnected = await manheimAPI.validateConnection();
      const manheimStatus = manheimAPI.getConnectionStatus();

      // Check scraper status
      const scrapingStatus = govAuctionScraper.getScrapingStatus();
      const availableScrapers = await govAuctionScraper.getAvailableScrapers();

      // Check database status
      const { count } = await supabase
        .from('opportunities')
        .select('*', { count: 'exact', head: true });

      const { data: lastOpportunity } = await supabase
        .from('opportunities')
        .select('created_at')
        .order('created_at', { ascending: false })
        .limit(1)
        .single();

      setStatus({
        manheim: {
          connected: manheimConnected,
          lastSync: manheimStatus.lastUpdate,
          status: manheimConnected ? 'connected' : 'disconnected'
        },
        scrapers: {
          running: scrapingStatus.isRunning,
          lastRun: null, // Would track from database
          availableScrapers: availableScrapers.length
        },
        database: {
          connected: true,
          recordCount: count || 0,
          lastUpdate: lastOpportunity?.created_at || null
        }
      });
    } catch (error) {
      console.error('Failed to check integration status:', error);
    }
  }, []);

  const syncManheimData = useCallback(async (): Promise<DataSyncResult> => {
    const startTime = Date.now();
    setIsLoading(true);
    setSyncInProgress(true);

    try {
      // Fetch latest auction listings from Manheim
      const listings = await manheimAPI.fetchAuctionListings({
        yearMin: new Date().getFullYear() - 10,
        yearMax: new Date().getFullYear()
      });

      let opportunitiesCreated = 0;
      const errors: string[] = [];

      // Process each listing for opportunities
      for (const listing of listings) {
        try {
          const marketData = await manheimAPI.fetchMarketValue(listing.vin);
          
          if (marketData) {
            // Create opportunity if profitable
            const profit = marketData.mmr - listing.salePrice;
            const roi = (profit / listing.salePrice) * 100;

            if (profit > 2000 && roi > 15) {
              await supabase
                .from('opportunities')
                .insert({
                  make: listing.make,
                  model: listing.model,
                  year: listing.year,
                  mileage: listing.mileage,
                  vin: listing.vin,
                  current_bid: listing.salePrice,
                  estimated_sale_price: marketData.mmr,
                  total_cost: listing.salePrice * 1.15, // Add fees
                  potential_profit: profit,
                  roi_percentage: roi,
                  risk_score: 30, // Calculate based on condition
                  confidence_score: 80, // Manheim data is reliable
                  transportation_cost: 1000, // Estimate
                  fees_cost: listing.salePrice * 0.15,
                  profit_margin: (profit / marketData.mmr) * 100,
                  source_site: 'Manheim',
                  location: listing.location,
                  status: roi > 25 ? 'hot' : roi > 20 ? 'good' : 'moderate'
                });

              opportunitiesCreated++;
            }
          }
        } catch (error) {
          errors.push(`Failed to process listing ${listing.vin}: ${error}`);
        }
      }

      const duration = Date.now() - startTime;
      
      toast({
        title: "Manheim Sync Complete",
        description: `Processed ${listings.length} listings, created ${opportunitiesCreated} opportunities`
      });

      await checkIntegrationStatus();

      return {
        success: true,
        recordsProcessed: listings.length,
        opportunitiesCreated,
        errors,
        duration
      };

    } catch (error) {
      const duration = Date.now() - startTime;
      toast({
        title: "Sync Failed",
        description: `Manheim sync failed: ${error}`,
        variant: "destructive"
      });

      return {
        success: false,
        recordsProcessed: 0,
        opportunitiesCreated: 0,
        errors: [error.toString()],
        duration
      };
    } finally {
      setIsLoading(false);
      setSyncInProgress(false);
    }
  }, [toast, checkIntegrationStatus]);

  const startAuctionScraping = useCallback(async (sites: string[] = ['govdeals', 'publicsurplus']): Promise<string> => {
    try {
      const jobId = await govAuctionScraper.startScraping(sites);
      
      toast({
        title: "Scraping Started",
        description: `Started scraping ${sites.join(', ')}`
      });

      await checkIntegrationStatus();
      return jobId;
    } catch (error) {
      toast({
        title: "Scraping Failed",
        description: `Failed to start scraping: ${error}`,
        variant: "destructive"
      });
      throw error;
    }
  }, [toast, checkIntegrationStatus]);

  const stopAuctionScraping = useCallback(async (): Promise<void> => {
    try {
      await govAuctionScraper.cancelScraping();
      
      toast({
        title: "Scraping Stopped",
        description: "Auction scraping has been cancelled"
      });

      await checkIntegrationStatus();
    } catch (error) {
      toast({
        title: "Stop Failed",
        description: `Failed to stop scraping: ${error}`,
        variant: "destructive"
      });
    }
  }, [toast, checkIntegrationStatus]);

  const uploadPostSaleReport = useCallback(async (file: File): Promise<DataSyncResult> => {
    const startTime = Date.now();
    setIsLoading(true);

    try {
      const result = await manheimAPI.processPostSaleReport(file);
      const duration = Date.now() - startTime;

      toast({
        title: "Upload Complete",
        description: `Processed ${result.processed} records, found ${result.opportunities} opportunities`
      });

      await checkIntegrationStatus();

      return {
        success: true,
        recordsProcessed: result.processed,
        opportunitiesCreated: result.opportunities,
        errors: result.errors,
        duration
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      toast({
        title: "Upload Failed",
        description: `Failed to process file: ${error}`,
        variant: "destructive"
      });

      return {
        success: false,
        recordsProcessed: 0,
        opportunitiesCreated: 0,
        errors: [error.toString()],
        duration
      };
    } finally {
      setIsLoading(false);
    }
  }, [toast, checkIntegrationStatus]);

  const refreshData = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      await checkIntegrationStatus();
      toast({
        title: "Data Refreshed",
        description: "Integration status updated"
      });
    } catch (error) {
      toast({
        title: "Refresh Failed",
        description: `Failed to refresh data: ${error}`,
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast, checkIntegrationStatus]);

  const getScrapingJobStatus = useCallback(async (jobId: string) => {
    try {
      return await govAuctionScraper.getJobStatus(jobId);
    } catch (error) {
      console.error('Failed to get job status:', error);
      return null;
    }
  }, []);

  return {
    status,
    isLoading,
    syncInProgress,
    syncManheimData,
    startAuctionScraping,
    stopAuctionScraping,
    uploadPostSaleReport,
    refreshData,
    getScrapingJobStatus,
    checkIntegrationStatus
  };
}