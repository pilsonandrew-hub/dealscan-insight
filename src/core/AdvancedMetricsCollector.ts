/**
 * Advanced Metrics Collector - Investment Grade
 * Sophisticated real-time metrics collection with statistical analysis
 * Integrates with enterprise orchestrator and monitoring systems
 */

import { logger } from './UnifiedLogger';
import { configService } from './UnifiedConfigService';
import { stateManager } from './UnifiedStateManager';

export interface MetricDefinition {
  name: string;
  type: 'counter' | 'gauge' | 'histogram' | 'summary';
  description: string;
  unit?: string;
  labels?: string[];
  buckets?: number[]; // For histograms
  quantiles?: number[]; // For summaries
}

export interface MetricValue {
  name: string;
  value: number;
  labels?: Record<string, string>;
  timestamp: number;
  metadata?: any;
}

export interface StatisticalAnalysis {
  mean: number;
  median: number;
  p95: number;
  p99: number;
  min: number;
  max: number;
  stdDev: number;
  count: number;
  trend: 'increasing' | 'decreasing' | 'stable';
}

export interface MetricAlert {
  metric: string;
  threshold: number;
  operator: 'gt' | 'lt' | 'eq' | 'gte' | 'lte';
  value: number;
  severity: 'info' | 'warning' | 'critical';
  message: string;
  timestamp: number;
}

class AdvancedMetricsCollector {
  private static instance: AdvancedMetricsCollector;
  private metrics = new Map<string, MetricDefinition>();
  private values = new Map<string, MetricValue[]>();
  private alerts = new Map<string, MetricAlert>();
  private collectors = new Map<string, () => Promise<MetricValue[]>>();
  private collectionInterval: number = 0;
  private isCollecting = false;
  private maxRetentionSize = 10000; // Per metric
  private alertThresholds = new Map<string, Array<{ threshold: number; operator: string; severity: string; }>>();

  private constructor() {
    this.setupCoreMetrics();
    this.setupCollectionSchedule();
    this.setupAlertingSystem();
    this.integrateWithStateManager();
  }

  static getInstance(): AdvancedMetricsCollector {
    if (!AdvancedMetricsCollector.instance) {
      AdvancedMetricsCollector.instance = new AdvancedMetricsCollector();
    }
    return AdvancedMetricsCollector.instance;
  }

  /**
   * Setup core business and system metrics
   */
  private setupCoreMetrics(): void {
    // Business metrics
    this.registerMetric({
      name: 'arbitrage_opportunities_found',
      type: 'counter',
      description: 'Total arbitrage opportunities identified',
      unit: 'count',
      labels: ['source', 'profit_tier', 'vehicle_type']
    });

    this.registerMetric({
      name: 'arbitrage_profit_potential',
      type: 'histogram',
      description: 'Distribution of profit potential per opportunity',
      unit: 'dollars',
      buckets: [100, 500, 1000, 2500, 5000, 10000, 25000]
    });

    this.registerMetric({
      name: 'deal_scoring_accuracy',
      type: 'gauge',
      description: 'ML model accuracy for deal scoring',
      unit: 'percentage',
      labels: ['model_version', 'vehicle_category']
    });

    // System performance metrics
    this.registerMetric({
      name: 'api_request_duration',
      type: 'histogram',
      description: 'API request processing time',
      unit: 'milliseconds',
      buckets: [10, 50, 100, 250, 500, 1000, 2500, 5000],
      labels: ['endpoint', 'method', 'status_code']
    });

    this.registerMetric({
      name: 'database_connection_pool_usage',
      type: 'gauge',
      description: 'Database connection pool utilization',
      unit: 'percentage'
    });

    this.registerMetric({
      name: 'scraping_success_rate',
      type: 'gauge',
      description: 'Vehicle data scraping success rate',
      unit: 'percentage',
      labels: ['source', 'region']
    });

    this.registerMetric({
      name: 'cache_hit_rate',
      type: 'gauge',
      description: 'Cache hit rate across different caches',
      unit: 'percentage',
      labels: ['cache_type', 'region']
    });

    this.registerMetric({
      name: 'memory_heap_usage',
      type: 'gauge',
      description: 'JavaScript heap memory usage',
      unit: 'bytes'
    });

    this.registerMetric({
      name: 'user_engagement_score',
      type: 'gauge',
      description: 'User engagement scoring',
      unit: 'score',
      labels: ['user_tier', 'session_type']
    });

    logger.info('Advanced metrics system initialized', {
      totalMetrics: this.metrics.size,
      retentionSize: this.maxRetentionSize
    });
  }

