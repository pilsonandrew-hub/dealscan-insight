/**
 * Performance monitoring and optimization utilities
 */

interface PerformanceMetrics {
  operationName: string;
  duration: number;
  timestamp: Date;
  success: boolean;
  errorMessage?: string;
  metadata?: Record<string, any>;
}

interface SystemMetrics {
  memoryUsage: number;
  activeConnections: number;
  queueLength: number;
  errorRate: number;
  averageResponseTime: number;
  requestsPerMinute: number;
}

class PerformanceMonitor {
  private metrics: PerformanceMetrics[] = [];
  private systemMetrics: SystemMetrics = {
    memoryUsage: 0,
    activeConnections: 0,
    queueLength: 0,
    errorRate: 0,
    averageResponseTime: 0,
    requestsPerMinute: 0
  };
  private readonly MAX_METRICS = 500; // Reduced from 1000
  private cleanupInterval: number | null = null;

  constructor() {
    this.startCleanupInterval();
  }

  private startCleanupInterval(): void {
    // Clean up metrics every 5 minutes
    this.cleanupInterval = window.setInterval(() => {
      this.performCleanup();
    }, 5 * 60 * 1000);
  }

  private performCleanup(): void {
    // Keep only recent metrics (last hour)
    const cutoffTime = Date.now() - (60 * 60 * 1000);
    this.metrics = this.metrics.filter(m => m.timestamp.getTime() > cutoffTime);
    
    // Also enforce max size more aggressively
    if (this.metrics.length > this.MAX_METRICS) {
      this.metrics = this.metrics.slice(-this.MAX_METRICS / 2);
    }
  }

  public async measureOperation<T>(
    operationName: string,
    operation: () => Promise<T>,
    metadata?: Record<string, any>
  ): Promise<T> {
    const startTime = Date.now();
    let success = true;
    let errorMessage: string | undefined;

    try {
      const result = await operation();
      return result;
    } catch (error) {
      success = false;
      errorMessage = error instanceof Error ? error.message : 'Unknown error';
      throw error;
    } finally {
      const duration = Date.now() - startTime;
      this.addMetric({
        operationName,
        duration,
        timestamp: new Date(),
        success,
        errorMessage,
        metadata
      });
    }
  }

  private addMetric(metric: PerformanceMetrics): void {
    this.metrics.push(metric);
    
    // Keep only recent metrics with more aggressive cleanup
    if (this.metrics.length > this.MAX_METRICS) {
      // Remove oldest 50% when we hit the limit
      this.metrics = this.metrics.slice(-Math.floor(this.MAX_METRICS * 0.5));
    }
    
    this.updateSystemMetrics();
  }

  private updateSystemMetrics(): void {
    const recentMetrics = this.getRecentMetrics(60000); // Last minute
    
    if (recentMetrics.length === 0) return;
    
    const successful = recentMetrics.filter(m => m.success);
    const failed = recentMetrics.filter(m => !m.success);
    
    this.systemMetrics.errorRate = failed.length / recentMetrics.length;
    this.systemMetrics.averageResponseTime = 
      successful.reduce((sum, m) => sum + m.duration, 0) / Math.max(successful.length, 1);
    this.systemMetrics.requestsPerMinute = recentMetrics.length;
  }

  private getRecentMetrics(timeWindowMs: number): PerformanceMetrics[] {
    const cutoffTime = Date.now() - timeWindowMs;
    return this.metrics.filter(m => m.timestamp.getTime() > cutoffTime);
  }

  public getOperationStats(operationName: string, timeWindowMs = 300000): {
    count: number;
    successRate: number;
    averageDuration: number;
    p95Duration: number;
    errorCount: number;
  } {
    const relevantMetrics = this.getRecentMetrics(timeWindowMs)
      .filter(m => m.operationName === operationName);
    
    if (relevantMetrics.length === 0) {
      return {
        count: 0,
        successRate: 0,
        averageDuration: 0,
        p95Duration: 0,
        errorCount: 0
      };
    }
    
    const successful = relevantMetrics.filter(m => m.success);
    const durations = relevantMetrics.map(m => m.duration).sort((a, b) => a - b);
    const p95Index = Math.floor(durations.length * 0.95);
    
    return {
      count: relevantMetrics.length,
      successRate: successful.length / relevantMetrics.length,
      averageDuration: successful.reduce((sum, m) => sum + m.duration, 0) / Math.max(successful.length, 1),
      p95Duration: durations[p95Index] || 0,
      errorCount: relevantMetrics.length - successful.length
    };
  }

  public getSlowestOperations(limit = 10): PerformanceMetrics[] {
    return [...this.metrics]
      .sort((a, b) => b.duration - a.duration)
      .slice(0, limit);
  }

