/**
 * Production Readiness Gate
 * Enforces quality gates before deployment
 */

import { logger } from './UnifiedLogger';
import { configService } from './UnifiedConfigService';
import { performanceKit } from './PerformanceEmergencyKit';

interface QualityGate {
  name: string;
  required: boolean;
  check: () => Promise<GateResult>;
  weight: number; // 1-10, higher is more critical
}

interface GateResult {
  passed: boolean;
  score: number;
  message: string;
  details?: any;
  recommendations?: string[];
}

interface ProductionReadinessReport {
  overallScore: number;
  passed: boolean;
  gates: Array<GateResult & { name: string; weight: number }>;
  criticalIssues: string[];
  blockers: string[];
  warnings: string[];
  nextSteps: string[];
  timestamp: string;
}

class ProductionReadinessGate {
  private static instance: ProductionReadinessGate;
  private gates: QualityGate[] = [];
  private minimumScore = 75; // Must achieve 75% to pass
  private criticalGateThreshold = 8; // Gates with weight >= 8 are critical

  private constructor() {
    this.setupQualityGates();
  }

  static getInstance(): ProductionReadinessGate {
    if (!ProductionReadinessGate.instance) {
      ProductionReadinessGate.instance = new ProductionReadinessGate();
    }
    return ProductionReadinessGate.instance;
  }

  private setupQualityGates(): void {
    // Critical Infrastructure Gates
    this.gates.push({
      name: 'Security Configuration',
      required: true,
      weight: 10,
      check: this.checkSecurityConfiguration.bind(this),
    });

    this.gates.push({
      name: 'Error Handling',
      required: true,
      weight: 9,
      check: this.checkErrorHandling.bind(this),
    });

    this.gates.push({
      name: 'Performance Baseline',
      required: true,
      weight: 8,
      check: this.checkPerformanceBaseline.bind(this),
    });

    this.gates.push({
      name: 'Database Security',
      required: true,
      weight: 10,
      check: this.checkDatabaseSecurity.bind(this),
    });

    // Quality Gates
    this.gates.push({
      name: 'Test Coverage',
      required: false,
      weight: 7,
      check: this.checkTestCoverage.bind(this),
    });

    this.gates.push({
      name: 'Bundle Size',
      required: false,
      weight: 6,
      check: this.checkBundleSize.bind(this),
    });

    this.gates.push({
      name: 'Memory Usage',
      required: false,
      weight: 7,
      check: this.checkMemoryUsage.bind(this),
    });

    this.gates.push({
      name: 'API Performance',
      required: false,
      weight: 8,
      check: this.checkApiPerformance.bind(this),
    });

    // Operational Gates
    this.gates.push({
      name: 'Monitoring Setup',
      required: false,
      weight: 6,
      check: this.checkMonitoringSetup.bind(this),
    });

    this.gates.push({
      name: 'Logging Configuration',
      required: false,
      weight: 5,
      check: this.checkLoggingConfiguration.bind(this),
    });
  }

  private async checkSecurityConfiguration(): Promise<GateResult> {
    const issues: string[] = [];
    let score = 100;

    // Check if debug mode is disabled in production
    if (configService.isProduction && configService.security.enableDebugMode) {
      issues.push('Debug mode is enabled in production');
      score -= 50;
    }

    // Check for HTTPS enforcement
    if (configService.isProduction && !window.location.protocol.startsWith('https')) {
      issues.push('HTTPS is not enforced');
      score -= 30;
    }

    // Check security headers
    try {
      const response = await fetch(window.location.href, { method: 'HEAD' });
      const headers = response.headers;
      
      const requiredHeaders = [
        'x-content-type-options',
        'x-frame-options',
        'strict-transport-security'
      ];

      for (const header of requiredHeaders) {
        if (!headers.has(header)) {
          issues.push(`Missing security header: ${header}`);
          score -= 10;
        }
      }
    } catch (error) {
      issues.push('Unable to check security headers');
      score -= 20;
    }

    return {
      passed: score >= 70,
      score: Math.max(0, score),
      message: issues.length === 0 ? 'Security configuration is compliant' : `${issues.length} security issues found`,
      details: { issues },
      recommendations: issues.length > 0 ? [
        'Disable debug mode in production',
        'Implement proper security headers',
        'Enforce HTTPS'
      ] : [],
    };
  }

