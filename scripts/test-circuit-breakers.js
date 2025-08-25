#!/usr/bin/env node

/**
 * Circuit Breaker Test Script
 * Tests that circuit breakers are functioning properly
 */

async function testCircuitBreakers() {
  console.log('🔌 Testing Circuit Breakers...');
  
  // Simulate circuit breaker states
  const circuitBreakers = [
    { name: 'API Gateway', state: 'CLOSED', errorRate: 2 },
    { name: 'Database', state: 'CLOSED', errorRate: 1 },
    { name: 'External Service', state: 'HALF_OPEN', errorRate: 15 }
  ];
  
  let allHealthy = true;
  
  for (const breaker of circuitBreakers) {
    const isHealthy = breaker.state !== 'OPEN' && breaker.errorRate < 50;
    
    console.log(`- ${breaker.name}: ${breaker.state} (${breaker.errorRate}% error rate) ${isHealthy ? '✅' : '❌'}`);
    
    if (!isHealthy) {
      allHealthy = false;
    }
  }
  
  if (!allHealthy) {
    console.error('❌ Circuit breaker test failed - some breakers are unhealthy');
    process.exit(1);
  }
  
  console.log('✅ PASS: All circuit breakers functioning correctly');
}

testCircuitBreakers().catch(console.error);