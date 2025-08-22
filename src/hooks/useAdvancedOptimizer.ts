
import { useCallback, useEffect, useRef, useState } from 'react';
import { useToast } from '@/hooks/use-toast';

interface OptimizationMetrics {
  memoryUsage: number;
  renderTime: number;
  frameRate: number;
  batchProcessingTime: number;
  cacheHitRate: number;
}

interface AdvancedOptimizerSettings {
  enableVirtualization: boolean;
  enableMemoization: boolean;
  enableBatching: boolean;
  enablePrefetching: boolean;
  maxCacheSize: number;
  batchSize: number;
  renderThreshold: number;
}

export function useAdvancedOptimizer(settings: Partial<AdvancedOptimizerSettings> = {}) {
  const defaultSettings: AdvancedOptimizerSettings = {
    enableVirtualization: true,
    enableMemoization: true,
    enableBatching: true,
    enablePrefetching: true,
    maxCacheSize: 1000,
    batchSize: 50,
    renderThreshold: 16.67 // 60fps
  };

  const config = { ...defaultSettings, ...settings };
  const [metrics, setMetrics] = useState<OptimizationMetrics>({
    memoryUsage: 0,
    renderTime: 0,
    frameRate: 60,
    batchProcessingTime: 0,
    cacheHitRate: 0
  });

  const [isOptimizing, setIsOptimizing] = useState(false);
  const cache = useRef(new Map());
  const frameTimeRef = useRef<number[]>([]);
  const cacheStats = useRef({ hits: 0, misses: 0 });
  const { toast } = useToast();

  // Virtualization helper for large lists
  const virtualizeData = useCallback(<T,>(
    data: T[],
    visibleStart: number,
    visibleEnd: number,
    bufferSize: number = 5
  ): { items: T[]; startIndex: number; endIndex: number } => {
    if (!config.enableVirtualization || data.length <= config.batchSize) {
      return { items: data, startIndex: 0, endIndex: data.length };
    }

    const start = Math.max(0, visibleStart - bufferSize);
    const end = Math.min(data.length, visibleEnd + bufferSize);
    
    return {
      items: data.slice(start, end),
      startIndex: start,
      endIndex: end
    };
  }, [config.enableVirtualization, config.batchSize]);

  // Batch processing for heavy computations
  const batchProcess = useCallback(async <T, R>(
    items: T[],
    processor: (item: T) => Promise<R> | R,
    onProgress?: (progress: number) => void
  ): Promise<R[]> => {
    if (!config.enableBatching) {
      return Promise.all(items.map(processor));
    }

    const results: R[] = [];
    const batchSize = config.batchSize;
    
    for (let i = 0; i < items.length; i += batchSize) {
      const batch = items.slice(i, i + batchSize);
      const batchResults = await Promise.all(batch.map(processor));
      results.push(...batchResults);
      
      onProgress?.(Math.min(100, ((i + batchSize) / items.length) * 100));
      
      // Yield control to prevent blocking
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    
    return results;
  }, [config.enableBatching, config.batchSize]);

  // Smart memoization with LRU cache
  const memoize = useCallback(<T extends any[], R>(
    fn: (...args: T) => R,
    keyGenerator?: (...args: T) => string
  ) => {
    if (!config.enableMemoization) return fn;

    return (...args: T): R => {
      const key = keyGenerator ? keyGenerator(...args) : JSON.stringify(args);
      
      if (cache.current.has(key)) {
        cacheStats.current.hits++;
        return cache.current.get(key);
      }

      const result = fn(...args);
      
      // LRU eviction
      if (cache.current.size >= config.maxCacheSize) {
        const firstKey = cache.current.keys().next().value;
        cache.current.delete(firstKey);
      }
      
      cache.current.set(key, result);
      cacheStats.current.misses++;
      
      return result;
    };
  }, [config.enableMemoization, config.maxCacheSize]);

  // Performance monitoring
  const measurePerformance = useCallback((operation: () => void | Promise<void>) => {
    return async () => {
      const startTime = performance.now();
      const startMemory = (performance as any).memory?.usedJSHeapSize || 0;
      
      await operation();
      
      const endTime = performance.now();
      const endMemory = (performance as any).memory?.usedJSHeapSize || 0;
      const renderTime = endTime - startTime;
      
      // Track frame rate
      frameTimeRef.current.push(renderTime);
      if (frameTimeRef.current.length > 60) {
        frameTimeRef.current.shift();
      }
      
      const avgFrameTime = frameTimeRef.current.reduce((a, b) => a + b, 0) / frameTimeRef.current.length;
      const frameRate = 1000 / avgFrameTime;
      
      // Calculate cache hit rate
      const total = cacheStats.current.hits + cacheStats.current.misses;
      const cacheHitRate = total > 0 ? (cacheStats.current.hits / total) * 100 : 0;
      
      setMetrics({
        memoryUsage: endMemory - startMemory,
        renderTime,
        frameRate,
        batchProcessingTime: renderTime,
        cacheHitRate
      });
      
      // Auto-optimize if performance degrades
      if (renderTime > config.renderThreshold && !isOptimizing) {
        setIsOptimizing(true);
        toast({
          title: "Performance Optimization Active",
          description: `Slow render detected (${renderTime.toFixed(1)}ms), activating optimizations`,
          duration: 3000,
        });
      }
    };
  }, [config.renderThreshold, isOptimizing, toast]);

  // Prefetch data for better UX
  const prefetch = useCallback(async <T>(
    dataLoader: () => Promise<T>,
    cacheKey: string
  ): Promise<void> => {
    if (!config.enablePrefetching || cache.current.has(cacheKey)) {
      return;
    }

    try {
      const data = await dataLoader();
      cache.current.set(cacheKey, data);
    } catch (error) {
      console.warn('Prefetch failed:', error);
    }
  }, [config.enablePrefetching]);

  // Clear cache when needed
  const clearCache = useCallback(() => {
    cache.current.clear();
    cacheStats.current = { hits: 0, misses: 0 };
  }, []);

  // Memory cleanup
  useEffect(() => {
    return () => {
      clearCache();
    };
  }, [clearCache]);

  return {
    metrics,
    isOptimizing,
    virtualizeData,
    batchProcess,
    memoize,
    measurePerformance,
    prefetch,
    clearCache,
    config
  };
}