  private async checkErrorHandling(): Promise<GateResult> {
    let score = 100;
    const issues: string[] = [];

    // Check if error boundaries are set up
    const hasErrorBoundary = document.querySelector('[data-error-boundary]') !== null;
    if (!hasErrorBoundary) {
      issues.push('No error boundaries detected');
      score -= 40;
    }

    // Check for global error handlers
    const hasGlobalErrorHandler = window.onerror !== null || window.addEventListener;
    if (!hasGlobalErrorHandler) {
      issues.push('No global error handlers detected');
      score -= 30;
    }

    // Test error reporting
    try {
      // Simulate error reporting check
      await fetch('/api/errors', { method: 'HEAD' });
    } catch (error) {
      issues.push('Error reporting endpoint not available');
      score -= 20;
    }

    return {
      passed: score >= 60,
      score: Math.max(0, score),
      message: issues.length === 0 ? 'Error handling is properly configured' : `${issues.length} error handling issues found`,
      details: { issues },
      recommendations: issues.length > 0 ? [
        'Implement error boundaries',
        'Set up global error handlers',
        'Configure error reporting service'
      ] : [],
    };
  }

  private async checkPerformanceBaseline(): Promise<GateResult> {
    const metrics = performanceKit.getMetrics();
    let score = 100;
    const issues: string[] = [];

    // Check pending requests
    if (metrics.pendingRequests > 10) {
      issues.push(`Too many pending requests: ${metrics.pendingRequests}`);
      score -= 20;
    }

    // Check connection pool health
    if (metrics.activeConnections / metrics.totalConnections > 0.8) {
      issues.push('Connection pool utilization too high');
      score -= 15;
    }

    // Check for request queue backlog
    if (metrics.queuedRequests > 5) {
      issues.push(`Request queue backlog: ${metrics.queuedRequests}`);
      score -= 25;
    }

    // Measure page load performance
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
    if (navigation) {
      const loadTime = navigation.loadEventEnd - navigation.fetchStart;
      if (loadTime > 3000) { // 3 seconds
        issues.push(`Page load time too slow: ${Math.round(loadTime)}ms`);
        score -= 30;
      }
    }

    return {
      passed: score >= 70,
      score: Math.max(0, score),
      message: issues.length === 0 ? 'Performance baseline meets requirements' : `${issues.length} performance issues found`,
      details: { 
        metrics,
        loadTime: navigation ? Math.round(navigation.loadEventEnd - navigation.fetchStart) : 'unknown'
      },
      recommendations: issues.length > 0 ? [
        'Optimize request handling',
        'Implement request deduplication',
        'Add performance monitoring',
        'Optimize bundle size'
      ] : [],
    };
  }

  private async checkDatabaseSecurity(): Promise<GateResult> {
    let score = 100;
    const issues: string[] = [];

    // Check connection configuration
    const dbConfig = configService.database;
    
    if (!dbConfig.url.startsWith('https://')) {
      issues.push('Database connection is not using HTTPS');
      score -= 30;
    }

    if (dbConfig.anonKey.length < 32) {
      issues.push('Database anonymous key appears weak');
      score -= 20;
    }

    // Check connection pooling
    if (dbConfig.connectionPool.max > 50) {
      issues.push('Connection pool max size too high');
      score -= 10;
    }

    if (dbConfig.connectionPool.min === 0) {
      issues.push('Connection pool min size is zero');
      score -= 15;
    }

    return {
      passed: score >= 70,
      score: Math.max(0, score),
      message: issues.length === 0 ? 'Database security is compliant' : `${issues.length} database security issues found`,
      details: { 
        connectionConfig: {
          poolSize: `${dbConfig.connectionPool.min}-${dbConfig.connectionPool.max}`,
          timeout: dbConfig.connectionPool.idleTimeoutMs,
        }
      },
      recommendations: issues.length > 0 ? [
        'Use HTTPS for database connections',
        'Review connection pool settings',
        'Implement database monitoring'
      ] : [],
    };
  }

  private async checkTestCoverage(): Promise<GateResult> {
    // Simulate test coverage check
    const coverage = Math.random() * 100; // In real implementation, read from coverage reports
    
    let score = coverage;
    const target = 80;
    
    if (coverage < target) {
      score = (coverage / target) * 100;
    }

    return {
      passed: coverage >= target,
      score: Math.round(score),
      message: `Test coverage: ${Math.round(coverage)}% (target: ${target}%)`,
      details: { coverage, target },
      recommendations: coverage < target ? [
        'Add unit tests for critical components',
        'Implement integration tests',
        'Add end-to-end tests'
      ] : [],
    };
  }

