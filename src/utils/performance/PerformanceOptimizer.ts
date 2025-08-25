/**
 * PerformanceOptimizer - Core performance optimization utilities
 * Handles lazy loading, memoization, and resource management
 */

import React, { useMemo, useCallback, useRef, useEffect } from 'react';
import { logger } from '@/utils/secureLogger';

// Lazy component loader with error handling
export const createLazyComponent = (importFn: () => Promise<any>) => {
  return React.lazy(() => 
    importFn().catch(error => {
      logger.error('Failed to load component', 'PERFORMANCE', error);
      return { default: () => React.createElement('div', null, 'Component failed to load') };
    })
  );
};

// Debounce hook for API calls
export const useDebounce = <T>(value: T, delay: number): T => {
  const [debouncedValue, setDebouncedValue] = React.useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};

// Throttle hook for scroll events
export const useThrottle = <T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): T => {
  const lastCall = useRef<number>(0);
  
  return useCallback((...args: Parameters<T>) => {
    const now = Date.now();
    if (now - lastCall.current >= delay) {
      lastCall.current = now;
      return callback(...args);
    }
  }, [callback, delay]) as T;
};

// Memoization hook with cache size limit
export const useAdvancedMemo = <T>(
  factory: () => T,
  deps: React.DependencyList,
  cacheSize: number = 10
): T => {
  const cache = useRef<Map<string, T>>(new Map());
  
  const key = useMemo(() => JSON.stringify(deps), deps);
  
  return useMemo(() => {
    if (cache.current.has(key)) {
      return cache.current.get(key)!;
    }
    
    const result = factory();
    
    // Implement LRU cache
    if (cache.current.size >= cacheSize) {
      const firstKey = cache.current.keys().next().value;
      cache.current.delete(firstKey);
    }
    
    cache.current.set(key, result);
    return result;
  }, [key, factory, cacheSize]);
};

// Performance monitoring hook
export const usePerformanceMonitor = (name: string) => {
  const startTime = useRef<number>();
  
  useEffect(() => {
    startTime.current = performance.now();
    
    return () => {
      if (startTime.current) {
        const duration = performance.now() - startTime.current;
        logger.debug(`Performance: ${name} took ${duration.toFixed(2)}ms`);
        
        // Report slow operations
        if (duration > 100) {
          logger.warn(`Slow operation detected: ${name} took ${duration.toFixed(2)}ms`);
        }
      }
    };
  }, [name]);
  
  const mark = useCallback((label: string) => {
    if (startTime.current) {
      const duration = performance.now() - startTime.current;
      logger.debug(`Performance marker: ${name}.${label} at ${duration.toFixed(2)}ms`);
    }
  }, [name]);
  
  return { mark };
};

// Resource cleanup hook
export const useResourceCleanup = () => {
  const resources = useRef<(() => void)[]>([]);
  
  const addCleanup = useCallback((cleanup: () => void) => {
    resources.current.push(cleanup);
  }, []);
  
  useEffect(() => {
    return () => {
      resources.current.forEach(cleanup => {
        try {
          cleanup();
        } catch (error) {
          logger.error('Error during resource cleanup:', error);
        }
      });
    };
  }, []);
  
  return { addCleanup };
};

export default {
  createLazyComponent,
  useDebounce,
  useThrottle,
  useAdvancedMemo,
  usePerformanceMonitor,
  useResourceCleanup
};