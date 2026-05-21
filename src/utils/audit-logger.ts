/**
 * Minimal client-side audit logger.
 * Current live surface is limited to upload/data/error logging used by the upload flow.
 */

import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('AuditLogger');

export interface AuditEvent {
  id: string;
  timestamp: number;
  action: string;
  details?: Record<string, unknown>;
  sessionId: string;
  userAgent: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
  category: 'data' | 'upload' | 'system';
}

class AuditLogger {
  private events: AuditEvent[] = [];
  private sessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

  constructor() {
    this.loadStoredEvents();
  }

  log(
    action: string,
    category: AuditEvent['category'] = 'system',
    severity: AuditEvent['severity'] = 'info',
    details?: Record<string, unknown>
  ): void {
    const event: AuditEvent = {
      id: `audit_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
      timestamp: Date.now(),
      action,
      details,
      sessionId: this.sessionId,
      userAgent: navigator.userAgent,
      severity,
      category,
    };

    this.events.push(event);
    this.persistEvents();

    const logMethod = severity === 'error' || severity === 'critical'
      ? logger.error.bind(logger)
      : severity === 'warning'
        ? logger.warn.bind(logger)
        : logger.info.bind(logger);

    logMethod(action, { event });
  }

  logUpload(filename: string, size: number, success: boolean): void {
    this.log('file_upload', 'upload', success ? 'info' : 'error', { filename, size, success });
  }

  logDataAccess(resource: string, operation: 'read' | 'write' | 'delete'): void {
    this.log(`data_${operation}`, 'data', 'info', { resource, operation });
  }

  logError(error: Error, context?: string): void {
    this.log('application_error', 'system', 'error', {
      message: error.message,
      stack: error.stack,
      context,
    });
  }

  private loadStoredEvents(): void {
    try {
      const stored = localStorage.getItem('dealerscope_audit_events');
      if (!stored) return;
      const parsed = JSON.parse(stored) as AuditEvent[];
      this.events = parsed.slice(-1000);
    } catch {
      this.events = [];
    }
  }

  private persistEvents(): void {
    try {
      localStorage.setItem('dealerscope_audit_events', JSON.stringify(this.events.slice(-1000)));
    } catch {
      // Ignore local persistence failures in client audit logging.
    }
  }
}

export const auditLogger = new AuditLogger();
