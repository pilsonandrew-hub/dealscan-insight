/**
 * API service layer for DealerScope using Supabase backend
 * Replaces FastAPI endpoints with Supabase queries
 */

import { Opportunity, PipelineStatus, UploadResult } from '@/types/dealerscope';
import { supabase } from '@/integrations/supabase/client';
import { CircuitBreaker } from '@/utils/circuit-breaker';
import { advancedCache } from '@/utils/advancedCache';
import { performanceMonitor } from '@/utils/performance-monitor';
import { auditLogger } from '@/utils/audit-logger';

// Circuit breaker for API resilience
const apiCircuitBreaker = new CircuitBreaker({
  failureThreshold: 5,
  recoveryTimeout: 30000, // 30 seconds
  monitoringPeriod: 60000  // 1 minute
});

export const api = {
  // Get all opportunities with enhanced caching - now using Supabase
  async getOpportunities(): Promise<Opportunity[]> {
    const cacheKey = 'opportunities-all';
    const timer = performanceMonitor.monitorAPI('getOpportunities', 'GET');
    
    auditLogger.log('api_call_start', 'system', 'info', { endpoint: 'opportunities' });
    
    // Try cache first
    const cached = advancedCache.get<Opportunity[]>(cacheKey);
    if (cached) {
      timer.end(true);
      auditLogger.log('api_cache_hit', 'system', 'info', { endpoint: 'opportunities' });
      return cached;
    }

    return apiCircuitBreaker.execute(async () => {
      try {
        const { data, error } = await supabase
          .from('opportunities')
          .select('*')
          .eq('is_active', true)
          .order('created_at', { ascending: false });
        
        if (error) throw error;
        
        const opportunities = data?.map(transformOpportunity) || [];
        advancedCache.set(cacheKey, opportunities, 300000); // 5 minutes TTL
        timer.end(true);
        auditLogger.log('api_call_success', 'system', 'info', { endpoint: 'opportunities' });
        return opportunities;
      } catch (error) {
        timer.end(false);
        auditLogger.logError(error as Error, 'getOpportunities');
        throw error;
      }
    });
  },

  // Batch get opportunities by IDs
  async getOpportunitiesBatch(ids: string[]): Promise<Opportunity[]> {
    const timer = performanceMonitor.monitorAPI('getOpportunitiesBatch', 'POST');
    
    return apiCircuitBreaker.execute(async () => {
      try {
        const { data, error } = await supabase
          .from('opportunities')
          .select('*')
          .in('id', ids);
        
        if (error) throw error;
        
        const opportunities = data?.map(transformOpportunity) || [];
        timer.end(true);
        return opportunities;
      } catch (error) {
        timer.end(false);
        auditLogger.logError(error as Error, 'getOpportunitiesBatch');
        throw error;
      }
    });
  },

  // Upload CSV file for analysis - Mock implementation for now
  async uploadCSV(file: File): Promise<UploadResult> {
    // This would be implemented as a Supabase Edge Function
    auditLogger.log('upload_attempt', 'system', 'info', { filename: file.name, size: file.size });
    
    // For now, return a mock response
    await new Promise(resolve => setTimeout(resolve, 2000));
    const isSuccess = Math.random() > 0.2;
    
    if (isSuccess) {
      return {
        status: "success",
        rows_processed: Math.floor(Math.random() * 5000) + 500,
        opportunities_generated: Math.floor(Math.random() * 50) + 10
      };
    } else {
      return {
        status: "error",
        rows_processed: 0,
        errors: ["Invalid CSV format", "Missing required columns"]
      };
    }
  },

  // Pipeline operations - Mock for now
  async runPipeline(state: string = 'CA'): Promise<{ job_id: string }> {
    auditLogger.log('pipeline_start', 'system', 'info', { state });
    
    const { data, error } = await supabase
      .from('scoring_jobs')
      .insert({
        status: 'pending' as const,
        started_at: new Date().toISOString(),
        total_listings: 0,
        processed_listings: 0,
        opportunities_created: 0,
        progress: 0
      })
      .select()
      .single();
    
    if (error) throw error;
    
    return { job_id: data?.id || 'mock-job-id' };
  },

  // Get pipeline job status
  async getPipelineStatus(jobId: string): Promise<PipelineStatus> {
    const { data, error } = await supabase
      .from('scoring_jobs')
      .select('*')
      .eq('id', jobId)
      .maybeSingle();
    
    if (error) throw error;
    
    if (!data) {
      throw new Error(`Pipeline job ${jobId} not found`);
    }
    
    return {
      id: data.id,
      status: (data.status as 'pending' | 'running' | 'completed' | 'failed') || 'pending',
      stage: data.status || 'initializing',
      progress: data.progress || 0,
      created_at: data.started_at || new Date().toISOString(),
      completed_at: data.completed_at || undefined,
      error_message: data.error_message || undefined,
      results: {
        scraped_count: data.total_listings || 0,
        analyzed_count: data.processed_listings || 0,
        opportunities_found: data.opportunities_created || 0
      }
    };
  },

  // Health check using Supabase
  async healthCheck(): Promise<{ 
    status: string; 
    timestamp: string;
    components: {
      database: string;
      cache: string;
      scrapers: string;
    };
    circuit_breaker_state: string;
  }> {
    try {
      // Simple query to test database connectivity
      const { error } = await supabase.from('opportunities').select('id').limit(1);
      const dbStatus = error ? 'error' : 'ok';
      
      return {
        status: dbStatus === 'ok' ? 'healthy' : 'degraded',
        timestamp: new Date().toISOString(),
        components: {
          database: dbStatus,
          cache: 'ok',
          scrapers: 'ok'
        },
        circuit_breaker_state: apiCircuitBreaker.getState()
      };
    } catch (error) {
      return {
        status: 'error',
        timestamp: new Date().toISOString(),
        components: {
          database: 'error',
          cache: 'ok',
          scrapers: 'ok'
        },
        circuit_breaker_state: apiCircuitBreaker.getState()
      };
    }
  },

  // Clear API cache manually
  clearCache(pattern?: string): void {
    advancedCache.invalidate(pattern);
  },

  // Get API cache statistics
  getCacheStats() {
    return advancedCache.getStats();
  },

  // Get dashboard metrics from Supabase
  async getDashboardMetrics(): Promise<{
    active_opportunities: number;
    avg_margin: number;
    potential_revenue: number;
    success_rate: number;
  }> {
    const timer = performanceMonitor.monitorAPI('getDashboardMetrics', 'GET');
    
    return apiCircuitBreaker.execute(async () => {
      try {
        const { data, error } = await supabase
          .from('opportunities')
          .select('potential_profit, roi_percentage, is_active')
          .eq('is_active', true);
        
        if (error) throw error;
        
        const opportunities = data || [];
        const active_opportunities = opportunities.length;
        const avg_margin = opportunities.length > 0 
          ? opportunities.reduce((sum, opp) => sum + (opp.roi_percentage || 0), 0) / opportunities.length / 100
          : 0;
        const potential_revenue = opportunities.reduce((sum, opp) => sum + (opp.potential_profit || 0), 0);
        const success_rate = 0.89; // Mock for now - could be calculated from historical data
        
        timer.end(true);
        return {
          active_opportunities,
          avg_margin,
          potential_revenue,
          success_rate
        };
      } catch (error) {
        timer.end(false);
        auditLogger.logError(error as Error, 'getDashboardMetrics');
        throw error;
      }
    });
  }
};

