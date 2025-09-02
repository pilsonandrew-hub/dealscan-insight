/**
 * Intrusion Detection System
 * Monitors and detects suspicious activities and potential attacks
 */

import { auditLogger } from './audit-logger';
import { DistributedRateLimit } from './distributedRateLimit';

export interface SecurityEvent {
  type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  userId?: string;
  ipAddress?: string;
  userAgent?: string;
  timestamp: Date;
  details: Record<string, any>;
}

export interface ThreatPattern {
  name: string;
  pattern: RegExp | ((data: any) => boolean);
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
}

class IntrusionDetectionSystem {
  private events: SecurityEvent[] = [];
  private readonly MAX_EVENTS = 10000;
  private readonly CLEANUP_INTERVAL = 24 * 60 * 60 * 1000; // 24 hours

  private readonly threatPatterns: ThreatPattern[] = [
    // SQL Injection patterns
    {
      name: 'sql_injection',
      pattern: /(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|SCRIPT)\b.*('|''|"|""|\-\-|#|\/\*))/gi,
      severity: 'critical',
      description: 'SQL injection attempt detected'
    },
    
    // XSS patterns
    {
      name: 'xss_attack',
      pattern: /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>|javascript:|on\w+\s*=/gi,
      severity: 'high',
      description: 'Cross-site scripting attempt detected'
    },
    
    // Directory traversal
    {
      name: 'directory_traversal',
      pattern: /(\.\.[\/\\]){2,}|(%2e%2e[\/\\]){2,}/gi,
      severity: 'high',
      description: 'Directory traversal attempt detected'
    },
    
    // Command injection
    {
      name: 'command_injection',
      pattern: /(\||&|;|\\$\(|`|<|>)\s*((ls|cat|pwd|id|whoami|uname|ps|netstat|ifconfig|ping|curl|wget)\b)/gi,
      severity: 'critical',
      description: 'Command injection attempt detected'
    },
    
    // Brute force login attempts
    {
      name: 'brute_force',
      pattern: (data: any) => {
        if (data.action === 'login_attempt' && data.failed) {
          const recentFailures = this.getRecentEvents('login_failure', data.ipAddress, 15 * 60 * 1000);
          return recentFailures.length >= 5;
        }
        return false;
      },
      severity: 'high',
      description: 'Brute force login attempt detected'
    },
    
    // Unusual data access patterns
    {
      name: 'data_exfiltration',
      pattern: (data: any) => {
        if (data.action === 'data_access') {
          const recentAccess = this.getRecentEvents('data_access', data.userId, 5 * 60 * 1000);
          return recentAccess.length >= 100; // 100 data access in 5 minutes
        }
        return false;
      },
      severity: 'medium',
      description: 'Unusual data access pattern detected'
    },
    
    // File upload attacks
    {
      name: 'malicious_upload',
      pattern: /\.(php|jsp|asp|aspx|exe|bat|cmd|sh|ps1|vbs|js|jar|war)$/gi,
      severity: 'high',
      description: 'Potentially malicious file upload detected'
    },
    
    // LDAP injection
    {
      name: 'ldap_injection',
      pattern: /(\*|\(|\)|\\x00|&|\|)/g,
      severity: 'medium',
      description: 'LDAP injection attempt detected'
    }
  ];

  constructor() {
    // Cleanup old events periodically
    setInterval(() => this.cleanup(), this.CLEANUP_INTERVAL);
  }

  /**
   * Analyze input for security threats
   */
  analyzeInput(
    input: string | Record<string, any>, 
    context: {
      userId?: string;
      ipAddress?: string;
      userAgent?: string;
      action: string;
    }
  ): SecurityEvent[] {
    const events: SecurityEvent[] = [];
    const inputStr = typeof input === 'string' ? input : JSON.stringify(input);

    for (const threat of this.threatPatterns) {
      let isMatch = false;
      
      if (threat.pattern instanceof RegExp) {
        isMatch = threat.pattern.test(inputStr);
      } else if (typeof threat.pattern === 'function') {
        isMatch = threat.pattern({ ...context, input });
      }

      if (isMatch) {
        const event: SecurityEvent = {
          type: threat.name,
          severity: threat.severity,
          userId: context.userId,
          ipAddress: context.ipAddress,
          userAgent: context.userAgent,
          timestamp: new Date(),
          details: {
            action: context.action,
            input: typeof input === 'string' ? input.substring(0, 500) : input,
            description: threat.description
          }
        };

        events.push(event);
        this.recordEvent(event);
      }
    }

    return events;
  }

  /**
   * Record security event
   */
  recordEvent(event: SecurityEvent): void {
    this.events.push(event);
    
    // Log to audit system
    auditLogger.log(
      `security_threat_${event.type}`,
      'system',
      event.severity === 'critical' ? 'error' : 
      event.severity === 'high' ? 'error' : 'warning',
      {
        threatType: event.type,
        severity: event.severity,
        userId: event.userId,
        ipAddress: event.ipAddress,
        details: event.details
      }
    );

    // Immediate response for critical threats
    if (event.severity === 'critical') {
      this.handleCriticalThreat(event);
    }

    // Keep only recent events
    if (this.events.length > this.MAX_EVENTS) {
      this.events = this.events.slice(-this.MAX_EVENTS);
    }
  }

  /**
   * Check for rate limiting violations
   */
  checkRateLimit(
    identifier: string,
    action: string,
    limits: { requests: number; windowMs: number }
  ): Promise<boolean> {
    const rateLimiter = new DistributedRateLimit({
      windowMs: limits.windowMs,
      maxRequests: limits.requests,
      keyPrefix: `ids_${action}`
    });

    return rateLimiter.checkLimit(identifier).then(result => {
      if (!result.allowed) {
        this.recordEvent({
          type: 'rate_limit_exceeded',
          severity: 'medium',
          userId: identifier,
          timestamp: new Date(),
          details: {
            action,
            limit: limits.requests,
            window: limits.windowMs,
            retryAfter: result.retryAfter
          }
        });
      }
      return result.allowed;
    });
  }

  /**
   * Get security events by type and time range
   */
  getEvents(
    type?: string,
    timeRangeMs?: number,
    severity?: string[]
  ): SecurityEvent[] {
    let filtered = [...this.events];

    if (type) {
      filtered = filtered.filter(e => e.type === type);
    }

    if (timeRangeMs) {
      const cutoff = new Date(Date.now() - timeRangeMs);
      filtered = filtered.filter(e => e.timestamp > cutoff);
    }

    if (severity) {
      filtered = filtered.filter(e => severity.includes(e.severity));
    }

    return filtered.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
  }

  /**
   * Get security metrics
   */
  getMetrics(timeRangeMs: number = 24 * 60 * 60 * 1000): {
    totalThreats: number;
    threatsByType: Record<string, number>;
    threatsBySeverity: Record<string, number>;
    topAttackers: Array<{ ip: string; count: number }>;
  } {
    const events = this.getEvents(undefined, timeRangeMs);
    
    const threatsByType: Record<string, number> = {};
    const threatsBySeverity: Record<string, number> = {};
    const attackerIPs: Record<string, number> = {};

    events.forEach(event => {
      // Count by type
      threatsByType[event.type] = (threatsByType[event.type] || 0) + 1;
      
      // Count by severity
      threatsBySeverity[event.severity] = (threatsBySeverity[event.severity] || 0) + 1;
      
      // Count by IP
      if (event.ipAddress) {
        attackerIPs[event.ipAddress] = (attackerIPs[event.ipAddress] || 0) + 1;
      }
    });

    const topAttackers = Object.entries(attackerIPs)
      .map(([ip, count]) => ({ ip, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);

    return {
      totalThreats: events.length,
      threatsByType,
      threatsBySeverity,
      topAttackers
    };
  }

  /**
   * Check if IP address should be blocked
   */
  shouldBlockIP(ipAddress: string, timeRangeMs: number = 60 * 60 * 1000): boolean {
    const recentEvents = this.events.filter(
      e => e.ipAddress === ipAddress && 
           e.timestamp > new Date(Date.now() - timeRangeMs)
    );

    // Block if too many critical or high severity events
    const criticalEvents = recentEvents.filter(e => e.severity === 'critical').length;
    const highEvents = recentEvents.filter(e => e.severity === 'high').length;

    return criticalEvents >= 3 || highEvents >= 10 || recentEvents.length >= 50;
  }

  private getRecentEvents(type: string, identifier?: string, timeRangeMs: number = 60 * 60 * 1000): SecurityEvent[] {
    const cutoff = new Date(Date.now() - timeRangeMs);
    return this.events.filter(e => 
      e.type === type && 
      e.timestamp > cutoff &&
      (!identifier || e.userId === identifier || e.ipAddress === identifier)
    );
  }

  private handleCriticalThreat(event: SecurityEvent): void {
    // For critical threats, we could:
    // 1. Temporarily block the IP
    // 2. Require additional authentication
    // 3. Alert administrators
    // 4. Lock the affected account
    
    auditLogger.log(
      'critical_threat_response',
      'system',
      'error',
      {
        event: event.type,
        response: 'immediate_mitigation_triggered',
        details: event.details
      }
    );
  }

  private cleanup(): void {
    const cutoff = new Date(Date.now() - (7 * 24 * 60 * 60 * 1000)); // 7 days
    const initialCount = this.events.length;
    this.events = this.events.filter(e => e.timestamp > cutoff);
    
    if (initialCount > this.events.length) {
      auditLogger.log(
        'ids_cleanup',
        'system',
        'info',
        {
          removedEvents: initialCount - this.events.length,
          remainingEvents: this.events.length
        }
      );
    }
  }
}

// Export singleton instance
export const intrusionDetection = new IntrusionDetectionSystem();

// Helper functions
export const analyzeInput = (input: string | Record<string, any>, context: any) =>
  intrusionDetection.analyzeInput(input, context);

export const recordSecurityEvent = (event: SecurityEvent) =>
  intrusionDetection.recordEvent(event);

export const getSecurityMetrics = (timeRangeMs?: number) =>
  intrusionDetection.getMetrics(timeRangeMs);

export const shouldBlockIP = (ipAddress: string, timeRangeMs?: number) =>
  intrusionDetection.shouldBlockIP(ipAddress, timeRangeMs);
