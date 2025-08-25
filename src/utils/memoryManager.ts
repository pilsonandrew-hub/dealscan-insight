/**
 * Memory Management and Monitoring Utilities
 * Prevents memory leaks and monitors usage in production
 */

interface MemoryStats {
  usedJSHeapSize: number;
  totalJSHeapSize: number;
  jsHeapSizeLimit: number;
}

interface MemoryManagerConfig {
  maxMemoryMB: number;
  cleanupIntervalMs: number;
  warningThresholdMB: number;
  enableMonitoring: boolean;
}

class MemoryManager {
  private config: MemoryManagerConfig;
  private monitoringInterval: number | null = null;
  private cleanupCallbacks: (() => void)[] = [];
  private memoryHistory: { timestamp: number; usedMB: number }[] = [];

  constructor(config: Partial<MemoryManagerConfig> = {}) {
    this.config = {
      maxMemoryMB: 120,
      cleanupIntervalMs: 60000, // 1 minute
      warningThresholdMB: 100,
      enableMonitoring: true,
      ...config
    };
  }

  /**
   * Start memory monitoring and automatic cleanup
   */
  startMonitoring(): void {
    if (!this.config.enableMonitoring || this.monitoringInterval) return;

    this.monitoringInterval = window.setInterval(() => {
      const stats = this.getMemoryStats();
      if (stats) {
        const usedMB = Math.round(stats.usedJSHeapSize / 1024 / 1024);
        
        // Track history (keep last 10 measurements)
        this.memoryHistory.push({ timestamp: Date.now(), usedMB });
        if (this.memoryHistory.length > 10) {
          this.memoryHistory.shift();
        }

        // Check if cleanup is needed
        if (usedMB > this.config.warningThresholdMB) {
          console.warn(`Memory usage high: ${usedMB}MB (>${this.config.warningThresholdMB}MB threshold)`);
          this.performCleanup();
        }

        if (usedMB > this.config.maxMemoryMB) {
          console.error(`Memory usage critical: ${usedMB}MB (>${this.config.maxMemoryMB}MB limit)`);
          this.performAggressiveCleanup();
        }
      }
    }, this.config.cleanupIntervalMs);
  }

  /**
   * Stop memory monitoring
   */
  stopMonitoring(): void {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = null;
    }
  }

  /**
   * Get current memory statistics
   */
  getMemoryStats(): MemoryStats | null {
    if ('memory' in performance) {
      return (performance as any).memory;
    }
    return null;
  }

  /**
   * Get current memory usage in MB
   */
  getCurrentMemoryUsageMB(): number {
    const stats = this.getMemoryStats();
    return stats ? Math.round(stats.usedJSHeapSize / 1024 / 1024) : 0;
  }

  /**
   * Register a cleanup callback
   */
  registerCleanupCallback(callback: () => void): void {
    this.cleanupCallbacks.push(callback);
  }

  /**
   * Unregister a cleanup callback
   */
  unregisterCleanupCallback(callback: () => void): void {
    const index = this.cleanupCallbacks.indexOf(callback);
    if (index > -1) {
      this.cleanupCallbacks.splice(index, 1);
    }
  }

  /**
   * Perform standard cleanup
   */
  private performCleanup(): void {
    console.log('🧹 Performing memory cleanup...');
    
    // Run all registered cleanup callbacks
    this.cleanupCallbacks.forEach(callback => {
      try {
        callback();
      } catch (error) {
        console.error('Cleanup callback failed:', error);
      }
    });

    // Force garbage collection if available
    if ('gc' in window) {
      try {
        (window as any).gc();
      } catch (e) {
        // Ignore - GC not available
      }
    }
  }

  /**
   * Perform aggressive cleanup when memory is critical
   */
  private performAggressiveCleanup(): void {
    console.log('🚨 Performing aggressive memory cleanup...');
    
    // Clear global caches more aggressively
    this.performCleanup();
    
    // Additional aggressive cleanup
    if ('clearResourceTimings' in performance) {
      performance.clearResourceTimings();
    }
    
    if ('clearMarks' in performance) {
      performance.clearMarks();
    }
    
    if ('clearMeasures' in performance) {
      performance.clearMeasures();
    }
  }

  /**
   * Get memory usage trend (increasing/decreasing/stable)
   */
  getMemoryTrend(): 'increasing' | 'decreasing' | 'stable' | 'unknown' {
    if (this.memoryHistory.length < 3) return 'unknown';
    
    const recent = this.memoryHistory.slice(-3);
    const trend = recent[2].usedMB - recent[0].usedMB;
    
    if (trend > 10) return 'increasing';
    if (trend < -10) return 'decreasing';
    return 'stable';
  }

  /**
   * Get detailed memory report
   */
  getMemoryReport(): {
    current: number;
    max: number;
    trend: string;
    history: { timestamp: number; usedMB: number }[];
    status: 'healthy' | 'warning' | 'critical';
  } {
    const current = this.getCurrentMemoryUsageMB();
    const trend = this.getMemoryTrend();
    
    let status: 'healthy' | 'warning' | 'critical' = 'healthy';
    if (current > this.config.warningThresholdMB) status = 'warning';
    if (current > this.config.maxMemoryMB) status = 'critical';
    
    return {
      current,
      max: this.config.maxMemoryMB,
      trend,
      history: [...this.memoryHistory],
      status
    };
  }

  /**
   * Create a memory-bounded cache
   */
  createBoundedCache<K, V>(maxSize: number = 50): Map<K, V> {
    const cache = new Map<K, V>();
    const originalSet = cache.set.bind(cache);
    
    cache.set = function(key: K, value: V) {
      if (this.size >= maxSize) {
        // Remove oldest entry (first one)
        const firstKey = this.keys().next().value;
        if (firstKey !== undefined) {
          this.delete(firstKey);
        }
      }
      return originalSet(key, value);
    };
    
    return cache;
  }

  /**
   * Create a memory-bounded array
   */
  createBoundedArray<T>(maxSize: number = 100): T[] & { push: (item: T) => number } {
    const array: any[] = [];
    const originalPush = array.push.bind(array);
    
    array.push = function(item: T) {
      if (this.length >= maxSize) {
        this.shift(); // Remove oldest item
      }
      return originalPush(item);
    };
    
    return array as T[] & { push: (item: T) => number };
  }
}

// Global memory manager instance
export const memoryManager = new MemoryManager({
  maxMemoryMB: 120,
  warningThresholdMB: 100,
  cleanupIntervalMs: 60000,
  enableMonitoring: true
});

// Auto-start monitoring
if (typeof window !== 'undefined') {
  memoryManager.startMonitoring();
}

// Export utilities
export const createBoundedCache = <K, V>(maxSize: number = 50) => 
  memoryManager.createBoundedCache<K, V>(maxSize);

export const createBoundedArray = <T>(maxSize: number = 100) => 
  memoryManager.createBoundedArray<T>(maxSize);

export const registerMemoryCleanup = (callback: () => void) => 
  memoryManager.registerCleanupCallback(callback);

export const unregisterMemoryCleanup = (callback: () => void) => 
  memoryManager.unregisterCleanupCallback(callback);

export const getCurrentMemoryUsage = () => 
  memoryManager.getCurrentMemoryUsageMB();

export const getMemoryReport = () => 
  memoryManager.getMemoryReport();
