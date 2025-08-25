/**
 * SLO Monitoring - Signal detection for red-bubble alerts
 * Tracks performance metrics and triggers alerts on SLA breaches
 */

import { logger } from '@/lib/logger';

export interface SLOMetrics {
  p50ResponseTime: number;
  p95ResponseTime: number;
  errorRate: number;
  driftDetected: boolean;
  budgetPercentage: number;
  successRate: number;
  extractionAccuracy: number;
  freshness: number; // Hours since last update
  uptime: number; // Percentage
}

export interface SLOThresholds {
  p95ResponseTimeMs: number;
  maxErrorRate: number;
  maxBudgetPercentage: number;
  minSuccessRate: number;
  minExtractionAccuracy: number;
  maxFreshnessHours: number;
  minUptime: number;
}

export interface SLOBreach {
  siteId: string;
  metric: keyof SLOMetrics;
  currentValue: number;
  thresholdValue: number;
  severity: 'warning' | 'critical';
  timestamp: string;
  description: string;
}

// Default SLO thresholds based on acceptance criteria
const DEFAULT_THRESHOLDS: SLOThresholds = {
  p95ResponseTimeMs: 12000,    // p95 ≤ 12s headless
  maxErrorRate: 0.05,          // < 5% error rate
  maxBudgetPercentage: 0.8,    // 80% budget usage warning
  minSuccessRate: 0.95,        // ≥ 95% success rate
  minExtractionAccuracy: 0.97, // ≥ 97% extraction success
  maxFreshnessHours: 24,       // 75th percentile recrawl < 24h
  minUptime: 0.99              // 99% uptime
};

class SLOMonitor {
  private thresholds: SLOThresholds = DEFAULT_THRESHOLDS;
  private metricsHistory = new Map<string, SLOMetrics[]>();

  /**
   * Check SLOs for a site and trigger alerts if breached
   */
  async checkSLOs(siteId: string, metrics: SLOMetrics): Promise<SLOBreach[]> {
    const breaches: SLOBreach[] = [];
    const timestamp = new Date().toISOString();

    // Store metrics history
    this.storeMetrics(siteId, metrics);

    // Check each SLO threshold
    const checks = [
      {
        metric: 'p95ResponseTime' as keyof SLOMetrics,
        current: metrics.p95ResponseTime,
        threshold: this.thresholds.p95ResponseTimeMs,
        operator: '>',
        description: `P95 response time ${metrics.p95ResponseTime}ms exceeds ${this.thresholds.p95ResponseTimeMs}ms threshold`
      },
      {
        metric: 'errorRate' as keyof SLOMetrics,
        current: metrics.errorRate,
        threshold: this.thresholds.maxErrorRate,
        operator: '>',
        description: `Error rate ${(metrics.errorRate * 100).toFixed(1)}% exceeds ${(this.thresholds.maxErrorRate * 100).toFixed(1)}% threshold`
      },
      {
        metric: 'budgetPercentage' as keyof SLOMetrics,
        current: metrics.budgetPercentage,
        threshold: this.thresholds.maxBudgetPercentage,
        operator: '>',
        description: `Budget usage ${(metrics.budgetPercentage * 100).toFixed(1)}% exceeds ${(this.thresholds.maxBudgetPercentage * 100).toFixed(1)}% threshold`
      },
      {
        metric: 'successRate' as keyof SLOMetrics,
        current: metrics.successRate,
        threshold: this.thresholds.minSuccessRate,
        operator: '<',
        description: `Success rate ${(metrics.successRate * 100).toFixed(1)}% below ${(this.thresholds.minSuccessRate * 100).toFixed(1)}% threshold`
      },
      {
        metric: 'extractionAccuracy' as keyof SLOMetrics,
        current: metrics.extractionAccuracy,
        threshold: this.thresholds.minExtractionAccuracy,
        operator: '<',
        description: `Extraction accuracy ${(metrics.extractionAccuracy * 100).toFixed(1)}% below ${(this.thresholds.minExtractionAccuracy * 100).toFixed(1)}% threshold`
      },
      {
        metric: 'freshness' as keyof SLOMetrics,
        current: metrics.freshness,
        threshold: this.thresholds.maxFreshnessHours,
        operator: '>',
        description: `Data freshness ${metrics.freshness.toFixed(1)}h exceeds ${this.thresholds.maxFreshnessHours}h threshold`
      },
      {
        metric: 'uptime' as keyof SLOMetrics,
        current: metrics.uptime,
        threshold: this.thresholds.minUptime,
        operator: '<',
        description: `Uptime ${(metrics.uptime * 100).toFixed(2)}% below ${(this.thresholds.minUptime * 100).toFixed(2)}% threshold`
      }
    ];

    // Special check for drift detection
    if (metrics.driftDetected) {
      breaches.push({
        siteId,
        metric: 'driftDetected',
        currentValue: 1,
        thresholdValue: 0,
        severity: 'critical',
        timestamp,
        description: 'Model drift detected - extraction confidence has dropped significantly'
      });
    }

    // Evaluate each threshold
    for (const check of checks) {
      const isBreached = check.operator === '>' 
        ? check.current > check.threshold
        : check.current < check.threshold;

      if (isBreached) {
        const severity = this.determineSeverity(check.metric, check.current, check.threshold);
        
        breaches.push({
          siteId,
          metric: check.metric,
          currentValue: check.current,
          thresholdValue: check.threshold,
          severity,
          timestamp,
          description: check.description
        });
      }
    }

    // Log SLO status
    if (breaches.length > 0) {
      logger.warn('SLO breaches detected', {
        siteId,
        breachCount: breaches.length,
        breaches: breaches.map(b => `${b.metric}: ${b.description}`)
      });

      // Create alerts for critical breaches
      await this.createSLOAlerts(siteId, breaches);
    } else {
      logger.debug('All SLOs passing', { siteId, metrics });
    }

    return breaches;
  }

