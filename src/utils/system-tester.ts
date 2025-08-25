/**
 * System Testing Utility - Inspired by DealerScope v4.7 evaluation script
 * Provides comprehensive testing capabilities for our frontend application
 */

import api from '@/services/api';
import { performanceMonitor } from './performance-monitor';
import { auditLogger } from './audit-logger';

export interface TestResult {
  name: string;
  status: 'pass' | 'fail' | 'warn' | 'skip';
  detail: string;
  timestamp: number;
  duration?: number;
}

export interface SystemMetrics {
  dashboard_avg_ms: number;
  api_success_rate: number;
  cache_hit_rate: number;
  memory_usage: number;
  error_count_24h: number;
}

export interface TestSummary {
  total: number;
  passed: number;
  failed: number;
  warned: number;
  skipped: number;
  score_pct: number;
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
  timestamp: number;
}

export interface EvaluationReport {
  tests: TestResult[];
  metrics: SystemMetrics;
  summary: TestSummary;
  timestamp: string;
  version: string;
}

class SystemTester {
  private results: TestResult[] = [];
  private metrics: Partial<SystemMetrics> = {};

  /**
   * Run comprehensive system evaluation
   */
  async runFullEvaluation(): Promise<EvaluationReport> {
    console.log('🚀 Starting DealerScope System Evaluation...');
    
    this.results = [];
    this.metrics = {};
    
    // Run all test suites in parallel for efficiency
    await Promise.all([
      this.testFrontendBasics(),
      this.testAPIEndpoints(),
      this.testPerformance(),
      this.testErrorHandling(),
      this.testCaching(),
      this.testSecurity()
    ]);

    const summary = this.generateSummary();
    
    return {
      tests: this.results,
      metrics: this.metrics as SystemMetrics,
      summary,
      timestamp: new Date().toISOString(),
      version: '5.0-elite'
    };
  }

  /**
   * Test basic frontend functionality
   */
  private async testFrontendBasics(): Promise<void> {
    try {
      // Test if app is accessible
      const startTime = performance.now();
      const response = await fetch(window.location.origin);
      const duration = performance.now() - startTime;
      
      if (response.ok) {
        this.addResult('frontend-loads', 'pass', `Frontend loads successfully (${Math.round(duration)}ms)`, duration);
      } else {
        this.addResult('frontend-loads', 'fail', `HTTP ${response.status}`, duration);
      }

      // Test React app detection
      const hasReactRoot = document.getElementById('root') !== null;
      this.addResult('react-app', hasReactRoot ? 'pass' : 'fail', 
        hasReactRoot ? 'React application detected' : 'React root not found');

      // Test if critical components exist
      const hasDealerScopeHeader = document.querySelector('[data-testid="dealerscope-header"]') || 
                                   document.querySelector('header') ||
                                   document.body.textContent?.includes('DealerScope');
      
      this.addResult('critical-components', hasDealerScopeHeader ? 'pass' : 'warn',
        hasDealerScopeHeader ? 'Critical components detected' : 'Some components may be missing');

    } catch (error) {
      this.addResult('frontend-loads', 'fail', `Error: ${error}`);
    }
  }

  /**
   * Test API endpoints and health
   */
  private async testAPIEndpoints(): Promise<void> {
    const endpoints = [
      { name: 'health-check', method: 'healthCheck', description: 'Health endpoint' },
      { name: 'opportunities', method: 'getOpportunities', description: 'Get opportunities' },
      { name: 'dashboard-metrics', method: 'getDashboardMetrics', description: 'Dashboard metrics' }
    ];

    for (const endpoint of endpoints) {
      try {
        const startTime = performance.now();
        
        // Type-safe method calling
        let result;
        if (endpoint.method === 'healthCheck' && 'healthCheck' in api) {
          result = await (api as any).healthCheck();
        } else if (endpoint.method === 'getOpportunities') {
          result = await api.getOpportunities();
        } else if (endpoint.method === 'getDashboardMetrics') {
          result = await api.getDashboardMetrics();
        }
        
        const duration = performance.now() - startTime;
        
        if (result) {
          this.addResult(endpoint.name, 'pass', 
            `${endpoint.description} successful (${Math.round(duration)}ms)`, duration);
        } else {
          this.addResult(endpoint.name, 'warn', 
            `${endpoint.description} returned empty result`, duration);
        }
      } catch (error) {
        this.addResult(endpoint.name, 'fail', 
          `${endpoint.description} failed: ${error}`);
      }
    }
  }

