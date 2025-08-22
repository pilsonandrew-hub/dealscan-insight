/**
 * Error Reporting and Analytics
 * Secure error tracking without sensitive data exposure
 */

import { logger } from '@/utils/secureLogger';

interface ErrorReport {
  id: string;
  timestamp: number;
  type: 'javascript' | 'network' | 'authentication' | 'validation' | 'security';
  severity: 'low' | 'medium' | 'high' | 'critical';
  message: string;
  stack?: string;
  userAgent: string;
  url: string;
  userId?: string;
  sessionId: string;
  metadata?: Record<string, any>;
}

interface ErrorContext {
  userId?: string;
  sessionId?: string;
  feature?: string;
  additionalData?: Record<string, any>;
}

class ErrorReporter {
  private static instance: ErrorReporter;
  private errorBuffer: ErrorReport[] = [];
  private maxBufferSize = 50;
  private sessionId: string;
  private isProduction: boolean;

  private constructor() {
    this.sessionId = this.generateSessionId();
    this.isProduction = import.meta.env.MODE === 'production';
    this.setupGlobalErrorHandlers();
  }

  public static getInstance(): ErrorReporter {
    if (!ErrorReporter.instance) {
      ErrorReporter.instance = new ErrorReporter();
    }
    return ErrorReporter.instance;
  }

