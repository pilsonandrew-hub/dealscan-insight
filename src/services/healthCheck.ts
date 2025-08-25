/**
 * Health Check System for Production Monitoring
 * Provides endpoints and monitoring for system health
 */

import { environmentManager } from '@/config/environmentManager';
import logger from '@/utils/productionLogger';

export enum HealthStatus {
  HEALTHY = 'healthy',
  DEGRADED = 'degraded',
  UNHEALTHY = 'unhealthy'
}

export interface HealthCheckResult {
  service: string;
  status: HealthStatus;
  responseTime: number;
  details: Record<string, any>;
  timestamp: string;
  error?: string;
}

export interface SystemHealth {
  overall: HealthStatus;
  services: HealthCheckResult[];
  uptime: number;
  version: string;
  environment: string;
  timestamp: string;
}

/**
 * Health Check Service
 */
export class HealthCheckService {
  private static instance: HealthCheckService;
  private services: Map<string, () => Promise<HealthCheckResult>> = new Map();
  private lastCheck: SystemHealth | null = null;
  private checkInterval: number = 30000; // 30 seconds

  private constructor() {
    this.registerDefaultServices();
    this.startPeriodicChecks();
  }

  static getInstance(): HealthCheckService {
    if (!HealthCheckService.instance) {
      HealthCheckService.instance = new HealthCheckService();
    }
    return HealthCheckService.instance;
  }

  /**
   * Register default health check services
   */
  private registerDefaultServices(): void {
    this.registerService('database', this.checkDatabase.bind(this));
    this.registerService('storage', this.checkStorage.bind(this));
    this.registerService('memory', this.checkMemory.bind(this));
    this.registerService('network', this.checkNetwork.bind(this));
  }

  /**
   * Register a health check service
   */
  registerService(name: string, checkFn: () => Promise<HealthCheckResult>): void {
    this.services.set(name, checkFn);
  }

  /**
   * Perform health check for all services
   */
  async performHealthCheck(): Promise<SystemHealth> {
    const startTime = Date.now();
    const results: HealthCheckResult[] = [];

    // Check all registered services
    for (const [serviceName, checkFn] of this.services) {
      try {
        const result = await Promise.race([
          checkFn(),
          new Promise<HealthCheckResult>((_, reject) =>
            setTimeout(() => reject(new Error('Health check timeout')), 5000)
          )
        ]);
        results.push(result);
      } catch (error) {
        results.push({
          service: serviceName,
          status: HealthStatus.UNHEALTHY,
          responseTime: Date.now() - startTime,
          details: {},
          timestamp: new Date().toISOString(),
          error: error instanceof Error ? error.message : 'Unknown error'
        });
      }
    }

    // Calculate overall status
    const overall = this.calculateOverallStatus(results);

    const systemHealth: SystemHealth = {
      overall,
      services: results,
      uptime: this.getUptime(),
      version: this.getVersion(),
      environment: environmentManager.getEnvironment(),
      timestamp: new Date().toISOString()
    };

    this.lastCheck = systemHealth;
    return systemHealth;
  }

  /**
   * Get last health check result
   */
  getLastHealthCheck(): SystemHealth | null {
    return this.lastCheck;
  }

  /**
   * Start periodic health checks
   */
  private startPeriodicChecks(): void {
    if (environmentManager.isProduction()) {
      setInterval(async () => {
        try {
          await this.performHealthCheck();
        } catch (error) {
          logger.error('Periodic health check failed', error as Error);
        }
      }, this.checkInterval);
    }
  }

  /**
   * Check database connectivity
   */
  private async checkDatabase(): Promise<HealthCheckResult> {
    const startTime = Date.now();
    
    try {
      const { supabase } = await import('@/integrations/supabase/client');
      
      // Simple query to test database connectivity
      const { data, error } = await supabase
        .from('profiles')
        .select('count', { count: 'exact', head: true });

      const responseTime = Date.now() - startTime;

      if (error) {
        return {
          service: 'database',
          status: HealthStatus.UNHEALTHY,
          responseTime,
          details: { error: error.message },
          timestamp: new Date().toISOString(),
          error: error.message
        };
      }

      return {
        service: 'database',
        status: responseTime < 1000 ? HealthStatus.HEALTHY : HealthStatus.DEGRADED,
        responseTime,
        details: { connected: true, count: data },
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'database',
        status: HealthStatus.UNHEALTHY,
        responseTime: Date.now() - startTime,
        details: {},
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : 'Database check failed'
      };
    }
  }

