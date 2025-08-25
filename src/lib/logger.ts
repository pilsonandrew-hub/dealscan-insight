/**
 * Production Logger - Replaces ALL console.* statements
 * Centralized, structured logging with correlation IDs
 */

import productionLogger from '@/utils/productionLogger';

export interface LogMeta {
  [key: string]: unknown;
}

/**
 * Centralized logger that replaces console.*
 * Routes to production logger with proper formatting
 */
export const logger = {
  /**
   * Debug level - development only
   */
  debug: (message: string, meta?: LogMeta): void => {
    productionLogger.debug(message, {
      component: getCurrentComponent(),
      ...meta
    });
  },

  /**
   * Info level - general information
   */
  info: (message: string, meta?: LogMeta): void => {
    productionLogger.info(message, {
      component: getCurrentComponent(),
      ...meta
    });
  },

  /**
   * Warning level - potential issues
   */
  warn: (message: string, meta?: LogMeta): void => {
    productionLogger.warn(message, {
      component: getCurrentComponent(),
      ...meta
    });
  },

  /**
   * Error level - errors and exceptions
   */
  error: (message: string, context?: LogMeta, error?: Error): void => {
    productionLogger.error(message, {
      component: getCurrentComponent(),
      ...context
    }, error);
  },

  /**
   * Fatal level - critical errors
   */
  fatal: (message: string, context?: LogMeta, error?: Error): void => {
    productionLogger.error(message, {
      component: getCurrentComponent(),
      severity: 'fatal',
      ...context
    }, error);
  },

  /**
   * Create a scoped logger for a specific component
   */
  scope: (component: string, additionalContext?: LogMeta) => {
    return productionLogger.child(component);
  },

  /**
   * Set correlation ID for request tracking
   */
  setCorrelationId: (correlationId: string): void => {
    productionLogger.setCorrelationId(correlationId);
  },

  /**
   * Generate new correlation ID
   */
  newCorrelation: (): string => {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
};

/**
 * Get current component name from stack trace
 */
function getCurrentComponent(): string {
  try {
    const stack = new Error().stack;
    if (!stack) return 'Unknown';

    const lines = stack.split('\n');
    // Find the first line that's not from this logger file
    for (let i = 2; i < lines.length; i++) {
      const line = lines[i];
      if (line && !line.includes('logger.ts') && !line.includes('productionLogger.ts')) {
        // Extract component name from file path
        const match = line.match(/\/([^\/]+)\.(tsx?|jsx?):/);
        if (match) {
          return match[1];
        }
      }
    }
    return 'Unknown';
  } catch {
    return 'Unknown';
  }
}

/**
 * Request correlation middleware
 */
export function withCorrelation<T extends (...args: unknown[]) => unknown>(
  fn: T,
  correlationId?: string
): T {
  return ((...args: Parameters<T>) => {
    const id = correlationId || logger.newCorrelation();
    logger.setCorrelationId(id);
    
    try {
      const result = fn(...args);
      
      // Handle async functions
      if (result instanceof Promise) {
        return result.catch((error) => {
          logger.error('Async function failed', { correlationId: id }, error);
          throw error;
        });
      }
      
      return result;
    } catch (error) {
      logger.error('Function failed', { correlationId: id }, error);
      throw error;
    }
  }) as T;
}

/**
 * Performance timing decorator
 */
export function withTiming<T extends (...args: unknown[]) => unknown>(
  fn: T,
  operationName: string
): T {
  return ((...args: Parameters<T>) => {
    const startTime = performance.now();
    const correlationId = logger.newCorrelation();
    
    logger.debug(`Starting ${operationName}`, { correlationId, operationName });
    
    try {
      const result = fn(...args);
      
      if (result instanceof Promise) {
        return result
          .then((res) => {
            const duration = performance.now() - startTime;
            logger.info(`Completed ${operationName}`, {
              correlationId,
              operationName,
              duration: `${duration.toFixed(2)}ms`
            });
            return res;
          })
          .catch((error) => {
            const duration = performance.now() - startTime;
            logger.error(`Failed ${operationName}`, { 
              correlationId,
              operationName,
              duration: `${duration.toFixed(2)}ms`
            }, error);
            throw error;
          });
      }
      
      const duration = performance.now() - startTime;
      logger.info(`Completed ${operationName}`, {
        correlationId,
        operationName,
        duration: `${duration.toFixed(2)}ms`
      });
      
      return result;
    } catch (error) {
      const duration = performance.now() - startTime;
      logger.error(`Failed ${operationName}`, {
        correlationId,
        operationName,
        duration: `${duration.toFixed(2)}ms`
      }, error);
      throw error;
    }
  }) as T;
}

// Export default for convenience
export default logger;