  public getSystemHealth(): {
    status: 'healthy' | 'degraded' | 'unhealthy';
    metrics: SystemMetrics;
    issues: string[];
  } {
    const issues: string[] = [];
    let status: 'healthy' | 'degraded' | 'unhealthy' = 'healthy';
    
    // Check error rate
    if (this.systemMetrics.errorRate > 0.1) {
      issues.push(`High error rate: ${(this.systemMetrics.errorRate * 100).toFixed(1)}%`);
      status = 'degraded';
    }
    
    if (this.systemMetrics.errorRate > 0.25) {
      status = 'unhealthy';
    }
    
    // Check response time
    if (this.systemMetrics.averageResponseTime > 5000) {
      issues.push(`Slow response time: ${this.systemMetrics.averageResponseTime.toFixed(0)}ms`);
      status = status === 'unhealthy' ? 'unhealthy' : 'degraded';
    }
    
    if (this.systemMetrics.averageResponseTime > 10000) {
      status = 'unhealthy';
    }
    
    // Check memory usage (if available)
    if (this.systemMetrics.memoryUsage > 0.8) {
      issues.push(`High memory usage: ${(this.systemMetrics.memoryUsage * 100).toFixed(1)}%`);
      status = status === 'unhealthy' ? 'unhealthy' : 'degraded';
    }
    
    return {
      status,
      metrics: { ...this.systemMetrics },
      issues
    };
  }

  public generateReport(): string {
    const health = this.getSystemHealth();
    const recentMetrics = this.getRecentMetrics(300000); // Last 5 minutes
    const operationTypes = [...new Set(recentMetrics.map(m => m.operationName))];
    
    let report = `Performance Report - ${new Date().toISOString()}\n`;
    report += `System Status: ${health.status.toUpperCase()}\n`;
    
    if (health.issues.length > 0) {
      report += `Issues: ${health.issues.join(', ')}\n`;
    }
    
    report += `\nSystem Metrics:\n`;
    report += `- Error Rate: ${(health.metrics.errorRate * 100).toFixed(1)}%\n`;
    report += `- Avg Response Time: ${health.metrics.averageResponseTime.toFixed(0)}ms\n`;
    report += `- Requests/min: ${health.metrics.requestsPerMinute}\n`;
    
    report += `\nOperation Breakdown:\n`;
    for (const opName of operationTypes) {
      const stats = this.getOperationStats(opName);
      report += `- ${opName}: ${stats.count} calls, ${(stats.successRate * 100).toFixed(1)}% success, ${stats.averageDuration.toFixed(0)}ms avg\n`;
    }
    
    return report;
  }

  public clearMetrics(): void {
    this.metrics = [];
    this.systemMetrics = {
      memoryUsage: 0,
      activeConnections: 0,
      queueLength: 0,
      errorRate: 0,
      averageResponseTime: 0,
      requestsPerMinute: 0
    };
  }

  public cleanup(): void {
    this.performCleanup();
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
      this.cleanupInterval = null;
    }
  }

  // Backward compatibility methods
  public startTimer(operationName?: string): { end: (success?: boolean) => number } {
    const startTime = Date.now();
    const opName = operationName || 'operation';
    return {
      end: (success: boolean = true) => {
        const duration = Date.now() - startTime;
        this.addMetric({
          operationName: opName,
          duration,
          timestamp: new Date(),
          success
        });
        return duration;
      }
    };
  }

  public monitorAPI(operationName: string, method: string): { end: (success?: boolean) => number } {
    const startTime = Date.now();
    return {
      end: (success: boolean = true) => {
        const duration = Date.now() - startTime;
        this.addMetric({
          operationName: `${operationName}_${method}`,
          duration,
          timestamp: new Date(),
          success
        });
        return duration;
      }
    };
  }

  public getStats(operationName?: string): any {
    if (operationName) {
      const opStats = this.getOperationStats(operationName);
      return {
        ...opStats,
        averageResponseTime: opStats.averageDuration,
        overallSuccessRate: opStats.successRate
      };
    }
    
    const systemHealth = this.getSystemHealth();
    return {
      averageResponseTime: systemHealth.metrics.averageResponseTime,
      overallSuccessRate: 1 - systemHealth.metrics.errorRate,
      requestsPerMinute: systemHealth.metrics.requestsPerMinute,
      ...systemHealth.metrics
    };
  }

  public recordMetric(operationName: string, duration: number, metadata?: any): void {
    this.addMetric({
      operationName,
      duration,
      timestamp: new Date(),
      success: true,
      metadata
    });
  }
}

// Singleton instance
export const performanceMonitor = new PerformanceMonitor();

// Decorator for automatic performance monitoring
export function monitored(operationName?: string) {
  return function <T extends (...args: any[]) => Promise<any>>(
    target: any,
    propertyName: string,
    descriptor: TypedPropertyDescriptor<T>
  ) {
    const method = descriptor.value!;
    const name = operationName || `${target.constructor.name}.${propertyName}`;
    
    descriptor.value = async function (...args: any[]) {
      return performanceMonitor.measureOperation(
        name,
        () => method.apply(this, args),
        { args: args.length }
      );
    } as any;
  };
}

// Utility functions
export const withPerformanceMonitoring = async <T>(
  operationName: string,
  operation: () => Promise<T>,
  metadata?: Record<string, any>
): Promise<T> => {
  return performanceMonitor.measureOperation(operationName, operation, metadata);
};

export const getPerformanceReport = (): string => {
  return performanceMonitor.generateReport();
};

export const clearPerformanceMetrics = (): void => {
  performanceMonitor.clearMetrics();
};
