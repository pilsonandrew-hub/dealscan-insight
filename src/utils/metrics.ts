/**
 * Production Metrics Collection & SLO Monitoring
 * Tracks system performance and triggers in-app alerts for SLO breaches
 */

import { supabase } from '@/integrations/supabase/client';
import { inHouseAlertSystem } from '@/lib/alerts/alertSystem';

export interface PerformanceMetric {
  name: string;
  value: number;
  unit: string;
  timestamp: string;
  tags: Record<string, string>;
}

export interface SLODefinition {
  name: string;
  description: string;
  target: number;
  window: string; // e.g., '5m', '1h', '1d'
  alertThreshold: number;
  errorBudget: number;
}

export interface SLOStatus {
  slo: SLODefinition;
  currentValue: number;
  errorBudgetRemaining: number;
  breaching: boolean;
  lastBreach?: string;
}

/**
 * Core metrics collection service
 */
export class MetricsCollector {
  private metrics: PerformanceMetric[] = [];
  private batchSize = 100;
  private flushInterval = 30000; // 30 seconds
  private timers: Map<string, number> = new Map();

  constructor() {
    // Flush metrics periodically
    setInterval(() => this.flush(), this.flushInterval);
    
    // Flush on page unload
    window.addEventListener('beforeunload', () => this.flush());
  }

  /**
   * Record a performance metric
   */
  metric(name: string, value: number, unit: string = 'count', tags: Record<string, string> = {}): void {
    this.metrics.push({
      name,
      value,
      unit,
      timestamp: new Date().toISOString(),
      tags: {
        ...tags,
        user_agent: navigator.userAgent.split(' ')[0], // Browser name only
        page: window.location.pathname,
      }
    });

    if (this.metrics.length >= this.batchSize) {
      this.flush();
    }
  }

  /**
   * Start a timer for duration measurements
   */
  startTimer(name: string): void {
    this.timers.set(name, performance.now());
  }

  /**
   * End a timer and record the duration
   */
  endTimer(name: string, tags: Record<string, string> = {}): number {
    const startTime = this.timers.get(name);
    if (!startTime) {
      console.warn(`Timer '${name}' was not started`);
      return 0;
    }

    const duration = performance.now() - startTime;
    this.timers.delete(name);
    
    this.metric(`${name}.duration`, duration, 'ms', tags);
    return duration;
  }

  /**
   * Record page load metrics
   */
  recordPageLoad(): void {
    if (typeof window !== 'undefined' && window.performance) {
      const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
      
      if (navigation) {
        this.metric('page.load_time', navigation.loadEventEnd - navigation.fetchStart, 'ms');
        this.metric('page.dom_content_loaded', navigation.domContentLoadedEventEnd - navigation.fetchStart, 'ms');
        this.metric('page.first_byte', navigation.responseStart - navigation.fetchStart, 'ms');
        this.metric('page.dns_lookup', navigation.domainLookupEnd - navigation.domainLookupStart, 'ms');
        this.metric('page.tcp_connect', navigation.connectEnd - navigation.connectStart, 'ms');
      }
    }
  }

  /**
   * Record API call metrics
   */
  recordAPICall(endpoint: string, method: string, statusCode: number, duration: number): void {
    this.metric('api.request', 1, 'count', {
      endpoint,
      method,
      status_code: String(statusCode),
      status_class: `${Math.floor(statusCode / 100)}xx`
    });
    
    this.metric('api.duration', duration, 'ms', {
      endpoint,
      method
    });

    if (statusCode >= 400) {
      this.metric('api.error', 1, 'count', {
        endpoint,
        method,
        status_code: String(statusCode)
      });
    }
  }

  /**
   * Record scraping job metrics
   */
  recordScrapingJob(siteId: string, success: boolean, duration: number, vehiclesFound: number): void {
    this.metric('scraping.job', 1, 'count', {
      site_id: siteId,
      success: String(success)
    });

    this.metric('scraping.duration', duration, 'ms', { site_id: siteId });
    
    if (success) {
      this.metric('scraping.vehicles_found', vehiclesFound, 'count', { site_id: siteId });
    }
  }

  /**
   * Record alert metrics
   */
  recordAlert(type: string, priority: string, userId: string): void {
    this.metric('alerts.sent', 1, 'count', {
      type,
      priority,
      user_id: userId
    });
  }

  /**
   * Flush metrics to database
   */
  private async flush(): Promise<void> {
    if (this.metrics.length === 0) return;

    const metricsToFlush = [...this.metrics];
    this.metrics = [];

    try {
      // For now, just log metrics. In production, send to external monitoring service
      console.log('Metrics flush:', metricsToFlush);
      
      // TODO: Implement actual metrics storage after types are regenerated
      // const { error } = await supabase
      //   .from('pipeline_metrics')
      //   .insert(metricsToFlush.map(metric => ({
      //     metric_name: metric.name,
      //     metric_value: metric.value,
      //     metric_unit: metric.unit,
      //     tags: metric.tags,
      //     created_at: metric.timestamp
      //   })));

    } catch (error) {
      console.error('Error flushing metrics:', error);
    }
  }
}

/**
 * SLO monitoring service
 */
