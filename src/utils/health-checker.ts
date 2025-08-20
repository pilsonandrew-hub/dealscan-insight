/**
 * Health checking system
 * Inspired by the health check patterns in the bootstrap script
 */

import { settings } from '@/config/settings';
import { apiCache } from './api-cache';
import { performanceMonitor } from './performance-monitor';
import { auditLogger } from './audit-logger';

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: number;
  checks: Record<string, HealthCheckResult>;
  overall: {
    score: number;
    message: string;
    uptime: number;
  };
}

export interface HealthCheckResult {
  status: 'pass' | 'warn' | 'fail';
  duration: number;
  message: string;
  details?: Record<string, any>;
  timestamp: number;
}

export interface HealthCheckConfig {
  timeout: number;
  enabled: boolean;
  critical: boolean;
  interval?: number;
}

type HealthCheckFunction = () => Promise<HealthCheckResult>;

export class HealthChecker {
  private checks: Map<string, { fn: HealthCheckFunction; config: HealthCheckConfig }> = new Map();
  private lastResults: Map<string, HealthCheckResult> = new Map();
  private startTime: number = Date.now();
  private intervals: Map<string, NodeJS.Timeout> = new Map();

  constructor() {
    this.registerDefaultChecks();
  }

  // Register a health check
  registerCheck(
    name: string,
    checkFn: HealthCheckFunction,
    config: Partial<HealthCheckConfig> = {}
  ) {
    const finalConfig: HealthCheckConfig = {
      timeout: 5000,
      enabled: true,
      critical: false,
      ...config
    };

    this.checks.set(name, { fn: checkFn, config: finalConfig });

    // Start periodic check if interval is specified
    if (finalConfig.interval && finalConfig.enabled) {
      this.startPeriodicCheck(name, finalConfig.interval);
    }

    auditLogger.log(
      'health_check_registered',
      'system',
      'info',
      { checkName: name, config: finalConfig }
    );
  }

  // Start periodic health check
  private startPeriodicCheck(name: string, interval: number) {
    if (this.intervals.has(name)) {
      clearInterval(this.intervals.get(name)!);
    }

    const intervalId = setInterval(async () => {
      try {
        await this.runSingleCheck(name);
      } catch (error) {
        console.error(`Periodic health check failed for ${name}:`, error);
      }
    }, interval);

    this.intervals.set(name, intervalId);
  }

  // Run a single health check
  async runSingleCheck(name: string): Promise<HealthCheckResult> {
    const check = this.checks.get(name);
    if (!check || !check.config.enabled) {
      return {
        status: 'warn',
        duration: 0,
        message: 'Check not found or disabled',
        timestamp: Date.now()
      };
    }

    const timer = performanceMonitor.startTimer(`health_check_${name}`);
    const startTime = Date.now();

    try {
      // Add timeout to the check
      const timeoutPromise = new Promise<HealthCheckResult>((_, reject) => {
        setTimeout(() => reject(new Error('Health check timeout')), check.config.timeout);
      });

      const checkPromise = check.fn();
      const result = await Promise.race([checkPromise, timeoutPromise]);
      
      const duration = timer.end(result.status === 'pass');
      result.duration = duration;
      result.timestamp = Date.now();

      this.lastResults.set(name, result);

      // Log health check result
      if (result.status === 'fail') {
        auditLogger.log(
          'health_check_failed',
          'system',
          check.config.critical ? 'error' : 'warning',
          { checkName: name, result }
        );
      }

      return result;
    } catch (error) {
      const duration = timer.end(false);
      const result: HealthCheckResult = {
        status: 'fail',
        duration,
        message: error instanceof Error ? error.message : 'Unknown error',
        timestamp: Date.now()
      };

      this.lastResults.set(name, result);
      auditLogger.logError(error as Error, `health_check_${name}`);
      
      return result;
    }
  }

  // Run all health checks
  async checkHealth(): Promise<HealthStatus> {
    const timer = performanceMonitor.startTimer('health_check_all');
    const checks: Record<string, HealthCheckResult> = {};

    // Run all enabled checks in parallel
    const checkPromises = Array.from(this.checks.entries())
      .filter(([, { config }]) => config.enabled)
      .map(async ([name]) => {
        const result = await this.runSingleCheck(name);
        checks[name] = result;
        return { name, result };
      });

    await Promise.allSettled(checkPromises);
    timer.end(true);

    // Calculate overall health
    const results = Object.values(checks);
    const passCount = results.filter(r => r.status === 'pass').length;
    const warnCount = results.filter(r => r.status === 'warn').length;
    const failCount = results.filter(r => r.status === 'fail').length;

    // Calculate health score (0-100)
    const score = results.length > 0 ? 
      Math.round(((passCount + (warnCount * 0.5)) / results.length) * 100) : 100;

    // Determine overall status
    let status: 'healthy' | 'degraded' | 'unhealthy';
    let message: string;

    if (score >= 90) {
      status = 'healthy';
      message = 'All systems operational';
    } else if (score >= 70) {
      status = 'degraded';
      message = `${warnCount + failCount} checks not passing`;
    } else {
      status = 'unhealthy';
      message = `${failCount} critical issues detected`;
    }

    const healthStatus: HealthStatus = {
      status,
      timestamp: Date.now(),
      checks,
      overall: {
        score,
        message,
        uptime: Date.now() - this.startTime
      }
    };

    return healthStatus;
  }

