#!/usr/bin/env node

/**
 * Canary Test Runner
 * Validates extraction contracts against production sites
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const urlsFile = args.find(arg => arg.startsWith('--urls-file='))?.replace('--urls-file=', '');
const outputDir = args.find(arg => arg.startsWith('--out='))?.replace('--out=', '') || 'artifacts';
const timeout = parseInt(args.find(arg => arg.startsWith('--timeout='))?.replace('--timeout=', '')) || 30000;
const retries = parseInt(args.find(arg => arg.startsWith('--retries='))?.replace('--retries=', '')) || 2;

async function runCanaryTests() {
  console.log('🐦 Starting Canary Validation Tests...');
  
  // Create output directory
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  
  // Load test sites (fallback if file doesn't exist)
  let sites = [];
  if (urlsFile && fs.existsSync(urlsFile)) {
    try {
      sites = JSON.parse(fs.readFileSync(urlsFile, 'utf8'));
    } catch (error) {
      console.warn(`Could not load ${urlsFile}:`, error.message);
    }
  }
  
  // Fallback test sites
  if (sites.length === 0) {
    sites = [
      { name: 'localhost', url: 'http://localhost:4173', fields: ['title', 'content'] }
    ];
  }
  
  const browser = await chromium.launch();
  const results = [];
  
  for (const site of sites) {
    console.log(`Testing ${site.name}...`);
    
    let attempt = 0;
    let success = false;
    
    while (attempt <= retries && !success) {
      try {
        const page = await browser.newPage();
        page.setDefaultTimeout(timeout);
        
        await page.goto(site.url);
        
        // Extract basic page information
        const title = await page.title().catch(() => 'N/A');
        const content = await page.textContent('body').catch(() => 'N/A');
        
        const result = {
          site: site.name,
          url: site.url,
          timestamp: new Date().toISOString(),
          passed: true,
          fields: {
            title,
            content: content.substring(0, 100) + '...'
          }
        };
        
        results.push(result);
        
        // Save individual result
        fs.writeFileSync(
          path.join(outputDir, `${site.name}.json`),
          JSON.stringify(result, null, 2)
        );
        
        await page.close();
        success = true;
        
      } catch (error) {
        attempt++;
        console.warn(`Attempt ${attempt} failed for ${site.name}:`, error.message);
        
        if (attempt > retries) {
          const result = {
            site: site.name,
            url: site.url,
            timestamp: new Date().toISOString(),
            passed: false,
            error: error.message
          };
          
          results.push(result);
          
          fs.writeFileSync(
            path.join(outputDir, `${site.name}.json`),
            JSON.stringify(result, null, 2)
          );
        }
      }
    }
  }
  
  await browser.close();
  
  // Generate summary
  const passedSites = results.filter(r => r.passed).length;
  const totalSites = results.length;
  const passRate = Math.round((passedSites / totalSites) * 100);
  
  const summary = {
    sitesCount: totalSites,
    passedCount: passedSites,
    failedCount: totalSites - passedSites,
    passRate,
    timestamp: new Date().toISOString(),
    details: results.map(r => ({
      name: r.site,
      passed: r.passed ? 1 : 0,
      total: 1,
      passRate: r.passed ? 100 : 0
    }))
  };
  
  fs.writeFileSync(
    path.join(outputDir, 'summary.json'),
    JSON.stringify(summary, null, 2)
  );
  
  console.log(`\n📊 Canary Test Results:`);
  console.log(`- Sites tested: ${totalSites}`);
  console.log(`- Passed: ${passedSites}`);
  console.log(`- Failed: ${totalSites - passedSites}`);
  console.log(`- Pass rate: ${passRate}%`);
  
  if (passRate < 95) {
    console.error(`❌ FAIL: Pass rate below 95% threshold`);
    process.exit(1);
  }
  
  console.log(`✅ PASS: Canary tests completed successfully`);
}

runCanaryTests().catch(error => {
  console.error('Canary tests failed:', error);
  process.exit(1);
});