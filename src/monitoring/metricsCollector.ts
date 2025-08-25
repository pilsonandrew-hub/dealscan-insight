/**
 * Advanced Metrics Collection for Production Monitoring
 * Comprehensive performance and business metrics tracking
 */

import { createLogger } from '@/utils/productionLogger';
import { supabase } from '@/integrations/supabase/client';
import { productionConfig } from '@/config/productionConfig';

const logger = createLogger('MetricsCollector');

export interface Metric {
  name: string;
  value: number;
  unit: string;
  timestamp: number;
  tags?: Record<string, string>;
  metadata?: Record<string, any>;
}

export interface BusinessMetric extends Metric {
  category: 'business' | 'technical' | 'user' | 'performance';
  importance: 'low' | 'medium' | 'high' | 'critical';
}

export interface MetricsSummary {
  totalMetrics: number;
  timeRange: {
    start: string;
    end: string;
  };
  categories: Record<string, number>;
  topMetrics: Array<{
    name: string;
    value: number;
    trend: 'up' | 'down' | 'stable';
  }>;
  alerts: Array<{
    metric: string;
    threshold: number;
    current: number;
    severity: 'warning' | 'critical';
  }>;
}

class AdvancedMetricsCollector {
  private metrics: Map<string, Metric[]> = new Map();
  private flushInterval?: NodeJS.Timeout;
  private thresholds: Map<string, { warning: number; critical: number }> = new Map();
  private isCollecting = false;

  constructor() {
    this.setupDefaultThresholds();
    this.startCollection();
  }

  /**
   * Start metrics collection
   */
  startCollection(): void {
    if (this.isCollecting) return;

    this.isCollecting = true;
    logger.info('Starting advanced metrics collection');

    // Start performance monitoring
    this.startPerformanceMonitoring();
    
    // Start business metrics monitoring
    this.startBusinessMetricsMonitoring();
    
    // Start user behavior tracking
    this.startUserBehaviorTracking();

    // Start periodic flush
    const flushInterval = productionConfig.getConfig().monitoring.metricsFlushInterval;
    this.flushInterval = setInterval(() => {
      this.flushMetrics();
    }, flushInterval);
  }

  /**
   * Stop metrics collection
   */
  stopCollection(): void {
    if (!this.isCollecting) return;

    this.isCollecting = false;
    logger.info('Stopping metrics collection');

    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = undefined;
    }

