/**
 * Centralized Error Handling System
 * Addresses Issue #2: Error Handling Inconsistencies
 * Replaces 106+ scattered console.log/error statements
 */

import { logger } from '@/utils/secureLogger';
import { globalErrorHandler } from '@/utils/globalErrorHandler';
import { supabase } from '@/integrations/supabase/client';

export type ErrorSeverity = 'low' | 'medium' | 'high' | 'critical';
export type ErrorCategory = 
  | 'network' 
  | 'validation' 
  | 'authentication' 
  | 'authorization' 
  | 'business_logic' 
  | 'system' 
  | 'user_input'
  | 'external_api';

export interface ErrorContext {
  component?: string;
  operation?: string;
  userId?: string;
  url?: string;
  userAgent?: string;
  timestamp?: string;
  metadata?: Record<string, any>;
}

export interface ErrorReport {
  id: string;
  severity: ErrorSeverity;
  category: ErrorCategory;
  message: string;
  stack?: string;
  context: ErrorContext;
  resolved: boolean;
  created_at: string;
}

/**
 * Enhanced Error Handler with structured logging and reporting
 */
class CentralizedErrorHandler {
  private errorBuffer: ErrorReport[] = [];
  private readonly maxBufferSize = 100;
  private isInitialized = false;

  constructor() {
    this.initialize();
  }

  /**
   * Initialize error handler with global listeners
   */
  private initialize() {
    if (this.isInitialized) return;
    
    // Setup global error handlers
    this.setupGlobalHandlers();
    this.isInitialized = true;
  }