  /**
   * Register a new metric definition
   */
  registerMetric(metric: MetricDefinition): void {
    if (this.metrics.has(metric.name)) {
      throw new Error(`Metric '${metric.name}' is already registered`);
    }

    this.metrics.set(metric.name, metric);
    this.values.set(metric.name, []);

    logger.debug('Metric registered', {
      name: metric.name,
      type: metric.type,
      description: metric.description
    });
  }

  /**
   * Record a metric value
   */
  recordMetric(name: string, value: number, labels?: Record<string, string>, metadata?: any): void {
    const metric = this.metrics.get(name);
    if (!metric) {
      logger.warn('Attempting to record unknown metric', { name });
      return;
    }

    const metricValue: MetricValue = {
      name,
      value,
      labels,
      timestamp: Date.now(),
      metadata
    };

    const values = this.values.get(name) || [];
    values.push(metricValue);

    // Maintain retention limit
    if (values.length > this.maxRetentionSize) {
      values.shift(); // Remove oldest value
    }

    this.values.set(name, values);

    // Check for alerts
    this.checkAlerts(name, value, labels);

    logger.debug('Metric recorded', {
      name,
      value,
      labels,
      timestamp: metricValue.timestamp
    });
  }

  /**
   * Register a custom metric collector
   */
  registerCollector(name: string, collector: () => Promise<MetricValue[]>): void {
    this.collectors.set(name, collector);
    logger.info('Custom collector registered', { name });
  }

  /**
   * Setup collection schedule
   */
  private setupCollectionSchedule(): void {
    const interval = configService.performance.monitoring.samplingRate === 1.0 ? 5000 : 15000; // 5s in dev, 15s in prod
    
    this.collectionInterval = window.setInterval(async () => {
      if (!this.isCollecting) {
        await this.collectMetrics();
      }
    }, interval);

    logger.info('Metrics collection scheduled', { intervalMs: interval });
  }

  /**
   * Collect all registered metrics
   */
  private async collectMetrics(): Promise<void> {
    if (!configService.performance.monitoring.enabled) {
      return;
    }

    this.isCollecting = true;
    const startTime = performance.now();

    try {
      // Collect system metrics
      await this.collectSystemMetrics();

      // Collect business metrics
      await this.collectBusinessMetrics();

      // Run custom collectors
      await this.runCustomCollectors();

      const duration = performance.now() - startTime;
      logger.performance('Metrics collection completed', {
        duration,
        totalMetrics: this.metrics.size,
        totalValues: Array.from(this.values.values()).reduce((sum, arr) => sum + arr.length, 0)
      });

    } catch (error) {
      logger.error('Metrics collection failed', { error });
    } finally {
      this.isCollecting = false;
    }
  }

  /**
   * Collect system performance metrics
   */
  private async collectSystemMetrics(): Promise<void> {
    // Memory usage
    if ('memory' in performance) {
      const memory = (performance as any).memory;
      this.recordMetric('memory_heap_usage', memory.usedJSHeapSize);
    }

    // Navigation timing metrics (if available)
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
    if (navigation) {
      this.recordMetric('api_request_duration', navigation.responseEnd - navigation.requestStart, {
        endpoint: 'page_load',
        method: 'GET',
        status_code: '200'
      });
    }

    // Resource timing
    const resources = performance.getEntriesByType('resource');
    resources.forEach(resource => {
      if (resource.name.includes('/api/')) {
        this.recordMetric('api_request_duration', resource.duration, {
          endpoint: resource.name,
          method: 'unknown',
          status_code: 'unknown'
        });
      }
    });
    
    // Clear performance entries to prevent memory buildup
    performance.clearResourceTimings();
  }