    // Final flush
    this.flushMetrics();
  }

  /**
   * Record a custom metric
   */
  recordMetric(metric: BusinessMetric): void {
    const metricName = metric.name;
    
    if (!this.metrics.has(metricName)) {
      this.metrics.set(metricName, []);
    }
    
    this.metrics.get(metricName)!.push(metric);
    
    // Check thresholds
    this.checkThresholds(metric);
    
    logger.debug('Metric recorded', {
      name: metric.name,
      value: metric.value,
      category: metric.category,
      importance: metric.importance
    });
  }

  /**
   * Record performance metric
   */
  recordPerformance(name: string, value: number, unit: string = 'ms'): void {
    this.recordMetric({
      name: `performance.${name}`,
      value,
      unit,
      timestamp: Date.now(),
      category: 'performance',
      importance: 'high',
      tags: {
        type: 'performance',
        environment: productionConfig.getConfig().app.environment
      }
    });
  }

  /**
   * Record business metric
   */
  recordBusiness(name: string, value: number, unit: string = 'count'): void {
    this.recordMetric({
      name: `business.${name}`,
      value,
      unit,
      timestamp: Date.now(),
      category: 'business',
      importance: 'critical',
      tags: {
        type: 'business',
        environment: productionConfig.getConfig().app.environment
      }
    });
  }

  /**
   * Record user behavior metric
   */
  recordUserBehavior(action: string, value: number = 1, metadata?: Record<string, any>): void {
    this.recordMetric({
      name: `user.${action}`,
      value,
      unit: 'count',
      timestamp: Date.now(),
      category: 'user',
      importance: 'medium',
      metadata,
      tags: {
        type: 'user_behavior',
        environment: productionConfig.getConfig().app.environment
      }
    });
  }

  /**
   * Get metrics summary
   */
  getMetricsSummary(timeRangeMs: number = 3600000): Promise<MetricsSummary> {
    const endTime = Date.now();
    const startTime = endTime - timeRangeMs;
    
    const allMetrics: BusinessMetric[] = [];
    let totalMetrics = 0;
    const categories: Record<string, number> = {};

    // Collect all metrics in time range
    for (const [name, metricList] of this.metrics.entries()) {
      const recentMetrics = metricList.filter(m => 
        m.timestamp >= startTime && m.timestamp <= endTime
      ) as BusinessMetric[];
      
      allMetrics.push(...recentMetrics);
      totalMetrics += recentMetrics.length;
      
      recentMetrics.forEach(metric => {
        categories[metric.category] = (categories[metric.category] || 0) + 1;
      });
    }

    // Calculate top metrics
    const metricAverages = new Map<string, { sum: number; count: number; latest: number }>();
    allMetrics.forEach(metric => {
      if (!metricAverages.has(metric.name)) {
        metricAverages.set(metric.name, { sum: 0, count: 0, latest: 0 });
      }
      const avg = metricAverages.get(metric.name)!;
      avg.sum += metric.value;
      avg.count += 1;
      avg.latest = metric.value;
    });

    const topMetrics = Array.from(metricAverages.entries())
      .map(([name, data]) => ({
        name,
        value: data.sum / data.count,
        trend: this.calculateTrend(name, timeRangeMs) as 'up' | 'down' | 'stable'
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);

    // Check for alerts
    const alerts: MetricsSummary['alerts'] = [];
    for (const [name, data] of metricAverages.entries()) {
      const threshold = this.thresholds.get(name);
      if (threshold) {
        const avgValue = data.sum / data.count;
        if (avgValue >= threshold.critical) {
          alerts.push({
            metric: name,
            threshold: threshold.critical,
            current: avgValue,
            severity: 'critical'
          });
        } else if (avgValue >= threshold.warning) {
          alerts.push({
            metric: name,
            threshold: threshold.warning,
            current: avgValue,
            severity: 'warning'
          });
        }
      }
    }

    return Promise.resolve({
      totalMetrics,
      timeRange: {
        start: new Date(startTime).toISOString(),
        end: new Date(endTime).toISOString()
      },
      categories,
      topMetrics,
      alerts
    });
  }

  /**
   * Set metric threshold
   */
  setThreshold(metricName: string, warning: number, critical: number): void {
    this.thresholds.set(metricName, { warning, critical });
    logger.info('Threshold set', { metricName, warning, critical });
  }

  /**
   * Start performance monitoring
   */
  private startPerformanceMonitoring(): void {
    if (typeof window === 'undefined') return;

    // Monitor page performance
    if ('performance' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'navigation') {
            const nav = entry as PerformanceNavigationTiming;
            this.recordPerformance('page_load_time', nav.loadEventEnd - nav.fetchStart);
            this.recordPerformance('dom_content_loaded', nav.domContentLoadedEventEnd - nav.fetchStart);
            this.recordPerformance('first_byte', nav.responseStart - nav.fetchStart);
          } else if (entry.entryType === 'paint') {
            this.recordPerformance(entry.name.replace('-', '_'), entry.startTime);
          }
        }
      });

      try {
        observer.observe({ type: 'navigation', buffered: true });
        observer.observe({ type: 'paint', buffered: true });
      } catch (error) {
        logger.warn('Performance observer not supported', {});
      }
    }

    // Monitor memory usage
    setInterval(() => {
      if ('memory' in performance) {
        const memory = (performance as any).memory;
        this.recordPerformance('memory_used', memory.usedJSHeapSize / 1024 / 1024, 'MB');
        this.recordPerformance('memory_total', memory.totalJSHeapSize / 1024 / 1024, 'MB');
      }
    }, 30000); // Every 30 seconds
  }

  /**
   * Start business metrics monitoring
   */
  private startBusinessMetricsMonitoring(): void {
    // Monitor API calls and their outcomes
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      const startTime = Date.now();
      try {
        const response = await originalFetch(...args);
        const duration = Date.now() - startTime;
        
        this.recordBusiness('api_calls_total');
        this.recordPerformance('api_response_time', duration);
        
        if (response.ok) {
          this.recordBusiness('api_calls_success');
        } else {
          this.recordBusiness('api_calls_error');
        }
        
        return response;
      } catch (error) {
        this.recordBusiness('api_calls_error');
        throw error;
      }
    };

    // Monitor business-specific events
    this.monitorOpportunityMetrics();
    this.monitorUserEngagement();
  }

  /**
   * Monitor opportunity-related metrics
   */
  private async monitorOpportunityMetrics(): Promise<void> {
    try {
      const { data: opportunities } = await supabase
        .from('opportunities')
        .select('status, roi_percentage, potential_profit')
        .eq('is_active', true);

      if (opportunities) {
        this.recordBusiness('active_opportunities', opportunities.length);
        
        const highROI = opportunities.filter(o => o.roi_percentage > 20).length;
        this.recordBusiness('high_roi_opportunities', highROI);
        
        const totalProfit = opportunities.reduce((sum, o) => sum + (o.potential_profit || 0), 0);
        this.recordBusiness('total_potential_profit', totalProfit, 'USD');
      }
    } catch (error) {
      logger.error('Failed to collect opportunity metrics', {});
    }
  }

  /**
   * Monitor user engagement metrics
   */
  private monitorUserEngagement(): void {
    let sessionStart = Date.now();
    let pageViews = 0;
    let interactions = 0;

    // Track page views
    pageViews++;
    this.recordUserBehavior('page_view');

    // Track user interactions
    ['click', 'keydown', 'scroll'].forEach(eventType => {
      document.addEventListener(eventType, () => {
        interactions++;
        if (interactions % 10 === 0) { // Report every 10 interactions
          this.recordUserBehavior('user_interactions', interactions);
        }
      }, { passive: true });
    });

    // Track session duration
    window.addEventListener('beforeunload', () => {
      const sessionDuration = Date.now() - sessionStart;
      this.recordUserBehavior('session_duration', sessionDuration, { 
        pageViews, 
        interactions,
        unit: 'ms'
      });
    });
  }

  /**
   * Start user behavior tracking
   */
  private startUserBehaviorTracking(): void {
    // Track feature usage
    this.trackFeatureUsage();
    
    // Track errors
    this.trackErrorMetrics();
  }

  /**
   * Track feature usage
   */
  private trackFeatureUsage(): void {
    // Monitor specific feature usage patterns
    const features = ['opportunities', 'dashboard', 'settings', 'upload'];
    
    features.forEach(feature => {
      // This would be integrated with actual feature usage tracking
      this.recordUserBehavior(`feature_usage_${feature}`, 1);
    });
  }

  /**
   * Track error metrics
   */
  private trackErrorMetrics(): void {
    window.addEventListener('error', (event) => {
      this.recordMetric({
        name: 'errors.javascript_error',
        value: 1,
        unit: 'count',
        timestamp: Date.now(),
        category: 'technical',
        importance: 'high',
        metadata: {
          message: event.error?.message,
          filename: event.filename,
          line: event.lineno,
          column: event.colno
        }
      });
    });

    window.addEventListener('unhandledrejection', (event) => {
      this.recordMetric({
        name: 'errors.unhandled_promise_rejection',
        value: 1,
        unit: 'count',
        timestamp: Date.now(),
        category: 'technical',
        importance: 'high',
        metadata: {
          reason: event.reason?.toString()
        }
      });
    });
  }

  /**
   * Setup default thresholds
   */
  private setupDefaultThresholds(): void {
    // Performance thresholds
    this.setThreshold('performance.page_load_time', 2000, 5000);
    this.setThreshold('performance.api_response_time', 1000, 3000);
    this.setThreshold('performance.memory_used', 100, 150);
    
    // Business thresholds
    this.setThreshold('business.api_calls_error', 5, 10);
    this.setThreshold('errors.javascript_error', 1, 5);
  }

  /**
   * Check metric thresholds
   */
  private checkThresholds(metric: BusinessMetric): void {
    const threshold = this.thresholds.get(metric.name);
    if (!threshold) return;

    if (metric.value >= threshold.critical) {
      logger.error('Critical threshold exceeded', {
        metric: metric.name,
        value: metric.value,
        threshold: threshold.critical
      });
    } else if (metric.value >= threshold.warning) {
      logger.warn('Warning threshold exceeded', {
        metric: metric.name,
        value: metric.value,
        threshold: threshold.warning
      });
    }
  }

  /**
   * Calculate trend for a metric
   */
  private calculateTrend(metricName: string, timeRangeMs: number): string {
    const metricList = this.metrics.get(metricName);
    if (!metricList || metricList.length < 2) return 'stable';

    const now = Date.now();
    const recentMetrics = metricList.filter(m => m.timestamp >= now - timeRangeMs);
    
    if (recentMetrics.length < 2) return 'stable';

    const firstHalf = recentMetrics.slice(0, Math.floor(recentMetrics.length / 2));
    const secondHalf = recentMetrics.slice(Math.floor(recentMetrics.length / 2));

    const firstAvg = firstHalf.reduce((sum, m) => sum + m.value, 0) / firstHalf.length;
    const secondAvg = secondHalf.reduce((sum, m) => sum + m.value, 0) / secondHalf.length;

    const percentChange = ((secondAvg - firstAvg) / firstAvg) * 100;

    if (percentChange > 5) return 'up';
    if (percentChange < -5) return 'down';
    return 'stable';
  }

  /**
   * Flush metrics to storage/external service
   */
  private async flushMetrics(): Promise<void> {
    if (this.metrics.size === 0) return;

    try {
      const metricsToFlush: BusinessMetric[] = [];
      
      // Collect all metrics
      for (const [name, metricList] of this.metrics.entries()) {
        metricsToFlush.push(...(metricList as BusinessMetric[]));
      }

      if (metricsToFlush.length === 0) return;

      logger.debug('Flushing metrics', { count: metricsToFlush.length });

      // Store in database (sample - store aggregated metrics)
      const aggregatedMetrics = this.aggregateMetrics(metricsToFlush);
      
      for (const metric of aggregatedMetrics) {
        await supabase.from('pipeline_metrics').insert({
          metric_name: metric.name,
          metric_value: metric.value,
          metric_unit: metric.unit,
          tags: metric.tags || {}
        });
      }

      // Clear flushed metrics
      this.metrics.clear();

      logger.info('Metrics flushed successfully', { count: metricsToFlush.length });

    } catch (error) {
      logger.error('Failed to flush metrics', {});
    }
  }

  /**
   * Aggregate metrics for storage efficiency
   */
  private aggregateMetrics(metrics: BusinessMetric[]): BusinessMetric[] {
    const aggregated = new Map<string, { sum: number; count: number; latest: BusinessMetric }>();

    metrics.forEach(metric => {
      const key = `${metric.name}_${metric.category}`;
      if (!aggregated.has(key)) {
        aggregated.set(key, { sum: 0, count: 0, latest: metric });
      }
      const agg = aggregated.get(key)!;
      agg.sum += metric.value;
      agg.count += 1;
      agg.latest = metric;
    });

    return Array.from(aggregated.values()).map(agg => ({
      ...agg.latest,
      value: agg.sum / agg.count,
      metadata: {
        ...agg.latest.metadata,
        aggregated: true,
        count: agg.count,
        sum: agg.sum
      }
    }));
  }
}

// Global metrics collector instance
export const metricsCollector = new AdvancedMetricsCollector();

// Auto-start collection in production
if (productionConfig.getConfig().monitoring.enabled) {
  metricsCollector.startCollection();
}