/**
 * Enhanced Circuit Breaker with monitoring and health checks
 */

export enum CircuitState {
  CLOSED = 'CLOSED',
  OPEN = 'OPEN', 
  HALF_OPEN = 'HALF_OPEN'
}

interface CircuitBreakerConfig {
  failureThreshold: number;
  recoveryTimeout: number;
  monitoringPeriod: number;
  healthCheckInterval: number;
}

interface CircuitBreakerMetrics {
  totalRequests: number;
  successfulRequests: number;
  failedRequests: number;
  circuitOpenCount: number;
  averageResponseTime: number;
  lastHealthCheck: Date | null;
}

export class EnhancedCircuitBreaker {
  private state: CircuitState = CircuitState.CLOSED;
  private failureCount = 0;
  private lastFailureTime: number | null = null;
  private nextAttemptTime = 0;
  private metrics: CircuitBreakerMetrics = {
    totalRequests: 0,
    successfulRequests: 0,
    failedRequests: 0,
    circuitOpenCount: 0,
    averageResponseTime: 0,
    lastHealthCheck: null
  };
  private responseTimes: number[] = [];

  constructor(private config: CircuitBreakerConfig) {
    // Start health check monitoring
    this.startHealthCheckMonitoring();
  }

  async execute<T>(operation: () => Promise<T>, operationName?: string): Promise<T> {
    const startTime = Date.now();
    this.metrics.totalRequests++;

    if (this.state === CircuitState.OPEN) {
      if (Date.now() < this.nextAttemptTime) {
        throw new Error(`Circuit breaker is OPEN for ${operationName || 'operation'} - failing fast`);
      }
      this.state = CircuitState.HALF_OPEN;
    }

    try {
      const result = await operation();
      this.onSuccess(Date.now() - startTime);
      return result;
    } catch (error) {
      this.onFailure(Date.now() - startTime, error);
      throw error;
    }
  }

  private onSuccess(responseTime: number): void {
    this.failureCount = 0;
    this.state = CircuitState.CLOSED;
    this.lastFailureTime = null;
    this.metrics.successfulRequests++;
    this.updateResponseTime(responseTime);
  }

  private onFailure(responseTime: number, error: any): void {
    this.failureCount++;
    this.lastFailureTime = Date.now();
    this.metrics.failedRequests++;
    this.updateResponseTime(responseTime);

    if (this.failureCount >= this.config.failureThreshold) {
      this.state = CircuitState.OPEN;
      this.nextAttemptTime = Date.now() + this.config.recoveryTimeout;
      this.metrics.circuitOpenCount++;
      console.warn(`Circuit breaker opened due to ${this.failureCount} failures. Next attempt at ${new Date(this.nextAttemptTime)}`);
    }
  }

  private updateResponseTime(responseTime: number): void {
    this.responseTimes.push(responseTime);
    
    // Keep only recent response times for rolling average
    if (this.responseTimes.length > 100) {
      this.responseTimes = this.responseTimes.slice(-50);
    }
    
    this.metrics.averageResponseTime = 
      this.responseTimes.reduce((sum, time) => sum + time, 0) / this.responseTimes.length;
  }

  private startHealthCheckMonitoring(): void {
    setInterval(() => {
      this.performHealthCheck();
    }, this.config.healthCheckInterval);
  }

  private performHealthCheck(): void {
    this.metrics.lastHealthCheck = new Date();
    
    // Reset circuit breaker if it's been open too long and error rate is acceptable
    if (this.state === CircuitState.OPEN && 
        Date.now() - (this.lastFailureTime || 0) > this.config.recoveryTimeout * 2) {
      
      const errorRate = this.metrics.failedRequests / Math.max(this.metrics.totalRequests, 1);
      if (errorRate < 0.1) { // Less than 10% error rate
        console.info('Health check: Resetting circuit breaker due to improved conditions');
        this.reset();
      }
    }
  }

  public reset(): void {
    this.state = CircuitState.CLOSED;
    this.failureCount = 0;
    this.lastFailureTime = null;
    this.nextAttemptTime = 0;
  }

  public getState(): CircuitState {
    return this.state;
  }

  public getMetrics(): CircuitBreakerMetrics {
    return { ...this.metrics };
  }

  public getFailureCount(): number {
    return this.failureCount;
  }

  public isHealthy(): boolean {
    const errorRate = this.metrics.failedRequests / Math.max(this.metrics.totalRequests, 1);
    return this.state === CircuitState.CLOSED && 
           errorRate < 0.05 && // Less than 5% error rate
           this.metrics.averageResponseTime < 5000; // Less than 5s average response
  }
}

// Factory for creating circuit breakers with common configurations
export const CircuitBreakerFactory = {
  createDefault: () => new EnhancedCircuitBreaker({
    failureThreshold: 5,
    recoveryTimeout: 60000, // 1 minute
    monitoringPeriod: 300000, // 5 minutes
    healthCheckInterval: 30000 // 30 seconds
  }),

  createAggressive: () => new EnhancedCircuitBreaker({
    failureThreshold: 3,
    recoveryTimeout: 30000, // 30 seconds
    monitoringPeriod: 120000, // 2 minutes
    healthCheckInterval: 15000 // 15 seconds
  }),

  createTolerant: () => new EnhancedCircuitBreaker({
    failureThreshold: 10,
    recoveryTimeout: 300000, // 5 minutes
    monitoringPeriod: 600000, // 10 minutes
    healthCheckInterval: 60000 // 1 minute
  })
};
