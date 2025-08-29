#!/usr/bin/env node

/**
 * REAL API Performance Test Script - NO FAUX CODE
 * Uses autocannon to measure ACTUAL API performance
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

class RealPerformanceTester {
  constructor(baseUrl = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl;
    this.reportsDir = path.join(process.cwd(), 'reports');
  }

  async ensureReportsDir() {
    if (!fs.existsSync(this.reportsDir)) {
      fs.mkdirSync(this.reportsDir, { recursive: true });
    }
  }

  async waitForAPI(maxAttempts = 30) {
    console.log('⏳ Waiting for API to be ready...');
    
    for (let i = 0; i < maxAttempts; i++) {
      try {
        const response = await fetch(`${this.baseUrl}/healthz`);
        if (response.ok) {
          console.log(`✅ API ready after ${i + 1} attempts`);
          return true;
        }
      } catch (error) {
        // API not ready yet
      }
      
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    
    console.error(`❌ API not ready after ${maxAttempts} attempts`);
    return false;
  }

  async runLoadTest() {
    console.log('⚡ Running REAL load test with autocannon...');
    
    return new Promise((resolve, reject) => {
      // Run autocannon with specific parameters
      const autocannon = spawn('npx', [
        'autocannon',
        '-d', '10',           // 10 seconds duration
        '-c', '20',           // 20 concurrent connections
        '-j',                 // JSON output
        `${this.baseUrl}/healthz`
      ]);

      let output = '';
      let errorOutput = '';

      autocannon.stdout.on('data', (data) => {
        output += data.toString();
      });

      autocannon.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      autocannon.on('close', (code) => {
        if (code === 0) {
          try {
            const results = JSON.parse(output);
            resolve(results);
          } catch (error) {
            reject(new Error(`Failed to parse autocannon output: ${error.message}`));
          }
        } else {
          reject(new Error(`Autocannon failed with code ${code}: ${errorOutput}`));
        }
      });

      autocannon.on('error', (error) => {
        reject(new Error(`Failed to start autocannon: ${error.message}`));
      });
    });
  }

  async testAPIPerformance() {
    console.log('📊 Testing API performance...');
    
    try {
      const results = await this.runLoadTest();
      
      // Extract key metrics
      const metrics = {
        p95_latency_ms: results.latency.p95,
        p99_latency_ms: results.latency.p99,
        average_latency_ms: results.latency.average,
        requests_per_second: results.requests.average,
        total_requests: results.requests.total,
        errors: results.errors,
        timeouts: results.timeouts,
        non_2xx_responses: results.non2xx
      };

      // Save detailed results
      const reportPath = path.join(this.reportsDir, 'api_perf.json');
      fs.writeFileSync(reportPath, JSON.stringify(results, null, 2));
      
      // Save summary
      const summaryPath = path.join(this.reportsDir, 'api_perf_summary.json');
      fs.writeFileSync(summaryPath, JSON.stringify(metrics, null, 2));

      console.log(`📊 Performance Results:`);
      console.log(`  P95 Latency: ${metrics.p95_latency_ms}ms`);
      console.log(`  P99 Latency: ${metrics.p99_latency_ms}ms`);
      console.log(`  Average Latency: ${metrics.average_latency_ms}ms`);
      console.log(`  Requests/sec: ${metrics.requests_per_second}`);
      console.log(`  Total Requests: ${metrics.total_requests}`);
      console.log(`  Errors: ${metrics.errors}`);

      // HARD FAIL conditions
      const failures = [];
      
      if (metrics.p95_latency_ms > 200) {
        failures.push(`P95 latency (${metrics.p95_latency_ms}ms) > 200ms`);
      }
      
      if (metrics.p99_latency_ms > 500) {
        failures.push(`P99 latency (${metrics.p99_latency_ms}ms) > 500ms`);
      }
      
      if (metrics.errors > 0) {
        failures.push(`${metrics.errors} errors occurred during load test`);
      }
      
      if (metrics.requests_per_second < 50) {
        failures.push(`RPS (${metrics.requests_per_second}) < 50 (too slow)`);
      }

      if (failures.length > 0) {
        console.error('❌ Performance test FAILED:');
        failures.forEach(failure => console.error(`  - ${failure}`));
        return false;
      }

      console.log('✅ Performance test PASSED');
      return true;

    } catch (error) {
      console.error(`❌ Performance test error: ${error.message}`);
      return false;
    }
  }

  async testResponseTimes() {
    console.log('⏱️ Testing individual response times...');
    
    const endpoints = [
      '/healthz',
      '/api/health',  // If it exists
      '/',            // Root endpoint
    ];

    const results = {};
    
    for (const endpoint of endpoints) {
      try {
        const url = `${this.baseUrl}${endpoint}`;
        const start = Date.now();
        
        const response = await fetch(url);
        const end = Date.now();
        const responseTime = end - start;
        
        results[endpoint] = {
          status: response.status,
          response_time_ms: responseTime,
          ok: response.ok
        };
        
        console.log(`  ${endpoint}: ${responseTime}ms (${response.status})`);
        
      } catch (error) {
        results[endpoint] = {
          status: 'ERROR',
          response_time_ms: null,
          error: error.message,
          ok: false
        };
        
        console.log(`  ${endpoint}: ERROR - ${error.message}`);
      }
    }

    // Save response time results
    const responseTimePath = path.join(this.reportsDir, 'response_times.json');
    fs.writeFileSync(responseTimePath, JSON.stringify(results, null, 2));

    return results;
  }

  async testCachePerformance() {
    console.log('💾 Testing cache performance...');
    
    const endpoint = `${this.baseUrl}/healthz`;
    
    try {
      // Cold request
      const coldStart = Date.now();
      await fetch(endpoint);
      const coldTime = Date.now() - coldStart;
      
      // Small delay
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // Warm request (should hit cache if implemented)
      const warmStart = Date.now();
      await fetch(endpoint);
      const warmTime = Date.now() - warmStart;
      
      const improvement = ((coldTime - warmTime) / coldTime) * 100;
      const cacheWorking = warmTime < (coldTime * 0.7); // 30% improvement threshold
      
      const results = {
        cold_time_ms: coldTime,
        warm_time_ms: warmTime,
        improvement_percent: improvement,
        cache_working: cacheWorking,
        timestamp: new Date().toISOString()
      };
      
      console.log(`  Cold request: ${coldTime}ms`);
      console.log(`  Warm request: ${warmTime}ms`);
      console.log(`  Improvement: ${improvement.toFixed(1)}%`);
      console.log(`  Cache working: ${cacheWorking ? 'YES' : 'NO'}`);
      
      // Save cache results
      const cachePath = path.join(this.reportsDir, 'cache_performance.json');
      fs.writeFileSync(cachePath, JSON.stringify(results, null, 2));
      
      return results;
      
    } catch (error) {
      console.error(`❌ Cache test error: ${error.message}`);
      return { error: error.message, cache_working: false };
    }
  }
}

async function main() {
  const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:8000';
  const tester = new RealPerformanceTester(baseUrl);
  
  console.log('🚀 Starting REAL performance tests...');
  
  try {
    await tester.ensureReportsDir();
    
    // Wait for API to be ready
    if (!(await tester.waitForAPI())) {
      console.error('❌ API not available for testing');
      process.exit(1);
    }
    
    // Run performance tests
    const loadTestPassed = await tester.testAPIPerformance();
    await tester.testResponseTimes();
    await tester.testCachePerformance();
    
    if (!loadTestPassed) {
      console.error('❌ Load test failed - performance requirements not met');
      process.exit(1);
    }
    
    console.log('✅ All performance tests completed successfully');
    
  } catch (error) {
    console.error(`❌ Performance testing failed: ${error.message}`);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  main().catch(error => {
    console.error('❌ Unexpected error:', error);
    process.exit(1);
  });
}

module.exports = { RealPerformanceTester };