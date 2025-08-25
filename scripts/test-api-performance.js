#!/usr/bin/env node

/**
 * API Performance Test Script
 * Tests API P95 latency is under 200ms
 */

const http = require('http');
const https = require('https');

const testEndpoints = [
  'http://localhost:4173',
  'http://localhost:4173/api/health'
];

async function makeRequest(url) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const client = url.startsWith('https') ? https : http;
    
    const req = client.get(url, (res) => {
      const duration = Date.now() - start;
      resolve({ url, duration, status: res.statusCode });
    });
    
    req.on('error', (err) => {
      const duration = Date.now() - start;
      resolve({ url, duration, status: 0, error: err.message });
    });
    
    req.setTimeout(5000, () => {
      req.destroy();
      resolve({ url, duration: 5000, status: 0, error: 'timeout' });
    });
  });
}

async function runPerformanceTests() {
  console.log('🚀 Running API Performance Tests...');
  
  const results = [];
  
  for (const endpoint of testEndpoints) {
    const requests = [];
    
    // Run 10 requests per endpoint
    for (let i = 0; i < 10; i++) {
      requests.push(makeRequest(endpoint));
    }
    
    const responses = await Promise.all(requests);
    results.push(...responses);
  }
  
  // Calculate P95
  const durations = results.map(r => r.duration).sort((a, b) => a - b);
  const p95Index = Math.ceil(durations.length * 0.95) - 1;
  const p95Latency = durations[p95Index];
  
  console.log(`📊 API Performance Results:`);
  console.log(`- Total requests: ${results.length}`);
  console.log(`- P95 latency: ${p95Latency}ms`);
  console.log(`- Target: <200ms`);
  
  if (p95Latency > 200) {
    console.error(`❌ FAIL: P95 latency (${p95Latency}ms) exceeds 200ms threshold`);
    process.exit(1);
  }
  
  console.log(`✅ PASS: P95 latency within acceptable range`);
}

runPerformanceTests().catch(console.error);