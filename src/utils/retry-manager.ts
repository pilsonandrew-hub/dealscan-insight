/**
 * Retry Manager with exponential backoff and circuit breaker integration
 * Implements resilience patterns from v4.7 optimization plan
 */

import { performanceMonitor } from './performance-monitor';
import { auditLogger } from './audit-logger';

export interface RetryConfig {
  maxAttempts: number;
  baseDelay: number;
  maxDelay: number;
  backoffFactor: number;
  jitter: boolean;
  retryableErrors?: string[];
  onRetry?: (attempt: number, error: Error) => void;
  onSuccess?: (attempt: number) => void;
  onFailure?: (error: Error, attempts: number) => void;
}

export interface RetryResult<T> {
  success: boolean;
  data?: T;
  error?: Error;
  attempts: number;
  totalDuration: number;
}

const DEFAULT_CONFIG: RetryConfig = {
  maxAttempts: 3,
  baseDelay: 1000,
  maxDelay: 30000,
  backoffFactor: 2,
  jitter: true,
  retryableErrors: [
    'NetworkError',
    'TimeoutError',
    'AbortError',
    'TypeError', // Often network-related
    'fetch' // Generic fetch errors
  ]
};

export class RetryManager {
  private static instance: RetryManager;
  private activeRetries: Map<string, number> = new Map();

  private constructor() {}

  static getInstance(): RetryManager {
    if (!RetryManager.instance) {
      RetryManager.instance = new RetryManager();
    }
    return RetryManager.instance;
  }

  /**
   * Execute function with retry logic
   */
  async executeWithRetry<T>(
    operation: () => Promise<T>,
    config: Partial<RetryConfig> = {},
    operationId?: string
  ): Promise<RetryResult<T>> {
    const finalConfig: RetryConfig = { ...DEFAULT_CONFIG, ...config };
    const opId = operationId || `op_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    const timer = performanceMonitor.startTimer(`retry_operation_${opId}`);
    const startTime = Date.now();
    
    this.activeRetries.set(opId, 0);

    let lastError: Error | null = null;
    let attempt = 0;

    for (attempt = 1; attempt <= finalConfig.maxAttempts; attempt++) {
      this.activeRetries.set(opId, attempt);

      try {
        // Execute the operation
        const result = await operation();
        
        // Success - clean up and return
        this.activeRetries.delete(opId);
        const duration = timer.end(true);
        
        if (attempt > 1) {
          finalConfig.onSuccess?.(attempt);
          auditLogger.log('retry_success', 'system', 'info');
        }

        return {
          success: true,
          data: result,
          attempts: attempt,
          totalDuration: Date.now() - startTime
        };

      } catch (error) {
        lastError = error as Error;
        
        // Check if error is retryable
        if (!this.isRetryableError(lastError, finalConfig)) {
          break;
        }

        // Don't wait after the last attempt
        if (attempt < finalConfig.maxAttempts) {
          const delay = this.calculateDelay(attempt, finalConfig);
          
          finalConfig.onRetry?.(attempt, lastError);
          auditLogger.log('retry_attempt', 'system', 'warning');

          await this.sleep(delay);
        }
      }
    }

    // All retries exhausted - failure
    this.activeRetries.delete(opId);
    const duration = timer.end(false);
    
    finalConfig.onFailure?.(lastError!, attempt - 1);
    auditLogger.logError(lastError!, `retry_exhausted_${opId}`);

    return {
      success: false,
      error: lastError!,
      attempts: attempt - 1,
      totalDuration: Date.now() - startTime
    };
  }

  /**
   * Retry decorator for functions
   */
  withRetry<T extends any[], R>(
    fn: (...args: T) => Promise<R>,
    config: Partial<RetryConfig> = {}
  ) {
    return async (...args: T): Promise<R> => {
      const result = await this.executeWithRetry(
        () => fn(...args),
        config,
        fn.name || 'anonymous_function'
      );

      if (result.success) {
        return result.data!;
      } else {
        throw result.error;
      }
    };
  }

  /**
   * Retry with circuit breaker pattern
   */
  async executeWithCircuitBreaker<T>(
    operation: () => Promise<T>,
    circuitId: string,
    config: Partial<RetryConfig> = {}
  ): Promise<RetryResult<T>> {
    // Simple circuit breaker state
    const failures = this.getCircuitFailures(circuitId);
    const threshold = 5;
    const cooldownPeriod = 60000; // 1 minute

    if (failures >= threshold) {
      const lastFailure = this.getLastFailureTime(circuitId);
      if (Date.now() - lastFailure < cooldownPeriod) {
        throw new Error(`Circuit breaker open for ${circuitId}`);
      } else {
        // Reset circuit breaker
        this.resetCircuit(circuitId);
      }
    }

    const result = await this.executeWithRetry(operation, config, circuitId);
    
    if (result.success) {
      this.resetCircuit(circuitId);
    } else {
      this.recordCircuitFailure(circuitId);
    }

    return result;
  }

  /**
   * Get current retry statistics
   */
  getActiveRetries(): Record<string, number> {
    return Object.fromEntries(this.activeRetries.entries());
  }

  /**
   * Check if error should trigger retry
   */
  private isRetryableError(error: Error, config: RetryConfig): boolean {
    if (!config.retryableErrors?.length) {
      return true; // Retry all errors by default
    }

    return config.retryableErrors.some(retryableError => 
      error.name.includes(retryableError) || 
      error.message.includes(retryableError)
    );
  }

  /**
   * Calculate delay with exponential backoff and jitter
   */
  private calculateDelay(attempt: number, config: RetryConfig): number {
    let delay = config.baseDelay * Math.pow(config.backoffFactor, attempt - 1);
    
    // Apply maximum delay cap
    delay = Math.min(delay, config.maxDelay);
    
    // Add jitter to prevent thundering herd
    if (config.jitter) {
      delay = delay * (0.5 + Math.random() * 0.5);
    }
    
    return Math.floor(delay);
  }

  /**
   * Sleep utility
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // Circuit breaker helpers
  private circuitState: Map<string, { failures: number; lastFailure: number }> = new Map();

  private getCircuitFailures(circuitId: string): number {
    return this.circuitState.get(circuitId)?.failures || 0;
  }

  private getLastFailureTime(circuitId: string): number {
    return this.circuitState.get(circuitId)?.lastFailure || 0;
  }

  private recordCircuitFailure(circuitId: string) {
    const current = this.circuitState.get(circuitId) || { failures: 0, lastFailure: 0 };
    this.circuitState.set(circuitId, {
      failures: current.failures + 1,
      lastFailure: Date.now()
    });
  }

  private resetCircuit(circuitId: string) {
    this.circuitState.set(circuitId, { failures: 0, lastFailure: 0 });
  }
}

// Global instance
export const retryManager = RetryManager.getInstance();

// Convenient retry decorators
export const withRetry = retryManager.withRetry.bind(retryManager);
export const executeWithRetry = retryManager.executeWithRetry.bind(retryManager);