/**
 * Web Vitals Performance Monitoring
 * Tracks Core Web Vitals and performance metrics
 */

import logger from '@/utils/productionLogger';
import { environmentManager } from '@/config/environmentManager';

export interface WebVitalsMetric {
  name: string;
  value: number;
  delta: number;
  rating: 'good' | 'needs-improvement' | 'poor';
  timestamp: string;
  id: string;
}

export interface PerformanceMetrics {
  fcp: number; // First Contentful Paint
  lcp: number; // Largest Contentful Paint
  fid: number; // First Input Delay
  cls: number; // Cumulative Layout Shift
  ttfb: number; // Time to First Byte
  inp: number; // Interaction to Next Paint
}

/**
 * Web Vitals Monitor
 */
export class WebVitalsMonitor {
  private static instance: WebVitalsMonitor;
  private metrics: Map<string, WebVitalsMetric> = new Map();
  private observers: Map<string, PerformanceObserver> = new Map();

  private constructor() {
    if (typeof window !== 'undefined' && environmentManager.isFeatureEnabled('enablePerformanceMonitoring')) {
      this.initializeWebVitals();
    }
  }

  static getInstance(): WebVitalsMonitor {
    if (!WebVitalsMonitor.instance) {
      WebVitalsMonitor.instance = new WebVitalsMonitor();
    }
    return WebVitalsMonitor.instance;
  }

  /**
   * Initialize Web Vitals monitoring
   */
  private initializeWebVitals(): void {
    // Monitor Largest Contentful Paint (LCP)
    this.observeLCP();
    
    // Monitor First Input Delay (FID)
    this.observeFID();
    
    // Monitor Cumulative Layout Shift (CLS)
    this.observeCLS();
    
    // Monitor First Contentful Paint (FCP)
    this.observeFCP();
    
    // Monitor Time to First Byte (TTFB)
    this.observeTTFB();
    
    // Monitor Interaction to Next Paint (INP)
    this.observeINP();
  }

  /**
   * Observe Largest Contentful Paint
   */
  private observeLCP(): void {
    try {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const lastEntry = entries[entries.length - 1] as any;
        
        if (lastEntry) {
          this.recordMetric('LCP', lastEntry.startTime, {
            element: lastEntry.element?.tagName,
            url: lastEntry.url
          });
        }
      });
      