  /**
   * Create red-bubble alerts for SLO breaches
   */
  private async createSLOAlerts(siteId: string, breaches: SLOBreach[]): Promise<void> {
    for (const breach of breaches) {
      if (breach.severity === 'critical') {
        try {
          // Log critical SLO breach for now - alert system integration pending
          logger.error('Critical SLO breach detected', undefined, {
            siteId,
            metric: breach.metric,
            currentValue: breach.currentValue,
            threshold: breach.thresholdValue,
            description: breach.description,
            timestamp: breach.timestamp
          });

          logger.info('SLO breach alert created', {
            siteId,
            metric: breach.metric,
            severity: breach.severity
          });
        } catch (error) {
          logger.error('Failed to create SLO breach alert', error, {
            siteId,
            breach: breach.metric
          });
        }
      }
    }
  }

  /**
   * Determine severity based on metric and threshold breach
   */
  private determineSeverity(metric: keyof SLOMetrics, current: number, threshold: number): 'warning' | 'critical' {
    const breachPercentage = Math.abs(current - threshold) / threshold;

    // Critical thresholds (immediate action required)
    if (
      metric === 'errorRate' && current > 0.1 || // >10% error rate
      metric === 'uptime' && current < 0.95 ||   // <95% uptime
      metric === 'extractionAccuracy' && current < 0.90 || // <90% accuracy
      breachPercentage > 0.5 // >50% threshold breach
    ) {
      return 'critical';
    }

    return 'warning';
  }

  /**
   * Store metrics history for trend analysis
   */
  private storeMetrics(siteId: string, metrics: SLOMetrics): void {
    if (!this.metricsHistory.has(siteId)) {
      this.metricsHistory.set(siteId, []);
    }

    const history = this.metricsHistory.get(siteId)!;
    history.push({
      ...metrics,
      timestamp: Date.now()
    } as SLOMetrics & { timestamp: number });

    // Keep only last 100 measurements
    if (history.length > 100) {
      history.shift();
    }
  }