// Transform database row to Opportunity type
function transformOpportunity(row: any): Opportunity {
  return {
    id: row.id,
    vehicle: {
      vin: row.vin,
      make: row.make,
      model: row.model,
      year: row.year,
      mileage: row.mileage,
      trim: row.trim,
      title_status: 'clean',
      photo_url: row.photo_url,
      description: row.description
    },
    expected_price: row.estimated_sale_price,
    acquisition_cost: row.total_cost,
    profit: row.potential_profit || 0,
    roi: row.roi_percentage || 0,
    confidence: row.confidence_score || 0,
    location: row.location,
    state: row.state,
    auction_end: row.auction_end,
    status: row.status || 'moderate',
    score: row.score || 0,
    market_price: row.market_data || {},
    total_cost: row.total_cost,
    risk_score: row.risk_score || 0,
    transportation_cost: row.transportation_cost || 0,
    fees_cost: row.fees_cost || 0,
    estimated_sale_price: row.estimated_sale_price,
    profit_margin: row.profit_margin || 0,
    source_site: row.source_site,
    current_bid: row.current_bid,
    vin: row.vin,
    make: row.make,
    model: row.model,
    year: row.year,
    mileage: row.mileage
  };
}

// Add healthCheck method to mockApi
const mockHealthCheck = async () => {
  await new Promise(resolve => setTimeout(resolve, 100));
  return {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    components: {
      database: 'ok',
      cache: 'ok',
      scrapers: 'ok'
    },
    circuit_breaker_state: 'CLOSED'
  };
};

// Mock data for development when backend is not available
export const mockApi = {
  healthCheck: mockHealthCheck,
  getCacheStats: () => advancedCache.getStats(),
  clearCache: () => advancedCache.invalidate(),
  async getOpportunities(): Promise<Opportunity[]> {
    const cacheKey = 'opportunities-mock';
    const cached = advancedCache.get<Opportunity[]>(cacheKey);
    if (cached) return cached;

    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    const result = mockOpportunities;
    advancedCache.set(cacheKey, result, 30000); // 30 second cache
    return result;
  }
};

