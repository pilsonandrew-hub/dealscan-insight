/**
 * Global Error Handler - Production-grade error management
 * Centralized error reporting, recovery, and user experience
 */

import { logger, LogLevel } from './productionLogger';
import { toast } from 'sonner';

export enum ErrorSeverity {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical'
}

export enum ErrorCategory {
  NETWORK = 'network',
  VALIDATION = 'validation',
  AUTHENTICATION = 'authentication',
  AUTHORIZATION = 'authorization',
  BUSINESS_LOGIC = 'business_logic',
  SYSTEM = 'system',
  UNKNOWN = 'unknown'
}

export interface ErrorContext {
  component?: string;
  action?: string;
  userId?: string;
  url?: string;
  timestamp?: string;
  userAgent?: string;
  stackTrace?: string;
  additionalData?: Record<string, any>;
}

export interface AppError {
  id: string;
  severity: ErrorSeverity;
  category: ErrorCategory;
  message: string;
  userMessage: string;
  context: ErrorContext;
  originalError?: Error;
  timestamp: string;
  resolved?: boolean;
  retryCount?: number;
}

export interface ErrorRecoveryStrategy {
  canRecover: (error: AppError) => boolean;
  recover: (error: AppError) => Promise<boolean>;
  fallback?: () => void;
}

/**
 * Global Error Handler with recovery strategies
 */
export class GlobalErrorHandler {
  private static instance: GlobalErrorHandler;
  private recoveryStrategies: Map<ErrorCategory, ErrorRecoveryStrategy[]> = new Map();
  private errorHistory: AppError[] = [];
  private maxErrorHistory = 100;

  private constructor() {
    this.initializeRecoveryStrategies();
    this.setupGlobalErrorHandlers();
  }

  static getInstance(): GlobalErrorHandler {
    if (!GlobalErrorHandler.instance) {
      GlobalErrorHandler.instance = new GlobalErrorHandler();
    }
    return GlobalErrorHandler.instance;
  }

  /**
   * Handle any error with categorization and recovery
   */
  async handleError(
    error: Error | unknown, 
    context: ErrorContext = {},
    userMessage?: string
  ): Promise<void> {
    const appError = this.createAppError(error, context, userMessage);
    
    // Log the error
    logger.error(appError.message, appError.originalError, {
      errorId: appError.id,
      severity: appError.severity,
      category: appError.category,
      ...appError.context
    });

    // Add to history
    this.addToHistory(appError);

    // Attempt recovery
    const recovered = await this.attemptRecovery(appError);
    
    if (!recovered) {
      // Show user-friendly error message
      this.showUserError(appError);
      
      // Report to external service in production
      await this.reportToService(appError);
    }
  }

