/**
 * Simplified Logger - Replaces the complex UnifiedLogger
 * Focus: Reliability over features
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  data?: any;
  context?: string;
}

class SimpleLogger {
  private isDevelopment = import.meta.env.MODE === 'development';

  private formatLog(entry: LogEntry): string {
    const { timestamp, level, message, context } = entry;
    return `${timestamp} [${level.toUpperCase()}]${context ? ` [${context}]` : ''} ${message}`;
  }

  private log(level: LogLevel, message: string, data?: any, context?: string) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      data,
      context
    };

    const formattedMessage = this.formatLog(entry);

    // Simple console logging
    switch (level) {
      case 'debug':
        if (this.isDevelopment) {
          console.debug(formattedMessage, data || '');
        }
        break;
      case 'info':
        console.info(formattedMessage, data || '');
        break;
      case 'warn':
        console.warn(formattedMessage, data || '');
        break;
      case 'error':
        console.error(formattedMessage, data || '');
        break;
    }
  }

  debug(message: string, data?: any, context?: string) {
    this.log('debug', message, data, context);
  }

  info(message: string, data?: any, context?: string) {
    this.log('info', message, data, context);
  }

  warn(message: string, data?: any, context?: string) {
    this.log('warn', message, data, context);
  }

  error(message: string, data?: any, context?: string) {
    this.log('error', message, data, context);
  }
}

export const logger = new SimpleLogger();