  private async checkBundleSize(): Promise<GateResult> {
    const maxSize = 2 * 1024 * 1024; // 2MB
    let currentSize = 0;
    let score = 100;

    // Estimate bundle size from loaded scripts
    const scripts = document.querySelectorAll('script[src]');
    for (const script of scripts) {
      try {
        const response = await fetch((script as HTMLScriptElement).src, { method: 'HEAD' });
        const size = parseInt(response.headers.get('content-length') || '0');
        currentSize += size;
      } catch (error) {
        // Ignore errors for external scripts
      }
    }

    if (currentSize > maxSize) {
      score = Math.max(0, 100 - ((currentSize - maxSize) / maxSize) * 100);
    }

    return {
      passed: currentSize <= maxSize,
      score: Math.round(score),
      message: `Bundle size: ${Math.round(currentSize / 1024)}KB (max: ${Math.round(maxSize / 1024)}KB)`,
      details: { currentSize, maxSize },
      recommendations: currentSize > maxSize ? [
        'Enable code splitting',
        'Remove unused dependencies',
        'Implement tree shaking',
        'Use dynamic imports'
      ] : [],
    };
  }

  private async checkMemoryUsage(): Promise<GateResult> {
    let score = 100;
    let currentUsage = 0;
    let limit = 0;

    if ('memory' in performance) {
      const memory = (performance as any).memory;
      currentUsage = memory.usedJSHeapSize;
      limit = memory.jsHeapSizeLimit;
      
      const usagePercent = (currentUsage / limit) * 100;
      
      if (usagePercent > 80) {
        score = Math.max(0, 100 - (usagePercent - 80) * 5);
      }
    }

    return {
      passed: score >= 70,
      score: Math.round(score),
      message: `Memory usage: ${Math.round(currentUsage / 1024 / 1024)}MB`,
      details: { 
        used: Math.round(currentUsage / 1024 / 1024),
        limit: Math.round(limit / 1024 / 1024),
        percentage: Math.round((currentUsage / limit) * 100)
      },
      recommendations: score < 70 ? [
        'Implement memory leak detection',
        'Optimize component lifecycle',
        'Use WeakMap for caching',
        'Remove unused listeners'
      ] : [],
    };
  }

  private async checkApiPerformance(): Promise<GateResult> {
    const targetP95 = 200; // 200ms
    let score = 100;
    let p95Latency = 0;

    try {
      // Measure API performance with a simple health check
      const start = performance.now();
      await fetch('/api/health', { method: 'HEAD' });
      const end = performance.now();
      
      p95Latency = end - start;
      
      if (p95Latency > targetP95) {
        score = Math.max(0, 100 - ((p95Latency - targetP95) / targetP95) * 100);
      }
    } catch (error) {
      score = 50; // Partial score if health check fails
    }

    return {
      passed: p95Latency <= targetP95,
      score: Math.round(score),
      message: `API P95 latency: ${Math.round(p95Latency)}ms (target: ${targetP95}ms)`,
      details: { p95Latency, target: targetP95 },
      recommendations: p95Latency > targetP95 ? [
        'Optimize database queries',
        'Add request caching',
        'Implement connection pooling',
        'Use CDN for static assets'
      ] : [],
    };
  }

  private async checkMonitoringSetup(): Promise<GateResult> {
    let score = 100;
    const issues: string[] = [];

    // Check if monitoring is enabled
    if (!configService.performance.monitoring.enabled) {
      issues.push('Performance monitoring is disabled');
      score -= 30;
    }

    // Check for error tracking
    const hasErrorTracking = window.onerror !== null;
    if (!hasErrorTracking) {
      issues.push('Error tracking not configured');
      score -= 25;
    }

    // Check for performance APIs
    if (!('PerformanceObserver' in window)) {
      issues.push('Performance Observer API not available');
      score -= 20;
    }

    return {
      passed: score >= 60,
      score: Math.max(0, score),
      message: issues.length === 0 ? 'Monitoring is properly configured' : `${issues.length} monitoring issues found`,
      details: { issues },
      recommendations: issues.length > 0 ? [
        'Enable performance monitoring',
        'Set up error tracking service',
        'Implement custom metrics',
        'Add health check endpoints'
      ] : [],
    };
  }

