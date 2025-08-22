/**
 * Performance Optimization Utilities
 * Implements lazy loading, memoization, and resource management
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

// Memoized selector hook
export const useMemoizedSelector = <T, R>(
  data: T,
  selector: (data: T) => R,
  deps: readonly unknown[] = []
): R => {
  return useMemo(() => selector(data), [data, ...deps]);
};

// Resource preloader
export class ResourcePreloader {
  private static cache = new Map<string, Promise<any>>();
  
  static preloadImage(src: string): Promise<HTMLImageElement> {
    if (this.cache.has(src)) {
      return this.cache.get(src)!;
    }
    
    const promise = new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
    
    this.cache.set(src, promise);
    return promise;
  }
  
  static preloadComponent(loader: () => Promise<any>): Promise<any> {
    const key = loader.toString();
    if (this.cache.has(key)) {
      return this.cache.get(key)!;
    }
    
    const promise = loader();
    this.cache.set(key, promise);
    return promise;
  }
}

// Intersection Observer hook for lazy loading
export const useIntersectionObserver = (
  options: IntersectionObserverInit = {}
) => {
  const [entry, setEntry] = React.useState<IntersectionObserverEntry>();
  const [node, setNode] = React.useState<Element | null>(null);

  const observer = useMemo(() => {
    if (typeof window === 'undefined' || !window.IntersectionObserver) {
      return null;
    }
    
    return new IntersectionObserver(([entry]) => setEntry(entry), {
      threshold: 0.1,
      rootMargin: '50px',
      ...options,
    });
  }, [options.threshold, options.root, options.rootMargin]);

  useEffect(() => {
    if (!observer || !node) return;

    observer.observe(node);
    return () => observer.disconnect();
  }, [observer, node]);

  return [setNode, entry] as const;
};

// Memory usage monitor
export class MemoryMonitor {
  private static checkInterval: number | null = null;
  
  static startMonitoring(intervalMs: number = 30000) {
    if (this.checkInterval) return;
    
    this.checkInterval = window.setInterval(() => {
      if ('memory' in performance) {
        const memory = (performance as any).memory;
        const usage = {
          usedJSHeapSize: memory.usedJSHeapSize,
          totalJSHeapSize: memory.totalJSHeapSize,
          jsHeapSizeLimit: memory.jsHeapSizeLimit,
          usagePercent: (memory.usedJSHeapSize / memory.jsHeapSizeLimit) * 100
        };
        
        if (usage.usagePercent > 80) {
          logger.warn('High memory usage detected', 'PERFORMANCE', usage);
        }
        
        logger.debug('Memory usage', 'PERFORMANCE', usage);
      }
    }, intervalMs);
  }
  
  static stopMonitoring() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }
}

// Batch processor for API calls
export class BatchProcessor<T> {
  private items: T[] = [];
  private timeout: number | null = null;
  
  constructor(
    private processor: (items: T[]) => Promise<void>,
    private batchSize: number = 10,
    private delay: number = 1000
  ) {}
  
  add(item: T): void {
    this.items.push(item);
    
    if (this.items.length >= this.batchSize) {
      this.flush();
    } else if (!this.timeout) {
      this.timeout = window.setTimeout(() => this.flush(), this.delay);
    }
  }
  
  private async flush(): Promise<void> {
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    
    if (this.items.length === 0) return;
    
    const itemsToProcess = [...this.items];
    this.items = [];
    
    try {
      await this.processor(itemsToProcess);
    } catch (error) {
      logger.error('Batch processing failed', 'PERFORMANCE', error);
    }
  }
}

// Smart cache with TTL and size limits
export class SmartCache<T> {
  private cache = new Map<string, { value: T; expiry: number; accessCount: number }>();
  private maxSize: number;
  private defaultTTL: number;
  
  constructor(maxSize: number = 100, defaultTTL: number = 300000) { // 5 minutes
    this.maxSize = maxSize;
    this.defaultTTL = defaultTTL;
  }
  
  set(key: string, value: T, ttl: number = this.defaultTTL): void {
    this.cleanup();
    
    if (this.cache.size >= this.maxSize) {
      this.evictLRU();
    }
    
    this.cache.set(key, {
      value,
      expiry: Date.now() + ttl,
      accessCount: 0
    });
  }
  
  get(key: string): T | null {
    const item = this.cache.get(key);
    
    if (!item || item.expiry < Date.now()) {
      this.cache.delete(key);
      return null;
    }
    
    item.accessCount++;
    return item.value;
  }
  
  private cleanup(): void {
    const now = Date.now();
    for (const [key, item] of this.cache.entries()) {
      if (item.expiry < now) {
        this.cache.delete(key);
      }
    }
  }
  
  private evictLRU(): void {
    let lruKey: string | null = null;
    let lruAccessCount = Infinity;
    
    for (const [key, item] of this.cache.entries()) {
      if (item.accessCount < lruAccessCount) {
        lruAccessCount = item.accessCount;
        lruKey = key;
      }
    }
    
    if (lruKey) {
      this.cache.delete(lruKey);
    }
  }
}

export default {
  createLazyComponent,
  useDebounce,
  useThrottle,
  useMemoizedSelector,
  useIntersectionObserver,
  ResourcePreloader,
  MemoryMonitor,
  BatchProcessor,
  SmartCache
};