  /**
   * Collect business metrics from state manager
   */
  private async collectBusinessMetrics(): Promise<void> {
    // Get opportunities data from state
    const opportunities = stateManager.select('opportunities') as any[];
    if (opportunities && Array.isArray(opportunities)) {
      // Count opportunities by profit tier
      const profitTiers = opportunities.reduce((acc: Record<string, number>, opp: any) => {
        const profit = typeof opp?.profitPotential === 'number' ? opp.profitPotential : 0;
        const tier = profit > 5000 ? 'high' : profit > 1000 ? 'medium' : 'low';
        acc[tier] = (acc[tier] || 0) + 1;
        return acc;
      }, {} as Record<string, number>);

      Object.entries(profitTiers).forEach(([tier, count]) => {
        this.recordMetric('arbitrage_opportunities_found', count as number, { profit_tier: tier });
      });

      // Record profit distribution
      opportunities.forEach((opp: any) => {
        if (typeof opp?.profitPotential === 'number') {
          this.recordMetric('arbitrage_profit_potential', opp.profitPotential, {
            source: opp.source || 'unknown',
            vehicle_type: opp.vehicle?.make || 'unknown'
          });
        }
      });
    }

    // User engagement metrics
    const authState = stateManager.select('auth') as any;
    if (authState && typeof authState === 'object' && authState.user) {
      const sessionStartTime = typeof authState.sessionStartTime === 'number' ? authState.sessionStartTime : Date.now();
      const sessionDuration = Date.now() - sessionStartTime;
      const engagementScore = Math.min(100, sessionDuration / 60000); // Score based on session time
      
      this.recordMetric('user_engagement_score', engagementScore, {
        user_tier: authState.user?.tier || 'basic',
        session_type: authState.sessionType || 'standard'
      });
    }
  }

  /**
   * Run custom metric collectors
   */
  private async runCustomCollectors(): Promise<void> {
    for (const [name, collector] of this.collectors.entries()) {
      try {
        const values = await collector();
        values.forEach(value => {
          this.recordMetric(value.name, value.value, value.labels, value.metadata);
        });
      } catch (error) {
        logger.error('Custom collector failed', { collector: name, error });
      }
    }
  }

  /**
   * Setup alerting system
   */
  private setupAlertingSystem(): void {
    // Setup default alert thresholds
    this.setAlertThreshold('memory_heap_usage', [
      { threshold: 100 * 1024 * 1024, operator: 'gt', severity: 'warning' }, // 100MB
      { threshold: 200 * 1024 * 1024, operator: 'gt', severity: 'critical' }  // 200MB
    ]);

    this.setAlertThreshold('api_request_duration', [
      { threshold: 1000, operator: 'gt', severity: 'warning' }, // 1 second
      { threshold: 5000, operator: 'gt', severity: 'critical' }  // 5 seconds
    ]);

    this.setAlertThreshold('cache_hit_rate', [
      { threshold: 80, operator: 'lt', severity: 'warning' }, // Less than 80%
      { threshold: 60, operator: 'lt', severity: 'critical' }  // Less than 60%
    ]);

    logger.info('Alert thresholds configured');
  }

  /**
   * Set alert threshold for a metric
   */
  setAlertThreshold(metricName: string, thresholds: Array<{ threshold: number; operator: string; severity: string; }>): void {
    this.alertThresholds.set(metricName, thresholds);
  }

  /**
   * Check if metric value triggers any alerts
   */
  private checkAlerts(metricName: string, value: number, labels?: Record<string, string>): void {
    const thresholds = this.alertThresholds.get(metricName);
    if (!thresholds) return;

    thresholds.forEach(threshold => {
      let triggered = false;
      
      switch (threshold.operator) {
        case 'gt':
          triggered = value > threshold.threshold;
          break;
        case 'lt':
          triggered = value < threshold.threshold;
          break;
        case 'gte':
          triggered = value >= threshold.threshold;
          break;
        case 'lte':
          triggered = value <= threshold.threshold;
          break;
        case 'eq':
          triggered = value === threshold.threshold;
          break;
      }

      if (triggered) {
        const alertKey = `${metricName}_${threshold.severity}_${threshold.threshold}`;
        const alert: MetricAlert = {
          metric: metricName,
          threshold: threshold.threshold,
          operator: threshold.operator as any,
          value,
          severity: threshold.severity as any,
          message: `Metric ${metricName} ${threshold.operator} ${threshold.threshold} (current: ${value})`,
          timestamp: Date.now()
        };

        this.alerts.set(alertKey, alert);
        
        logger.warn('Metric alert triggered', {
          metric: metricName,
          severity: threshold.severity,
          threshold: threshold.threshold,
          value,
          labels
        });
      }
    });
  }

