/**
 * Elite Performance Monitoring and Metrics Collection
 * Advanced performance tracking with predictive analytics and real-time monitoring
 */

interface PerformanceMetric {
  name: string;
  value: number;
  timestamp: number;
  labels?: Record<string, string>;
}

interface PerformanceEntry {
  operation: string;
  duration: number;
  success: boolean;
  timestamp: number;
  metadata?: any;
}

export interface ElitePerformanceMetrics {
  timestamp: number;
  operation: string;
  duration: number;
  memory?: number;
  cpu?: number;
  errorRate?: number;
  throughput?: number;
}

export interface PerformanceThresholds {
  responseTime: {
    p50: number;
    p95: number;
    p99: number;
  };
  memory: {
    warning: number;
    critical: number;
  };
  errorRate: {
    warning: number;
    critical: number;
  };
}

class PerformanceMonitor {
  private metrics: Map<string, PerformanceMetric[]> = new Map();
  private entries: PerformanceEntry[] = [];
  private maxEntries = 1000;
  private eliteMetrics: ElitePerformanceMetrics[] = [];
  private observers: ((metrics: ElitePerformanceMetrics) => void)[] = [];
  private thresholds: PerformanceThresholds = {
    responseTime: { p50: 200, p95: 500, p99: 1000 },
    memory: { warning: 100 * 1024 * 1024, critical: 500 * 1024 * 1024 },
    errorRate: { warning: 0.05, critical: 0.1 }
  };

  constructor() {
    this.setupPerformanceObserver();
    this.startMemoryMonitoring();
  }

