/**
 * API Optimization Utilities
 * Implements request deduplication, caching, and retry logic
 */

import { logger } from '@/utils/secureLogger';

interface RequestConfig {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
  timeout?: number;
  retries?: number;
  cache?: boolean;
  dedupe?: boolean;
}

interface CacheEntry {
  data: any;
  timestamp: number;
  expiry: number;
}

class APIOptimizer {
  private static instance: APIOptimizer;
  private cache = new Map<string, CacheEntry>();
  private pendingRequests = new Map<string, Promise<any>>();
  private defaultTimeout = 30000; // 30 seconds
  private maxCacheSize = 100;

  private constructor() {}

  public static getInstance(): APIOptimizer {
    if (!APIOptimizer.instance) {
      APIOptimizer.instance = new APIOptimizer();
    }
    return APIOptimizer.instance;
  }

  public async request(
    url: string, 
    config: RequestConfig = {},
    cacheTTL: number = 300000 // 5 minutes default
  ): Promise<any> {
    const cacheKey = this.generateCacheKey(url, config);
    
    // Check cache first
    if (config.cache !== false) {
      const cached = this.getFromCache(cacheKey);
      if (cached) {
        logger.debug('API cache hit', 'API_OPTIMIZER', { url });
        return cached;
      }
    }

    // Check for pending request (deduplication)
    if (config.dedupe !== false && this.pendingRequests.has(cacheKey)) {
      logger.debug('API request deduplicated', 'API_OPTIMIZER', { url });
      return this.pendingRequests.get(cacheKey)!;
    }

    // Make new request
    const requestPromise = this.makeRequest(url, config, cacheTTL, cacheKey);
    
    if (config.dedupe !== false) {
      this.pendingRequests.set(cacheKey, requestPromise);
    }

    try {
      const result = await requestPromise;
      return result;
    } finally {
      this.pendingRequests.delete(cacheKey);
    }
  }

  private async makeRequest(
    url: string, 
    config: RequestConfig, 
    cacheTTL: number,
    cacheKey: string
  ): Promise<any> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), config.timeout || this.defaultTimeout);

    try {
      const response = await fetch(url, {
        method: config.method || 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...config.headers
        },
        body: config.body ? JSON.stringify(config.body) : undefined,
        signal: controller.signal
      });

      clearTimeout(timeout);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      // Cache successful response
      if (config.cache !== false) {
        this.setCache(cacheKey, data, cacheTTL);
      }

      logger.debug('API request successful', 'API_OPTIMIZER', { 
        url, 
        status: response.status,
        cached: config.cache !== false 
      });

      return data;
    } catch (error) {
      clearTimeout(timeout);
      
      if (error.name === 'AbortError') {
        throw new Error('Request timeout');
      }

      // Retry logic
      const retries = config.retries || 0;
      if (retries > 0) {
        logger.warn('API request failed, retrying', 'API_OPTIMIZER', { 
          url, 
          retriesLeft: retries,
          error: error.message 
        });
        
        await this.delay(1000 * (4 - retries)); // Exponential backoff
        return this.makeRequest(url, { ...config, retries: retries - 1 }, cacheTTL, cacheKey);
      }

      logger.error('API request failed', 'API_OPTIMIZER', { url, error: error.message });
      throw error;
    }
  }

  private generateCacheKey(url: string, config: RequestConfig): string {
    const method = config.method || 'GET';
    const body = config.body ? JSON.stringify(config.body) : '';
    return `${method}:${url}:${body}`;
  }

  private getFromCache(key: string): any | null {
    const entry = this.cache.get(key);
    if (!entry) return null;

    if (Date.now() > entry.expiry) {
      this.cache.delete(key);
      return null;
    }

    return entry.data;
  }

  private setCache(key: string, data: any, ttl: number): void {
    // Cleanup old entries if cache is full
    if (this.cache.size >= this.maxCacheSize) {
      const oldestKey = this.cache.keys().next().value;
      this.cache.delete(oldestKey);
    }

    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      expiry: Date.now() + ttl
    });
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  public clearCache(): void {
    this.cache.clear();
    logger.info('API cache cleared', 'API_OPTIMIZER');
  }

  public getCacheStats(): { size: number; entries: string[] } {
    return {
      size: this.cache.size,
      entries: Array.from(this.cache.keys())
    };
  }

  // Batch request utility
  public async batchRequest(
    requests: Array<{ url: string; config?: RequestConfig }>,
    maxConcurrency: number = 5
  ): Promise<any[]> {
    const results: any[] = [];
    const errors: any[] = [];

    for (let i = 0; i < requests.length; i += maxConcurrency) {
      const batch = requests.slice(i, i + maxConcurrency);
      
      const batchPromises = batch.map(async ({ url, config = {} }, index) => {
        try {
          const result = await this.request(url, config);
          return { index: i + index, result, error: null };
        } catch (error) {
          return { index: i + index, result: null, error };
        }
      });

      const batchResults = await Promise.all(batchPromises);
      
      batchResults.forEach(({ index, result, error }) => {
        if (error) {
          errors.push({ index, error });
        } else {
          results[index] = result;
        }
      });
    }

    if (errors.length > 0) {
      logger.warn('Batch request completed with errors', 'API_OPTIMIZER', { 
        totalRequests: requests.length,
        errors: errors.length 
      });
    }

    return results;
  }
}

// Singleton instance
const apiOptimizer = APIOptimizer.getInstance();

// React hook for optimized API calls
export const useOptimizedAPI = () => {
  const request = async (
    url: string, 
    config: RequestConfig = {},
    cacheTTL?: number
  ) => {
    return apiOptimizer.request(url, config, cacheTTL);
  };

  const batchRequest = async (
    requests: Array<{ url: string; config?: RequestConfig }>,
    maxConcurrency?: number
  ) => {
    return apiOptimizer.batchRequest(requests, maxConcurrency);
  };

  const clearCache = () => {
    apiOptimizer.clearCache();
  };

  const getCacheStats = () => {
    return apiOptimizer.getCacheStats();
  };

  return {
    request,
    batchRequest,
    clearCache,
    getCacheStats
  };
};

export { apiOptimizer, APIOptimizer };
export default useOptimizedAPI;