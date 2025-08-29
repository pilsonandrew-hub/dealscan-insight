/**
 * Unified Logging System
 * Replaces 3 separate logging systems with a single, efficient interface
 */

import { configService } from './UnifiedConfigService';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'fatal';
export type LogContext = 'auth' | 'database' | 'api' | 'security' | 'performance' | 'business' | 'system';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  context: LogContext;
  message: string;
  data?: any;
  userId?: string;
  requestId?: string;
  sessionId?: string;
  stack?: string;
}

interface LogBackend {
  write(entry: LogEntry): Promise<void>;
  flush(): Promise<void>;
}

class ConsoleBackend implements LogBackend {
  async write(entry: LogEntry): Promise<void> {
    const color = this.getColor(entry.level);
    const prefix = `${entry.timestamp} [${entry.level.toUpperCase()}] [${entry.context}]`;
    
    if (entry.level === 'error' || entry.level === 'fatal') {
      console.error(`${color}${prefix}${'\x1b[0m'} ${entry.message}`, entry.data || '');
      if (entry.stack) {
        console.error(entry.stack);
      }
    } else if (entry.level === 'warn') {
      console.warn(`${color}${prefix}${'\x1b[0m'} ${entry.message}`, entry.data || '');
    } else {
      console.log(`${color}${prefix}${'\x1b[0m'} ${entry.message}`, entry.data || '');
    }
  }

  async flush(): Promise<void> {
    // Console doesn't need flushing
  }

  private getColor(level: LogLevel): string {
    switch (level) {
      case 'debug': return '\x1b[36m'; // Cyan
      case 'info': return '\x1b[32m';  // Green
      case 'warn': return '\x1b[33m';  // Yellow
      case 'error': return '\x1b[31m'; // Red
      case 'fatal': return '\x1b[35m'; // Magenta
      default: return '\x1b[0m';       // Reset
    }
  }
}

class RemoteBackend implements LogBackend {
  private buffer: LogEntry[] = [];
  private flushInterval: number;
  private maxBufferSize = 100;

  constructor() {
    // Flush every 30 seconds
    this.flushInterval = window.setInterval(() => {
      this.flush();
    }, 30000);
  }

  async write(entry: LogEntry): Promise<void> {
    this.buffer.push(entry);
    
    // Auto-flush on errors or when buffer is full
    if (entry.level === 'error' || entry.level === 'fatal' || this.buffer.length >= this.maxBufferSize) {
      await this.flush();
    }
  }

  async flush(): Promise<void> {
    if (this.buffer.length === 0) return;

    const entries = [...this.buffer];
    this.buffer = [];

    try {
      // Send to remote logging service
      await fetch('/api/logs', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ entries }),
      });
    } catch (error) {
      // Fallback to console if remote logging fails
      console.error('Failed to send logs to remote service:', error);
      // Put entries back in buffer for retry
      this.buffer.unshift(...entries);
    }
  }

  destroy(): void {
    clearInterval(this.flushInterval);
    this.flush();
  }
}

class PerformanceBackend implements LogBackend {
  private performanceEntries: LogEntry[] = [];
  private maxEntries = 1000;

  async write(entry: LogEntry): Promise<void> {
    if (entry.context === 'performance') {
      this.performanceEntries.push(entry);
      
      if (this.performanceEntries.length > this.maxEntries) {
        this.performanceEntries.shift(); // Remove oldest entry
      }
    }
  }

  async flush(): Promise<void> {
    // Performance metrics are kept in memory for analysis
  }

  getPerformanceMetrics(): LogEntry[] {
    return [...this.performanceEntries];
  }

  clearMetrics(): void {
    this.performanceEntries = [];
  }
}

class UnifiedLogger {
  private static instance: UnifiedLogger;
  private backends: LogBackend[] = [];
  private context: LogContext = 'system';
  private userId?: string;
  private sessionId?: string;
  private requestId?: string;
  private minLevel: LogLevel;

  private constructor() {
    this.minLevel = configService.isDevelopment ? 'debug' : 'info';
    this.setupBackends();
    this.setupGlobalErrorHandling();
  }

  static getInstance(): UnifiedLogger {
    if (!UnifiedLogger.instance) {
      UnifiedLogger.instance = new UnifiedLogger();
    }
    return UnifiedLogger.instance;
  }

