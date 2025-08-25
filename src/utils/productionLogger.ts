/**
 * Production-Grade Centralized Logging System
 * Replaces all console.* calls with structured, level-based logging
 */

export enum LogLevel {
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error',
  FATAL = 'fatal'
}

export interface LogContext {
  component?: string;
  action?: string;
  userId?: string;
  correlationId?: string;
  timestamp?: string;
  url?: string;
  userAgent?: string;
  sessionId?: string;
  [key: string]: any;
}

export interface LogEntry {
  level: LogLevel;
  message: string;
  context: LogContext;
  timestamp: string;
  correlationId: string;
  stack?: string;
}

/**
 * Production Logger - Centralized logging with correlation tracking
 */
export class ProductionLogger {
  private static instance: ProductionLogger;
  private logLevel: LogLevel;
  private correlationId: string;
  private baseContext: LogContext;
  private logBuffer: LogEntry[] = [];
  private maxBufferSize: number = 1000;
  private isProduction: boolean;

  private constructor() {
    this.isProduction = import.meta.env.PROD || import.meta.env.MODE === 'production';
    this.logLevel = this.isProduction ? LogLevel.WARN : LogLevel.DEBUG;
    this.correlationId = this.generateCorrelationId();
    this.baseContext = this.createBaseContext();
    
    // Flush logs periodically in production
    if (this.isProduction) {
      setInterval(() => this.flushLogs(), 30000); // Every 30 seconds
    }
  }

  static getInstance(): ProductionLogger {
    if (!ProductionLogger.instance) {
      ProductionLogger.instance = new ProductionLogger();
    }
    return ProductionLogger.instance;
  }

  /**
   * Debug level logging (development only)
   */
  debug(message: string, context: LogContext = {}): void {
    this.log(LogLevel.DEBUG, message, context);
  }

  /**
   * Info level logging
   */
  info(message: string, context: LogContext = {}): void {
    this.log(LogLevel.INFO, message, context);
  }

  /**
   * Warning level logging
   */
  warn(message: string, context: LogContext = {}): void {
    this.log(LogLevel.WARN, message, context);
  }

  /**
   * Error level logging
   */
  error(message: string, error?: Error, context: LogContext = {}): void {
    const enrichedContext = {
      ...context,
      stack: error?.stack,
      errorName: error?.name,
      errorMessage: error?.message
    };
    this.log(LogLevel.ERROR, message, enrichedContext);
  }

  /**
   * Fatal level logging
   */
  fatal(message: string, error?: Error, context: LogContext = {}): void {
    const enrichedContext = {
      ...context,
      stack: error?.stack,
      errorName: error?.name,
      errorMessage: error?.message
    };
    this.log(LogLevel.FATAL, message, enrichedContext);
  }

  /**
   * Create scoped logger for specific component
   */
  scope(component: string, additionalContext: LogContext = {}): ScopedLogger {
    return new ScopedLogger(this, component, additionalContext);
  }

  /**
   * Set correlation ID for request tracking
   */
  setCorrelationId(correlationId: string): void {
    this.correlationId = correlationId;
  }

  /**
   * Generate new correlation ID
   */
  newCorrelation(): string {
    this.correlationId = this.generateCorrelationId();
    return this.correlationId;
  }

  /**
   * Core logging method
   */
  private log(level: LogLevel, message: string, context: LogContext = {}): void {
    if (level < this.logLevel) return;

    const logEntry: LogEntry = {
      level,
      message,
      context: { ...this.baseContext, ...context },
      timestamp: new Date().toISOString(),
      correlationId: this.correlationId,
      stack: level >= LogLevel.ERROR ? new Error().stack : undefined
    };

    // In development, also log to console for debugging
    if (!this.isProduction) {
      this.logToConsole(logEntry);
    }

    // Buffer for production logging
    this.addToBuffer(logEntry);

    // Immediate flush for fatal errors
    if (level === LogLevel.FATAL) {
      this.flushLogs();
    }
  }

  /**
   * Log to console in development
   */
  private logToConsole(entry: LogEntry): void {
    const { level, message, context, timestamp, correlationId } = entry;
    const prefix = `[${timestamp}] [${LogLevel[level]}] [${correlationId}]`;
    
    switch (level) {
      case LogLevel.DEBUG:
        console.debug(prefix, message, context);
        break;
      case LogLevel.INFO:
        console.info(prefix, message, context);
        break;
      case LogLevel.WARN:
        console.warn(prefix, message, context);
        break;
      case LogLevel.ERROR:
      case LogLevel.FATAL:
        console.error(prefix, message, context, entry.stack);
        break;
    }
  }

