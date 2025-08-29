/**
 * Performance Emergency Kit
 * Immediate fixes for critical performance issues
 */

import { logger } from './UnifiedLogger';
import { configService } from './UnifiedConfigService';

interface PendingRequest {
  promise: Promise<any>;
  timestamp: number;
  key: string;
}

interface ConnectionPoolConfig {
  min: number;
  max: number;
  idleTimeoutMs: number;
}

class PerformanceEmergencyKit {
  private static instance: PerformanceEmergencyKit;
  private pendingRequests = new Map<string, PendingRequest>();
  private connectionPool: Connection[] = [];
  private activeConnections = 0;
  private requestQueue: (() => void)[] = [];
  private isInitialized = false;

  private constructor() {
    this.setupErrorBoundaries();
    this.setupConnectionPool();
    this.setupRequestDeduplication();
    this.setupMemoryLeakPrevention();
    this.isInitialized = true;
  }

  static getInstance(): PerformanceEmergencyKit {
    if (!PerformanceEmergencyKit.instance) {
      PerformanceEmergencyKit.instance = new PerformanceEmergencyKit();
    }
    return PerformanceEmergencyKit.instance;
  }

  private setupErrorBoundaries(): void {
    // Global error handling for unhandled promises
    window.addEventListener('unhandledrejection', (event) => {
      logger.error('Unhandled promise rejection caught by emergency kit', {
        reason: event.reason,
        stack: event.reason?.stack,
      });
      
      // Prevent browser default behavior
      event.preventDefault();
    });

    // Global error handling for runtime errors
    window.addEventListener('error', (event) => {
      logger.error('Runtime error caught by emergency kit', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
      });
    });
  }

  private setupConnectionPool(): void {
    const config = configService.database.connectionPool;
    
    // Initialize minimum connections
    for (let i = 0; i < config.min; i++) {
      this.connectionPool.push(this.createConnection());
    }

    // Cleanup idle connections periodically
    setInterval(() => {
      this.cleanupIdleConnections();
    }, config.idleTimeoutMs / 2);
  }

  private createConnection(): Connection {
    return {
      id: `conn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      createdAt: Date.now(),
      lastUsed: Date.now(),
      isIdle: true,
      query: async (sql: string, params?: any[]) => {
        // Placeholder for actual database query
        return new Promise(resolve => setTimeout(resolve, 10));
      },
    };
  }

  private cleanupIdleConnections(): void {
    const config = configService.database.connectionPool;
    const now = Date.now();
    
    this.connectionPool = this.connectionPool.filter(conn => {
      const isExpired = now - conn.lastUsed > config.idleTimeoutMs;
      const canRemove = this.connectionPool.length > config.min && isExpired;
      
      if (canRemove) {
        logger.debug('Removing idle connection', { connectionId: conn.id });
      }
      
      return !canRemove;
    });
  }

  async getConnection(): Promise<Connection> {
    // Try to get an idle connection first
    let connection = this.connectionPool.find(conn => conn.isIdle);
    
    if (connection) {
      connection.isIdle = false;
      connection.lastUsed = Date.now();
      return connection;
    }

    // Create new connection if under max limit
    const config = configService.database.connectionPool;
    if (this.connectionPool.length < config.max) {
      connection = this.createConnection();
      connection.isIdle = false;
      this.connectionPool.push(connection);
      return connection;
    }

    // Wait for a connection to become available
    return new Promise((resolve) => {
      this.requestQueue.push(() => {
        const availableConnection = this.connectionPool.find(conn => conn.isIdle);
        if (availableConnection) {
          availableConnection.isIdle = false;
          availableConnection.lastUsed = Date.now();
          resolve(availableConnection);
        }
      });
    });
  }

  releaseConnection(connection: Connection): void {
    connection.isIdle = true;
    connection.lastUsed = Date.now();
    
    // Process queued requests
    if (this.requestQueue.length > 0) {
      const nextRequest = this.requestQueue.shift();
      if (nextRequest) {
        nextRequest();
      }
    }
  }

  private setupRequestDeduplication(): void {
    // Clean up old pending requests periodically
    setInterval(() => {
      const now = Date.now();
      const maxAge = 30000; // 30 seconds
      
      for (const [key, request] of this.pendingRequests.entries()) {
        if (now - request.timestamp > maxAge) {
          this.pendingRequests.delete(key);
          logger.warn('Cleaned up stale pending request', { key });
        }
      }
    }, 10000); // Check every 10 seconds
  }

  async deduplicateRequest<T>(
    key: string,
    requestFn: () => Promise<T>
  ): Promise<T> {
    // Check if request is already pending
    const existing = this.pendingRequests.get(key);
    if (existing) {
      logger.debug('Request deduplicated', { key });
      return existing.promise as Promise<T>;
    }

    // Create new request
    const promise = requestFn();
    this.pendingRequests.set(key, {
      promise,
      timestamp: Date.now(),
      key,
    });

    try {
      const result = await promise;
      this.pendingRequests.delete(key);
      return result;
    } catch (error) {
      this.pendingRequests.delete(key);
      throw error;
    }
  }

  private setupMemoryLeakPrevention(): void {
    // Monitor memory usage
    if ('memory' in performance) {
      setInterval(() => {
        const memory = (performance as any).memory;
        const usedMB = Math.round(memory.usedJSHeapSize / 1024 / 1024);
        const limitMB = Math.round(memory.jsHeapSizeLimit / 1024 / 1024);
        
        logger.performance('Memory usage', {
          used: usedMB,
          limit: limitMB,
          percentage: Math.round((usedMB / limitMB) * 100),
        });

        // Trigger garbage collection hint if memory usage is high
        if (usedMB / limitMB > 0.8) {
          logger.warn('High memory usage detected', {
            used: usedMB,
            limit: limitMB,
          });
          
          // Force cleanup of our own caches
          this.emergencyCleanup();
        }
      }, 30000); // Check every 30 seconds
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
      this.emergencyCleanup();
    });
  }

  private emergencyCleanup(): void {
    logger.info('Performing emergency cleanup');
    
    // Clear pending requests
    this.pendingRequests.clear();
    
    // Clear request queue
    this.requestQueue = [];
    
    // Force garbage collection hint
    if ('gc' in window) {
      (window as any).gc();
    }
  }

  // Public API for request optimization
  async optimizedFetch(url: string, options?: RequestInit): Promise<Response> {
    const key = `fetch_${url}_${JSON.stringify(options)}`;
    
    return this.deduplicateRequest(key, async () => {
      const connection = await this.getConnection();
      
      try {
        const response = await fetch(url, {
          ...options,
          signal: AbortSignal.timeout(10000), // 10 second timeout
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response;
      } finally {
        this.releaseConnection(connection);
      }
    });
  }

  // Circuit breaker pattern for failing requests
  private failureCount = new Map<string, number>();
  private circuitState = new Map<string, 'closed' | 'open' | 'half-open'>();

  async circuitBreakerFetch(url: string, options?: RequestInit): Promise<Response> {
    const key = `circuit_${url}`;
    const state = this.circuitState.get(key) || 'closed';
    const failures = this.failureCount.get(key) || 0;

    // Circuit is open - reject immediately
    if (state === 'open' && failures >= 5) {
      throw new Error(`Circuit breaker is open for ${url}`);
    }

    try {
      const response = await this.optimizedFetch(url, options);
      
      // Success - reset failure count
      this.failureCount.set(key, 0);
      this.circuitState.set(key, 'closed');
      
      return response;
    } catch (error) {
      // Failure - increment count and potentially open circuit
      const newFailures = failures + 1;
      this.failureCount.set(key, newFailures);
      
      if (newFailures >= 5) {
        this.circuitState.set(key, 'open');
        logger.warn('Circuit breaker opened', { url, failures: newFailures });
        
        // Auto-reset after 30 seconds
        setTimeout(() => {
          this.circuitState.set(key, 'half-open');
        }, 30000);
      }
      
      throw error;
    }
  }

  // Get performance metrics
  getMetrics() {
    return {
      pendingRequests: this.pendingRequests.size,
      activeConnections: this.connectionPool.filter(c => !c.isIdle).length,
      totalConnections: this.connectionPool.length,
      queuedRequests: this.requestQueue.length,
      circuitBreakerStates: Object.fromEntries(this.circuitState),
      isInitialized: this.isInitialized,
    };
  }
}

interface Connection {
  id: string;
  createdAt: number;
  lastUsed: number;
  isIdle: boolean;
  query: (sql: string, params?: any[]) => Promise<any>;
}

export const performanceKit = PerformanceEmergencyKit.getInstance();
export { PerformanceEmergencyKit };