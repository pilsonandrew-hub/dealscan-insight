import { useEffect, useRef } from 'react';

interface PerformanceMetrics {
  loadTime: number;
  renderTime: number;
  memoryUsage?: number;
  connectionType?: string;
}

export function usePerformanceMonitor(componentName: string) {
  const startTimeRef = useRef<number>(performance.now());
  const observerRef = useRef<PerformanceObserver | null>(null);

  useEffect(() => {
    const startTime = startTimeRef.current;

    // Measure component render time
    const renderTime = performance.now() - startTime;

    // Collect performance metrics
    const metrics: PerformanceMetrics = {
      loadTime: performance.timing ? performance.timing.loadEventEnd - performance.timing.navigationStart : 0,
      renderTime,
      memoryUsage: (performance as any).memory?.usedJSHeapSize,
      connectionType: (navigator as any).connection?.effectiveType
    };

    // Report slow renders (>16ms for 60fps)
    if (renderTime > 16) {
      console.warn(`Slow render detected in ${componentName}: ${renderTime.toFixed(2)}ms`);
    }

    // Set up Performance Observer for Web Vitals
    if ('PerformanceObserver' in window) {
      observerRef.current = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          // Log performance entries
          if (entry.entryType === 'measure' || entry.entryType === 'navigation') {
            console.log(`Performance: ${entry.name} - ${entry.duration}ms`);
          }
        }
      });

      observerRef.current.observe({ 
        entryTypes: ['measure', 'navigation', 'paint']
      });
    }

    // Report metrics to analytics (in production)
    if (import.meta.env.PROD) {
      reportMetrics(componentName, metrics);
    }

    return () => {
      observerRef.current?.disconnect();
    };
  }, [componentName]);

  const reportMetrics = (component: string, metrics: PerformanceMetrics) => {
    // Send to analytics service
    fetch('/api/metrics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        component,
        metrics,
        timestamp: Date.now(),
        userAgent: navigator.userAgent,
        url: window.location.pathname
      })
    }).catch(() => {
      // Silently fail in production
    });
  };

  const measureAsync = async <T>(
    name: string,
    asyncOperation: () => Promise<T>
  ): Promise<T> => {
    const start = performance.now();
    try {
      const result = await asyncOperation();
      const duration = performance.now() - start;
      performance.mark(`${name}-start`);
      performance.mark(`${name}-end`);
      performance.measure(name, `${name}-start`, `${name}-end`);
      
      if (duration > 1000) {
        console.warn(`Slow async operation: ${name} took ${duration.toFixed(2)}ms`);
      }
      
      return result;
    } catch (error) {
      const duration = performance.now() - start;
      console.error(`Failed async operation: ${name} failed after ${duration.toFixed(2)}ms`, error);
      throw error;
    }
  };

  return { measureAsync };
}