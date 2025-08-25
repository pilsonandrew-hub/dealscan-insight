#!/usr/bin/env node
/**
 * API Performance Testing Script
 * Validates P95 latency < 200ms for /api/opportunities
 */

const { performance } = require('perf_hooks');
const fs = require('fs');

const API_BASE = process.env.API_BASE || 'http://localhost:4173';
const ITERATIONS = parseInt(process.env.PERF_ITERATIONS || '100');
const P95_THRESHOLD = parseInt(process.env.P95_THRESHOLD || '200'); // ms

async function measureAPIPerformance() {
  const results = [];
  const warmupRuns = 10;
  
  console.log(`🔥 Warming up API with ${warmupRuns} requests...`);
  
  // Warmup phase
  for (let i = 0; i < warmupRuns; i++) {
    try {
      await fetch(`${API_BASE}/api/opportunities?page=1&limit=50`);
    } catch (error) {
      console.warn(`Warmup request ${i + 1} failed:`, error.message);
    }
  }
  
  console.log(`📊 Running ${ITERATIONS} performance measurements...`);
  
  // Measurement phase
  for (let i = 0; i < ITERATIONS; i++) {
    const start = performance.now();
    
    try {
      const response = await fetch(`${API_BASE}/api/opportunities?page=${(i % 5) + 1}&limit=100`);
      const end = performance.now();
      const duration = end - start;
      
      if (response.ok) {
        results.push({
          iteration: i + 1,
          duration,
          status: response.status,
          timestamp: new Date().toISOString()
        });
      } else {
        console.warn(`Request ${i + 1} failed with status:`, response.status);
      }
    } catch (error) {
      console.error(`Request ${i + 1} failed:`, error.message);
    }
    
    // Progress indicator
    if ((i + 1) % 20 === 0) {
      console.log(`Progress: ${i + 1}/${ITERATIONS} (${Math.round((i + 1) / ITERATIONS * 100)}%)`);
    }
  }
  
  if (results.length === 0) {
    throw new Error('No successful API requests recorded');
  }
  
  // Calculate statistics
  const durations = results.map(r => r.duration).sort((a, b) => a - b);
  const stats = {
    total_requests: results.length,
    min_duration: Math.min(...durations),
    max_duration: Math.max(...durations),
    avg_duration: durations.reduce((sum, d) => sum + d, 0) / durations.length,
    p50_duration: durations[Math.floor(durations.length * 0.5)],
    p95_duration: durations[Math.floor(durations.length * 0.95)],
    p99_duration: durations[Math.floor(durations.length * 0.99)],
    threshold: P95_THRESHOLD,
    success_rate: (results.length / ITERATIONS) * 100
  };
  
  // Save detailed results
  const report = {
    test_name: 'API Performance Test',
    timestamp: new Date().toISOString(),
    configuration: {
      api_base: API_BASE,
      iterations: ITERATIONS,
      p95_threshold: P95_THRESHOLD
    },
    statistics: stats,
    raw_data: results
  };
  
  // Ensure reports directory exists
  if (!fs.existsSync('reports')) {
    fs.mkdirSync('reports', { recursive: true });
  }
  
  const filename = `reports/performance-api-${Date.now()}.json`;
  fs.writeFileSync(filename, JSON.stringify(report, null, 2));
  
  // Console output
  console.log('\n📈 API Performance Results:');
  console.log(`Average Response Time: ${stats.avg_duration.toFixed(2)}ms`);
  console.log(`P50 Response Time: ${stats.p50_duration.toFixed(2)}ms`);
  console.log(`P95 Response Time: ${stats.p95_duration.toFixed(2)}ms`);
  console.log(`P99 Response Time: ${stats.p99_duration.toFixed(2)}ms`);
  console.log(`Success Rate: ${stats.success_rate.toFixed(2)}%`);
  console.log(`Report saved: ${filename}`);
  
  // Validation
  const passed = stats.p95_duration <= P95_THRESHOLD && stats.success_rate >= 95;
  
  if (passed) {
    console.log(`✅ PASS: P95 latency ${stats.p95_duration.toFixed(2)}ms <= ${P95_THRESHOLD}ms threshold`);
    process.exit(0);
  } else {
    console.log(`❌ FAIL: P95 latency ${stats.p95_duration.toFixed(2)}ms > ${P95_THRESHOLD}ms threshold`);
    process.exit(1);
  }
}

// Run the test
measureAPIPerformance().catch(error => {
  console.error('❌ Performance test failed:', error.message);
  process.exit(1);
});