  private setupBackends(): void {
    // Always use console backend
    this.backends.push(new ConsoleBackend());
    
    // Add remote backend for production
    if (configService.isProduction) {
      this.backends.push(new RemoteBackend());
    }

    // Add performance backend if monitoring is enabled
    if (configService.performance.monitoring.enabled) {
      this.backends.push(new PerformanceBackend());
    }
  }

  private setupGlobalErrorHandling(): void {
    // Catch unhandled errors
    window.addEventListener('error', (event) => {
      this.error('Unhandled error', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
      });
    });

    // Catch unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      this.error('Unhandled promise rejection', {
        reason: event.reason,
        stack: event.reason?.stack,
      });
    });
  }

  private shouldLog(level: LogLevel): boolean {
    const levels: LogLevel[] = ['debug', 'info', 'warn', 'error', 'fatal'];
    const currentIndex = levels.indexOf(level);
    const minIndex = levels.indexOf(this.minLevel);
    return currentIndex >= minIndex;
  }

  private async writeToBackends(entry: LogEntry): Promise<void> {
    const writePromises = this.backends.map(backend => 
      backend.write(entry).catch(error => {
        console.error('Backend write failed:', error);
      })
    );
    
    await Promise.allSettled(writePromises);
  }

  // Context setters
  setContext(context: LogContext): UnifiedLogger {
    this.context = context;
    return this;
  }

  setUserId(userId: string): UnifiedLogger {
    this.userId = userId;
    return this;
  }

  setSessionId(sessionId: string): UnifiedLogger {
    this.sessionId = sessionId;
    return this;
  }

  setRequestId(requestId: string): UnifiedLogger {
    this.requestId = requestId;
    return this;
  }

  // Logging methods
  debug(message: string, data?: any): void {
    if (this.shouldLog('debug')) {
      this.log('debug', message, data);
    }
  }

  info(message: string, data?: any): void {
    if (this.shouldLog('info')) {
      this.log('info', message, data);
    }
  }

  warn(message: string, data?: any): void {
    if (this.shouldLog('warn')) {
      this.log('warn', message, data);
    }
  }

  error(message: string, data?: any): void {
    if (this.shouldLog('error')) {
      this.log('error', message, data);
    }
  }

  fatal(message: string, data?: any): void {
    if (this.shouldLog('fatal')) {
      this.log('fatal', message, data);
    }
  }

  private log(level: LogLevel, message: string, data?: any): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      context: this.context,
      message,
      data,
      userId: this.userId,
      requestId: this.requestId,
      sessionId: this.sessionId,
      stack: level === 'error' || level === 'fatal' ? new Error().stack : undefined,
    };

    this.writeToBackends(entry);
  }

  // Performance logging helpers
  performance(message: string, data?: any): void {
    this.setContext('performance').info(message, data);
  }

  // Security logging helpers
  security(message: string, data?: any): void {
    this.setContext('security').warn(message, data);
  }

  // Business logging helpers
  business(message: string, data?: any): void {
    this.setContext('business').info(message, data);
  }

  // Timing helpers
  time(label: string): void {
    performance.mark(`${label}-start`);
  }

  timeEnd(label: string): void {
    performance.mark(`${label}-end`);
    performance.measure(label, `${label}-start`, `${label}-end`);
    
    const measure = performance.getEntriesByName(label, 'measure')[0];
    if (measure) {
      this.performance(`Timer: ${label}`, {
        duration: measure.duration,
        startTime: measure.startTime,
      });
    }
  }

  // Cleanup
  async flush(): Promise<void> {
    const flushPromises = this.backends.map(backend => backend.flush());
    await Promise.allSettled(flushPromises);
  }

  destroy(): void {
    this.flush();
    this.backends.forEach(backend => {
      if ('destroy' in backend) {
        (backend as any).destroy();
      }
    });
  }
}

// Export singleton instance
export const logger = UnifiedLogger.getInstance();

// Export typed logger instances for different contexts
export const authLogger = logger.setContext('auth');
export const dbLogger = logger.setContext('database');
export const apiLogger = logger.setContext('api');
export const securityLogger = logger.setContext('security');
export const performanceLogger = logger.setContext('performance');
export const businessLogger = logger.setContext('business');