  private generateSessionId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  private setupGlobalErrorHandlers(): void {
    // JavaScript errors
    window.addEventListener('error', (event) => {
      this.reportError({
        type: 'javascript',
        severity: 'high',
        message: event.message,
        stack: event.error?.stack,
        url: event.filename,
        line: event.lineno,
        column: event.colno
      });
    });

    // Promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      this.reportError({
        type: 'javascript',
        severity: 'high',
        message: `Unhandled Promise Rejection: ${event.reason}`,
        stack: event.reason?.stack
      });
    });

    // Network errors (fetch interceptor)
    this.interceptFetch();
  }

  private interceptFetch(): void {
    const originalFetch = window.fetch;
    
    window.fetch = async (...args): Promise<Response> => {
      try {
        const response = await originalFetch(...args);
        
        if (!response.ok) {
          this.reportError({
            type: 'network',
            severity: response.status >= 500 ? 'high' : 'medium',
            message: `HTTP ${response.status}: ${response.statusText}`,
            url: typeof args[0] === 'string' ? args[0] : (args[0] as Request).url,
            httpStatus: response.status
          });
        }
        
        return response;
      } catch (error) {
        this.reportError({
          type: 'network',
          severity: 'high',
          message: `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`,
          url: typeof args[0] === 'string' ? args[0] : (args[0] as Request)?.url
        });
        throw error;
      }
    };
  }

  public reportError(error: {
    type: ErrorReport['type'];
    severity: ErrorReport['severity'];
    message: string;
    stack?: string;
    url?: string;
    line?: number;
    column?: number;
    httpStatus?: number;
  }, context: ErrorContext = {}): void {
    try {
      const errorReport: ErrorReport = {
        id: this.generateErrorId(),
        timestamp: Date.now(),
        type: error.type,
        severity: error.severity,
        message: this.sanitizeMessage(error.message),
        stack: this.sanitizeStack(error.stack),
        userAgent: navigator.userAgent,
        url: error.url || window.location.href,
        userId: context.userId,
        sessionId: this.sessionId,
        metadata: {
          ...context.additionalData,
          line: error.line,
          column: error.column,
          httpStatus: error.httpStatus,
          feature: context.feature
        }
      };

      this.addToBuffer(errorReport);
      this.logError(errorReport);

      // In production, you might want to send to external service
      if (this.isProduction && error.severity === 'critical') {
        this.sendCriticalError(errorReport);
      }
    } catch (reportingError) {
      logger.error('Failed to report error', 'ERROR_REPORTING', reportingError);
    }
  }

  private generateErrorId(): string {
    return `err_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private sanitizeMessage(message: string): string {
    // Remove sensitive information from error messages
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

  private sanitizeStack(stack?: string): string | undefined {
    if (!stack) return undefined;
    
    // Remove file paths that might contain sensitive info
    return stack.replace(/file:\/\/\/[^\s)]+/g, '[FILE_PATH_REDACTED]');
  }

  private addToBuffer(errorReport: ErrorReport): void {
    this.errorBuffer.push(errorReport);
    
    if (this.errorBuffer.length > this.maxBufferSize) {
      this.errorBuffer.shift(); // Remove oldest error
    }
  }

  private logError(errorReport: ErrorReport): void {
    const logLevel = this.getLogLevel(errorReport.severity);
    logger[logLevel](
      `${errorReport.type.toUpperCase()} ERROR: ${errorReport.message}`,
      'ERROR_REPORTING',
      {
        id: errorReport.id,
        type: errorReport.type,
        severity: errorReport.severity,
        url: errorReport.url,
        metadata: errorReport.metadata
      }
    );
  }

  private getLogLevel(severity: ErrorReport['severity']): 'debug' | 'info' | 'warn' | 'error' {
    switch (severity) {
      case 'low': return 'debug';
      case 'medium': return 'info';
      case 'high': return 'warn';
      case 'critical': return 'error';
      default: return 'error';
    }
  }

  private async sendCriticalError(errorReport: ErrorReport): Promise<void> {
    try {
      // In a real implementation, send to external service like Sentry
      logger.error('CRITICAL ERROR DETECTED', 'ERROR_REPORTING', errorReport);
    } catch (error) {
      logger.error('Failed to send critical error', 'ERROR_REPORTING', error);
    }
  }

  public getErrorBuffer(): ErrorReport[] {
    return [...this.errorBuffer];
  }

  public clearErrorBuffer(): void {
    this.errorBuffer = [];
  }

  public getErrorStats(): {
    totalErrors: number;
    errorsByType: Record<string, number>;
    errorsBySeverity: Record<string, number>;
  } {
    const totalErrors = this.errorBuffer.length;
    const errorsByType: Record<string, number> = {};
    const errorsBySeverity: Record<string, number> = {};

    this.errorBuffer.forEach(error => {
      errorsByType[error.type] = (errorsByType[error.type] || 0) + 1;
      errorsBySeverity[error.severity] = (errorsBySeverity[error.severity] || 0) + 1;
    });

    return { totalErrors, errorsByType, errorsBySeverity };
  }
}

// React hook for error reporting
export const useErrorReporter = () => {
  const errorReporter = ErrorReporter.getInstance();

  const reportError = (
    error: Error | string,
    type: ErrorReport['type'] = 'javascript',
    severity: ErrorReport['severity'] = 'medium',
    context: ErrorContext = {}
  ) => {
    const message = error instanceof Error ? error.message : error;
    const stack = error instanceof Error ? error.stack : undefined;

    errorReporter.reportError({
      type,
      severity,
      message,
      stack
    }, context);
  };

  const reportNetworkError = (
    url: string,
    status: number,
    statusText: string,
    context: ErrorContext = {}
  ) => {
    errorReporter.reportError({
      type: 'network',
      severity: status >= 500 ? 'high' : 'medium',
      message: `HTTP ${status}: ${statusText}`,
      url,
      httpStatus: status
    }, context);
  };

  const reportValidationError = (
    field: string,
    message: string,
    context: ErrorContext = {}
  ) => {
    errorReporter.reportError({
      type: 'validation',
      severity: 'low',
      message: `Validation error on ${field}: ${message}`
    }, context);
  };

  const reportSecurityEvent = (
    event: string,
    severity: ErrorReport['severity'] = 'high',
    context: ErrorContext = {}
  ) => {
    errorReporter.reportError({
      type: 'security',
      severity,
      message: `Security event: ${event}`
    }, context);
  };

  return {
    reportError,
    reportNetworkError,
    reportValidationError,
    reportSecurityEvent,
    getErrorStats: () => errorReporter.getErrorStats(),
    clearErrors: () => errorReporter.clearErrorBuffer()
  };
};

// Initialize error reporter
const errorReporter = ErrorReporter.getInstance();

export { errorReporter, ErrorReporter };
export default useErrorReporter;