  /**
   * Setup global error event listeners
   */
  private setupGlobalHandlers() {
    // Unhandled JavaScript errors
    window.addEventListener('error', (event) => {
      this.handleError({
        error: event.error || new Error(event.message),
        severity: 'high',
        category: 'system',
        context: {
          component: 'global',
          operation: 'uncaught_error',
          url: event.filename,
          metadata: {
            line: event.lineno,
            column: event.colno,
            message: event.message
          }
        }
      });
    });

    // Unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      this.handleError({
        error: new Error(`Unhandled Promise Rejection: ${event.reason}`),
        severity: 'high',
        category: 'system',
        context: {
          component: 'global',
          operation: 'unhandled_promise_rejection',
          metadata: {
            reason: event.reason
          }
        }
      });
    });

    // Network error interception
    this.interceptFetch();
  }

  /**
   * Intercept fetch requests to catch network errors
   */
  private interceptFetch() {
    const originalFetch = window.fetch;
    
    window.fetch = async (...args): Promise<Response> => {
      try {
        const response = await originalFetch(...args);
        
        // Log failed HTTP requests
        if (!response.ok) {
          this.handleError({
            error: new Error(`HTTP ${response.status}: ${response.statusText}`),
            severity: response.status >= 500 ? 'high' : 'medium',
            category: 'network',
            context: {
              operation: 'fetch_request',
              url: typeof args[0] === 'string' ? args[0] : (args[0] as Request).url,
              metadata: {
                status: response.status,
                statusText: response.statusText,
                method: args[1]?.method || 'GET'
              }
            }
          });
        }
        
        return response;
      } catch (error) {
        this.handleError({
          error: error as Error,
          severity: 'high',
          category: 'network',
          context: {
            operation: 'fetch_request',
            url: typeof args[0] === 'string' ? args[0] : (args[0] as Request)?.url,
            metadata: {
              method: args[1]?.method || 'GET'
            }
          }
        });
        throw error;
      }
    };
  }

  /**
   * Main error handling method
   */
  public handleError({
    error,
    severity = 'medium',
    category = 'system',
    context = {}
  }: {
    error: Error | string;
    severity?: ErrorSeverity;
    category?: ErrorCategory;
    context?: ErrorContext;
  }) {
    const errorObj = typeof error === 'string' ? new Error(error) : error;
    const timestamp = new Date().toISOString();
    
    // Create error report
    const errorReport: ErrorReport = {
      id: this.generateErrorId(),
      severity,
      category,
      message: this.sanitizeMessage(errorObj.message),
      stack: errorObj.stack,
      context: {
        ...context,
        timestamp,
        userAgent: navigator.userAgent,
        url: context.url || window.location.href
      },
      resolved: false,
      created_at: timestamp
    };

    // Add to buffer
    this.addToBuffer(errorReport);

    // Log with appropriate level
    this.logError(errorReport);

    // Store critical errors in database
    if (severity === 'critical' || severity === 'high') {
      this.storeErrorInDatabase(errorReport);
    }

    // Notify global error handler
    globalErrorHandler.handleError(errorObj, context);

    // Send to external monitoring (if configured)
    this.sendToExternalMonitoring(errorReport);

    return errorReport.id;
  }

  /**
   * Handle specific error types with context
   */
  public handleNetworkError(error: Error, url: string, method = 'GET') {
    return this.handleError({
      error,
      severity: 'high',
      category: 'network',
      context: {
        operation: 'network_request',
        url,
        metadata: { method }
      }
    });
  }

  public handleValidationError(error: Error, field: string, value?: any) {
    return this.handleError({
      error,
      severity: 'low',
      category: 'validation',
      context: {
        operation: 'input_validation',
        metadata: { field, value: this.sanitizeValue(value) }
      }
    });
  }

  public handleAuthError(error: Error, operation: string) {
    return this.handleError({
      error,
      severity: 'high',
      category: 'authentication',
      context: {
        operation,
        component: 'auth'
      }
    });
  }

  public handleBusinessLogicError(error: Error, component: string, operation: string) {
    return this.handleError({
      error,
      severity: 'medium',
      category: 'business_logic',
      context: {
        component,
        operation
      }
    });
  }

  /**
   * Utility methods
   */
  private generateErrorId(): string {
    return `err_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private sanitizeMessage(message: string): string {
    // Remove sensitive information
    const sensitivePatterns = [
      /password[=:]\s*\S+/gi,
      /token[=:]\s*\S+/gi,
      /key[=:]\s*\S+/gi,
      /secret[=:]\s*\S+/gi,
      /authorization:\s*\S+/gi,
      /bearer\s+\S+/gi
    ];

    let sanitized = message;
    sensitivePatterns.forEach(pattern => {
      sanitized = sanitized.replace(pattern, '[REDACTED]');
    });

    return sanitized;
  }

  private sanitizeValue(value: any): any {
    if (typeof value === 'string' && value.length > 100) {
      return value.substring(0, 100) + '...';
    }
    return value;
  }

  private addToBuffer(errorReport: ErrorReport) {
    this.errorBuffer.push(errorReport);
    
    if (this.errorBuffer.length > this.maxBufferSize) {
      this.errorBuffer.shift();
    }
  }

  private logError(errorReport: ErrorReport) {
    const logLevel = this.getLogLevel(errorReport.severity);
    
    logger[logLevel](
      `[${errorReport.category.toUpperCase()}] ${errorReport.message}`,
      errorReport.context.component || 'SYSTEM',
      {
        errorId: errorReport.id,
        severity: errorReport.severity,
        category: errorReport.category,
        context: errorReport.context
      }
    );
  }

  private getLogLevel(severity: ErrorSeverity): 'debug' | 'info' | 'warn' | 'error' {
    switch (severity) {
      case 'low': return 'debug';
      case 'medium': return 'info';
      case 'high': return 'warn';
      case 'critical': return 'error';
      default: return 'error';
    }
  }

  private async storeErrorInDatabase(errorReport: ErrorReport) {
    try {
      await supabase.from('error_reports').insert({
        error_id: errorReport.id,
        category: errorReport.category,
        severity: errorReport.severity,
        message: errorReport.message,
        stack_trace: errorReport.stack,
        context: errorReport.context,
        timestamp: errorReport.created_at,
        user_message: this.generateUserFriendlyMessage(errorReport),
        resolved: false
      });
    } catch (error) {
      logger.error('Failed to store error in database', 'ERROR_HANDLER', error);
    }
  }

  private generateUserFriendlyMessage(errorReport: ErrorReport): string {
    switch (errorReport.category) {
      case 'network':
        return 'A network error occurred. Please check your connection and try again.';
      case 'validation':
        return 'Please check your input and try again.';
      case 'authentication':
        return 'Authentication failed. Please sign in again.';
      case 'authorization':
        return 'You do not have permission to perform this action.';
      default:
        return 'An unexpected error occurred. Our team has been notified.';
    }
  }

  private sendToExternalMonitoring(errorReport: ErrorReport) {
    // Integration point for external services like Sentry
    if (typeof window !== 'undefined' && (window as any).Sentry) {
      (window as any).Sentry.captureException(new Error(errorReport.message), {
        tags: {
          severity: errorReport.severity,
          category: errorReport.category,
          component: errorReport.context.component
        },
        extra: errorReport.context
      });
    }
  }

  /**
   * Public methods for accessing error data
   */
  public getErrorBuffer(): ErrorReport[] {
    return [...this.errorBuffer];
  }

  public getErrorStats() {
    const totalErrors = this.errorBuffer.length;
    const errorsBySeverity: Record<string, number> = {};
    const errorsByCategory: Record<string, number> = {};

    this.errorBuffer.forEach(error => {
      errorsBySeverity[error.severity] = (errorsBySeverity[error.severity] || 0) + 1;
      errorsByCategory[error.category] = (errorsByCategory[error.category] || 0) + 1;
    });

    return {
      totalErrors,
      errorsBySeverity,
      errorsByCategory,
      recentErrors: this.errorBuffer.slice(-10)
    };
  }

  public clearErrorBuffer() {
    this.errorBuffer = [];
  }
}

// Create singleton instance
export const centralizedErrorHandler = new CentralizedErrorHandler();

// Convenience methods for easy usage throughout the app
export const handleError = (error: Error | string, context?: ErrorContext) =>
  centralizedErrorHandler.handleError({ error, context });

export const handleNetworkError = (error: Error, url: string, method?: string) =>
  centralizedErrorHandler.handleNetworkError(error, url, method);

export const handleValidationError = (error: Error, field: string, value?: any) =>
  centralizedErrorHandler.handleValidationError(error, field, value);

export const handleAuthError = (error: Error, operation: string) =>
  centralizedErrorHandler.handleAuthError(error, operation);

export const handleBusinessLogicError = (error: Error, component: string, operation: string) =>
  centralizedErrorHandler.handleBusinessLogicError(error, component, operation);

// React hook for using centralized error handling
export const useErrorHandler = () => {
  return {
    handleError: centralizedErrorHandler.handleError.bind(centralizedErrorHandler),
    handleNetworkError: centralizedErrorHandler.handleNetworkError.bind(centralizedErrorHandler),
    handleValidationError: centralizedErrorHandler.handleValidationError.bind(centralizedErrorHandler),
    handleAuthError: centralizedErrorHandler.handleAuthError.bind(centralizedErrorHandler),
    handleBusinessLogicError: centralizedErrorHandler.handleBusinessLogicError.bind(centralizedErrorHandler),
    getErrorStats: centralizedErrorHandler.getErrorStats.bind(centralizedErrorHandler),
    clearErrors: centralizedErrorHandler.clearErrorBuffer.bind(centralizedErrorHandler)
  };
};

export default centralizedErrorHandler;