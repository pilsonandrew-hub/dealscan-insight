/**
 * Minimal performance monitoring utility.
 * Current live surface is limited to upload timing around startTimer() and monitorAPI().
 */

interface PerformanceMetric {
  operationName: string;
  duration: number;
  timestamp: number;
  success: boolean;
}

class PerformanceMonitor {
  private metrics: PerformanceMetric[] = [];
  private cleanupInterval: number | null = null;
  private readonly MAX_METRICS = 500;

  constructor() {
    this.cleanupInterval = window.setInterval(() => {
      this.cleanup();
    }, 5 * 60 * 1000);
  }

  startTimer(operationName = 'operation'): { end: (success?: boolean) => number } {
    const startTime = performance.now();

    return {
      end: (success = true) => {
        const duration = performance.now() - startTime;
        this.record(operationName, duration, success);
        return duration;
      }
    };
  }

  monitorAPI(operationName: string, method: string): { end: (success?: boolean) => number } {
    return this.startTimer(`${operationName}_${method}`);
  }

  private record(operationName: string, duration: number, success: boolean): void {
    this.metrics.push({
      operationName,
      duration,
      timestamp: Date.now(),
      success,
    });

    if (this.metrics.length > this.MAX_METRICS) {
      this.metrics = this.metrics.slice(-Math.floor(this.MAX_METRICS / 2));
    }
  }

  private cleanup(): void {
    const cutoff = Date.now() - 60 * 60 * 1000;
    this.metrics = this.metrics.filter(metric => metric.timestamp > cutoff);
  }
}

export const performanceMonitor = new PerformanceMonitor();
