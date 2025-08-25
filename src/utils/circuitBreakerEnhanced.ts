/**
 * Enhanced Circuit Breaker with per-service state and metrics
 */

import productionLogger from '@/utils/productionLogger';

export enum CircuitState {
  CLOSED = 'closed',
  OPEN = 'open',
  HALF_OPEN = 'half_open'
}

export interface CircuitBreakerConfig {
  failureThreshold: number;
  recoveryTimeout: number;
  monitoringPeriod: number;
  successThreshold: number; // for half-open state
  maxRetries: number;
}

export interface CircuitBreakerStats {
  state: CircuitState;
  failures: number;
  successes: number;
  totalRequests: number;
  failureRate: number;
  lastFailureTime?: number;
  lastSuccessTime?: number;
  nextRetryTime?: number;
}

/**
 * Enhanced Circuit Breaker with exponential backoff and metrics
 */
export class EnhancedCircuitBreaker {
  private state: CircuitState = CircuitState.CLOSED;
  private failures: number = 0;
  private successes: number = 0;
  private totalRequests: number = 0;
  private lastFailureTime?: number;
  private lastSuccessTime?: number;
  private nextRetryTime?: number;
  private halfOpenSuccesses: number = 0;
  private monitoringInterval?: number;

  constructor(
    private name: string,
    private config: CircuitBreakerConfig
  ) {
    this.startMonitoring();
  }

  /**
   * Execute function with circuit breaker protection
   */
  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === CircuitState.OPEN) {
      if (!this.shouldAttemptReset()) {
        throw new Error(`Circuit breaker ${this.name} is OPEN`);
      }
      this.state = CircuitState.HALF_OPEN;
      this.halfOpenSuccesses = 0;
      productionLogger.info('Circuit breaker transitioning to HALF_OPEN', { name: this.name });
    }

    this.totalRequests++;

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  /**
   * Execute with retry logic
   */
  async executeWithRetry<T>(
    fn: () => Promise<T>,
    retries: number = this.config.maxRetries
  ): Promise<T> {
    let lastError: Error;
    
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        return await this.execute(fn);
      } catch (error) {
        lastError = error as Error;
        
        if (attempt < retries && this.state !== CircuitState.OPEN) {
          const backoffDelay = Math.min(1000 * Math.pow(2, attempt), 10000);
          productionLogger.warn('Circuit breaker retry attempt', {
            name: this.name,
            attempt: attempt + 1,
            maxRetries: retries,
            backoffDelay
          });
          await new Promise(resolve => setTimeout(resolve, backoffDelay));
        }
      }
    }
    
    throw lastError!;
  }

  /**
   * Check if circuit breaker should allow request
   */
  canExecute(): boolean {
    if (this.state === CircuitState.CLOSED) {
      return true;
    }
    
    if (this.state === CircuitState.HALF_OPEN) {
      return true;
    }
    
    // OPEN state - check if we should attempt reset
    return this.shouldAttemptReset();
  }

  /**
   * Get current circuit breaker statistics
   */
  getStats(): CircuitBreakerStats {
    return {
      state: this.state,
      failures: this.failures,
      successes: this.successes,
      totalRequests: this.totalRequests,
      failureRate: this.totalRequests > 0 ? this.failures / this.totalRequests : 0,
      lastFailureTime: this.lastFailureTime,
      lastSuccessTime: this.lastSuccessTime,
      nextRetryTime: this.nextRetryTime
    };
  }

  /**
   * Force circuit breaker to specific state
   */
  forceState(state: CircuitState): void {
    const oldState = this.state;
    this.state = state;
    
    if (state === CircuitState.CLOSED) {
      this.reset();
    } else if (state === CircuitState.OPEN) {
      this.nextRetryTime = Date.now() + this.config.recoveryTimeout;
    }
    
    productionLogger.info('Circuit breaker state forced', {
      name: this.name,
      oldState,
      newState: state
    });
  }

  /**
   * Reset circuit breaker to initial state
   */
  reset(): void {
    this.state = CircuitState.CLOSED;
    this.failures = 0;
    this.successes = 0;
    this.halfOpenSuccesses = 0;
    this.nextRetryTime = undefined;
    
    productionLogger.info('Circuit breaker reset', { name: this.name });
  }

  /**
   * Handle successful execution
   */
  private onSuccess(): void {
    this.successes++;
    this.lastSuccessTime = Date.now();

    if (this.state === CircuitState.HALF_OPEN) {
      this.halfOpenSuccesses++;
      
      if (this.halfOpenSuccesses >= this.config.successThreshold) {
        this.state = CircuitState.CLOSED;
        this.failures = 0;
        this.halfOpenSuccesses = 0;
        productionLogger.info('Circuit breaker closed after successful recovery', { name: this.name });
      }
    } else if (this.state === CircuitState.CLOSED) {
      // Reset failure count on success in closed state
      this.failures = Math.max(0, this.failures - 1);
    }
  }

  /**
   * Handle failed execution
   */
  private onFailure(): void {
    this.failures++;
    this.lastFailureTime = Date.now();

    if (this.state === CircuitState.HALF_OPEN) {
      // Immediately return to OPEN state on failure in HALF_OPEN
      this.state = CircuitState.OPEN;
      this.nextRetryTime = Date.now() + this.config.recoveryTimeout;
      productionLogger.warn('Circuit breaker returned to OPEN from HALF_OPEN', { name: this.name });
    } else if (this.state === CircuitState.CLOSED) {
      // Check if we should trip the circuit
      if (this.failures >= this.config.failureThreshold) {
        this.state = CircuitState.OPEN;
        this.nextRetryTime = Date.now() + this.config.recoveryTimeout;
        productionLogger.error('Circuit breaker OPENED due to failures', {
          name: this.name,
          failures: this.failures,
          threshold: this.config.failureThreshold
        });
      }
    }
  }

  /**
   * Check if circuit breaker should attempt reset
   */
  private shouldAttemptReset(): boolean {
    return this.nextRetryTime ? Date.now() >= this.nextRetryTime : false;
  }

  /**
   * Start monitoring and periodic cleanup
   */
  private startMonitoring(): void {
    this.monitoringInterval = window.setInterval(() => {
      // Reset counters periodically to prevent stale data
      const now = Date.now();
      const periodExpired = this.lastFailureTime && 
        (now - this.lastFailureTime) > this.config.monitoringPeriod;
      
      if (periodExpired && this.state === CircuitState.CLOSED) {
        // Decay failure count over time in closed state
        this.failures = Math.floor(this.failures * 0.9);
        this.successes = Math.floor(this.successes * 0.9);
        this.totalRequests = Math.floor(this.totalRequests * 0.9);
      }
    }, this.config.monitoringPeriod);
  }

  /**
   * Dispose circuit breaker
   */
  dispose(): void {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
    }
  }
}

