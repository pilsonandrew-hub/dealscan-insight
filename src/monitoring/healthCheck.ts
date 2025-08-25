/**
 * Production Health Check and Monitoring System
 * Provides comprehensive health monitoring for all system components
 */

import { createLogger } from '@/utils/productionLogger';
import { supabase } from '@/integrations/supabase/client';
import api from '@/services/api';

const logger = createLogger('HealthCheck');

export interface HealthStatus {
  service: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  responseTime: number;
  details?: Record<string, any>;
  lastCheck: string;
  uptime?: number;
}

export interface SystemHealth {
  overall: 'healthy' | 'degraded' | 'unhealthy';
  services: HealthStatus[];
  summary: {
    healthy: number;
    degraded: number;
    unhealthy: number;
    total: number;
  };
  timestamp: string;
  version: string;
}

class HealthMonitor {
  private checks: Map<string, () => Promise<HealthStatus>> = new Map();
  private lastResults: Map<string, HealthStatus> = new Map();
  private monitoring = false;
  private monitoringInterval?: NodeJS.Timeout;

  constructor() {
    this.registerDefaultChecks();
  }

  /**
   * Register default health checks
   */
  private registerDefaultChecks(): void {
    this.addHealthCheck('frontend', this.checkFrontend.bind(this));
    this.addHealthCheck('database', this.checkDatabase.bind(this));
    this.addHealthCheck('api', this.checkAPI.bind(this));
    this.addHealthCheck('memory', this.checkMemory.bind(this));
    this.addHealthCheck('performance', this.checkPerformance.bind(this));
    this.addHealthCheck('storage', this.checkStorage.bind(this));
  }

  /**
   * Add a custom health check
   */
  addHealthCheck(service: string, checkFn: () => Promise<HealthStatus>): void {
    this.checks.set(service, checkFn);
  }

  /**
   * Run all health checks
   */
  async runHealthChecks(): Promise<SystemHealth> {
    logger.info('Running system health checks', { 
      checkCount: this.checks.size 
    });

    const startTime = Date.now();
    const services: HealthStatus[] = [];

    // Run all checks in parallel
    const checkPromises = Array.from(this.checks.entries()).map(async ([service, checkFn]) => {
      try {
        const result = await Promise.race([
          checkFn(),
          this.timeoutPromise(service, 5000) // 5 second timeout
        ]);
        
        this.lastResults.set(service, result);
        services.push(result);
        return result;
      } catch (error) {
        const failedResult: HealthStatus = {
          service,
          status: 'unhealthy',
          responseTime: 5000,
          details: { 
            error: error instanceof Error ? error.message : String(error)
          },
          lastCheck: new Date().toISOString()
        };
        
        this.lastResults.set(service, failedResult);
        services.push(failedResult);
        return failedResult;
      }
    });

    await Promise.all(checkPromises);

    // Calculate overall health
    const healthy = services.filter(s => s.status === 'healthy').length;
    const degraded = services.filter(s => s.status === 'degraded').length;
    const unhealthy = services.filter(s => s.status === 'unhealthy').length;
    const total = services.length;

    let overall: SystemHealth['overall'] = 'healthy';
    if (unhealthy > 0 || degraded > total / 2) {
      overall = 'unhealthy';
    } else if (degraded > 0) {
      overall = 'degraded';
    }

    const duration = Date.now() - startTime;
    logger.info('Health check completed', {
      overall,
      healthy,
      degraded,
      unhealthy,
      duration: `${duration}ms`
    });

    return {
      overall,
      services,
      summary: { healthy, degraded, unhealthy, total },
      timestamp: new Date().toISOString(),
      version: '5.0-production'
    };
  }

  /**
   * Start continuous monitoring
   */
  startMonitoring(intervalMs: number = 60000): void {
    if (this.monitoring) return;

    this.monitoring = true;
    logger.info('Starting health monitoring', { intervalMs });

    this.monitoringInterval = setInterval(async () => {
      try {
        const health = await this.runHealthChecks();
        
        // Log critical issues
        if (health.overall === 'unhealthy') {
          logger.error('System health critical', {
            unhealthyServices: health.services
              .filter(s => s.status === 'unhealthy')
              .map(s => s.service)
          });
        }
        
        // Store health data in database for trending
        await this.storeHealthData(health);
        
      } catch (error) {
        logger.error('Health monitoring error', {}, error as Error);
      }
    }, intervalMs);
  }

