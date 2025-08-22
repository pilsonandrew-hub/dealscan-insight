/**
 * Secure Logging Service
 * Replaces all console.log statements with production-safe logging
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: string;
  data?: any;
}

class SecureLogger {
  private static instance: SecureLogger;
  private logBuffer: LogEntry[] = [];
  private maxBufferSize = 100;

  private constructor() {}

  public static getInstance(): SecureLogger {
    if (!SecureLogger.instance) {
      SecureLogger.instance = new SecureLogger();
    }
    return SecureLogger.instance;
  }

  private shouldLog(level: LogLevel): boolean {
    // In production, only log errors and warnings
    if (import.meta.env.MODE === 'production') {
      return level === 'error' || level === 'warn';
    }
    return true;
  }

  private sanitizeData(data: any): any {
    if (typeof data !== 'object' || data === null) {
      return data;
    }

    // Remove sensitive fields
    const sensitiveKeys = ['password', 'token', 'secret', 'key', 'auth', 'credential'];
    const sanitized = { ...data };

    for (const key in sanitized) {
      const lowerKey = key.toLowerCase();
      if (sensitiveKeys.some(sensitive => lowerKey.includes(sensitive))) {
        sanitized[key] = '[REDACTED]';
      }
    }

    return sanitized;
  }

  private addToBuffer(entry: LogEntry): void {
    this.logBuffer.push(entry);
    if (this.logBuffer.length > this.maxBufferSize) {
      this.logBuffer.shift(); // Remove oldest entry
    }
  }

  public debug(message: string, context?: string, data?: any): void {
    if (!this.shouldLog('debug')) return;
    
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'debug',
      message,
      context,
      data: this.sanitizeData(data)
    };

    this.addToBuffer(entry);
    console.debug(`[${context || 'APP'}] ${message}`, data);
  }

  public info(message: string, context?: string, data?: any): void {
    if (!this.shouldLog('info')) return;
    
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'info',
      message,
      context,
      data: this.sanitizeData(data)
    };

    this.addToBuffer(entry);
    console.info(`[${context || 'APP'}] ${message}`, data);
  }

  public warn(message: string, context?: string, data?: any): void {
    if (!this.shouldLog('warn')) return;
    
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'warn',
      message,
      context,
      data: this.sanitizeData(data)
    };

    this.addToBuffer(entry);
    console.warn(`[${context || 'APP'}] ${message}`, data);
  }

  public error(message: string, context?: string, error?: Error | any): void {
    if (!this.shouldLog('error')) return;
    
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'error',
      message,
      context,
      data: error instanceof Error ? {
        name: error.name,
        message: error.message,
        stack: error.stack
      } : this.sanitizeData(error)
    };

    this.addToBuffer(entry);
    console.error(`[${context || 'APP'}] ${message}`, error);
  }

  public getLogBuffer(): LogEntry[] {
    return [...this.logBuffer];
  }

  public clearBuffer(): void {
    this.logBuffer = [];
  }
}

export const logger = SecureLogger.getInstance();
export default logger;