  /**
   * Get SLO dashboard data
   */
  getSLODashboard(siteIds: string[]): Array<{
    siteId: string;
    status: 'healthy' | 'warning' | 'critical';
    metrics: SLOMetrics;
    breaches: SLOBreach[];
    trend: 'improving' | 'stable' | 'degrading';
  }> {
    return siteIds.map(siteId => {
      const history = this.metricsHistory.get(siteId) || [];
      const latest = history[history.length - 1];
      
      if (!latest) {
        return {
          siteId,
          status: 'warning' as const,
          metrics: this.getDefaultMetrics(),
          breaches: [],
          trend: 'stable' as const
        };
      }

      // Calculate current breaches
      const breaches = this.checkSLOsSync(siteId, latest);
      
      // Determine overall status
      const hasCritical = breaches.some(b => b.severity === 'critical');
      const hasWarning = breaches.some(b => b.severity === 'warning');
      const status = hasCritical ? 'critical' : hasWarning ? 'warning' : 'healthy';

      // Calculate trend
      const trend = this.calculateTrend(history);

      return {
        siteId,
        status,
        metrics: latest,
        breaches,
        trend
      };
    });
  }

  /**
   * Synchronous SLO check for dashboard
   */
  private checkSLOsSync(siteId: string, metrics: SLOMetrics): SLOBreach[] {
    // Simplified sync version of checkSLOs for dashboard
    const breaches: SLOBreach[] = [];
    const timestamp = new Date().toISOString();

    if (metrics.p95ResponseTime > this.thresholds.p95ResponseTimeMs) {
      breaches.push({
        siteId,
        metric: 'p95ResponseTime',
        currentValue: metrics.p95ResponseTime,
        thresholdValue: this.thresholds.p95ResponseTimeMs,
        severity: 'warning',
        timestamp,
        description: `P95 response time exceeds threshold`
      });
    }

    if (metrics.errorRate > this.thresholds.maxErrorRate) {
      breaches.push({
        siteId,
        metric: 'errorRate',
        currentValue: metrics.errorRate,
        thresholdValue: this.thresholds.maxErrorRate,
        severity: metrics.errorRate > 0.1 ? 'critical' : 'warning',
        timestamp,
        description: `Error rate exceeds threshold`
      });
    }

    // Add other checks as needed...

    return breaches;
  }

  /**
   * Calculate performance trend
   */
  private calculateTrend(history: SLOMetrics[]): 'improving' | 'stable' | 'degrading' {
    if (history.length < 2) return 'stable';

    const recent = history.slice(-5); // Last 5 measurements
    const older = history.slice(-10, -5); // Previous 5 measurements

    if (recent.length === 0 || older.length === 0) return 'stable';

    const recentAvg = recent.reduce((sum, m) => sum + m.successRate, 0) / recent.length;
    const olderAvg = older.reduce((sum, m) => sum + m.successRate, 0) / older.length;

    const change = recentAvg - olderAvg;
    
    if (change > 0.02) return 'improving';
    if (change < -0.02) return 'degrading';
    return 'stable';
  }

  /**
   * Get default metrics for missing data
   */
  private getDefaultMetrics(): SLOMetrics {
    return {
      p50ResponseTime: 0,
      p95ResponseTime: 0,
      errorRate: 0,
      driftDetected: false,
      budgetPercentage: 0,
      successRate: 0,
      extractionAccuracy: 0,
      freshness: 0,
      uptime: 0
    };
  }

  /**
   * Update SLO thresholds
   */
  setThresholds(newThresholds: Partial<SLOThresholds>): void {
    this.thresholds = { ...this.thresholds, ...newThresholds };
    logger.info('SLO thresholds updated', { thresholds: this.thresholds });
  }

  /**
   * Get current thresholds
   */
  getThresholds(): SLOThresholds {
    return { ...this.thresholds };
  }
}

// Singleton instance
export const sloMonitor = new SLOMonitor();

export default sloMonitor;
