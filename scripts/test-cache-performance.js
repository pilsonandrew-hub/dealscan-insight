#!/usr/bin/env node
/**
 * Cache Performance Testing Script
 * Validates cache hit rate > 70% on warm cache
 */

const { performance } = require('perf_hooks');
const fs = require('fs');

const API_BASE = process.env.API_BASE || 'http://localhost:4173';
const CACHE_HIT_THRESHOLD = parseFloat(process.env.CACHE_HIT_THRESHOLD || '0.70');
const WARMUP_REQUESTS = parseInt(process.env.WARMUP_REQUESTS || '20');
const TEST_REQUESTS = parseInt(process.env.TEST_REQUESTS || '100');

async function measureCachePerformance() {
  console.log('🚀 Starting cache performance test...');
  
  const testEndpoints = [
    '/api/opportunities?page=1&limit=50',
    '/api/opportunities?page=2&limit=50', 
    '/api/opportunities?page=1&limit=100',
    '/api/dashboard-metrics',
    '/api/health'
  ];
  
  const measurements = [];
  
  // Phase 1: Warmup - populate cache
  console.log(`🔥 Cache warmup phase: ${WARMUP_REQUESTS} requests...`);
  
  for (let i = 0; i < WARMUP_REQUESTS; i++) {
    const endpoint = testEndpoints[i % testEndpoints.length];
    const start = performance.now();
    
    try {
      const response = await fetch(`${API_BASE}${endpoint}`);
      const end = performance.now();
      
      if (response.ok) {
        console.log(`Warmup ${i + 1}/${WARMUP_REQUESTS}: ${endpoint} (${(end - start).toFixed(2)}ms)`);
      }
    } catch (error) {
      console.warn(`Warmup request ${i + 1} failed:`, error.message);
    }
    
    // Small delay between warmup requests
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  
  // Small pause between warmup and testing
  await new Promise(resolve => setTimeout(resolve, 2000));
  
  // Phase 2: Performance measurement
  console.log(`📊 Cache performance measurement: ${TEST_REQUESTS} requests...`);
  
  for (let i = 0; i < TEST_REQUESTS; i++) {
    const endpoint = testEndpoints[i % testEndpoints.length];
    const start = performance.now();
    
    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
          'Cache-Control': 'no-cache'
        }
      });
      const end = performance.now();
      const duration = end - start;
      
      if (response.ok) {
        const cacheStatus = response.headers.get('x-cache-status') || 'unknown';
        const etag = response.headers.get('etag');
        
        measurements.push({
          iteration: i + 1,
          endpoint,
          duration,
          cache_status: cacheStatus,
          has_etag: Boolean(etag),
          status: response.status,
          timestamp: new Date().toISOString()
        });
        
        // Detect likely cache hits (very fast responses)
        const likelyCacheHit = duration < 50; // Less than 50ms is likely cached
        if (likelyCacheHit && cacheStatus === 'unknown') {
          measurements[measurements.length - 1].cache_status = 'hit_inferred';
        }
      }
    } catch (error) {
      console.warn(`Test request ${i + 1} failed:`, error.message);
    }
    
    // Progress indicator
    if ((i + 1) % 25 === 0) {
      console.log(`Progress: ${i + 1}/${TEST_REQUESTS} (${Math.round((i + 1) / TEST_REQUESTS * 100)}%)`);
    }
    
    // Small delay between requests to allow cache to work
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  
  if (measurements.length === 0) {
    throw new Error('No successful cache test requests recorded');
  }
  
  // Calculate cache statistics
  const totalRequests = measurements.length;
  const explicitHits = measurements.filter(m => m.cache_status === 'hit').length;
  const inferredHits = measurements.filter(m => m.cache_status === 'hit_inferred').length;
  const totalHits = explicitHits + inferredHits;
  const cacheHitRate = totalHits / totalRequests;
  
  // Performance analysis
  const hitDurations = measurements.filter(m => 
    m.cache_status === 'hit' || m.cache_status === 'hit_inferred'
  ).map(m => m.duration);
  
  const missDurations = measurements.filter(m => 
    m.cache_status === 'miss' || (m.cache_status === 'unknown' && m.duration >= 50)
  ).map(m => m.duration);
  
  const stats = {
    total_requests: totalRequests,
    cache_hits: totalHits,
    cache_misses: totalRequests - totalHits,
    cache_hit_rate: cacheHitRate,
    hit_rate_percentage: cacheHitRate * 100,
    threshold_percentage: CACHE_HIT_THRESHOLD * 100,
    avg_hit_duration: hitDurations.length > 0 ? 
      hitDurations.reduce((s, d) => s + d, 0) / hitDurations.length : 0,
    avg_miss_duration: missDurations.length > 0 ? 
      missDurations.reduce((s, d) => s + d, 0) / missDurations.length : 0,
    performance_improvement: 0
  };
  
  if (stats.avg_miss_duration > 0 && stats.avg_hit_duration > 0) {
    stats.performance_improvement = ((stats.avg_miss_duration - stats.avg_hit_duration) / stats.avg_miss_duration) * 100;
  }
  
  // Save detailed results
  const report = {
    test_name: 'Cache Performance Test',
    timestamp: new Date().toISOString(),
    configuration: {
      api_base: API_BASE,
      cache_hit_threshold: CACHE_HIT_THRESHOLD,
      warmup_requests: WARMUP_REQUESTS,
      test_requests: TEST_REQUESTS
    },
    statistics: stats,
    endpoint_breakdown: testEndpoints.map(endpoint => {
      const endpointMeasurements = measurements.filter(m => m.endpoint === endpoint);
      const endpointHits = endpointMeasurements.filter(m => 
        m.cache_status === 'hit' || m.cache_status === 'hit_inferred'
      ).length;
      
      return {
        endpoint,
        requests: endpointMeasurements.length,
        hits: endpointHits,
        hit_rate: endpointMeasurements.length > 0 ? endpointHits / endpointMeasurements.length : 0
      };
    }),
    raw_measurements: measurements
  };
  
  // Ensure reports directory exists
  if (!fs.existsSync('reports')) {
    fs.mkdirSync('reports', { recursive: true });
  }
  
  const filename = `reports/cache-performance-${Date.now()}.json`;
  fs.writeFileSync(filename, JSON.stringify(report, null, 2));
  
  // Console output
  console.log('\n🚀 Cache Performance Results:');
  console.log(`Cache Hit Rate: ${stats.hit_rate_percentage.toFixed(2)}%`);
  console.log(`Cache Hits: ${stats.cache_hits}/${stats.total_requests}`);
  console.log(`Average Hit Duration: ${stats.avg_hit_duration.toFixed(2)}ms`);
  console.log(`Average Miss Duration: ${stats.avg_miss_duration.toFixed(2)}ms`);
  console.log(`Performance Improvement: ${stats.performance_improvement.toFixed(2)}%`);
  console.log(`Report saved: ${filename}`);
  
  // Validation
  const passed = cacheHitRate >= CACHE_HIT_THRESHOLD;
  
  if (passed) {
    console.log(`✅ PASS: Cache hit rate ${stats.hit_rate_percentage.toFixed(2)}% >= ${(CACHE_HIT_THRESHOLD * 100)}% threshold`);
    process.exit(0);
  } else {
    console.log(`❌ FAIL: Cache hit rate ${stats.hit_rate_percentage.toFixed(2)}% < ${(CACHE_HIT_THRESHOLD * 100)}% threshold`);
    process.exit(1);
  }
}

// Run the test
measureCachePerformance().catch(error => {
  console.error('❌ Cache performance test failed:', error.message);
  process.exit(1);
});