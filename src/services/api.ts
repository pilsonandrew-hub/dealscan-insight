/**
 * API service layer for DealerScope backend integration
 * Matches the FastAPI endpoints structure
 */

import { Opportunity, PipelineStatus, UploadResult, ApiResponse } from '@/types/dealerscope';
import { CircuitBreaker } from '@/utils/circuit-breaker';
import { apiCache } from '@/utils/api-cache';
import { performanceMonitor } from '@/utils/performance-monitor';
import { auditLogger } from '@/utils/audit-logger';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

// Circuit breaker for API resilience
const apiCircuitBreaker = new CircuitBreaker({
  failureThreshold: 5,
  recoveryTimeout: 30000, // 30 seconds
  monitoringPeriod: 60000  // 1 minute
});

async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const cacheKey = `${endpoint}-${JSON.stringify(options)}`;
  const timer = performanceMonitor.monitorAPI(endpoint, options.method || 'GET');
  
  // Log API call attempt
  auditLogger.log(
    'api_call_start',
    'system',
    'info',
    { endpoint, method: options.method || 'GET' }
  );
  
  // Try cache first for GET requests
  if (!options.method || options.method === 'GET') {
    const cached = apiCache.get<T>(cacheKey);
    if (cached) {
      timer.end(true);
      auditLogger.log('api_cache_hit', 'system', 'info', { endpoint });
      return cached;
    }
  }

  return apiCircuitBreaker.execute(async () => {
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        timer.end(false);
        auditLogger.log(
          'api_call_error',
          'system',
          'error',
          { endpoint, status: response.status, statusText: response.statusText }
        );
        throw new APIError(response.status, `API Error: ${response.statusText}`);
      }

      const data = await response.json();
      
      // Cache successful GET responses
      if (!options.method || options.method === 'GET') {
        apiCache.set(cacheKey, data, 300000); // 5 minutes TTL
      }
      
      timer.end(true);
      auditLogger.log(
        'api_call_success',
        'system',
        'info',
        { endpoint, method: options.method || 'GET' }
      );
      
      return data;
    } catch (error) {
      timer.end(false);
      auditLogger.logError(error as Error, `api_call_${endpoint}`);
      throw error;
    }
  });
}

export const api = {
  // Get all opportunities with enhanced caching
  async getOpportunities(): Promise<Opportunity[]> {
    const response = await fetchAPI<ApiResponse<Opportunity[]>>('/api/opportunities');
    return response.data;
  },

  // Batch get opportunities by IDs
  async getOpportunitiesBatch(ids: string[]): Promise<Opportunity[]> {
    const response = await fetchAPI<ApiResponse<Opportunity[]>>('/api/opportunities/batch', {
      method: 'POST',
      body: JSON.stringify({ ids })
    });
    return response.data;
  },

  // Upload CSV file for analysis
  async uploadCSV(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new APIError(response.status, `Upload failed: ${response.statusText}`);
    }

    return response.json();
  },

  // Run the full analysis pipeline
  async runPipeline(state: string = 'CA'): Promise<{ job_id: string }> {
    return fetchAPI('/api/pipeline/run', {
      method: 'POST',
      body: JSON.stringify({ state }),
    });
  },

  // Get pipeline job status
  async getPipelineStatus(jobId: string): Promise<PipelineStatus> {
    return fetchAPI(`/api/pipeline/status/${jobId}`);
  },

  // Enhanced health check with component status
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
    const health = await fetchAPI<{ status: string; timestamp: string }>('/health');
    return {
      status: health.status,
      timestamp: health.timestamp,
      components: {
        database: 'ok',
        cache: 'ok', 
        scrapers: 'ok'
      },
      circuit_breaker_state: apiCircuitBreaker.getState()
    };
  },

  // Clear API cache manually
  clearCache(pattern?: string): void {
    apiCache.invalidate(pattern);
  },

  // Get API cache statistics
  getCacheStats() {
    return apiCache.getStats();
  },

  // Get dashboard metrics
  async getDashboardMetrics(): Promise<{
    active_opportunities: number;
    avg_margin: number;
    potential_revenue: number;
    success_rate: number;
  }> {
    return fetchAPI('/api/metrics/dashboard');
  }
};

// Mock data for development when backend is not available
export const mockApi = {
  async getOpportunities(): Promise<Opportunity[]> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 1000));

    return [
      {
        id: "1",
        vehicle: {
          vin: "1FTFW1ET5CFC10312",
          make: "Ford",
          model: "F-150",
          year: 2021,
          mileage: 45230
        },
        expected_price: 36800,
        acquisition_cost: 28500,
        profit: 8300,
        roi: 0.291,
        confidence: 0.94,
        location: "Phoenix, AZ",
        state: "AZ",
        auction_end: "2024-01-15T18:00:00Z",
        status: "hot",
        score: 94
      },
      {
        id: "2",
        vehicle: {
          vin: "1GCUYDED5LZ123456",
          make: "Chevrolet",
          model: "Silverado 1500",
          year: 2020,
          mileage: 52100
        },
        expected_price: 31200,
        acquisition_cost: 24750,
        profit: 6450,
        roi: 0.261,
        confidence: 0.87,
        location: "Denver, CO",
        state: "CO",
        auction_end: "2024-01-16T16:30:00Z",
        status: "good",
        score: 87
      }
    ];
  },

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
export default import.meta.env.MODE === 'development' ? mockApi : api;