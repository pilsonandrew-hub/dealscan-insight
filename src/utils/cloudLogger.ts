/**
 * Cloud Logging Integration
 * Sends logs to external monitoring services like Google Cloud Logging
 */

import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('CloudLogger');

interface CloudLogEntry {
  timestamp: string;
  severity: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  message: string;
  resource: {
    type: string;
    labels: Record<string, string>;
  };
  labels: Record<string, string>;
  jsonPayload: Record<string, any>;
  trace?: string;
  spanId?: string;
}

class CloudLogger {
  private static instance: CloudLogger;
  private logBuffer: CloudLogEntry[] = [];
  private maxBufferSize = 50;
  private flushInterval = 30000; // 30 seconds
  private isEnabled = true;

  private constructor() {
    this.setupPeriodicFlush();
    this.setupGlobalErrorHandlers();
  }

  public static getInstance(): CloudLogger {
    if (!CloudLogger.instance) {
      CloudLogger.instance = new CloudLogger();
    }
    return CloudLogger.instance;
  }

  private setupPeriodicFlush(): void {
    if (typeof window !== 'undefined') {
      setInterval(() => {
        this.flushLogs();
      }, this.flushInterval);

      // Flush on page unload
      window.addEventListener('beforeunload', () => {
        this.flushLogs();
      });
    }
  }

  private setupGlobalErrorHandlers(): void {
    if (typeof window !== 'undefined') {
      // Capture unhandled errors
      window.addEventListener('error', (event) => {
        this.logError(event.error || new Error(event.message), {
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
          type: 'javascript_error'
        });
      });

      // Capture unhandled promise rejections
      window.addEventListener('unhandledrejection', (event) => {
        this.logError(event.reason, {
          type: 'unhandled_promise_rejection'
        });
      });

      // Capture network errors
      const originalFetch = window.fetch;
      window.fetch = async (...args) => {
        const [url] = args;
        const startTime = Date.now();
        
        try {
          const response = await originalFetch(...args);
          
          if (!response.ok) {
            this.logWarning(`Network request failed: ${response.status} ${response.statusText}`, {
              url: typeof url === 'string' ? url : url.toString(),
              status: response.status,
              duration: Date.now() - startTime,
              type: 'network_error'
            });
          }
          
          return response;
        } catch (error) {
          this.logError(error as Error, {
            url: typeof url === 'string' ? url : url.toString(),
            duration: Date.now() - startTime,
            type: 'network_failure'
          });
          throw error;
        }
      };
    }
  }

  public logDebug(message: string, context: Record<string, any> = {}): void {
    this.addLog('DEBUG', message, context);
  }

  public logInfo(message: string, context: Record<string, any> = {}): void {
    this.addLog('INFO', message, context);
  }

  public logWarning(message: string, context: Record<string, any> = {}): void {
    this.addLog('WARNING', message, context);
  }

  public logError(error: Error | string, context: Record<string, any> = {}): void {
    const message = error instanceof Error ? error.message : error;
    const errorContext = {
      ...context,
      ...(error instanceof Error && {
        stack: error.stack,
        name: error.name
      })
    };
    this.addLog('ERROR', message, errorContext);
  }

  public logCritical(message: string, context: Record<string, any> = {}): void {
    this.addLog('CRITICAL', message, context);
    // Immediately flush critical logs
    this.flushLogs();
  }

  private addLog(severity: CloudLogEntry['severity'], message: string, context: Record<string, any>): void {
    if (!this.isEnabled) return;

    const entry: CloudLogEntry = {
      timestamp: new Date().toISOString(),
      severity,
      message: this.sanitizeMessage(message),
      resource: {
        type: 'webapp',
        labels: {
          environment: import.meta.env.MODE || 'development',
          version: '1.0.0',
          service: 'dealerscope-frontend'
        }
      },
      labels: {
        source: 'frontend',
        user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
        url: typeof window !== 'undefined' ? window.location.href : 'unknown'
      },
      jsonPayload: this.sanitizeContext(context)
    };

    this.logBuffer.push(entry);

    // Also log locally for development
    logger.info('Cloud log entry created', { severity, message, context });

    if (this.logBuffer.length >= this.maxBufferSize) {
      this.flushLogs();
    }
  }

  private sanitizeMessage(message: string): string {
    // Remove sensitive information from log messages
    const sensitivePatterns = [
      /password[=:]\s*\S+/gi,
      /token[=:]\s*\S+/gi,
      /key[=:]\s*\S+/gi,
      /secret[=:]\s*\S+/gi,
      /authorization:\s*bearer\s+\S+/gi
    ];

    let sanitized = message;
    sensitivePatterns.forEach(pattern => {
      sanitized = sanitized.replace(pattern, '[REDACTED]');
    });

    return sanitized.substring(0, 1000); // Limit message length
  }

  private sanitizeContext(context: Record<string, any>): Record<string, any> {
    const sanitized = { ...context };
    const sensitiveKeys = ['password', 'token', 'secret', 'key', 'auth', 'credential'];

    Object.keys(sanitized).forEach(key => {
      const lowerKey = key.toLowerCase();
      if (sensitiveKeys.some(sensitive => lowerKey.includes(sensitive))) {
        sanitized[key] = '[REDACTED]';
      }
    });

    return sanitized;
  }

  private async flushLogs(): Promise<void> {
    if (this.logBuffer.length === 0) return;

    const logsToFlush = [...this.logBuffer];
    this.logBuffer = [];

    try {
      // In a real implementation, you would send these to your cloud logging service
      // For now, we'll just log them locally
      if (import.meta.env.MODE === 'development') {
        logger.info('Would send to cloud logging', { 
          logCount: logsToFlush.length,
          logs: logsToFlush
        });
      } else {
        // In production, send to actual cloud logging service
        await this.sendToCloudLogging(logsToFlush);
      }
    } catch (error) {
      logger.error('Failed to flush logs to cloud service', { error });
      // Put logs back in buffer for retry
      this.logBuffer.unshift(...logsToFlush);
    }
  }

  private async sendToCloudLogging(logs: CloudLogEntry[]): Promise<void> {
    // This would be replaced with actual cloud logging API calls
    // Example for Google Cloud Logging:
    // await fetch('https://logging.googleapis.com/v2/entries:write', {
    //   method: 'POST',
    //   headers: {
    //     'Authorization': `Bearer ${await getAccessToken()}`,
    //     'Content-Type': 'application/json'
    //   },
    //   body: JSON.stringify({
    //     entries: logs
    //   })
    // });

    logger.info('Cloud logging would be sent here', { logCount: logs.length });
  }

  public getBufferedLogs(): CloudLogEntry[] {
    return [...this.logBuffer];
  }

  public clearBuffer(): void {
    this.logBuffer = [];
  }

  public disable(): void {
    this.isEnabled = false;
  }

  public enable(): void {
    this.isEnabled = true;
  }
}

export const cloudLogger = CloudLogger.getInstance();
export default cloudLogger;