      observer.observe({ type: 'largest-contentful-paint', buffered: true });
      this.observers.set('lcp', observer);
    } catch (error) {
      logger.warn('Failed to observe LCP', error as Error);
    }
  }

  /**
   * Observe First Input Delay
   */
  private observeFID(): void {
    try {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        
        entries.forEach((entry: any) => {
          this.recordMetric('FID', entry.processingStart - entry.startTime, {
            eventType: entry.name,
            target: entry.target?.tagName
          });
        });
      });
      
      observer.observe({ type: 'first-input', buffered: true });
      this.observers.set('fid', observer);
    } catch (error) {
      logger.warn('Failed to observe FID', error as Error);
    }
  }

  /**
   * Observe Cumulative Layout Shift
   */
  private observeCLS(): void {
    try {
      let clsValue = 0;
      
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        
        entries.forEach((entry: any) => {
          if (!entry.hadRecentInput) {
            clsValue += entry.value;
            this.recordMetric('CLS', clsValue, {
              sources: entry.sources?.map((s: any) => s.node?.tagName)
            });
          }
        });
      });
      
      observer.observe({ type: 'layout-shift', buffered: true });
      this.observers.set('cls', observer);
    } catch (error) {
      logger.warn('Failed to observe CLS', error as Error);
    }
  }

  /**
   * Observe First Contentful Paint
   */
  private observeFCP(): void {
    try {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        
        entries.forEach((entry) => {
          if (entry.name === 'first-contentful-paint') {
            this.recordMetric('FCP', entry.startTime);
          }
        });
      });
      
      observer.observe({ type: 'paint', buffered: true });
      this.observers.set('fcp', observer);
    } catch (error) {
      logger.warn('Failed to observe FCP', error as Error);
    }
  }

  /**
   * Observe Time to First Byte
   */
  private observeTTFB(): void {
    try {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        
        entries.forEach((entry: any) => {
          if (entry.responseStart > 0) {
            this.recordMetric('TTFB', entry.responseStart - entry.requestStart);
          }
        });
      });
      
      observer.observe({ type: 'navigation', buffered: true });
      this.observers.set('ttfb', observer);
    } catch (error) {
      logger.warn('Failed to observe TTFB', error as Error);
    }
  }

  /**
   * Observe Interaction to Next Paint
   */
  private observeINP(): void {
    try {
      // INP is still experimental, so we'll track it if available
      if ('PerformanceEventTiming' in window) {
        const observer = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          
          entries.forEach((entry: any) => {
            if (entry.processingEnd && entry.startTime) {
              const inp = entry.processingEnd - entry.startTime;
              this.recordMetric('INP', inp, {
                eventType: entry.name,
                duration: entry.duration
              });
            }
          });
        });
        
        observer.observe({ type: 'event', buffered: true });
        this.observers.set('inp', observer);
      }
    } catch (error) {
      logger.warn('Failed to observe INP', error as Error);
    }
  }

  /**
   * Record a performance metric
   */
  private recordMetric(name: string, value: number, details?: any): void {
    const rating = this.getRating(name, value);
    const metric: WebVitalsMetric = {
      name,
      value,
      delta: value - (this.metrics.get(name)?.value || 0),
      rating,
      timestamp: new Date().toISOString(),
      id: this.generateId()
    };

    this.metrics.set(name, metric);

    // Log the metric
    logger.info(`Web Vital: ${name}`, {
      value,
      rating,
      details,
      component: 'webvitals'
    });

    // Send to analytics if in production
    if (environmentManager.isProduction()) {
      this.sendToAnalytics(metric, details);
    }
  }

  /**
   * Get rating for a metric value
   */
  private getRating(name: string, value: number): 'good' | 'needs-improvement' | 'poor' {
    const thresholds = {
      FCP: [1800, 3000],
      LCP: [2500, 4000],
      FID: [100, 300],
      CLS: [0.1, 0.25],
      TTFB: [800, 1800],
      INP: [200, 500]
    };

    const [good, poor] = thresholds[name as keyof typeof thresholds] || [0, Infinity];
    
    if (value <= good) return 'good';
    if (value <= poor) return 'needs-improvement';
    return 'poor';
  }

  /**
   * Generate unique ID for metric
   */
  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Send metric to analytics service
   */
  private async sendToAnalytics(metric: WebVitalsMetric, details?: any): Promise<void> {
    try {
      // Send to analytics service (Google Analytics, custom endpoint, etc.)
      if (typeof window !== 'undefined' && 'gtag' in window) {
        const gtag = (window as any).gtag;
        gtag('event', metric.name, {
          custom_map: { metric_value: 'value' },
          value: Math.round(metric.value),
          metric_rating: metric.rating
        });
      }

      // Also store in our own metrics system
      logger.info('Web vital recorded', {
        metric: metric.name,
        value: metric.value,
        rating: metric.rating,
        ...details
      });
    } catch (error) {
      logger.warn('Failed to send metric to analytics', error as Error);
    }
  }

  /**
   * Get all recorded metrics
   */
  getMetrics(): Map<string, WebVitalsMetric> {
    return new Map(this.metrics);
  }

  /**
   * Get performance summary
   */
  getPerformanceSummary(): PerformanceMetrics {
    return {
      fcp: this.metrics.get('FCP')?.value || 0,
      lcp: this.metrics.get('LCP')?.value || 0,
      fid: this.metrics.get('FID')?.value || 0,
      cls: this.metrics.get('CLS')?.value || 0,
      ttfb: this.metrics.get('TTFB')?.value || 0,
      inp: this.metrics.get('INP')?.value || 0
    };
  }

  /**
   * Check if performance is within acceptable thresholds
   */
  isPerformanceGood(): boolean {
    const summary = this.getPerformanceSummary();
    
    return (
      summary.fcp <= 1800 &&
      summary.lcp <= 2500 &&
      summary.fid <= 100 &&
      summary.cls <= 0.1 &&
      summary.ttfb <= 800
    );
  }

  /**
   * Disconnect all observers
   */
  disconnect(): void {
    this.observers.forEach(observer => observer.disconnect());
    this.observers.clear();
  }
}

// Global instance
export const webVitalsMonitor = WebVitalsMonitor.getInstance();

// Convenience functions
export const startWebVitalsMonitoring = () => webVitalsMonitor;
export const getPerformanceMetrics = () => webVitalsMonitor.getPerformanceSummary();
export const isPerformanceGood = () => webVitalsMonitor.isPerformanceGood();

export default webVitalsMonitor;