/**
 * Circuit Breaker Manager for multiple services
 */
export class CircuitBreakerManager {
  private static instance: CircuitBreakerManager;
  private breakers = new Map<string, EnhancedCircuitBreaker>();

  static getInstance(): CircuitBreakerManager {
    if (!CircuitBreakerManager.instance) {
      CircuitBreakerManager.instance = new CircuitBreakerManager();
    }
    return CircuitBreakerManager.instance;
  }

  /**
   * Get or create circuit breaker for service
   */
  getBreaker(name: string, config?: Partial<CircuitBreakerConfig>): EnhancedCircuitBreaker {
    if (!this.breakers.has(name)) {
      const defaultConfig: CircuitBreakerConfig = {
        failureThreshold: 5,
        recoveryTimeout: 30000,
        monitoringPeriod: 60000,
        successThreshold: 3,
        maxRetries: 3
      };
      
      const finalConfig = { ...defaultConfig, ...config };
      this.breakers.set(name, new EnhancedCircuitBreaker(name, finalConfig));
    }
    
    return this.breakers.get(name)!;
  }

  /**
   * Get all circuit breaker stats
   */
  getAllStats(): Record<string, CircuitBreakerStats> {
    const stats: Record<string, CircuitBreakerStats> = {};
    
    for (const [name, breaker] of this.breakers) {
      stats[name] = breaker.getStats();
    }
    
    return stats;
  }

  /**
   * Reset all circuit breakers
   */
  resetAll(): void {
    for (const breaker of this.breakers.values()) {
      breaker.reset();
    }
    productionLogger.info('All circuit breakers reset');
  }

  /**
   * Dispose all circuit breakers
   */
  dispose(): void {
    for (const breaker of this.breakers.values()) {
      breaker.dispose();
    }
    this.breakers.clear();
  }
}

// Global instance
export const circuitBreakerManager = CircuitBreakerManager.getInstance();

// Pre-configured circuit breakers for common services
export const apiCircuitBreaker = circuitBreakerManager.getBreaker('api', {
  failureThreshold: 5,
  recoveryTimeout: 30000,
  successThreshold: 3
});

export const scraperCircuitBreaker = circuitBreakerManager.getBreaker('scraper', {
  failureThreshold: 3,
  recoveryTimeout: 60000,
  successThreshold: 2
});

export const supabaseCircuitBreaker = circuitBreakerManager.getBreaker('supabase', {
  failureThreshold: 10,
  recoveryTimeout: 15000,
  successThreshold: 5
});