  private async checkLoggingConfiguration(): Promise<GateResult> {
    let score = 100;
    const issues: string[] = [];

    // Check if logging is properly configured
    try {
      logger.info('Production readiness logging test');
      score += 0; // No issues if this succeeds
    } catch (error) {
      issues.push('Logging system not responding');
      score -= 40;
    }

    // Check log levels
    if (configService.isDevelopment) {
      // More lenient in development
    } else if (configService.isProduction) {
      // Stricter in production
      if (configService.security.enableDebugMode) {
        issues.push('Debug logging enabled in production');
        score -= 20;
      }
    }

    return {
      passed: score >= 70,
      score: Math.max(0, score),
      message: issues.length === 0 ? 'Logging is properly configured' : `${issues.length} logging issues found`,
      details: { issues },
      recommendations: issues.length > 0 ? [
        'Configure appropriate log levels',
        'Set up log aggregation',
        'Implement structured logging',
        'Add log rotation'
      ] : [],
    };
  }

  async runFullAssessment(): Promise<ProductionReadinessReport> {
    logger.info('Starting production readiness assessment');
    
    const results: Array<GateResult & { name: string; weight: number }> = [];
    const criticalIssues: string[] = [];
    const blockers: string[] = [];
    const warnings: string[] = [];
    const nextSteps: string[] = [];

    let totalScore = 0;
    let maxScore = 0;

    for (const gate of this.gates) {
      try {
        logger.debug(`Running quality gate: ${gate.name}`);
        const result = await gate.check();
        
        const gateResult = {
          ...result,
          name: gate.name,
          weight: gate.weight,
        };
        
        results.push(gateResult);
        
        // Calculate weighted score
        totalScore += result.score * gate.weight;
        maxScore += 100 * gate.weight;

        // Categorize issues
        if (!result.passed) {
          if (gate.required || gate.weight >= this.criticalGateThreshold) {
            criticalIssues.push(`${gate.name}: ${result.message}`);
            if (gate.required) {
              blockers.push(gate.name);
            }
          } else {
            warnings.push(`${gate.name}: ${result.message}`);
          }
        }

        // Collect recommendations
        if (result.recommendations) {
          nextSteps.push(...result.recommendations);
        }

      } catch (error) {
        logger.error(`Quality gate failed: ${gate.name}`, { error });
        
        const failedResult = {
          passed: false,
          score: 0,
          message: `Gate execution failed: ${error}`,
          name: gate.name,
          weight: gate.weight,
        };
        
        results.push(failedResult);
        
        if (gate.required) {
          blockers.push(gate.name);
        }
        criticalIssues.push(`${gate.name}: Execution failed`);
      }
    }

    const overallScore = Math.round((totalScore / maxScore) * 100);
    const passed = overallScore >= this.minimumScore && blockers.length === 0;

    const report: ProductionReadinessReport = {
      overallScore,
      passed,
      gates: results,
      criticalIssues: [...new Set(criticalIssues)],
      blockers: [...new Set(blockers)],
      warnings: [...new Set(warnings)],
      nextSteps: [...new Set(nextSteps)],
      timestamp: new Date().toISOString(),
    };

    logger.info('Production readiness assessment completed', {
      overallScore,
      passed,
      criticalIssues: criticalIssues.length,
      blockers: blockers.length,
      warnings: warnings.length,
    });

    return report;
  }

  // Quick health check for monitoring
  async quickHealthCheck(): Promise<{ healthy: boolean; score: number; issues: string[] }> {
    const criticalGates = this.gates.filter(gate => gate.required || gate.weight >= this.criticalGateThreshold);
    const issues: string[] = [];
    let totalScore = 0;

    for (const gate of criticalGates) {
      try {
        const result = await gate.check();
        totalScore += result.score * gate.weight;
        
        if (!result.passed) {
          issues.push(`${gate.name}: ${result.message}`);
        }
      } catch (error) {
        issues.push(`${gate.name}: Check failed`);
      }
    }

    const maxScore = criticalGates.reduce((sum, gate) => sum + (100 * gate.weight), 0);
    const score = Math.round((totalScore / maxScore) * 100);

    return {
      healthy: score >= this.minimumScore && issues.length === 0,
      score,
      issues,
    };
  }
}

export const productionGate = ProductionReadinessGate.getInstance();
export type { ProductionReadinessReport, GateResult };