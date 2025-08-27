/**
 * Performance Monitoring for Cloud Logging
 * Tracks Core Web Vitals and performance metrics
 */

import { cloudLogger } from './cloudLogger';
import { createLogger } from './productionLogger';

const logger = createLogger('PerformanceMonitor');

interface PerformanceMetric {
  name: string;
  value: number;
  rating: 'good' | 'needs-improvement' | 'poor';
  timestamp: number;
  url: string;
  user_agent: string;
}

class PerformanceMonitor {
  private static instance: PerformanceMonitor;
  private metrics: PerformanceMetric[] = [];
  private isInitialized = false;

  private constructor() {}

  public static getInstance(): PerformanceMonitor {
    if (!PerformanceMonitor.instance) {
      PerformanceMonitor.instance = new PerformanceMonitor();
    }
    return PerformanceMonitor.instance;
  }

  public initialize(): void {
    if (this.isInitialized || typeof window === 'undefined') return;

    this.isInitialized = true;
    
    // Monitor Core Web Vitals
    this.observeCLS();
    this.observeFID();
    this.observeLCP();
    this.observeFCP();
    this.observeTTFB();
    
    // Monitor navigation timing
    this.observeNavigationTiming();
    
    // Monitor resource loading
    this.observeResourceTiming();

    logger.info('Performance monitoring initialized');
  }

  private observeCLS(): void {
    // Cumulative Layout Shift
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'layout-shift' && !(entry as any).hadRecentInput) {
            const cls = (entry as any).value;
            this.recordMetric('CLS', cls, this.getRating('CLS', cls));
          }
        }
      });

      observer.observe({ type: 'layout-shift', buffered: true });
    }
  }

  private observeFID(): void {
    // First Input Delay
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'first-input') {
            const perfEntry = entry as any; // PerformanceEventTiming
            const fid = perfEntry.processingStart - entry.startTime;
            this.recordMetric('FID', fid, this.getRating('FID', fid));
          }
        }
      });

      observer.observe({ type: 'first-input', buffered: true });
    }
  }

  private observeLCP(): void {
    // Largest Contentful Paint
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const lastEntry = entries[entries.length - 1];
        if (lastEntry) {
          const lcp = lastEntry.startTime;
          this.recordMetric('LCP', lcp, this.getRating('LCP', lcp));
        }
      });

      observer.observe({ type: 'largest-contentful-paint', buffered: true });
    }
  }

  private observeFCP(): void {
    // First Contentful Paint
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.name === 'first-contentful-paint') {
            const fcp = entry.startTime;
            this.recordMetric('FCP', fcp, this.getRating('FCP', fcp));
          }
        }
      });

      observer.observe({ type: 'paint', buffered: true });
    }
  }

  private observeTTFB(): void {
    // Time to First Byte
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'navigation') {
            const navEntry = entry as PerformanceNavigationTiming;
            const ttfb = navEntry.responseStart - navEntry.requestStart;
            this.recordMetric('TTFB', ttfb, this.getRating('TTFB', ttfb));
          }
        }
      });

      observer.observe({ type: 'navigation', buffered: true });
    }
  }

  private observeNavigationTiming(): void {
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'navigation') {
            const navEntry = entry as PerformanceNavigationTiming;
            
            // Page Load Time
            const loadTime = navEntry.loadEventEnd - navEntry.fetchStart;
            this.recordMetric('Page Load Time', loadTime, this.getRating('Load', loadTime));
            
            // DOM Content Loaded
            const domReady = navEntry.domContentLoadedEventEnd - navEntry.fetchStart;
            this.recordMetric('DOM Ready', domReady, this.getRating('DOM', domReady));
          }
        }
      });

      observer.observe({ type: 'navigation', buffered: true });
    }
  }

  private observeResourceTiming(): void {
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'resource') {
            const resourceEntry = entry as PerformanceResourceTiming;
            
            // Track slow resources
            const duration = resourceEntry.responseEnd - resourceEntry.startTime;
            if (duration > 1000) { // Resources taking more than 1 second
              this.recordSlowResource(resourceEntry.name, duration);
            }
          }
        }
      });

      observer.observe({ type: 'resource', buffered: true });
    }
  }

  private recordMetric(name: string, value: number, rating: 'good' | 'needs-improvement' | 'poor'): void {
    const metric: PerformanceMetric = {
      name,
      value,
      rating,
      timestamp: Date.now(),
      url: window.location.href,
      user_agent: navigator.userAgent
    };

    this.metrics.push(metric);

    // Log to cloud if performance is poor
    if (rating === 'poor') {
      cloudLogger.logWarning(`Poor performance detected: ${name}`, {
        metric: name,
        value,
        rating,
        threshold: this.getThreshold(name, 'poor'),
        type: 'performance_issue'
      });
    }

    logger.info('Performance metric recorded', { name, value, rating });
  }

  private recordSlowResource(url: string, duration: number): void {
    cloudLogger.logWarning('Slow resource loading detected', {
      resource_url: url,
      duration,
      threshold: 1000,
      type: 'slow_resource'
    });
  }

  private getRating(metric: string, value: number): 'good' | 'needs-improvement' | 'poor' {
    const thresholds = {
      'CLS': { good: 0.1, poor: 0.25 },
      'FID': { good: 100, poor: 300 },
      'LCP': { good: 2500, poor: 4000 },
      'FCP': { good: 1800, poor: 3000 },
      'TTFB': { good: 800, poor: 1800 },
      'Load': { good: 3000, poor: 5000 },
      'DOM': { good: 2000, poor: 4000 }
    };

    const threshold = thresholds[metric as keyof typeof thresholds];
    if (!threshold) return 'good';

    if (value <= threshold.good) return 'good';
    if (value <= threshold.poor) return 'needs-improvement';
    return 'poor';
  }

  private getThreshold(metric: string, rating: 'good' | 'poor'): number {
    const thresholds = {
      'CLS': { good: 0.1, poor: 0.25 },
      'FID': { good: 100, poor: 300 },
      'LCP': { good: 2500, poor: 4000 },
      'FCP': { good: 1800, poor: 3000 },
      'TTFB': { good: 800, poor: 1800 },
      'Load': { good: 3000, poor: 5000 },
      'DOM': { good: 2000, poor: 4000 }
    };

    const threshold = thresholds[metric as keyof typeof thresholds];
    return threshold ? threshold[rating] : 0;
  }

  public getMetrics(): PerformanceMetric[] {
    return [...this.metrics];
  }

  public clearMetrics(): void {
    this.metrics = [];
  }

  public reportToCloud(): void {
    if (this.metrics.length === 0) return;

    cloudLogger.logInfo('Performance metrics report', {
      metrics: this.metrics,
      summary: this.getMetricsSummary(),
      type: 'performance_report'
    });

    this.clearMetrics();
  }

  private getMetricsSummary(): Record<string, any> {
    const summary: Record<string, any> = {};
    
    this.metrics.forEach(metric => {
      if (!summary[metric.name]) {
        summary[metric.name] = {
          count: 0,
          total: 0,
          good: 0,
          needs_improvement: 0,
          poor: 0
        };
      }
      
      summary[metric.name].count++;
      summary[metric.name].total += metric.value;
      summary[metric.name][metric.rating.replace('-', '_')]++;
    });

    // Calculate averages
    Object.keys(summary).forEach(key => {
      summary[key].average = summary[key].total / summary[key].count;
    });

    return summary;
  }
}

export const performanceMonitor = PerformanceMonitor.getInstance();
export default performanceMonitor;