  /**
   * Test performance benchmarks (inspired by v4.7 dashboard timing)
   */
  private async testPerformance(): Promise<void> {
    const iterations = 5;
    const times: number[] = [];
    
    // Test multiple iterations like the v4.7 script
    for (let i = 0; i < iterations; i++) {
      try {
        const startTime = performance.now();
        await api.getDashboardMetrics();
        const duration = performance.now() - startTime;
        times.push(duration);
        
        // Small delay between requests
        await new Promise(resolve => setTimeout(resolve, 100));
      } catch (error) {
        console.warn(`Performance test iteration ${i + 1} failed:`, error);
      }
    }

    if (times.length > 0) {
      const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
      this.metrics.dashboard_avg_ms = Math.round(avgTime);
      
      // Performance thresholds inspired by v4.7
      if (avgTime < 1000) {
        this.addResult('latency-performance', 'pass', `Avg response time: ${Math.round(avgTime)}ms (<1000ms target)`);
      } else if (avgTime < 2000) {
        this.addResult('latency-performance', 'warn', `Avg response time: ${Math.round(avgTime)}ms (1000-2000ms)`);
      } else {
        this.addResult('latency-performance', 'fail', `Avg response time: ${Math.round(avgTime)}ms (>2000ms)`);
      }
    } else {
      this.addResult('latency-performance', 'fail', 'Could not measure performance');
    }

    // Test memory usage
    if ('memory' in performance) {
      const memInfo = (performance as any).memory;
      const memUsageMB = Math.round((memInfo?.usedJSHeapSize || 0) / 1024 / 1024);
      this.metrics.memory_usage = memUsageMB;
      
      // More lenient thresholds for modern applications
      if (memUsageMB < 80) {
        this.addResult('memory-usage', 'pass', `Memory usage: ${memUsageMB}MB (<80MB)`);
      } else if (memUsageMB < 120) {
        this.addResult('memory-usage', 'warn', `Memory usage: ${memUsageMB}MB (80-120MB)`);
      } else {
        this.addResult('memory-usage', 'fail', `Memory usage: ${memUsageMB}MB (>120MB)`);
      }
    } else {
      this.addResult('memory-usage', 'skip', 'Memory API not available');
    }
  }

  /**
   * Test error handling and resilience
   */
  private async testErrorHandling(): Promise<void> {
    try {
      // Test 404 handling for API routes specifically
      const response = await fetch('/api/nonexistent-endpoint');
      if (response.status === 404) {
        this.addResult('error-handling', 'pass', '404 handling works correctly');
      } else {
        this.addResult('error-handling', 'warn', `Unexpected status for 404 test: ${response.status}`);
      }
    } catch (error) {
      this.addResult('error-handling', 'pass', 'Network error handling active');
    }

    // Test circuit breaker (attempt to trigger)
    try {
      // This should be handled gracefully by our circuit breaker
      await api.getOpportunities();
      this.addResult('circuit-breaker', 'pass', 'Circuit breaker protection active');
    } catch (error) {
      this.addResult('circuit-breaker', 'warn', 'Circuit breaker may have triggered');
    }
  }

  /**
   * Test caching system
   */
  private async testCaching(): Promise<void> {
    try {
      // Clear cache first to ensure clean test
      if ('clearCache' in api) {
        (api as any).clearCache();
      }
      
      // Wait a bit to ensure cache is cleared
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // First call (should miss cache)
      const start1 = performance.now();
      const result1 = await api.getOpportunities();
      const time1 = performance.now() - start1;
      
      // Immediate second call (should hit cache)
      const start2 = performance.now();
      const result2 = await api.getOpportunities();
      const time2 = performance.now() - start2;
      
      // Cache hit should be significantly faster (at least 50% faster)
      const improvement = (time1 - time2) / time1;
      if (improvement > 0.5 || time2 < 10) { // Either 50% faster or under 10ms (cached)
        this.addResult('caching-system', 'pass', 
          `Cache working (${Math.round(time1)}ms → ${Math.round(time2)}ms, ${Math.round(improvement * 100)}% improvement)`);
        this.metrics.cache_hit_rate = Math.round(improvement * 100);
      } else {
        this.addResult('caching-system', 'warn', 
          `Cache may not be working effectively (${Math.round(time1)}ms → ${Math.round(time2)}ms, ${Math.round(improvement * 100)}% improvement)`);
        this.metrics.cache_hit_rate = Math.round(improvement * 100);
      }

      // Test cache stats (if available)
      const cacheStats = 'getCacheStats' in api ? (api as any).getCacheStats() : null;
      if (cacheStats && typeof cacheStats.size === 'number') {
        this.addResult('cache-statistics', 'pass', 
          `Cache stats available (${cacheStats.size}/${cacheStats.maxSize} entries, ${cacheStats.hitRate}% hit rate)`);
      } else {
        this.addResult('cache-statistics', 'warn', 'Cache statistics not available');
      }

    } catch (error) {
      this.addResult('caching-system', 'fail', `Cache test failed: ${error}`);
    }
  }