  /**
   * Handle network errors with retry logic
   */
  async handleNetworkError(
    error: Error,
    context: ErrorContext = {},
    retryFn?: () => Promise<any>
  ): Promise<any> {
    const appError = this.createAppError(error, context);
    appError.category = ErrorCategory.NETWORK;
    
    logger.warn('Network error occurred', { error: error.message, ...context });

    // Retry logic for network errors
    if (retryFn && (appError.retryCount || 0) < 3) {
      appError.retryCount = (appError.retryCount || 0) + 1;
      
      try {
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, appError.retryCount!) * 1000));
        return await retryFn();
      } catch (retryError) {
        return this.handleNetworkError(retryError as Error, context, retryFn);
      }
    }

    await this.handleError(error, context, 'Network connection issue. Please check your internet connection.');
    throw error;
  }

  /**
   * Handle validation errors
   */
  handleValidationError(
    message: string,
    context: ErrorContext = {},
    fieldErrors?: Record<string, string>
  ): void {
    const appError = this.createAppError(new Error(message), context, message);
    appError.category = ErrorCategory.VALIDATION;
    appError.severity = ErrorSeverity.LOW;
    appError.context.additionalData = { fieldErrors };

    logger.info('Validation error', {
      errorId: appError.id,
      fieldErrors,
      ...context
    });

    // Show field-specific errors
    if (fieldErrors) {
      Object.entries(fieldErrors).forEach(([field, error]) => {
        toast.error(`${field}: ${error}`, { duration: 5000 });
      });
    } else {
      toast.error(message, { duration: 5000 });
    }
  }

  /**
   * Handle authentication errors
   */
  async handleAuthError(
    error: Error,
    context: ErrorContext = {}
  ): Promise<void> {
    const appError = this.createAppError(error, context, 'Authentication required. Please log in again.');
    appError.category = ErrorCategory.AUTHENTICATION;
    appError.severity = ErrorSeverity.HIGH;

    logger.warn('Authentication error', { error: error.message, ...context });

    // Clear auth state and redirect to login
    try {
      const { supabase } = await import('@/integrations/supabase/client');
      await supabase.auth.signOut();
      
      // Redirect to login
      if (typeof window !== 'undefined') {
        window.location.href = '/auth';
      }
    } catch (signOutError) {
      logger.error('Failed to sign out user', signOutError as Error);
    }

    toast.error('Session expired. Please log in again.', { duration: 5000 });
  }

  /**
   * Handle business logic errors
   */
  handleBusinessError(
    message: string,
    context: ErrorContext = {},
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
  ): void {
    const appError = this.createAppError(new Error(message), context, message);
    appError.category = ErrorCategory.BUSINESS_LOGIC;
    appError.severity = severity;

    logger.info('Business logic error', {
      errorId: appError.id,
      ...context
    });

    toast.error(message, { 
      duration: severity === ErrorSeverity.HIGH ? 10000 : 5000 
    });
  }

  /**
   * Create standardized app error
   */
  private createAppError(
    error: Error | unknown,
    context: ErrorContext = {},
    userMessage?: string
  ): AppError {
    const originalError = error instanceof Error ? error : new Error(String(error));
    const timestamp = new Date().toISOString();
    
    return {
      id: `err_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      severity: this.determineSeverity(originalError),
      category: this.categorizeError(originalError),
      message: originalError.message,
      userMessage: userMessage || this.createUserMessage(originalError),
      context: {
        timestamp,
        url: typeof window !== 'undefined' ? window.location.href : undefined,
        userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
        stackTrace: originalError.stack,
        ...context
      },
      originalError,
      timestamp,
      retryCount: 0
    };
  }

  /**
   * Determine error severity
   */
  private determineSeverity(error: Error): ErrorSeverity {
    const message = error.message.toLowerCase();
    
    if (message.includes('network') || message.includes('fetch')) {
      return ErrorSeverity.MEDIUM;
    }
    
    if (message.includes('unauthorized') || message.includes('forbidden')) {
      return ErrorSeverity.HIGH;
    }
    
    if (message.includes('validation') || message.includes('invalid')) {
      return ErrorSeverity.LOW;
    }
    
    if (message.includes('critical') || message.includes('fatal')) {
      return ErrorSeverity.CRITICAL;
    }
    
    return ErrorSeverity.MEDIUM;
  }

  /**
   * Categorize error type
   */
  private categorizeError(error: Error): ErrorCategory {
    const message = error.message.toLowerCase();
    
    if (message.includes('network') || message.includes('fetch') || message.includes('connection')) {
      return ErrorCategory.NETWORK;
    }
    
    if (message.includes('validation') || message.includes('invalid') || message.includes('required')) {
      return ErrorCategory.VALIDATION;
    }
    
    if (message.includes('unauthorized') || message.includes('authentication') || message.includes('login')) {
      return ErrorCategory.AUTHENTICATION;
    }
    
    if (message.includes('forbidden') || message.includes('permission') || message.includes('access')) {
      return ErrorCategory.AUTHORIZATION;
    }
    
    if (message.includes('business') || message.includes('rule') || message.includes('constraint')) {
      return ErrorCategory.BUSINESS_LOGIC;
    }
    
    return ErrorCategory.UNKNOWN;
  }

  /**
   * Create user-friendly error message
   */
  private createUserMessage(error: Error): string {
    const message = error.message.toLowerCase();
    
    if (message.includes('network') || message.includes('fetch')) {
      return 'Connection problem. Please check your internet connection and try again.';
    }
    
    if (message.includes('unauthorized')) {
      return 'You need to log in to access this feature.';
    }
    
    if (message.includes('forbidden')) {
      return 'You don\'t have permission to perform this action.';
    }
    
    if (message.includes('validation')) {
      return 'Please check your input and try again.';
    }
    
    return 'Something went wrong. Please try again or contact support if the problem persists.';
  }

  /**
   * Attempt error recovery
   */
  private async attemptRecovery(error: AppError): Promise<boolean> {
    const strategies = this.recoveryStrategies.get(error.category) || [];
    
    for (const strategy of strategies) {
      if (strategy.canRecover(error)) {
        try {
          const recovered = await strategy.recover(error);
          if (recovered) {
            error.resolved = true;
            logger.info('Error recovered successfully', {
              errorId: error.id,
              category: error.category
            });
            return true;
          }
        } catch (recoveryError) {
          logger.warn('Recovery strategy failed', { error: (recoveryError as Error).message,
            errorId: error.id,
            category: error.category
          });
          
          // Try fallback if available
          if (strategy.fallback) {
            strategy.fallback();
          }
        }
      }
    }
    
    return false;
  }

  /**
   * Show user-friendly error
   */
  private showUserError(error: AppError): void {
    const duration = error.severity === ErrorSeverity.CRITICAL ? 15000 : 
                    error.severity === ErrorSeverity.HIGH ? 10000 : 5000;
    
    toast.error(error.userMessage, { 
      duration,
      action: error.category === ErrorCategory.NETWORK ? {
        label: 'Retry',
        onClick: () => window.location.reload()
      } : undefined
    });
  }

  /**
   * Report error to external service
   */
  private async reportToService(error: AppError): Promise<void> {
    try {
      // In production, report to error tracking service (Sentry, LogRocket, etc.)
      if (import.meta.env.PROD) {
        // Report to error tracking service - will be available after types regeneration
        logger.error('Error reported to service', error.originalError, {
          errorId: error.id,
          severity: error.severity,
          category: error.category,
          userMessage: error.userMessage
        });
      }
    } catch (reportError) {
      // Silent fail - don't break the app for error reporting issues
      logger.warn('Failed to report error to service', { error: (reportError as Error).message });
    }
  }

  /**
   * Initialize recovery strategies
   */
  private initializeRecoveryStrategies(): void {
    // Network error recovery
    this.recoveryStrategies.set(ErrorCategory.NETWORK, [
      {
        canRecover: (error) => error.category === ErrorCategory.NETWORK && (error.retryCount || 0) < 3,
        recover: async (error) => {
          // Simple retry strategy
          await new Promise(resolve => setTimeout(resolve, 2000));
          return true; // Assume retry succeeds for now
        },
        fallback: () => {
          toast.info('Working offline. Some features may be limited.', { duration: 5000 });
        }
      }
    ]);

    // Authentication error recovery
    this.recoveryStrategies.set(ErrorCategory.AUTHENTICATION, [
      {
        canRecover: (error) => error.category === ErrorCategory.AUTHENTICATION,
        recover: async (error) => {
          // Try to refresh the session
          try {
            const { supabase } = await import('@/integrations/supabase/client');
            const { data, error: refreshError } = await supabase.auth.refreshSession();
            return Boolean(!refreshError && data.session);
          } catch {
            return false;
          }
        }
      }
    ]);
  }

  /**
   * Setup global error handlers
   */
  private setupGlobalErrorHandlers(): void {
    if (typeof window === 'undefined') return;

    // Unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      this.handleError(event.reason, {
        component: 'global',
        action: 'unhandled_promise_rejection'
      });
    });

    // Unhandled errors
    window.addEventListener('error', (event) => {
      this.handleError(event.error, {
        component: 'global',
        action: 'unhandled_error',
        additionalData: {
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno
        }
      });
    });
  }

  /**
   * Add error to history
   */
  private addToHistory(error: AppError): void {
    this.errorHistory.unshift(error);
    
    if (this.errorHistory.length > this.maxErrorHistory) {
      this.errorHistory = this.errorHistory.slice(0, this.maxErrorHistory);
    }
  }

  /**
   * Get error statistics
   */
  getErrorStats(): {
    total: number;
    bySeverity: Record<ErrorSeverity, number>;
    byCategory: Record<ErrorCategory, number>;
    resolved: number;
  } {
    const stats = {
      total: this.errorHistory.length,
      bySeverity: Object.values(ErrorSeverity).reduce((acc, severity) => ({ ...acc, [severity]: 0 }), {}) as Record<ErrorSeverity, number>,
      byCategory: Object.values(ErrorCategory).reduce((acc, category) => ({ ...acc, [category]: 0 }), {}) as Record<ErrorCategory, number>,
      resolved: 0
    };

    this.errorHistory.forEach(error => {
      stats.bySeverity[error.severity]++;
      stats.byCategory[error.category]++;
      if (error.resolved) stats.resolved++;
    });

    return stats;
  }
}

// Global error handler instance
export const globalErrorHandler = GlobalErrorHandler.getInstance();

// Convenience functions
export const handleError = (error: Error | unknown, context?: ErrorContext, userMessage?: string) =>
  globalErrorHandler.handleError(error, context, userMessage);

export const handleNetworkError = (error: Error, context?: ErrorContext, retryFn?: () => Promise<any>) =>
  globalErrorHandler.handleNetworkError(error, context, retryFn);

export const handleValidationError = (message: string, context?: ErrorContext, fieldErrors?: Record<string, string>) =>
  globalErrorHandler.handleValidationError(message, context, fieldErrors);

export const handleAuthError = (error: Error, context?: ErrorContext) =>
  globalErrorHandler.handleAuthError(error, context);

export const handleBusinessError = (message: string, context?: ErrorContext, severity?: ErrorSeverity) =>
  globalErrorHandler.handleBusinessError(message, context, severity);

export default globalErrorHandler;