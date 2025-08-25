/**
 * Async Helpers - Fix common async patterns and avoid event loop churn
 * Addresses broken async generator handling and improves concurrency control
 */

import { logger } from '@/lib/logger';

/**
 * Safely execute concurrent async operations with proper error handling
 * Replaces problematic Promise.all usage patterns
 */
export async function safeConcurrentExecution<T, R>(
  items: T[],
  processor: (item: T, index: number) => Promise<R>,
  options: {
    concurrency?: number;
    continueOnError?: boolean;
    timeout?: number;
  } = {}
): Promise<{ results: R[]; errors: Array<{ index: number; error: any }> }> {
  const { concurrency = 10, continueOnError = true, timeout = 30000 } = options;
  
  const results: R[] = new Array(items.length);
  const errors: Array<{ index: number; error: any }> = [];
  
  // Process in batches to control concurrency
  for (let i = 0; i < items.length; i += concurrency) {
    const batch = items.slice(i, i + concurrency);
    const batchPromises = batch.map(async (item, batchIndex) => {
      const globalIndex = i + batchIndex;
      try {
        // Add timeout wrapper
        const timeoutPromise = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('Operation timeout')), timeout);
        });
        
        const result = await Promise.race([
          processor(item, globalIndex),
          timeoutPromise
        ]);
        
        results[globalIndex] = result;
        return { index: globalIndex, result, error: null };
      } catch (error) {
        const errorInfo = { index: globalIndex, error };
        errors.push(errorInfo);
        
        if (!continueOnError) {
          throw error;
        }
        
        return errorInfo;
      }
    });
    
    try {
      await Promise.allSettled(batchPromises);
    } catch (error) {
      if (!continueOnError) {
        throw error;
      }
    }
  }
  
  return { results: results.filter(r => r !== undefined), errors };
}

/**
 * Async generator consumer that buffers results before batch processing
 * Fixes the async generator + gather anti-pattern
 */
export async function consumeAsyncGenerator<T>(
  generator: AsyncGenerator<T>,
  options: {
    batchSize?: number;
    timeout?: number;
    onBatch?: (batch: T[]) => Promise<void>;
  } = {}
): Promise<T[]> {
  const { batchSize = 100, timeout = 30000, onBatch } = options;
  const results: T[] = [];
  let batch: T[] = [];
  
  const timeoutPromise = new Promise<never>((_, reject) => {
    setTimeout(() => reject(new Error('Generator consumption timeout')), timeout);
  });
  
  try {
    for await (const item of generator) {
      batch.push(item);
      
      if (batch.length >= batchSize) {
        if (onBatch) {
          await onBatch([...batch]);
        }
        results.push(...batch);
        batch = [];
      }
    }
    
    // Handle remaining items
    if (batch.length > 0) {
      if (onBatch) {
        await onBatch([...batch]);
      }
      results.push(...batch);
    }
    
    return results;
  } catch (error) {
    logger.error('Error consuming async generator', { error, resultsCount: results.length });
    throw error;
  }
}

/**
 * Fetch multiple URLs with proper concurrency and error handling
 * Replaces problematic async generator patterns in scraping
 */
export async function fetchMultipleUrls(
  urls: string[],
  options: {
    concurrency?: number;
    timeout?: number;
    retries?: number;
    headers?: Record<string, string>;
  } = {}
): Promise<Array<{ url: string; content: string | null; error: string | null }>> {
  const { concurrency = 5, timeout = 15000, retries = 2, headers = {} } = options;
  
  const fetchSingle = async (url: string): Promise<string> => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; DealerScope/1.0)',
          ...headers
        }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      return await response.text();
    } finally {
      clearTimeout(timeoutId);
    }
  };
  
  const fetchWithRetry = async (url: string): Promise<{ url: string; content: string | null; error: string | null }> => {
    let lastError: Error | null = null;
    
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const content = await fetchSingle(url);
        return { url, content, error: null };
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        if (attempt < retries) {
          // Exponential backoff
          await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        }
      }
    }
    
    return { 
      url, 
      content: null, 
      error: lastError?.message || 'Unknown error' 
    };
  };
  
  const { results } = await safeConcurrentExecution(
    urls,
    fetchWithRetry,
    { concurrency, continueOnError: true }
  );
  
  return results;
}

/**
 * Environment validation helper - prevents runtime crashes
 */
export function validateRequiredEnv(requiredVars: string[]): void {
  const missing = requiredVars.filter(varName => !process.env[varName]);
  
  if (missing.length > 0) {
    const errorMsg = `Missing required environment variables: ${missing.join(', ')}`;
    logger.error(errorMsg);
    throw new Error(errorMsg);
  }
}

/**
 * Safe async operation wrapper with timeout and error boundaries
 */
export async function safeAsyncOperation<T>(
  operation: () => Promise<T>,
  options: {
    timeout?: number;
    retries?: number;
    fallback?: T;
    errorHandler?: (error: any) => void;
  } = {}
): Promise<T> {
  const { timeout = 30000, retries = 0, fallback, errorHandler } = options;
  
  let lastError: any;
  
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('Operation timeout')), timeout);
      });
      
      return await Promise.race([operation(), timeoutPromise]);
    } catch (error) {
      lastError = error;
      
      if (errorHandler) {
        errorHandler(error);
      }
      
      if (attempt < retries) {
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
      }
    }
  }
  
  if (fallback !== undefined) {
    logger.warn('Operation failed, using fallback', { error: lastError });
    return fallback;
  }
  
  throw lastError;
}