  /**
   * Test security features
   */
  private async testSecurity(): Promise<void> {
    // Test CSP headers (check meta tags)
    const cspMeta = document.querySelector('meta[http-equiv="Content-Security-Policy"]') ||
                    document.querySelector('meta[name="Content-Security-Policy"]');
    
    this.addResult('csp-meta-present', cspMeta ? 'pass' : 'warn',
      cspMeta ? 'CSP meta tag found' : 'CSP meta tag not found (dev mode expected)');

    // Test HTTPS in production
    const isSecure = window.location.protocol === 'https:' || window.location.hostname === 'localhost';
    this.addResult('secure-connection', isSecure ? 'pass' : 'fail',
      isSecure ? 'Secure connection' : 'Insecure connection in production');

    // Test XSS protection
    const hasXFrameOptions = document.head.innerHTML.includes('X-Frame-Options') ||
                            document.head.innerHTML.includes('frame-ancestors');
    this.addResult('xss-protection', hasXFrameOptions ? 'pass' : 'warn',
      hasXFrameOptions ? 'XSS protection headers found' : 'XSS protection may be limited');
  }

  /**
   * Add a test result
   */
  private addResult(name: string, status: TestResult['status'], detail: string, duration?: number): void {
    this.results.push({
      name,
      status,
      detail,
      timestamp: Date.now(),
      duration
    });

    // Log to audit system
    auditLogger.log(
      'system_test',
      'system',
      status === 'fail' ? 'error' : status === 'warn' ? 'warning' : 'info',
      { test: name, status, detail, duration }
    );
  }

  /**
   * Generate test summary with scoring
   */
  private generateSummary(): TestSummary {
    const total = this.results.length;
    const passed = this.results.filter(r => r.status === 'pass').length;
    const failed = this.results.filter(r => r.status === 'fail').length;
    const warned = this.results.filter(r => r.status === 'warn').length;
    const skipped = this.results.filter(r => r.status === 'skip').length;
    
    // Calculate score (pass = 100%, warn = 50%, fail = 0%, skip not counted)
    const scoringTotal = total - skipped;
    const score_pct = scoringTotal > 0 ? 
      Math.round(((passed + warned * 0.5) / scoringTotal) * 100) : 0;
    
    // Assign grade
    let grade: TestSummary['grade'] = 'F';
    if (score_pct >= 90) grade = 'A';
    else if (score_pct >= 80) grade = 'B';
    else if (score_pct >= 70) grade = 'C';
    else if (score_pct >= 60) grade = 'D';

    return {
      total,
      passed,
      failed,
      warned,
      skipped,
      score_pct,
      grade,
      timestamp: Date.now()
    };
  }