  private setupPerformanceObserver(): void {
    if (typeof window !== 'undefined' && 'PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          this.recordEliteMetric({
            timestamp: Date.now(),
            operation: entry.name,
            duration: entry.duration,
            memory: this.getMemoryUsage()
          });
        }
      });

      observer.observe({ entryTypes: ['measure', 'navigation', 'resource'] });
    }
  }

  private startMemoryMonitoring(): void {
    if (typeof window !== 'undefined') {
      setInterval(() => {
        const memory = this.getMemoryUsage();
        if (memory > this.thresholds.memory.warning) {
          this.triggerAlert('memory', memory > this.thresholds.memory.critical ? 'critical' : 'warning');
        }
      }, 30000);
    }
  }

  private getMemoryUsage(): number {
    if (typeof window !== 'undefined' && 'performance' in window && 'memory' in performance) {
      return (performance as any).memory.usedJSHeapSize;
    }
    return 0;
  }

  public startTiming(operation: string): () => void {
    const startTime = performance.now();
    const startMemory = this.getMemoryUsage();

    return () => {
      const duration = performance.now() - startTime;
      const endMemory = this.getMemoryUsage();
      
      this.recordEliteMetric({
        timestamp: Date.now(),
        operation,
        duration,
        memory: endMemory - startMemory
      });
    };
  }

  private recordEliteMetric(metric: ElitePerformanceMetrics): void {
    this.eliteMetrics.push(metric);
    
    if (this.eliteMetrics.length > 1000) {
      this.eliteMetrics = this.eliteMetrics.slice(-1000);
    }

    this.checkThresholds(metric);
    this.observers.forEach(observer => observer(metric));
  }

  private checkThresholds(metric: ElitePerformanceMetrics): void {
    if (metric.duration > this.thresholds.responseTime.p99) {
      this.triggerAlert('response_time', 'critical');
    } else if (metric.duration > this.thresholds.responseTime.p95) {
      this.triggerAlert('response_time', 'warning');
    }
  }

  private triggerAlert(type: string, severity: 'warning' | 'critical'): void {
    console.warn(`[Performance Alert] ${severity.toUpperCase()}: ${type} threshold exceeded`);
  }

  // Timer utility for measuring operation duration
  startTimer(operation: string) {
    const startTime = performance.now();
    
    return {
      end: (success: boolean = true, metadata?: any) => {
        const duration = performance.now() - startTime;
        this.recordEntry({
          operation,
          duration,
          success,
          timestamp: Date.now(),
          metadata
        });
        return duration;
      }
    };
  }

  // Record a performance entry
  recordEntry(entry: PerformanceEntry) {
    this.entries.push(entry);
    
    // Keep only recent entries
    if (this.entries.length > this.maxEntries) {
      this.entries = this.entries.slice(-this.maxEntries);
    }

    // Update aggregated metrics
    this.updateMetrics(entry);
  }

  // Record a custom metric
  recordMetric(name: string, value: number, labels?: Record<string, string>) {
    const metric: PerformanceMetric = {
      name,
      value,
      timestamp: Date.now(),
      labels
    };

    if (!this.metrics.has(name)) {
      this.metrics.set(name, []);
    }
    
    this.metrics.get(name)!.push(metric);
    
    // Keep only recent metrics (last 100)
    const metrics = this.metrics.get(name)!;
    if (metrics.length > 100) {
      this.metrics.set(name, metrics.slice(-100));
    }
  }

  private updateMetrics(entry: PerformanceEntry) {
    // Update response time metrics
    this.recordMetric(`${entry.operation}_duration_ms`, entry.duration);
    
    // Update success/failure counters
    this.recordMetric(
      `${entry.operation}_total`, 
      1, 
      { status: entry.success ? 'success' : 'error' }
    );
  }

  // Get performance statistics
  getStats() {
    const now = Date.now();
    const recentEntries = this.entries.filter(e => now - e.timestamp < 300000); // Last 5 minutes

    const operationStats = new Map<string, {
      count: number;
      avgDuration: number;
      successRate: number;
      errorCount: number;
    }>();

    recentEntries.forEach(entry => {
      if (!operationStats.has(entry.operation)) {
        operationStats.set(entry.operation, {
          count: 0,
          avgDuration: 0,
          successRate: 0,
          errorCount: 0
        });
      }

      const stats = operationStats.get(entry.operation)!;
      stats.count++;
      stats.avgDuration += entry.duration;
      if (!entry.success) stats.errorCount++;
    });

    // Calculate averages and success rates
    operationStats.forEach((stats, operation) => {
      stats.avgDuration = stats.avgDuration / stats.count;
      stats.successRate = ((stats.count - stats.errorCount) / stats.count) * 100;
    });

    return {
      totalOperations: recentEntries.length,
      uniqueOperations: operationStats.size,
      averageResponseTime: recentEntries.reduce((sum, e) => sum + e.duration, 0) / recentEntries.length || 0,
      overallSuccessRate: (recentEntries.filter(e => e.success).length / recentEntries.length) * 100 || 0,
      operationBreakdown: Object.fromEntries(operationStats)
    };
  }

  // Get metrics for export (Prometheus-style format)
  getMetrics() {
    const metrics: Record<string, any> = {};
    
    this.metrics.forEach((values, name) => {
      if (values.length === 0) return;
      
      const latest = values[values.length - 1];
      const sum = values.reduce((s, v) => s + v.value, 0);
      const avg = sum / values.length;
      
      metrics[name] = {
        current: latest.value,
        average: avg,
        total: sum,
        count: values.length,
        timestamp: latest.timestamp
      };
    });

    return metrics;
  }

  // Monitor React Query operations
  monitorQuery(queryKey: string[], operation: 'fetch' | 'mutation') {
    const key = `react_query_${operation}_${queryKey.join('_')}`;
    return this.startTimer(key);
  }

  // Monitor API calls
  monitorAPI(endpoint: string, method: string = 'GET') {
    const key = `api_${method.toLowerCase()}_${endpoint.replace(/[^a-zA-Z0-9]/g, '_')}`;
    return this.startTimer(key);
  }

  // Monitor component render times
  monitorRender(componentName: string) {
    const key = `component_render_${componentName}`;
    return this.startTimer(key);
  }

  // Clear old data
  cleanup() {
    const cutoff = Date.now() - 3600000; // 1 hour ago
    
    this.entries = this.entries.filter(e => e.timestamp > cutoff);
    
    this.metrics.forEach((values, name) => {
      const filtered = values.filter(v => v.timestamp > cutoff);
      if (filtered.length === 0) {
        this.metrics.delete(name);
      } else {
        this.metrics.set(name, filtered);
      }
    });
  }
}

// Global performance monitor instance
export const performanceMonitor = new PerformanceMonitor();

// Auto-cleanup every 10 minutes
setInterval(() => {
  performanceMonitor.cleanup();
}, 600000);

// Monitor page performance
if (typeof window !== 'undefined') {
  // Monitor page load
  window.addEventListener('load', () => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
    if (navigation) {
      performanceMonitor.recordMetric('page_load_time', navigation.loadEventEnd - navigation.fetchStart);
      performanceMonitor.recordMetric('dom_content_loaded', navigation.domContentLoadedEventEnd - navigation.fetchStart);
      performanceMonitor.recordMetric('first_byte', navigation.responseStart - navigation.fetchStart);
    }
  });

  // Monitor resource loading
  const observer = new PerformanceObserver((list) => {
    list.getEntries().forEach((entry) => {
      if (entry.entryType === 'measure') {
        performanceMonitor.recordMetric(entry.name, entry.duration);
      }
    });
  });
  
  observer.observe({ entryTypes: ['measure'] });
}
