/**
 * Production Logger - Phase 1 Core Fix
 * Structured JSON logging with correlation IDs and levels
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogContext {
  [key: string]: any;
}

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: LogContext;
  correlationId?: string;
  component?: string;
  error?: {
    name: string;
    message: string;
    stack?: string;
  };
}

class ProductionLogger {
  private correlationId: string = '';
  private component: string = '';
  
  constructor() {
    this.generateCorrelationId();
  }
  
  /**
   * Generate unique correlation ID for request tracing
   */
  private generateCorrelationId(): void {
    this.correlationId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
  
  /**
   * Set correlation ID for request tracing
   */
  setCorrelationId(id: string): void {
    this.correlationId = id;
  }
  
  /**
   * Set component name for better log organization
   */
  setComponent(name: string): void {
    this.component = name;
  }
  
  /**
   * Create new logger instance with component context
   */
  child(component: string): ProductionLogger {
    const childLogger = new ProductionLogger();
    childLogger.correlationId = this.correlationId;
    childLogger.component = component;
    return childLogger;
  }
  
  /**
   * Format and output log entry
   */
  private log(level: LogLevel, message: string, context?: LogContext, error?: Error): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      correlationId: this.correlationId,
      component: this.component || 'unknown'
    };
    
    if (context) {
      entry.context = context;
    }
    
    if (error) {
      entry.error = {
        name: error.name,
        message: error.message,
        stack: error.stack
      };
    }
    
    // Output structured JSON
    const logLine = JSON.stringify(entry);
    
    // Route to appropriate console method based on level
    switch (level) {
      case 'debug':
        console.debug(logLine);
        break;
      case 'info':
        console.info(logLine);
        break;
      case 'warn':
        console.warn(logLine);
        break;
      case 'error':
        console.error(logLine);
        break;
    }
  }
  
  /**
   * Debug level logging
   */
  debug(message: string, context?: LogContext): void {
    this.log('debug', message, context);
  }
  
  /**
   * Info level logging
   */
  info(message: string, context?: LogContext): void {
    this.log('info', message, context);
  }
  
  /**
   * Warning level logging
   */
  warn(message: string, context?: LogContext): void {
    this.log('warn', message, context);
  }
  
  /**
   * Error level logging
   */
  error(message: string, context?: LogContext, error?: Error): void {
    this.log('error', message, context, error);
  }
  
  /**
   * Log API request
   */
  logRequest(method: string, url: string, context?: LogContext): void {
    this.info(`${method} ${url}`, {
      type: 'api_request',
      method,
      url,
      ...context
    });
  }
  
  /**
   * Log API response
   */
  logResponse(method: string, url: string, statusCode: number, duration: number, context?: LogContext): void {
    this.info(`${method} ${url} - ${statusCode}`, {
      type: 'api_response',
      method,
      url,
      status_code: statusCode,
      duration_ms: duration,
      ...context
    });
  }
  
  /**
   * Log database operation
   */
  logDatabaseOperation(operation: string, table: string, duration: number, context?: LogContext): void {
    this.info(`DB ${operation} on ${table}`, {
      type: 'database_operation',
      operation,
      table,
      duration_ms: duration,
      ...context
    });
  }
  
  /**
   * Log scraping operation
   */
  logScrapingOperation(site: string, operation: string, context?: LogContext): void {
    this.info(`Scraping ${operation} for ${site}`, {
      type: 'scraping_operation',
      site,
      operation,
      ...context
    });
  }
  
  /**
   * Log cache operation
   */
  logCacheOperation(operation: 'hit' | 'miss' | 'set' | 'delete', key: string, context?: LogContext): void {
    this.debug(`Cache ${operation}: ${key}`, {
      type: 'cache_operation',
      operation,
      key,
      ...context
    });
  }
  
  /**
   * Log performance metric
   */
  logPerformanceMetric(metric: string, value: number, unit: string, context?: LogContext): void {
    this.info(`Performance: ${metric} = ${value}${unit}`, {
      type: 'performance_metric',
      metric,
      value,
      unit,
      ...context
    });
  }
  
  /**
   * Log security event
   */
  logSecurityEvent(event: string, severity: 'low' | 'medium' | 'high' | 'critical', context?: LogContext): void {
    this.warn(`Security event: ${event}`, {
      type: 'security_event',
      event,
      severity,
      ...context
    });
  }
  
  /**
   * Log circuit breaker state change
   */
  logCircuitBreakerStateChange(name: string, oldState: string, newState: string, context?: LogContext): void {
    this.warn(`Circuit breaker ${name}: ${oldState} -> ${newState}`, {
      type: 'circuit_breaker_state_change',
      circuit_breaker: name,
      old_state: oldState,
      new_state: newState,
      ...context
    });
  }
  
  /**
   * Log rate limit event
   */
  logRateLimitEvent(identifier: string, limit: number, current: number, context?: LogContext): void {
    this.warn(`Rate limit approached for ${identifier}`, {
      type: 'rate_limit_event',
      identifier,
      limit,
      current,
      utilization: (current / limit) * 100,
      ...context
    });
  }
}

// Global logger instance
export const productionLogger = new ProductionLogger();

// Export as default for easier imports
export default productionLogger;

// Helper function to create child loggers
export function createLogger(component: string): ProductionLogger {
  return productionLogger.child(component);
}

// Performance timing helper
export function timeFunction<T>(
  logger: ProductionLogger,
  operation: string,
  fn: () => Promise<T>
): Promise<T> {
  return new Promise(async (resolve, reject) => {
    const startTime = Date.now();
    
    try {
      const result = await fn();
      const duration = Date.now() - startTime;
      
      logger.logPerformanceMetric(`${operation}_duration`, duration, 'ms');
      resolve(result);
    } catch (error) {
      const duration = Date.now() - startTime;
      
      logger.error(`${operation} failed`, {
        duration_ms: duration
      }, error as Error);
      
      reject(error);
    }
  });
}