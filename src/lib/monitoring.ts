import { supabase } from '@/integrations/supabase/client';

interface PerformanceMetric {
  component: string;
  metric_type: string;
  value: number;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface ErrorReport {
  message: string;
  stack?: string;
  component?: string;
  user_id?: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

class MonitoringService {
  private metrics: PerformanceMetric[] = [];
  private errors: ErrorReport[] = [];
  private flushInterval: NodeJS.Timeout | null = null;

  constructor() {
    // Flush metrics every 30 seconds
    this.flushInterval = setInterval(() => {
      this.flush();
    }, 30000);

    // Flush on page unload
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => {
        this.flush();
      });
    }
  }

  // Track performance metrics
  trackMetric(
    component: string,
    metricType: string,
    value: number,
    metadata?: Record<string, any>
  ) {
    this.metrics.push({
      component,
      metric_type: metricType,
      value,
      timestamp: new Date().toISOString(),
      metadata
    });

    // Auto-flush if we have too many metrics
    if (this.metrics.length > 50) {
      this.flush();
    }
  }

  // Track errors
  trackError(error: Error | string, component?: string, metadata?: Record<string, any>) {
    const errorMessage = typeof error === 'string' ? error : error.message;
    const stack = typeof error === 'object' ? error.stack : undefined;

    this.errors.push({
      message: errorMessage,
      stack,
      component,
      timestamp: new Date().toISOString(),
      metadata
    });

    // Always flush errors immediately in production
    if (import.meta.env.PROD) {
      this.flushErrors();
    }
  }

  // Web Vitals tracking
  trackWebVital(name: string, value: number) {
    this.trackMetric('web-vitals', name, value, {
      userAgent: navigator.userAgent,
      connectionType: (navigator as any).connection?.effectiveType || 'unknown'
    });
  }

  // Component render tracking
  trackRender(componentName: string, renderTime: number) {
    this.trackMetric(componentName, 'render-time', renderTime);
    
    // Warn about slow renders
    if (renderTime > 16) {
      console.warn(`Slow render: ${componentName} took ${renderTime.toFixed(2)}ms`);
    }
  }

  // API call tracking
  trackApiCall(endpoint: string, duration: number, status: number) {
    this.trackMetric('api', 'request-duration', duration, {
      endpoint,
      status,
      timestamp: Date.now()
    });
  }

  // Flush metrics to Supabase
  private async flush() {
    await Promise.all([
      this.flushMetrics(),
      this.flushErrors()
    ]);
  }

  private async flushMetrics() {
    if (this.metrics.length === 0) return;

    const metricsToFlush = [...this.metrics];
    this.metrics = [];

    try {
      // In production, send to Supabase
      if (import.meta.env.PROD) {
        const { error } = await supabase
          .from('pipeline_metrics')
          .insert(
            metricsToFlush.map(metric => ({
              metric_name: `${metric.component}.${metric.metric_type}`,
              metric_value: metric.value,
              metric_unit: 'ms',
              tags: metric.metadata || {}
            }))
          );

        if (error) {
          console.error('Failed to flush metrics:', error);
          // Re-add metrics to queue on failure
          this.metrics.unshift(...metricsToFlush);
        }
      }
    } catch (error) {
      console.error('Error flushing metrics:', error);
      this.metrics.unshift(...metricsToFlush);
    }
  }

  private async flushErrors() {
    if (this.errors.length === 0) return;

    const errorsToFlush = [...this.errors];
    this.errors = [];

    try {
      // In production, send to Supabase
      if (import.meta.env.PROD) {
        const { error } = await supabase
          .from('error_reports')
          .insert(
            errorsToFlush.map(errorReport => ({
              error_id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
              message: errorReport.message,
              stack_trace: errorReport.stack,
              category: errorReport.component || 'unknown',
              severity: 'error',
              timestamp: new Date(errorReport.timestamp).toISOString(),
              context: errorReport.metadata || {},
              user_message: 'An unexpected error occurred'
            }))
          );

        if (error) {
          console.error('Failed to flush errors:', error);
          // Re-add errors to queue on failure
          this.errors.unshift(...errorsToFlush);
        }
      } else {
        // In development, just log
        errorsToFlush.forEach(error => {
          console.error('Error Report:', error);
        });
      }
    } catch (error) {
      console.error('Error flushing error reports:', error);
      this.errors.unshift(...errorsToFlush);
    }
  }

  // Cleanup
  destroy() {
    if (this.flushInterval) {
      clearInterval(this.flushInterval);
    }
    this.flush(); // Final flush
  }
}

// Global monitoring instance
export const monitoring = new MonitoringService();

// Performance observer for automatic Web Vitals
if (typeof window !== 'undefined' && 'PerformanceObserver' in window) {
  const observer = new PerformanceObserver((list) => {
    list.getEntries().forEach((entry) => {
      // Track paint metrics
      if (entry.entryType === 'paint') {
        monitoring.trackWebVital(entry.name, entry.startTime);
      }
      
      // Track navigation timing
      if (entry.entryType === 'navigation') {
        const navEntry = entry as PerformanceNavigationTiming;
        monitoring.trackWebVital('load-time', navEntry.loadEventEnd - navEntry.fetchStart);
        monitoring.trackWebVital('dom-content-loaded', navEntry.domContentLoadedEventEnd - navEntry.fetchStart);
      }

      // Track resource loading
      if (entry.entryType === 'resource' && entry.duration > 100) {
        monitoring.trackMetric('resources', 'load-time', entry.duration, {
          name: entry.name,
          type: (entry as any).initiatorType
        });
      }
    });
  });

  observer.observe({ 
    entryTypes: ['paint', 'navigation', 'resource', 'measure'] 
  });
}

// Hook for React components
export function useMonitoring(componentName: string) {
  const trackRender = (renderTime: number) => {
    monitoring.trackRender(componentName, renderTime);
  };

  const trackError = (error: Error | string, metadata?: Record<string, any>) => {
    monitoring.trackError(error, componentName, metadata);
  };

  const measureAsync = async <T>(
    operationName: string, 
    asyncOperation: () => Promise<T>
  ): Promise<T> => {
    const start = performance.now();
    try {
      const result = await asyncOperation();
      const duration = performance.now() - start;
      monitoring.trackMetric(componentName, operationName, duration);
      return result;
    } catch (error) {
      const duration = performance.now() - start;
      monitoring.trackMetric(componentName, `${operationName}-error`, duration);
      trackError(error as Error, { operation: operationName });
      throw error;
    }
  };

  return {
    trackRender,
    trackError,
    measureAsync
  };
}