export class SLOMonitor {
  private slos: SLODefinition[] = [
    {
      name: 'page_load_time',
      description: 'Page load time should be under 2 seconds',
      target: 2000, // 2 seconds
      window: '5m',
      alertThreshold: 0.05, // Alert if 5% of requests exceed target
      errorBudget: 0.01 // 1% error budget
    },
    {
      name: 'api_success_rate',
      description: 'API success rate should be above 99%',
      target: 0.99, // 99%
      window: '5m',
      alertThreshold: 0.95, // Alert if below 95%
      errorBudget: 0.01 // 1% error budget
    },
    {
      name: 'scraping_success_rate',
      description: 'Scraping success rate should be above 95%',
      target: 0.95, // 95%
      window: '15m',
      alertThreshold: 0.90, // Alert if below 90%
      errorBudget: 0.05 // 5% error budget
    },
    {
      name: 'alert_delivery_time',
      description: 'Alerts should be delivered within 1 second',
      target: 1000, // 1 second
      window: '5m',
      alertThreshold: 0.1, // Alert if 10% exceed target
      errorBudget: 0.05 // 5% error budget
    }
  ];

  private lastCheck: Map<string, Date> = new Map();

  /**
   * Check all SLOs and trigger alerts if breaching
   */
  async checkSLOs(userId?: string): Promise<SLOStatus[]> {
    const results: SLOStatus[] = [];

    for (const slo of this.slos) {
      try {
        const status = await this.checkSLO(slo);
        results.push(status);

        // Trigger alert if breaching and we haven't alerted recently
        if (status.breaching && this.shouldAlert(slo.name)) {
          await this.triggerSLOAlert(slo, status, userId);
          this.lastCheck.set(slo.name, new Date());
        }
      } catch (error) {
        console.error(`Failed to check SLO ${slo.name}:`, error);
      }
    }

    return results;
  }

  /**
   * Check individual SLO
   */
  private async checkSLO(slo: SLODefinition): Promise<SLOStatus> {
    const windowMs = this.parseTimeWindow(slo.window);
    const since = new Date(Date.now() - windowMs).toISOString();

    let currentValue: number;
    let breaching: boolean;

    switch (slo.name) {
      case 'page_load_time':
        currentValue = await this.getPageLoadP95(since);
        breaching = currentValue > slo.target;
        break;

      case 'api_success_rate':
        currentValue = await this.getAPISuccessRate(since);
        breaching = currentValue < slo.target;
        break;

      case 'scraping_success_rate':
        currentValue = await this.getScrapingSuccessRate(since);
        breaching = currentValue < slo.target;
        break;

      case 'alert_delivery_time':
        currentValue = await this.getAlertDeliveryP95(since);
        breaching = currentValue > slo.target;
        break;

      default:
        currentValue = 0;
        breaching = false;
    }

    const errorBudgetRemaining = breaching ? 0 : slo.errorBudget;

    return {
      slo,
      currentValue,
      errorBudgetRemaining,
      breaching,
      lastBreach: breaching ? new Date().toISOString() : undefined
    };
  }

  /**
   * Get 95th percentile page load time (mock implementation)
   */
  private async getPageLoadP95(since: string): Promise<number> {
    // Mock implementation until DB types are updated
    return Math.random() * 3000; // 0-3s
  }

  /**
   * Get API success rate (mock implementation)
   */
  private async getAPISuccessRate(since: string): Promise<number> {
    // Mock implementation until DB types are updated
    return 0.99; // 99% success rate
  }

  /**
   * Get scraping success rate (mock implementation)
   */
  private async getScrapingSuccessRate(since: string): Promise<number> {
    // Mock implementation until DB types are updated
    return 0.95; // 95% success rate
  }

  /**
   * Get 95th percentile alert delivery time
   */
  private async getAlertDeliveryP95(since: string): Promise<number> {
    // This would track time from alert creation to delivery
    // For now, return a mock value
    return 500; // 500ms
  }

  /**
   * Trigger SLO breach alert
   */
  private async triggerSLOAlert(slo: SLODefinition, status: SLOStatus, userId?: string): Promise<void> {
    if (!userId) return;

    // Create an in-app alert for SLO breach
    const opportunity = {
      id: `slo_breach_${slo.name}_${Date.now()}`,
      profit: 0,
      roi: 0,
      risk_score: 100,
      confidence: 100
    };

    await inHouseAlertSystem.createAlert(
      opportunity,
      userId,
      'hot_deal' // Use hot_deal for critical SLO breaches
    );
  }

  /**
   * Check if we should alert (rate limiting)
   */
  private shouldAlert(sloName: string): boolean {
    const lastAlert = this.lastCheck.get(sloName);
    if (!lastAlert) return true;

    // Don't alert more than once every 15 minutes
    return Date.now() - lastAlert.getTime() > 15 * 60 * 1000;
  }

  /**
   * Parse time window string to milliseconds
   */
  private parseTimeWindow(window: string): number {
    const match = window.match(/^(\d+)([smhd])$/);
    if (!match) return 300000; // Default 5 minutes

    const value = parseInt(match[1]);
    const unit = match[2];

    switch (unit) {
      case 's': return value * 1000;
      case 'm': return value * 60 * 1000;
      case 'h': return value * 60 * 60 * 1000;
      case 'd': return value * 24 * 60 * 60 * 1000;
      default: return 300000;
    }
  }
}

// Global instances
export const metricsCollector = new MetricsCollector();
export const sloMonitor = new SLOMonitor();

// Convenience functions
export const recordMetric = (name: string, value: number, unit?: string, tags?: Record<string, string>) => 
  metricsCollector.metric(name, value, unit, tags);

export const startTimer = (name: string) => metricsCollector.startTimer(name);
export const endTimer = (name: string, tags?: Record<string, string>) => metricsCollector.endTimer(name, tags);