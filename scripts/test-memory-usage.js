#!/usr/bin/env node
/**
 * Memory Usage Testing Script
 * Validates memory usage stays under 120MB threshold
 */

const puppeteer = require('puppeteer');
const fs = require('fs');

const APP_URL = process.env.APP_URL || 'http://localhost:4173';
const MEMORY_THRESHOLD = parseInt(process.env.MEMORY_THRESHOLD || '120'); // MB
const TEST_DURATION = parseInt(process.env.TEST_DURATION || '300'); // seconds

async function measureMemoryUsage() {
  console.log('🧠 Starting memory usage test...');
  
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage']
  });
  
  const page = await browser.newPage();
  const measurements = [];
  
  try {
    // Navigate to application
    await page.goto(APP_URL);
    await page.waitForSelector('body', { timeout: 10000 });
    
    console.log(`📊 Measuring memory usage for ${TEST_DURATION} seconds...`);
    
    const startTime = Date.now();
    const endTime = startTime + (TEST_DURATION * 1000);
    let measurementCount = 0;
    
    while (Date.now() < endTime) {
      // Get memory metrics from browser
      const metrics = await page.metrics();
      const memoryUsage = await page.evaluate(() => {
        if ('memory' in performance) {
          const mem = performance.memory;
          return {
            usedJSHeapSize: mem.usedJSHeapSize,
            totalJSHeapSize: mem.totalJSHeapSize,
            jsHeapSizeLimit: mem.jsHeapSizeLimit
          };
        }
        return null;
      });
      
      const measurement = {
        timestamp: new Date().toISOString(),
        elapsed_seconds: Math.floor((Date.now() - startTime) / 1000),
        js_heap_used_mb: memoryUsage ? Math.round(memoryUsage.usedJSHeapSize / 1024 / 1024) : 0,
        js_heap_total_mb: memoryUsage ? Math.round(memoryUsage.totalJSHeapSize / 1024 / 1024) : 0,
        dom_nodes: metrics.Nodes,
        js_event_listeners: metrics.JSEventListeners
      };
      
      measurements.push(measurement);
      measurementCount++;
      
      // Simulate user interactions
      if (measurementCount % 10 === 0) {
        try {
          // Navigate to different sections
          await page.click('[data-testid="dashboard-tab"]').catch(() => {});
          await page.waitForTimeout(1000);
          await page.click('[data-testid="opportunities-tab"]').catch(() => {});
          await page.waitForTimeout(1000);
        } catch (error) {
          // Ignore interaction errors
        }
      }
      
      // Progress indicator
      if (measurementCount % 20 === 0) {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const progress = Math.round((elapsed / TEST_DURATION) * 100);
        console.log(`Progress: ${elapsed}/${TEST_DURATION}s (${progress}%)`);
      }
      
      await page.waitForTimeout(5000); // Measure every 5 seconds
    }
    
  } finally {
    await browser.close();
  }
  
  if (measurements.length === 0) {
    throw new Error('No memory measurements recorded');
  }
  
  // Calculate statistics
  const memoryValues = measurements.map(m => m.js_heap_used_mb).filter(v => v > 0);
  const stats = {
    total_measurements: measurements.length,
    min_memory_mb: Math.min(...memoryValues),
    max_memory_mb: Math.max(...memoryValues),
    avg_memory_mb: memoryValues.reduce((sum, v) => sum + v, 0) / memoryValues.length,
    final_memory_mb: memoryValues[memoryValues.length - 1],
    memory_threshold_mb: MEMORY_THRESHOLD,
    test_duration_seconds: TEST_DURATION
  };
  
  // Memory trend analysis
  const firstHalf = memoryValues.slice(0, Math.floor(memoryValues.length / 2));
  const secondHalf = memoryValues.slice(Math.floor(memoryValues.length / 2));
  const firstHalfAvg = firstHalf.reduce((sum, v) => sum + v, 0) / firstHalf.length;
  const secondHalfAvg = secondHalf.reduce((sum, v) => sum + v, 0) / secondHalf.length;
  
  stats.memory_trend = secondHalfAvg > firstHalfAvg + 10 ? 'increasing' : 
                       secondHalfAvg < firstHalfAvg - 10 ? 'decreasing' : 'stable';
  stats.memory_growth_mb = secondHalfAvg - firstHalfAvg;
  
  // Save detailed results
  const report = {
    test_name: 'Memory Usage Test',
    timestamp: new Date().toISOString(),
    configuration: {
      app_url: APP_URL,
      memory_threshold_mb: MEMORY_THRESHOLD,
      test_duration_seconds: TEST_DURATION
    },
    statistics: stats,
    raw_measurements: measurements
  };
  
  // Ensure reports directory exists
  if (!fs.existsSync('reports')) {
    fs.mkdirSync('reports', { recursive: true });
  }
  
  const filename = `reports/memory-usage-${Date.now()}.json`;
  fs.writeFileSync(filename, JSON.stringify(report, null, 2));
  
  // Console output
  console.log('\n🧠 Memory Usage Results:');
  console.log(`Average Memory Usage: ${stats.avg_memory_mb.toFixed(2)}MB`);
  console.log(`Peak Memory Usage: ${stats.max_memory_mb}MB`);
  console.log(`Final Memory Usage: ${stats.final_memory_mb}MB`);
  console.log(`Memory Trend: ${stats.memory_trend} (${stats.memory_growth_mb.toFixed(2)}MB change)`);
  console.log(`Report saved: ${filename}`);
  
  // Validation
  const passed = stats.max_memory_mb <= MEMORY_THRESHOLD && stats.memory_trend !== 'increasing';
  
  if (passed) {
    console.log(`✅ PASS: Peak memory ${stats.max_memory_mb}MB <= ${MEMORY_THRESHOLD}MB threshold`);
    process.exit(0);
  } else {
    console.log(`❌ FAIL: Peak memory ${stats.max_memory_mb}MB > ${MEMORY_THRESHOLD}MB threshold`);
    process.exit(1);
  }
}

// Run the test
measureMemoryUsage().catch(error => {
  console.error('❌ Memory test failed:', error.message);
  process.exit(1);
});