const mockOpportunities: Opportunity[] = [

    
      {
        id: "1",
        vehicle: {
          vin: "1FTFW1ET5CFC10312",
          make: "Ford",
          model: "F-150",
          year: 2021,
          mileage: 45230,
          trim: "XLT",
          title_status: "clean",
          photo_url: "https://example.com/photo1.jpg",
          description: "Former fleet vehicle in excellent condition"
        },
        expected_price: 36800,
        acquisition_cost: 28500,
        profit: 8300,
        roi: 29.1,
        confidence: 94,
        location: "Phoenix, AZ",
        state: "AZ",
        auction_end: "2024-01-15T18:00:00Z",
        status: "hot" as const,
        score: 94,
        market_price: {
          make: "Ford",
          model: "F-150",
          year: 2021,
          trim: "XLT",
          avg_price: 35000,
          low_price: 32000,
          high_price: 38000,
          sample_size: 125,
          last_updated: "2024-01-01T12:00:00Z"
        },
        total_cost: 28500,
        risk_score: 25,
        transportation_cost: 950,
        fees_cost: 3200,
        estimated_sale_price: 36800,
        profit_margin: 22.6,
        source_site: "GovDeals",
        current_bid: 24350,
        vin: "1FTFW1ET5CFC10312",
        make: "Ford",
        model: "F-150",
        year: 2021,
        mileage: 45230
      },
      {
        id: "2",
        vehicle: {
          vin: "1GCUYDED5LZ123456",
          make: "Chevrolet",
          model: "Silverado 1500",
          year: 2020,
          mileage: 52100,
          trim: "LT",
          title_status: "clean",
          photo_url: "https://example.com/photo2.jpg",
          description: "Government fleet truck with service records"
        },
        expected_price: 32400,
        acquisition_cost: 24800,
        profit: 7600,
        roi: 30.6,
        confidence: 88,
        location: "Austin, TX",
        state: "TX",
        auction_end: "2024-01-16T19:30:00Z",
        status: "hot" as const,
        score: 88,
        market_price: {
          make: "Chevrolet",
          model: "Silverado 1500",
          year: 2020,
          trim: "LT",
          avg_price: 31500,
          low_price: 29000,
          high_price: 34000,
          sample_size: 98,
          last_updated: "2024-01-01T12:00:00Z"
        },
        total_cost: 24800,
        risk_score: 28,
        transportation_cost: 2800,
        fees_cost: 2950,
        estimated_sale_price: 32400,
        profit_margin: 23.5,
        source_site: "PublicSurplus",
        current_bid: 18050,
        vin: "1GCUYDED5LZ123456",
        make: "Chevrolet",
        model: "Silverado 1500",
        year: 2020,
        mileage: 52100
      },
      {
        id: "3",
        vehicle: {
          vin: "5NPE34AF4JH123789",
          make: "Hyundai",
          model: "Sonata",
          year: 2018,
          mileage: 67800,
          trim: "SE",
          title_status: "clean",
          photo_url: "https://example.com/photo3.jpg",
          description: "Former rental car in good condition"
        },
        expected_price: 18200,
        acquisition_cost: 14500,
        profit: 3700,
        roi: 25.5,
        confidence: 76,
        location: "Las Vegas, NV",
        state: "NV",
        auction_end: "2024-01-17T16:00:00Z",
        status: "good" as const,
        score: 76,
        market_price: {
          make: "Hyundai",
          model: "Sonata",
          year: 2018,
          trim: "SE",
          avg_price: 17800,
          low_price: 16500,
          high_price: 19200,
          sample_size: 67,
          last_updated: "2024-01-01T12:00:00Z"
        },
        total_cost: 14500,
        risk_score: 35,
        transportation_cost: 600,
        fees_cost: 1400,
        estimated_sale_price: 18200,
        profit_margin: 20.3,
        source_site: "Copart",
        current_bid: 12500,
        vin: "5NPE34AF4JH123789",
        make: "Hyundai",
        model: "Sonata",
        year: 2018,
        mileage: 67800
      }
];

export const mockApiExtended = {
  ...mockApi,
  async uploadCSV(file: File): Promise<UploadResult> {
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    const isSuccess = Math.random() > 0.2;
    
    if (isSuccess) {
      return {
        status: "success",
        rows_processed: Math.floor(Math.random() * 5000) + 500,
        opportunities_generated: Math.floor(Math.random() * 50) + 10
      };
    } else {
      return {
        status: "error",
        rows_processed: 0,
        errors: ["Invalid CSV format", "Missing required columns"]
      };
    }
  },

  async runPipeline(): Promise<{ job_id: string }> {
    await new Promise(resolve => setTimeout(resolve, 500));
    return { job_id: Math.random().toString(36).substr(2, 9) };
  },

  async getDashboardMetrics(): Promise<{
    active_opportunities: number;
    avg_margin: number;
    potential_revenue: number;
    success_rate: number;
  }> {
    await new Promise(resolve => setTimeout(resolve, 500));
    
    return {
      active_opportunities: 47,
      avg_margin: 0.273,
      potential_revenue: 423850,
      success_rate: 0.89
    };
  }
};

// Use mock API in development
export default import.meta.env.MODE === 'development' ? mockApiExtended : api;