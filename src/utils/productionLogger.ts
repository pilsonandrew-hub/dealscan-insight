/**
 * Production Logger
 * Structured JSON logging with correlation IDs and only the live method surface.
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

  private generateCorrelationId(): void {
    this.correlationId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  setCorrelationId(id: string): void {
    this.correlationId = id;
  }

  setComponent(name: string): void {
    this.component = name;
  }

  child(component: string): ProductionLogger {
    const childLogger = new ProductionLogger();
    childLogger.correlationId = this.correlationId;
    childLogger.component = component;
    return childLogger;
  }

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

    const logLine = JSON.stringify(entry);

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

  debug(message: string, context?: LogContext): void {
    this.log('debug', message, context);
  }

  info(message: string, context?: LogContext): void {
    this.log('info', message, context);
  }

  warn(message: string, context?: LogContext): void {
    this.log('warn', message, context);
  }

  error(message: string, context?: LogContext, error?: Error): void {
    this.log('error', message, context, error);
  }

  logSecurityEvent(event: string, severity: 'low' | 'medium' | 'high' | 'critical', context?: LogContext): void {
    this.warn(`Security event: ${event}`, {
      type: 'security_event',
      event,
      severity,
      ...context
    });
  }

  logAnalyticsTrustEvent(event: string, severity: 'low' | 'medium' | 'high', context?: LogContext): void {
    const level: LogLevel = severity === 'high' ? 'error' : severity === 'medium' ? 'warn' : 'info';
    this.log(level, `Analytics trust event: ${event}`, {
      type: 'analytics_trust_event',
      event,
      severity,
      ...context,
    });
  }
}

export const productionLogger = new ProductionLogger();
export default productionLogger;

export function createLogger(component: string): ProductionLogger {
  return productionLogger.child(component);
}