  /**
   * Check storage/localStorage functionality
   */
  private async checkStorage(): Promise<HealthCheckResult> {
    const startTime = Date.now();
    
    try {
      const testKey = 'health_check_test';
      const testValue = 'test_value';
      
      localStorage.setItem(testKey, testValue);
      const retrieved = localStorage.getItem(testKey);
      localStorage.removeItem(testKey);
      
      const success = retrieved === testValue;
      const responseTime = Date.now() - startTime;

      return {
        service: 'storage',
        status: success ? HealthStatus.HEALTHY : HealthStatus.UNHEALTHY,
        responseTime,
        details: { localStorage: success },
        timestamp: new Date().toISOString(),
        error: success ? undefined : 'localStorage test failed'
      };
    } catch (error) {
      return {
        service: 'storage',
        status: HealthStatus.UNHEALTHY,
        responseTime: Date.now() - startTime,
        details: {},
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : 'Storage check failed'
      };
    }
  }

  /**
   * Check memory usage
   */
  private async checkMemory(): Promise<HealthCheckResult> {
    const startTime = Date.now();
    
    try {
      const memoryInfo = (performance as any).memory;
      const responseTime = Date.now() - startTime;
      
      if (memoryInfo) {
        const usedMB = memoryInfo.usedJSHeapSize / 1024 / 1024;
        const totalMB = memoryInfo.totalJSHeapSize / 1024 / 1024;
        const limitMB = memoryInfo.jsHeapSizeLimit / 1024 / 1024;
        
        const memoryUsage = (usedMB / limitMB) * 100;
        
        let status = HealthStatus.HEALTHY;
        if (memoryUsage > 90) status = HealthStatus.UNHEALTHY;
        else if (memoryUsage > 70) status = HealthStatus.DEGRADED;

        return {
          service: 'memory',
          status,
          responseTime,
          details: {
            usedMB: Math.round(usedMB),
            totalMB: Math.round(totalMB),
            limitMB: Math.round(limitMB),
            usagePercent: Math.round(memoryUsage)
          },
          timestamp: new Date().toISOString()
        };
      } else {
        return {
          service: 'memory',
          status: HealthStatus.HEALTHY,
          responseTime,
          details: { available: false },
          timestamp: new Date().toISOString()
        };
      }
    } catch (error) {
      return {
        service: 'memory',
        status: HealthStatus.DEGRADED,
        responseTime: Date.now() - startTime,
        details: {},
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : 'Memory check failed'
      };
    }
  }

  /**
   * Check network connectivity
   */
  private async checkNetwork(): Promise<HealthCheckResult> {
    const startTime = Date.now();
    
    try {
      // Use navigator.onLine and a simple fetch test
      const online = navigator.onLine;
      
      if (!online) {
        return {
          service: 'network',
          status: HealthStatus.UNHEALTHY,
          responseTime: Date.now() - startTime,
          details: { online: false },
          timestamp: new Date().toISOString(),
          error: 'Network offline'
        };
      }

      // Test with a lightweight endpoint
      const response = await fetch('/favicon.ico', { 
        method: 'HEAD',
        cache: 'no-cache'
      });
      
      const responseTime = Date.now() - startTime;
      const status = response.ok ? 
        (responseTime < 2000 ? HealthStatus.HEALTHY : HealthStatus.DEGRADED) :
        HealthStatus.UNHEALTHY;

      return {
        service: 'network',
        status,
        responseTime,
        details: { 
          online: true, 
          statusCode: response.status 
        },
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        service: 'network',
        status: HealthStatus.UNHEALTHY,
        responseTime: Date.now() - startTime,
        details: {},
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : 'Network check failed'
      };
    }
  }

  /**
   * Calculate overall system status
   */
  private calculateOverallStatus(results: HealthCheckResult[]): HealthStatus {
    const statuses = results.map(r => r.status);
    
    if (statuses.includes(HealthStatus.UNHEALTHY)) {
      return HealthStatus.UNHEALTHY;
    }
    
    if (statuses.includes(HealthStatus.DEGRADED)) {
      return HealthStatus.DEGRADED;
    }
    
    return HealthStatus.HEALTHY;
  }

  /**
   * Get application uptime
   */
  private getUptime(): number {
    return performance.now();
  }

  /**
   * Get application version
   */
  private getVersion(): string {
    return import.meta.env.VITE_APP_VERSION || '1.0.0';
  }

  /**
   * Store health check result in database
   */
  private async storeHealthCheck(result: SystemHealth): Promise<void> {
    try {
      if (environmentManager.isProduction()) {
        // Store in database when types are available
        logger.info('Health check completed', {
          overall: result.overall,
          services: result.services.length,
          uptime: result.uptime
        });
      }
    } catch (error) {
      logger.error('Failed to store health check', error as Error);
    }
  }
}

// Global health check service
export const healthCheckService = HealthCheckService.getInstance();

// Health check endpoint for monitoring
export const getSystemHealth = () => healthCheckService.performHealthCheck();
export const getLastHealthCheck = () => healthCheckService.getLastHealthCheck();

export default healthCheckService;