  /**
   * Get statistical analysis for a metric
   */
  getStatisticalAnalysis(metricName: string, timeRangeMs?: number): StatisticalAnalysis | null {
    const values = this.values.get(metricName);
    if (!values || values.length === 0) {
      return null;
    }

    const now = Date.now();
    const filteredValues = timeRangeMs 
      ? values.filter(v => now - v.timestamp <= timeRangeMs)
      : values;

    if (filteredValues.length === 0) {
      return null;
    }

    const numericValues = filteredValues.map(v => v.value).sort((a, b) => a - b);
    const count = numericValues.length;
    const sum = numericValues.reduce((a, b) => a + b, 0);
    const mean = sum / count;

    const median = count % 2 === 0
      ? (numericValues[count / 2 - 1] + numericValues[count / 2]) / 2
      : numericValues[Math.floor(count / 2)];

    const p95Index = Math.floor(count * 0.95);
    const p99Index = Math.floor(count * 0.99);
    const p95 = numericValues[p95Index] || numericValues[count - 1];
    const p99 = numericValues[p99Index] || numericValues[count - 1];

    const variance = numericValues.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / count;
    const stdDev = Math.sqrt(variance);

    // Simple trend analysis (last 10% vs first 10%)
    const trendSampleSize = Math.max(1, Math.floor(count * 0.1));
    const recentValues = numericValues.slice(-trendSampleSize);
    const oldValues = numericValues.slice(0, trendSampleSize);
    const recentMean = recentValues.reduce((a, b) => a + b, 0) / recentValues.length;
    const oldMean = oldValues.reduce((a, b) => a + b, 0) / oldValues.length;
    
    let trend: 'increasing' | 'decreasing' | 'stable';
    const trendThreshold = stdDev * 0.5; // Use half standard deviation as threshold
    if (recentMean > oldMean + trendThreshold) {
      trend = 'increasing';
    } else if (recentMean < oldMean - trendThreshold) {
      trend = 'decreasing';
    } else {
      trend = 'stable';
    }

    return {
      mean,
      median,
      p95,
      p99,
      min: numericValues[0],
      max: numericValues[count - 1],
      stdDev,
      count,
      trend
    };
  }

  /**
   * Integrate with state manager for reactive metrics
   */
  private integrateWithStateManager(): void {
    // Listen for state changes to collect relevant metrics
    stateManager.addGlobalListener((newState, oldState, action) => {
      // Performance metric: state update duration
      if (action.meta?.timestamp) {
        const duration = Date.now() - action.meta.timestamp;
        this.recordMetric('state_update_duration', duration, {
          action_type: action.type
        });
      }

      // Business metrics based on state changes
      if (action.type === 'OPPORTUNITIES_LOADED' && newState.opportunities) {
        this.recordMetric('arbitrage_opportunities_found', newState.opportunities.length, {
          source: 'state_update'
        });
      }
    });
  }

  /**
   * Get comprehensive metrics report
   */
  getMetricsReport(timeRangeMs: number = 300000): { // Default 5 minute window
    metrics: Record<string, StatisticalAnalysis>;
    alerts: MetricAlert[];
    systemHealth: 'healthy' | 'warning' | 'critical';
    totalDataPoints: number;
  } {
    const report: any = {
      metrics: {},
      alerts: Array.from(this.alerts.values()),
      systemHealth: 'healthy' as const,
      totalDataPoints: 0
    };

    // Generate statistical analysis for all metrics
    for (const metricName of this.metrics.keys()) {
      const analysis = this.getStatisticalAnalysis(metricName, timeRangeMs);
      if (analysis) {
        report.metrics[metricName] = analysis;
        report.totalDataPoints += analysis.count;
      }
    }

    // Determine overall system health
    const criticalAlerts = report.alerts.filter((a: MetricAlert) => a.severity === 'critical');
    const warningAlerts = report.alerts.filter((a: MetricAlert) => a.severity === 'warning');

    if (criticalAlerts.length > 0) {
      report.systemHealth = 'critical';
    } else if (warningAlerts.length > 0) {
      report.systemHealth = 'warning';
    }

    return report;
  }

  /**
   * Clear old alerts
   */
  clearOldAlerts(maxAgeMs: number = 300000): void { // Default 5 minutes
    const now = Date.now();
    for (const [key, alert] of this.alerts.entries()) {
      if (now - alert.timestamp > maxAgeMs) {
        this.alerts.delete(key);
      }
    }
  }

  /**
   * Get current metrics values
   */
  getCurrentValues(): Record<string, MetricValue[]> {
    return Object.fromEntries(this.values.entries());
  }

  /**
   * Cleanup and shutdown
   */
  shutdown(): void {
    if (this.collectionInterval) {
      clearInterval(this.collectionInterval);
    }
    
    this.collectors.clear();
    this.clearOldAlerts(0); // Clear all alerts
    
    logger.info('Advanced metrics collector shutdown completed');
  }
}

// Create singleton instance
export const metricsCollector = AdvancedMetricsCollector.getInstance();

export default AdvancedMetricsCollector;