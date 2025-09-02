/**
 * Simplified Performance Hook - Replaces complex performance monitoring
 * Focus: Essential metrics only
 */

import { useEffect, useCallback } from 'react';
import { logger } from '@/core/SimpleLogger';

export interface PerformanceMetrics {
  pageLoadTime?: number;
  memoryUsage?: number;
  renderTime?: number;
}

export function useSimplePerformance(componentName?: string) {
  const startTime = performance.now();

  // Log component render time
  useEffect(() => {
    const renderTime = performance.now() - startTime;
    if (componentName && renderTime > 100) { // Only log slow renders
      logger.warn(`Slow render detected: ${componentName}`, {
        renderTime: Math.round(renderTime),
        threshold: 100
      });
    }
  }, [componentName, startTime]);

  const measureOperation = useCallback((operationName: string, fn: () => Promise<any> | any) => {
    const opStart = performance.now();
    
    const handleComplete = () => {
      const opTime = performance.now() - opStart;
      if (opTime > 1000) { // Only log operations taking > 1s
        logger.info(`Operation completed: ${operationName}`, {
          duration: Math.round(opTime)
        });
      }
    };

    try {
      const result = fn();
      if (result instanceof Promise) {
        return result.finally(handleComplete);
      } else {
        handleComplete();
        return result;
      }
    } catch (error) {
      handleComplete();
      throw error;
    }
  }, []);

  const getBasicMetrics = useCallback((): PerformanceMetrics => {
    const metrics: PerformanceMetrics = {};

    // Basic memory info (if available)
    if ('memory' in performance) {
      const memory = (performance as any).memory;
      metrics.memoryUsage = Math.round(memory.usedJSHeapSize / 1024 / 1024); // MB
    }

    // Navigation timing (page load)
    if (performance.navigation) {
      const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
      if (navEntries.length > 0) {
        const nav = navEntries[0];
        metrics.pageLoadTime = Math.round(nav.loadEventEnd - nav.fetchStart);
      }
    }

    return metrics;
  }, []);

  return {
    measureOperation,
    getBasicMetrics
  };
}