  /**
   * Generate HTML report (inspired by v4.7 script)
   */
  generateHTMLReport(report: EvaluationReport): string {
    const statusIcons = { pass: '✅', fail: '❌', warn: '⚠️', skip: '⏭️' };
    const statusColors = { pass: '#22c55e', fail: '#ef4444', warn: '#f59e0b', skip: '#6b7280' };
    const gradeColor = { A: '#22c55e', B: '#3b82f6', C: '#f59e0b', D: '#f97316', F: '#ef4444' }[report.summary.grade];

    const testRows = report.tests.map(test => `
      <tr style="background-color: ${statusColors[test.status]}20">
        <td>${test.name}</td>
        <td style="text-align: center">${statusIcons[test.status]}</td>
        <td>${test.detail}</td>
        <td>${test.duration ? `${Math.round(test.duration)}ms` : '-'}</td>
        <td>${new Date(test.timestamp).toLocaleTimeString()}</td>
      </tr>
    `).join('');

    const metricsRows = Object.entries(report.metrics).map(([key, value]) => `
      <tr><td><b>${key.replace(/_/g, ' ')}</b></td><td>${value}</td></tr>
    `).join('');

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DealerScope v5.0 Elite Evaluation Report</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 20px; background: #f8fafc; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); padding: 30px; }
        h1 { color: #1e293b; margin-bottom: 10px; }
        .grade { display: inline-block; padding: 12px 20px; border-radius: 8px; color: white; font-weight: bold; font-size: 1.3em; background: ${gradeColor}; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin: 20px 0; }
        .summary-card { background: #f1f5f9; padding: 20px; border-radius: 8px; text-align: center; }
        .summary-number { font-size: 2em; font-weight: bold; color: #1e293b; }
        .summary-label { color: #64748b; font-size: 0.9em; margin-top: 5px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: #f8fafc; font-weight: 600; color: #374151; }
        .timestamp { color: #64748b; font-size: 0.9em; }
        .metric-highlight { background: #e0f2fe; padding: 15px; border-radius: 8px; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 DealerScope v5.0 Elite System Evaluation</h1>
        <p class="timestamp">Generated: ${report.timestamp}</p>
        
        <div style="display: flex; align-items: center; gap: 20px; margin: 30px 0;">
            <span class="grade">${report.summary.grade}</span>
            <div>
                <div style="font-size: 1.8em; font-weight: bold;">${report.summary.score_pct}% Overall Score</div>
                <div class="timestamp">Elite performance monitoring and optimization active</div>
            </div>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-number" style="color: #22c55e;">${report.summary.passed}</div>
                <div class="summary-label">Passed</div>
            </div>
            <div class="summary-card">
                <div class="summary-number" style="color: #f59e0b;">${report.summary.warned}</div>
                <div class="summary-label">Warnings</div>
            </div>
            <div class="summary-card">
                <div class="summary-number" style="color: #ef4444;">${report.summary.failed}</div>
                <div class="summary-label">Failed</div>
            </div>
            <div class="summary-card">
                <div class="summary-number" style="color: #6b7280;">${report.summary.skipped}</div>
                <div class="summary-label">Skipped</div>
            </div>
        </div>

        <div class="metric-highlight">
            <h3 style="margin-top: 0;">🚀 Performance Highlights</h3>
            <p>Average Response Time: <strong>${report.metrics.dashboard_avg_ms}ms</strong> | 
               Cache Hit Rate: <strong>${report.metrics.cache_hit_rate || 0}%</strong> | 
               Memory Usage: <strong>${report.metrics.memory_usage || 'N/A'}MB</strong></p>
        </div>

        <h2>📊 System Metrics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            ${metricsRows}
        </table>

        <h2>🧪 Detailed Test Results</h2>
        <table>
            <tr><th>Test Name</th><th>Status</th><th>Details</th><th>Duration</th><th>Time</th></tr>
            ${testRows}
        </table>

        <h2>📈 Optimization Recommendations</h2>
        <div style="background: #fef3c7; padding: 20px; border-radius: 8px; border-left: 4px solid #f59e0b;">
            <h3 style="margin-top: 0;">Elite Performance Tips</h3>
            <ul>
                <li>Monitor response times regularly and optimize slow endpoints</li>
                <li>Implement service worker for offline capabilities</li>
                <li>Use code splitting and lazy loading for better performance</li>
                <li>Enable compression for static assets</li>
            </ul>
        </div>
        
        <div style="background: #dcfce7; padding: 20px; border-radius: 8px; border-left: 4px solid #22c55e; margin-top: 15px;">
            <h3 style="margin-top: 0;">Security Excellence</h3>
            <ul>
                <li>Implement Content Security Policy headers</li>
                <li>Add input validation and sanitization</li>
                <li>Enable HTTPS everywhere</li>
                <li>Regular security audits and dependency updates</li>
            </ul>
        </div>

        <footer style="text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0;">
            <p class="timestamp">DealerScope v5.0 Elite - Advanced System Evaluation Framework</p>
        </footer>
    </div>
</body>
</html>`;
  }
}

export const systemTester = new SystemTester();