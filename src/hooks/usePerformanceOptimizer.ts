/**
 * Performance optimizer hook for large datasets and real-time updates
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useToast } from '@/hooks/use-toast';

interface PerformanceMetrics {
  renderTime: number;
  memoryUsage: number;
  updateFrequency: number;
  lastUpdate: number;
}

interface OptimizationSettings {
  maxRenderItems?: number;
  throttleDelay?: number;
  enableVirtualization?: boolean;
  enableMemoization?: boolean;
  enableLazyLoading?: boolean;
}

export function usePerformanceOptimizer(
  settings: OptimizationSettings = {}
) {
  const {
    maxRenderItems = 100,
    throttleDelay = 100,
    enableVirtualization = true,
    enableMemoization = true,
    enableLazyLoading = true
  } = settings;

  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    renderTime: 0,
    memoryUsage: 0,
    updateFrequency: 0,
    lastUpdate: Date.now()
  });

  const [isOptimized, setIsOptimized] = useState(false);
  const renderStartTime = useRef<number>(0);
  const updateCount = useRef<number>(0);
  const throttleTimeout = useRef<NodeJS.Timeout>();
  const { toast } = useToast();

  // Performance monitoring
  const startRenderTimer = useCallback(() => {
    renderStartTime.current = performance.now();
  }, []);

  const endRenderTimer = useCallback(() => {
    const renderTime = performance.now() - renderStartTime.current;
    const now = Date.now();
    
    setMetrics(prev => ({
      renderTime,
      memoryUsage: (performance as any).memory?.usedJSHeapSize || 0,
      updateFrequency: updateCount.current / Math.max((now - prev.lastUpdate) / 1000, 1),
      lastUpdate: now
    }));

    updateCount.current++;

    // Auto-optimize if performance degrades
    if (renderTime > 100 && !isOptimized) {
      setIsOptimized(true);
      toast({
        title: "Performance Optimization Enabled",
        description: "Large dataset detected, optimizations activated",
        duration: 3000,
      });
    }
  }, [isOptimized, toast]);

  // Throttled update function
  const throttledUpdate = useCallback((updateFn: () => void) => {
    if (throttleTimeout.current) {
      clearTimeout(throttleTimeout.current);
    }
    
    throttleTimeout.current = setTimeout(() => {
      updateFn();
    }, throttleDelay);
  }, [throttleDelay]);

  // Virtualization helper
  const getVisibleItems = useCallback(<T,>(
    items: T[],
    startIndex: number = 0,
    endIndex?: number
  ): T[] => {
    if (!enableVirtualization) return items;
    
    const end = endIndex || Math.min(startIndex + maxRenderItems, items.length);
    return items.slice(startIndex, end);
  }, [enableVirtualization, maxRenderItems]);

  // Memoization helper
  const shouldUpdate = useCallback((
    prevDeps: any[],
    currentDeps: any[]
  ): boolean => {
    if (!enableMemoization) return true;
    
    return prevDeps.length !== currentDeps.length || 
           prevDeps.some((dep, index) => dep !== currentDeps[index]);
  }, [enableMemoization]);

  // Lazy loading helper
  const shouldLazyLoad = useCallback((
    itemIndex: number,
    visibleRange: { start: number; end: number }
  ): boolean => {
    if (!enableLazyLoading) return false;
    
    return itemIndex < visibleRange.start - 10 || 
           itemIndex > visibleRange.end + 10;
  }, [enableLazyLoading]);

  // Batch updates for better performance
  const batchUpdates = useCallback((updates: (() => void)[]) => {
    requestAnimationFrame(() => {
      updates.forEach(update => update());
    });
  }, []);

  // Memory cleanup
  useEffect(() => {
    return () => {
      if (throttleTimeout.current) {
        clearTimeout(throttleTimeout.current);
      }
    };
  }, []);

  // Performance monitoring alerts
  useEffect(() => {
    if (metrics.renderTime > 200) {
      console.warn('Slow render detected:', metrics.renderTime + 'ms');
    }
    
    if (metrics.memoryUsage > 50 * 1024 * 1024) { // 50MB
      console.warn('High memory usage detected:', (metrics.memoryUsage / 1024 / 1024).toFixed(2) + 'MB');
    }
  }, [metrics]);

  return {
    metrics,
    isOptimized,
    startRenderTimer,
    endRenderTimer,
    throttledUpdate,
    getVisibleItems,
    shouldUpdate,
    shouldLazyLoad,
    batchUpdates,
    settings: {
      maxRenderItems,
      throttleDelay,
      enableVirtualization,
      enableMemoization,
      enableLazyLoading
    }
  };
}