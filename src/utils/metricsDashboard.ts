/**
 * Comprehensive Metrics Dashboard
 * Provides real-time monitoring of application performance
 */

import { logger } from '@/lib/logger';

interface MetricSnapshot {
  timestamp: number;
  memory: {
    used: number;
    total: number;
    percentage: number;
  };
  performance: {
    loadTime: number;
    apiResponseTime: number;
    renderTime: number;
  };
  cache: {
    hitRate: number;
    missRate: number;
    size: number;
  };
  errors: {
    count: number;
    lastError: string | null;
  };
}

export class MetricsDashboard {
  private snapshots: MetricSnapshot[] = [];
  private maxSnapshots = 100;
  private errorCount = 0;
  private lastError: string | null = null;
  private apiResponseTimes: number[] = [];

  captureSnapshot(): MetricSnapshot {
    const snapshot: MetricSnapshot = {
      timestamp: Date.now(),
      memory: this.getMemoryMetrics(),
      performance: this.getPerformanceMetrics(),
      cache: this.getCacheMetrics(),
      errors: {
        count: this.errorCount,
        lastError: this.lastError
      }
    };

    this.snapshots.push(snapshot);
    
    // Keep only recent snapshots
    if (this.snapshots.length > this.maxSnapshots) {
      this.snapshots.shift();
    }

    return snapshot;
  }

  private getMemoryMetrics() {
    const memInfo = (performance as any).memory;
    if (memInfo) {
      return {
        used: memInfo.usedJSHeapSize,
        total: memInfo.totalJSHeapSize,
        percentage: (memInfo.usedJSHeapSize / memInfo.totalJSHeapSize) * 100
      };
    }
    
    return { used: 0, total: 0, percentage: 0 };
  }

  private getPerformanceMetrics() {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
    
    return {
      loadTime: navigation ? navigation.loadEventEnd - navigation.fetchStart : 0,
      apiResponseTime: this.getAverageApiResponseTime(),
      renderTime: navigation ? navigation.domContentLoadedEventEnd - navigation.fetchStart : 0
    };
  }

  private getCacheMetrics() {
    // This would integrate with your cache manager
    return {
      hitRate: 0.85, // Placeholder
      missRate: 0.15,
      size: 0
    };
  }

  recordApiResponse(responseTime: number): void {
    this.apiResponseTimes.push(responseTime);
    
    // Keep only recent 50 response times
    if (this.apiResponseTimes.length > 50) {
      this.apiResponseTimes.shift();
    }
  }

  recordError(error: string): void {
    this.errorCount++;
    this.lastError = error;
    logger.error('Application error recorded', { error, count: this.errorCount });
  }

  private getAverageApiResponseTime(): number {
    if (this.apiResponseTimes.length === 0) return 0;
    
    const sum = this.apiResponseTimes.reduce((a, b) => a + b, 0);
    return sum / this.apiResponseTimes.length;
  }

  getHealthScore(): number {
    const latest = this.snapshots[this.snapshots.length - 1];
    if (!latest) return 100;

    let score = 100;
    
    // Penalize high memory usage
    if (latest.memory.percentage > 80) score -= 20;
    else if (latest.memory.percentage > 60) score -= 10;
    
    // Penalize slow performance
    if (latest.performance.loadTime > 3000) score -= 15;
    else if (latest.performance.loadTime > 1000) score -= 5;
    
    // Penalize errors
    if (this.errorCount > 10) score -= 30;
    else if (this.errorCount > 5) score -= 15;
    
    return Math.max(0, score);
  }

  getRecentTrends(minutes = 10) {
    const cutoff = Date.now() - (minutes * 60 * 1000);
    const recentSnapshots = this.snapshots.filter(s => s.timestamp > cutoff);
    
    if (recentSnapshots.length === 0) return null;
    
    return {
      memoryTrend: this.calculateTrend(recentSnapshots.map(s => s.memory.percentage)),
      performanceTrend: this.calculateTrend(recentSnapshots.map(s => s.performance.loadTime)),
      errorTrend: this.calculateTrend(recentSnapshots.map(s => s.errors.count))
    };
  }

  private calculateTrend(values: number[]): 'improving' | 'stable' | 'degrading' {
    if (values.length < 2) return 'stable';
    
    const first = values[0];
    const last = values[values.length - 1];
    const change = (last - first) / first;
    
    if (change > 0.1) return 'degrading';
    if (change < -0.1) return 'improving';
    return 'stable';
  }

  exportMetrics() {
    return {
      snapshots: this.snapshots,
      healthScore: this.getHealthScore(),
      trends: this.getRecentTrends(),
      summary: {
        totalSnapshots: this.snapshots.length,
        totalErrors: this.errorCount,
        averageResponseTime: this.getAverageApiResponseTime()
      }
    };
  }
}

export const metricsDashboard = new MetricsDashboard();