  // Get last known results without running checks
  getLastResults(): HealthStatus {
    const checks: Record<string, HealthCheckResult> = {};
    this.lastResults.forEach((result, name) => {
      checks[name] = result;
    });

    const results = Object.values(checks);
    const passCount = results.filter(r => r.status === 'pass').length;
    const score = results.length > 0 ? 
      Math.round((passCount / results.length) * 100) : 100;

    return {
      status: score >= 90 ? 'healthy' : score >= 70 ? 'degraded' : 'unhealthy',
      timestamp: Date.now(),
      checks,
      overall: {
        score,
        message: `Last check: ${passCount}/${results.length} passing`,
        uptime: Date.now() - this.startTime
      }
    };
  }

  // Register default health checks
  private registerDefaultChecks() {
    // API connectivity check
    this.registerCheck('api_connectivity', async () => {
      try {
        const response = await fetch(`${settings.api.baseUrl}/health`, {
          method: 'GET',
          timeout: 3000
        } as any);

        if (response.ok) {
          return {
            status: 'pass',
            duration: 0,
            message: 'API is reachable',
            timestamp: Date.now()
          };
        } else {
          return {
            status: 'fail',
            duration: 0,
            message: `API returned ${response.status}`,
            timestamp: Date.now()
          };
        }
      } catch (error) {
        return {
          status: 'fail',
          duration: 0,
          message: 'API unreachable',
          details: { error: error instanceof Error ? error.message : 'Unknown error' },
          timestamp: Date.now()
        };
      }
    }, { critical: true, interval: 30000 });

    // Cache health check
    this.registerCheck('cache_health', async () => {
      try {
        const stats = apiCache.getStats();
        const healthScore = Math.min(100, (stats.maxSize - stats.size) / stats.maxSize * 100);

        if (healthScore > 80) {
          return {
            status: 'pass',
            duration: 0,
            message: 'Cache is healthy',
            details: stats,
            timestamp: Date.now()
          };
        } else if (healthScore > 50) {
          return {
            status: 'warn',
            duration: 0,
            message: 'Cache is getting full',
            details: stats,
            timestamp: Date.now()
          };
        } else {
          return {
            status: 'fail',
            duration: 0,
            message: 'Cache is nearly full',
            details: stats,
            timestamp: Date.now()
          };
        }
      } catch (error) {
        return {
          status: 'fail',
          duration: 0,
          message: 'Cache check failed',
          timestamp: Date.now()
        };
      }
    }, { interval: 60000 });

    // Performance check
    this.registerCheck('performance', async () => {
      try {
        const stats = performanceMonitor.getStats();
        const avgResponseTime = stats.averageResponseTime || 0;

        if (avgResponseTime < 1000) {
          return {
            status: 'pass',
            duration: 0,
            message: 'Performance is good',
            details: { avgResponseTime },
            timestamp: Date.now()
          };
        } else if (avgResponseTime < 3000) {
          return {
            status: 'warn',
            duration: 0,
            message: 'Performance is degraded',
            details: { avgResponseTime },
            timestamp: Date.now()
          };
        } else {
          return {
            status: 'fail',
            duration: 0,
            message: 'Performance is poor',
            details: { avgResponseTime },
            timestamp: Date.now()
          };
        }
      } catch (error) {
        return {
          status: 'fail',
          duration: 0,
          message: 'Performance check failed',
          timestamp: Date.now()
        };
      }
    }, { interval: 120000 });

    // Local storage check
    this.registerCheck('storage', async () => {
      try {
        const testKey = 'health_check_test';
        const testValue = Date.now().toString();
        
        localStorage.setItem(testKey, testValue);
        const retrieved = localStorage.getItem(testKey);
        localStorage.removeItem(testKey);

        if (retrieved === testValue) {
          return {
            status: 'pass',
            duration: 0,
            message: 'Local storage is working',
            timestamp: Date.now()
          };
        } else {
          return {
            status: 'fail',
            duration: 0,
            message: 'Local storage read/write failed',
            timestamp: Date.now()
          };
        }
      } catch (error) {
        return {
          status: 'fail',
          duration: 0,
          message: 'Local storage is not available',
          timestamp: Date.now()
        };
      }
    });
  }

  // Cleanup
  destroy() {
    this.intervals.forEach(interval => clearInterval(interval));
    this.intervals.clear();
  }
}

// Global health checker instance
export const healthChecker = new HealthChecker();

import { useState } from 'react';

// React hook for health status
export function useHealthStatus() {
  const [status, setStatus] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const checkHealth = async () => {
    setLoading(true);
    try {
      const healthStatus = await healthChecker.checkHealth();
      setStatus(healthStatus);
    } catch (error) {
      console.error('Health check failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const getLastResults = () => {
    setStatus(healthChecker.getLastResults());
  };

  return {
    status,
    loading,
    checkHealth,
    getLastResults
  };
}