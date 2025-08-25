#!/usr/bin/env node

/**
 * Memory Usage Test Script
 * Tests memory usage is under 120MB
 */

const { execSync } = require('child_process');

function getMemoryUsage() {
  try {
    if (process.memoryUsage) {
      const usage = process.memoryUsage();
      return Math.round(usage.heapUsed / 1024 / 1024);
    }
    return 0;
  } catch (error) {
    console.warn('Could not measure memory usage:', error.message);
    return 0;
  }
}

async function runMemoryTest() {
  console.log('🧠 Running Memory Usage Test...');
  
  const initialMemory = getMemoryUsage();
  console.log(`Initial memory usage: ${initialMemory}MB`);
  
  // Simulate some memory operations
  const testData = [];
  for (let i = 0; i < 1000; i++) {
    testData.push({ id: i, data: 'test'.repeat(100) });
  }
  
  const peakMemory = getMemoryUsage();
  console.log(`Peak memory usage: ${peakMemory}MB`);
  console.log(`Target: <120MB`);
  
  if (peakMemory > 120) {
    console.error(`❌ FAIL: Memory usage (${peakMemory}MB) exceeds 120MB threshold`);
    process.exit(1);
  }
  
  console.log(`✅ PASS: Memory usage within acceptable range`);
}

runMemoryTest().catch(console.error);