  /**
   * Stop continuous monitoring
   */
  stopMonitoring(): void {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = undefined;
    }
    this.monitoring = false;
    logger.info('Health monitoring stopped');
  }

  /**
   * Get last health check results
   */
  getLastResults(): Map<string, HealthStatus> {
    return new Map(this.lastResults);
  }

  // INDIVIDUAL HEALTH CHECKS

  private async checkFrontend(): Promise<HealthStatus> {
    const startTime = Date.now();
    
    try {
      // Check if React is loaded and working
      const hasReactRoot = document.getElementById('root') !== null;
      const hasContent = document.body.textContent && document.body.textContent.length > 0;
      
      let status: HealthStatus['status'] = 'healthy';
      let details: Record<string, any> = {
        reactRoot: hasReactRoot,
        hasContent,
        url: window.location.href
      };

      if (!hasReactRoot || !hasContent) {
        status = 'degraded';
        details.issue = 'Missing React root or content';
      }

      return {
        service: 'frontend',
        status,
        responseTime: Date.now() - startTime,
        details,
        lastCheck: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'frontend',
        status: 'unhealthy',
        responseTime: Date.now() - startTime,
        details: { 
          error: error instanceof Error ? error.message : String(error)
        },
        lastCheck: new Date().toISOString()
      };
    }
  }

  private async checkDatabase(): Promise<HealthStatus> {
    const startTime = Date.now();
    
    try {
      // Test basic database connectivity
      const { data, error } = await supabase
        .from('opportunities')
        .select('count')
        .limit(1);

      let status: HealthStatus['status'] = 'healthy';
      let details: Record<string, any> = {
        connected: !error,
        error: error?.message
      };

      if (error) {
        status = 'unhealthy';
      }

      return {
        service: 'database',
        status,
        responseTime: Date.now() - startTime,
        details,
        lastCheck: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'database',
        status: 'unhealthy',
        responseTime: Date.now() - startTime,
        details: { 
          error: error instanceof Error ? error.message : String(error)
        },
        lastCheck: new Date().toISOString()
      };
    }
  }

  private async checkAPI(): Promise<HealthStatus> {
    const startTime = Date.now();
    
    try {
      // Test API functionality
      const metrics = await api.getDashboardMetrics();
      
      let status: HealthStatus['status'] = 'healthy';
      let details: Record<string, any> = {
        metricsAvailable: !!metrics,
        responseTime: Date.now() - startTime
      };

      // Check response time
      const responseTime = Date.now() - startTime;
      if (responseTime > 2000) {
        status = 'degraded';
        details.slowResponse = true;
      }

      return {
        service: 'api',
        status,
        responseTime,
        details,
        lastCheck: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'api',
        status: 'unhealthy',
        responseTime: Date.now() - startTime,
        details: { 
          error: error instanceof Error ? error.message : String(error)
        },
        lastCheck: new Date().toISOString()
      };
    }
  }

  private async checkMemory(): Promise<HealthStatus> {
    const startTime = Date.now();
    
    try {
      let status: HealthStatus['status'] = 'healthy';
      let details: Record<string, any> = {};

      if ('memory' in performance) {
        const memInfo = (performance as any).memory;
        const usedMB = Math.round((memInfo?.usedJSHeapSize || 0) / 1024 / 1024);
        const totalMB = Math.round((memInfo?.totalJSHeapSize || 0) / 1024 / 1024);
        const limitMB = Math.round((memInfo?.jsHeapSizeLimit || 0) / 1024 / 1024);

        details = {
          usedMB,
          totalMB,
          limitMB,
          usagePercent: Math.round((usedMB / limitMB) * 100)
        };

        // Memory thresholds
        if (usedMB > 150) {
          status = 'unhealthy';
        } else if (usedMB > 100) {
          status = 'degraded';
        }
      } else {
        details.note = 'Memory API not available';
      }

      return {
        service: 'memory',
        status,
        responseTime: Date.now() - startTime,
        details,
        lastCheck: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'memory',
        status: 'unhealthy',
        responseTime: Date.now() - startTime,
        details: { 
          error: error instanceof Error ? error.message : String(error)
        },
        lastCheck: new Date().toISOString()
      };
    }
  }

  private async checkPerformance(): Promise<HealthStatus> {
    const startTime = Date.now();
    
    try {
      let status: HealthStatus['status'] = 'healthy';
      let details: Record<string, any> = {};

      if (typeof window !== 'undefined' && window.performance) {
        const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
        
        if (navigation) {
          const loadTime = navigation.loadEventEnd - navigation.fetchStart;
          const domContentLoaded = navigation.domContentLoadedEventEnd - navigation.fetchStart;
          const firstByte = navigation.responseStart - navigation.fetchStart;

          details = {
            loadTime: Math.round(loadTime),
            domContentLoaded: Math.round(domContentLoaded),
            firstByte: Math.round(firstByte)
          };

          // Performance thresholds
          if (loadTime > 3000) {
            status = 'unhealthy';
          } else if (loadTime > 2000) {
            status = 'degraded';
          }
        }
      } else {
        details.note = 'Performance API not available';
      }

      return {
        service: 'performance',
        status,
        responseTime: Date.now() - startTime,
        details,
        lastCheck: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'performance',
        status: 'unhealthy',
        responseTime: Date.now() - startTime,
        details: { 
          error: error instanceof Error ? error.message : String(error)
        },
        lastCheck: new Date().toISOString()
      };
    }
  }

  private async checkStorage(): Promise<HealthStatus> {
    const startTime = Date.now();
    
    try {
      let status: HealthStatus['status'] = 'healthy';
      let details: Record<string, any> = {};

      // Test localStorage
      const testKey = 'health-check-test';
      const testValue = Date.now().toString();
      
      try {
        localStorage.setItem(testKey, testValue);
        const retrieved = localStorage.getItem(testKey);
        localStorage.removeItem(testKey);
        
        details.localStorage = retrieved === testValue;
        
        if (retrieved !== testValue) {
          status = 'degraded';
        }
      } catch (storageError) {
        status = 'degraded';
        details.localStorageError = storageError instanceof Error ? storageError.message : String(storageError);
      }

      // Check storage quota if available
      if ('storage' in navigator && 'estimate' in navigator.storage) {
        try {
          const estimate = await navigator.storage.estimate();
          details.storageQuota = {
            used: estimate.usage ? Math.round(estimate.usage / 1024 / 1024) : 0,
            available: estimate.quota ? Math.round(estimate.quota / 1024 / 1024) : 0
          };
        } catch (quotaError) {
          details.quotaError = quotaError instanceof Error ? quotaError.message : String(quotaError);
        }
      }

      return {
        service: 'storage',
        status,
        responseTime: Date.now() - startTime,
        details,
        lastCheck: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'storage',
        status: 'unhealthy',
        responseTime: Date.now() - startTime,
        details: { 
          error: error instanceof Error ? error.message : String(error)
        },
        lastCheck: new Date().toISOString()
      };
    }
  }

  /**
   * Create a timeout promise for health checks
   */
  private async timeoutPromise(service: string, ms: number): Promise<HealthStatus> {
    return new Promise((_, reject) => {
      setTimeout(() => {
        reject(new Error(`Health check timeout for ${service} after ${ms}ms`));
      }, ms);
    });
  }

  /**
   * Store health data in database for trending
   */
  private async storeHealthData(health: SystemHealth): Promise<void> {
    try {
      await supabase.from('health_checks').insert({
        service_name: 'system',
        status: health.overall,
        response_time_ms: health.services.reduce((sum, s) => sum + s.responseTime, 0) / health.services.length,
        details: {
          summary: health.summary,
          services: health.services.map(s => ({
            name: s.service,
            status: s.status,
            responseTime: s.responseTime
          }))
        }
      });
    } catch (error) {
      logger.error('Failed to store health data', {}, error as Error);
    }
  }
}

export const healthMonitor = new HealthMonitor();