  /**
   * Add entry to buffer
   */
  private addToBuffer(entry: LogEntry): void {
    this.logBuffer.push(entry);
    
    // Prevent memory overflow
    if (this.logBuffer.length > this.maxBufferSize) {
      this.logBuffer.shift(); // Remove oldest entry
    }
  }

  /**
   * Flush logs to external service in production
   */
  private async flushLogs(): Promise<void> {
    if (this.logBuffer.length === 0) return;

    const logsToFlush = [...this.logBuffer];
    this.logBuffer = [];

    try {
      // In production, send to logging service (e.g., Supabase, LogRocket, Sentry)
      if (this.isProduction) {
        await this.sendToLoggingService(logsToFlush);
      }
    } catch (error) {
      // Fallback: store in localStorage for later retry
      this.storeLogsLocally(logsToFlush);
    }
  }

  /**
   * Send logs to external logging service
   */
  private async sendToLoggingService(logs: LogEntry[]): Promise<void> {
    // Implementation would depend on chosen logging service
    // For now, we'll use Supabase for simplicity
    
    try {
      const { supabase } = await import('@/integrations/supabase/client');
      
      // Note: This will be available after types are regenerated
      await supabase.from('system_logs' as any).insert(
        logs.map(log => ({
          level: LogLevel[log.level],
          message: log.message,
          context: log.context,
          timestamp: log.timestamp,
          correlation_id: log.correlationId,
          stack_trace: log.stack
        }))
      );
    } catch (error) {
      // Silent fail - don't break the app for logging issues
    }
  }

  /**
   * Store logs locally for retry
   */
  private storeLogsLocally(logs: LogEntry[]): void {
    try {
      const existingLogs = localStorage.getItem('pending_logs');
      const pendingLogs = existingLogs ? JSON.parse(existingLogs) : [];
      pendingLogs.push(...logs);
      
      // Limit local storage size
      if (pendingLogs.length > 500) {
        pendingLogs.splice(0, pendingLogs.length - 500);
      }
      
      localStorage.setItem('pending_logs', JSON.stringify(pendingLogs));
    } catch (error) {
      // Silent fail - don't break the app
    }
  }

  /**
   * Generate correlation ID
   */
  private generateCorrelationId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Create base context
   */
  private createBaseContext(): LogContext {
    return {
      url: typeof window !== 'undefined' ? window.location.href : undefined,
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
      timestamp: new Date().toISOString(),
      sessionId: this.getSessionId()
    };
  }

  /**
   * Get or create session ID
   */
  private getSessionId(): string {
    if (typeof window === 'undefined') return 'server';
    
    let sessionId = sessionStorage.getItem('session_id');
    if (!sessionId) {
      sessionId = this.generateCorrelationId();
      sessionStorage.setItem('session_id', sessionId);
    }
    return sessionId;
  }

  /**
   * Get current logs (for debugging)
   */
  getLogs(): LogEntry[] {
    return [...this.logBuffer];
  }

  /**
   * Clear logs (for testing)
   */
  clearLogs(): void {
    this.logBuffer = [];
  }
}

/**
 * Scoped logger for specific components
 */
export class ScopedLogger {
  constructor(
    private logger: ProductionLogger,
    private component: string,
    private additionalContext: LogContext = {}
  ) {}

  debug(message: string, context: LogContext = {}): void {
    this.logger.debug(message, this.mergeContext(context));
  }

  info(message: string, context: LogContext = {}): void {
    this.logger.info(message, this.mergeContext(context));
  }

  warn(message: string, context: LogContext = {}): void {
    this.logger.warn(message, this.mergeContext(context));
  }

  error(message: string, error?: Error, context: LogContext = {}): void {
    this.logger.error(message, error, this.mergeContext(context));
  }

  fatal(message: string, error?: Error, context: LogContext = {}): void {
    this.logger.fatal(message, error, this.mergeContext(context));
  }

  private mergeContext(context: LogContext): LogContext {
    return {
      component: this.component,
      ...this.additionalContext,
      ...context
    };
  }
}

// Global logger instance
export const logger = ProductionLogger.getInstance();

// Component-specific loggers
export const createComponentLogger = (component: string, context?: LogContext) => 
  logger.scope(component, context);

export default logger;