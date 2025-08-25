/**
 * Global Error Handler - Phase 1 Core Fix
 * Centralized error handling with structured logging
 */

import productionLogger from '@/utils/productionLogger';

interface ErrorContext {
  component?: string;
  operation?: string;
  url?: string;
  userId?: string;
  additionalInfo?: Record<string, any>;
}

interface ErrorMetrics {
  errorCounts: Map<string, number>;
  lastErrors: Array<{
    timestamp: Date;
    type: string;
    message: string;
    context?: ErrorContext;
  }>;
}

class GlobalErrorHandler {
  private metrics: ErrorMetrics = {
    errorCounts: new Map(),
    lastErrors: []
  };
  
  private readonly MAX_LAST_ERRORS = 100;
  
  constructor() {
    this.setupGlobalHandlers();
  }
  
  /**
   * Setup global error handlers for unhandled exceptions
   */
  private setupGlobalHandlers(): void {
    // Handle unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      this.handleError(
        event.reason instanceof Error ? event.reason : new Error(String(event.reason)),
        {
          component: 'global',
          operation: 'unhandled_promise_rejection'
        }
      );
      
      // Prevent console error spam
      event.preventDefault();
    });
    
    // Handle uncaught errors
    window.addEventListener('error', (event) => {
      this.handleError(
        event.error || new Error(event.message),
        {
          component: 'global',
          operation: 'uncaught_error',
          url: event.filename,
          additionalInfo: {
            line: event.lineno,
            column: event.colno
          }
        }
      );
    });
    
    // Handle React error boundaries (if needed)
    if (typeof window !== 'undefined') {
      const originalConsoleError = console.error;
      console.error = (...args) => {
        // Check if this is a React error boundary error
        const errorMessage = args[0];
        if (typeof errorMessage === 'string' && errorMessage.includes('React')) {
          this.handleError(
            new Error(errorMessage),
            {
              component: 'react',
              operation: 'error_boundary',
              additionalInfo: { args }
            }
          );
        }
        
        // Call original console.error
        originalConsoleError.apply(console, args);
      };
    }
  }
  
  /**
   * Main error handling method
   */
  handleError(error: Error, context: ErrorContext = {}): void {
    const errorType = error.name || 'UnknownError';
    const timestamp = new Date();
    
    // Update metrics
    this.updateMetrics(errorType, error.message, context);
    
    // Log structured error
    productionLogger.error(
      `${errorType}: ${error.message}`,
      {
        error_type: errorType,
        stack_trace: error.stack,
        ...context
      },
      error
    );
    
    // Handle specific error types
    this.handleSpecificError(error, context);
    
    // Notify error monitoring service (if configured)
    this.notifyErrorMonitoring(error, context);
  }
  
  /**
   * Update error metrics
   */
  private updateMetrics(errorType: string, message: string, context: ErrorContext): void {
    // Increment error count
    const currentCount = this.metrics.errorCounts.get(errorType) || 0;
    this.metrics.errorCounts.set(errorType, currentCount + 1);
    
    // Add to recent errors
    this.metrics.lastErrors.push({
      timestamp: new Date(),
      type: errorType,
      message,
      context
    });
    
    // Keep only last N errors
    if (this.metrics.lastErrors.length > this.MAX_LAST_ERRORS) {
      this.metrics.lastErrors = this.metrics.lastErrors.slice(-this.MAX_LAST_ERRORS);
    }
  }
  
  /**
   * Handle specific error types with custom logic
   */
  private handleSpecificError(error: Error, context: ErrorContext): void {
    switch (error.name) {
      case 'NetworkError':
      case 'TypeError':
        if (error.message.includes('fetch')) {
          this.handleNetworkError(error, context);
        }
        break;
        
      case 'ChunkLoadError':
        this.handleChunkLoadError(error, context);
        break;
        
      case 'SecurityError':
        this.handleSecurityError(error, context);
        break;
        
      case 'QuotaExceededError':
        this.handleQuotaError(error, context);
        break;
        
      default:
        // Generic error handling
        break;
    }
  }
  
  /**
   * Handle network-related errors
   */
  private handleNetworkError(error: Error, context: ErrorContext): void {
    productionLogger.warn('Network error detected', {
      ...context,
      error_category: 'network',
      retry_suggested: true
    });
    
    // Could trigger retry logic or offline mode
  }
  
  /**
   * Handle chunk loading errors (common in SPAs)
   */
  private handleChunkLoadError(error: Error, context: ErrorContext): void {
    productionLogger.warn('Chunk load error - suggesting page reload', {
      ...context,
      error_category: 'chunk_load',
      action: 'reload_suggested'
    });
    
    // Could show user notification to reload
  }
  
  /**
   * Handle security errors
   */
  private handleSecurityError(error: Error, context: ErrorContext): void {
    productionLogger.logSecurityEvent('security_error', 'medium', {
      error_message: error.message,
      ...context
    });
  }
  
  /**
   * Handle quota exceeded errors (localStorage, etc.)
   */
  private handleQuotaError(error: Error, context: ErrorContext): void {
    productionLogger.warn('Storage quota exceeded', {
      ...context,
      error_category: 'quota',
      action: 'cleanup_suggested'
    });
    
    // Could trigger storage cleanup
  }
  
  /**
   * Notify external error monitoring service (Sentry, etc.)
   */
  private notifyErrorMonitoring(error: Error, context: ErrorContext): void {
    // Integration point for external error monitoring
    // Could send to Sentry, LogRocket, etc.
    
    if (typeof window !== 'undefined' && (window as any).Sentry) {
      (window as any).Sentry.captureException(error, {
        tags: {
          component: context.component,
          operation: context.operation
        },
        extra: context.additionalInfo
      });
    }
  }
  
  /**
   * Get error metrics for monitoring dashboard
   */
  getMetrics(): {
    errorCounts: Record<string, number>;
    recentErrors: Array<{
      timestamp: Date;
      type: string;
      message: string;
    }>;
    totalErrors: number;
  } {
    return {
      errorCounts: Object.fromEntries(this.metrics.errorCounts),
      recentErrors: this.metrics.lastErrors.map(({ context, ...rest }) => rest),
      totalErrors: Array.from(this.metrics.errorCounts.values()).reduce((sum, count) => sum + count, 0)
    };
  }
  
  /**
   * Get error statistics (alias for getMetrics for backward compatibility)
   */
  getErrorStats(): {
    errorCounts: Record<string, number>;
    recentErrors: Array<{
      timestamp: Date;
      type: string;
      message: string;
    }>;
    totalErrors: number;
  } {
    return this.getMetrics();
  }
  
  /**
   * Handle async operation with error catching
   */
  async wrapAsync<T>(
    operation: () => Promise<T>,
    context: ErrorContext
  ): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      this.handleError(error as Error, context);
      throw error; // Re-throw for caller to handle
    }
  }
  
  /**
   * Handle sync operation with error catching
   */
  wrapSync<T>(
    operation: () => T,
    context: ErrorContext
  ): T {
    try {
      return operation();
    } catch (error) {
      this.handleError(error as Error, context);
      throw error; // Re-throw for caller to handle
    }
  }
}

// Global instance
export const globalErrorHandler = new GlobalErrorHandler();

// Convenience methods
export const handleError = (error: Error, context?: ErrorContext) => 
  globalErrorHandler.handleError(error, context);

export const wrapAsync = <T>(operation: () => Promise<T>, context: ErrorContext) =>
  globalErrorHandler.wrapAsync(operation, context);

export const wrapSync = <T>(operation: () => T, context: ErrorContext) =>
  globalErrorHandler.wrapSync(operation, context);

export const getErrorMetrics = () => globalErrorHandler.getMetrics();

// Export as default
export default globalErrorHandler;
