/**
 * Client-side audit logging system
 * Inspired by the audit logging in the bootstrap script
 */

import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('AuditLogger');

export interface AuditEvent {
  id: string;
  timestamp: number;
  action: string;
  details?: Record<string, any>;
  userId?: string;
  sessionId: string;
  ipAddress?: string;
  userAgent: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
  category: 'auth' | 'data' | 'upload' | 'system' | 'user_action';
  metadata?: Record<string, any>;
}

export interface AuditConfig {
  enableRemoteLogging: boolean;
  endpoint?: string;
  batchSize: number;
  flushInterval: number;
  maxLocalStorage: number;
}

class AuditLogger {
  private events: AuditEvent[] = [];
  private sessionId: string;
  private config: AuditConfig;
  private flushTimeout?: NodeJS.Timeout;

  constructor(config: Partial<AuditConfig> = {}) {
    this.config = {
      enableRemoteLogging: false,
      batchSize: 10,
      flushInterval: 30000, // 30 seconds
      maxLocalStorage: 1000,
      ...config
    };

    this.sessionId = this.generateSessionId();
    this.loadStoredEvents();
    this.startPeriodicFlush();
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private loadStoredEvents() {
    try {
      const stored = localStorage.getItem('dealerscope_audit_events');
      if (stored) {
        const events = JSON.parse(stored) as AuditEvent[];
        this.events = events.slice(-this.config.maxLocalStorage);
      }
    } catch (error) {
      console.warn('Failed to load stored audit events:', error);
    }
  }

  private saveEvents() {
    try {
      const eventsToStore = this.events.slice(-this.config.maxLocalStorage);
      localStorage.setItem('dealerscope_audit_events', JSON.stringify(eventsToStore));
    } catch (error) {
      console.warn('Failed to save audit events:', error);
    }
  }

  private startPeriodicFlush() {
    this.flushTimeout = setInterval(() => {
      this.flush();
    }, this.config.flushInterval);
  }

  // Log an audit event
  log(
    action: string,
    category: AuditEvent['category'] = 'user_action',
    severity: AuditEvent['severity'] = 'info',
    details?: Record<string, any>,
    metadata?: Record<string, any>
  ) {
    const event: AuditEvent = {
      id: `audit_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
      action,
      details,
      sessionId: this.sessionId,
      userAgent: navigator.userAgent,
      severity,
      category,
      metadata
    };

    this.events.push(event);
    this.saveEvents();

    // Console logging based on severity
    const logLevel = severity === 'error' || severity === 'critical' ? 'error' :
                    severity === 'warning' ? 'warn' : 'log';
    
    console[logLevel](`[AUDIT] ${action}`, { event });

    // Auto-flush if batch size reached
    if (this.events.length >= this.config.batchSize) {
      this.flush();
    }
  }

  // Convenience methods for different event types
  logAuth(action: string, details?: Record<string, any>) {
    this.log(action, 'auth', 'info', details);
  }

  logUpload(filename: string, size: number, success: boolean) {
    this.log(
      'file_upload',
      'upload',
      success ? 'info' : 'error',
      { filename, size, success }
    );
  }

  logDataAccess(resource: string, operation: 'read' | 'write' | 'delete') {
    this.log(
      `data_${operation}`,
      'data',
      'info',
      { resource, operation }
    );
  }

  logError(error: Error, context?: string) {
    this.log(
      'application_error',
      'system',
      'error',
      {
        message: error.message,
        stack: error.stack,
        context
      }
    );
  }

  logUserAction(action: string, details?: Record<string, any>) {
    this.log(action, 'user_action', 'info', details);
  }

  // Async flush to remote endpoint
  async flush(): Promise<void> {
    if (this.events.length === 0) return;

    const eventsToFlush = [...this.events];
    this.events = [];
    this.saveEvents();

    if (this.config.enableRemoteLogging && this.config.endpoint) {
      try {
        const response = await fetch(this.config.endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            events: eventsToFlush,
            sessionId: this.sessionId,
            timestamp: Date.now()
          })
        });

        if (!response.ok) {
          throw new Error(`Audit flush failed: ${response.statusText}`);
        }

        logger.info('Audit events flushed to remote', { count: eventsToFlush.length });
      } catch (error) {
        console.error('Failed to flush audit events:', error);
        // Put events back if remote flush failed
        this.events = [...eventsToFlush, ...this.events];
        this.saveEvents();
      }
    }
  }

  // Get audit events with filtering options
  getEvents(options: {
    category?: AuditEvent['category'];
    severity?: AuditEvent['severity'];
    since?: number;
    limit?: number;
  } = {}): AuditEvent[] {
    let filtered = [...this.events];

    if (options.category) {
      filtered = filtered.filter(e => e.category === options.category);
    }

    if (options.severity) {
      filtered = filtered.filter(e => e.severity === options.severity);
    }

    if (options.since) {
      filtered = filtered.filter(e => e.timestamp >= options.since);
    }

    if (options.limit) {
      filtered = filtered.slice(-options.limit);
    }

    return filtered.sort((a, b) => b.timestamp - a.timestamp);
  }

  // Get audit statistics
  getStats() {
    const now = Date.now();
    const last24h = this.events.filter(e => now - e.timestamp < 86400000);
    const lastHour = this.events.filter(e => now - e.timestamp < 3600000);

    const categoryCounts = this.events.reduce((acc, event) => {
      acc[event.category] = (acc[event.category] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    const severityCounts = this.events.reduce((acc, event) => {
      acc[event.severity] = (acc[event.severity] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return {
      total: this.events.length,
      last24h: last24h.length,
      lastHour: lastHour.length,
      categories: categoryCounts,
      severities: severityCounts,
      sessionId: this.sessionId,
      oldestEvent: this.events.length > 0 ? this.events[0].timestamp : null,
      newestEvent: this.events.length > 0 ? this.events[this.events.length - 1].timestamp : null
    };
  }

  // Clear all events
  clear() {
    this.events = [];
    this.saveEvents();
  }

  // Destroy the logger
  destroy() {
    if (this.flushTimeout) {
      clearInterval(this.flushTimeout);
    }
    this.flush();
  }
}

// Global audit logger instance
export const auditLogger = new AuditLogger({
  enableRemoteLogging: process.env.NODE_ENV === 'production',
  endpoint: '/api/audit',
  batchSize: 5,
  flushInterval: 15000
});

// React hook for audit logging
export function useAuditLogger() {
  return {
    log: auditLogger.log.bind(auditLogger),
    logAuth: auditLogger.logAuth.bind(auditLogger),
    logUpload: auditLogger.logUpload.bind(auditLogger),
    logDataAccess: auditLogger.logDataAccess.bind(auditLogger),
    logError: auditLogger.logError.bind(auditLogger),
    logUserAction: auditLogger.logUserAction.bind(auditLogger),
    getEvents: auditLogger.getEvents.bind(auditLogger),
    getStats: auditLogger.getStats.bind(auditLogger)
  };
}

// Auto-cleanup before page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    auditLogger.flush();
  });
}