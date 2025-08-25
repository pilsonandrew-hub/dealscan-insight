#!/usr/bin/env node

/**
 * Canary test runner for continuous validation
 * Runs extraction tests against production sites and validates contracts
 */

import fs from 'fs';
import path from 'path';
import { POCHarness } from './poc_harness';

interface CanaryConfig {
  timeout: number;
  retries: number;
  outputDir: string;
  urlsFile: string;
}

interface CanarySite {
  name: string;
  url: string;
  expectedFields: string[];
  criticalFields: string[];
}

async function main() {
  const args = process.argv.slice(2);
  const config = parseArgs(args);
  
  console.log('🐦 Starting canary validation...');
  console.log(`📂 URLs file: ${config.urlsFile}`);
  console.log(`📁 Output dir: ${config.outputDir}`);
  console.log(`⏱️ Timeout: ${config.timeout}ms`);
  
  try {
    // Load canary sites configuration
    const canarySites = loadCanarySites(config.urlsFile);
    console.log(`🎯 Loaded ${canarySites.length} canary sites`);
    
    // Run POC tests
    const pocHarness = new POCHarness({
      urls: canarySites.map(site => site.url),
      outputDir: config.outputDir,
      timeout: config.timeout,
      saveArtifacts: true,
      validateContracts: true,
      checkCompliance: true
    });
    
    const results = await pocHarness.runPOC();
    
    // Calculate pass rates
    const canaryResults = results.map((result, index) => {
      const site = canarySites[index];
      return calculateCanaryPassRate(result, site);
    });
    
    // Generate canary-specific summary
    const summary = generateCanarySummary(canaryResults);
    saveSummary(summary, config.outputDir);
    
    // Print results
    printResults(summary);
    
    // Exit with error code if below threshold
    const minPassRate = 0.95; // 95% threshold
    if (summary.passRate < minPassRate) {
      console.error(`❌ Canary pass rate (${summary.passRate.toFixed(1)}%) below threshold (${minPassRate * 100}%)`);
      process.exit(1);
    }
    
    console.log(`✅ Canary validation passed (${summary.passRate.toFixed(1)}% pass rate)`);
    process.exit(0);
    
  } catch (error) {
    console.error('❌ Canary validation failed:', error);
    process.exit(1);
  }
}

function parseArgs(args: string[]): CanaryConfig {
  const config: CanaryConfig = {
    timeout: 30000,
    retries: 2,
    outputDir: 'artifacts',
    urlsFile: 'contracts/canaries/top_sites.json'
  };
  
  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--timeout':
        config.timeout = parseInt(args[++i]);
        break;
      case '--retries':
        config.retries = parseInt(args[++i]);
        break;
      case '--out':
        config.outputDir = args[++i];
        break;
      case '--urls-file':
        config.urlsFile = args[++i];
        break;
    }
  }
  
  return config;
}

function loadCanarySites(urlsFile: string): CanarySite[] {
  if (!fs.existsSync(urlsFile)) {
    // Create default canary sites if file doesn't exist
    const defaultSites: CanarySite[] = [
      {
        name: 'GovDeals',
        url: 'https://www.govdeals.com/search?query=vehicle',
        expectedFields: ['price', 'title', 'location', 'endTime'],
        criticalFields: ['price', 'title']
      },
      {
        name: 'PublicSurplus',
        url: 'https://www.publicsurplus.com/auctions',
        expectedFields: ['price', 'title', 'location', 'endTime'],
        criticalFields: ['price', 'title']
      },
      {
        name: 'Copart',
        url: 'https://www.copart.com/vehicleFinder',
        expectedFields: ['price', 'year', 'make', 'model', 'location'],
        criticalFields: ['price', 'make', 'model']
      }
    ];
    
    // Create directory if it doesn't exist
    const dir = path.dirname(urlsFile);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    
    fs.writeFileSync(urlsFile, JSON.stringify(defaultSites, null, 2));
    console.log(`📝 Created default canary sites file: ${urlsFile}`);
    return defaultSites;
  }
  
  const content = fs.readFileSync(urlsFile, 'utf8');
  return JSON.parse(content) as CanarySite[];
}

function calculateCanaryPassRate(result: any, site: CanarySite): any {
  const extractedFields = Object.keys(result.artifacts.extractedJson || {});
  const strategyLog = result.metadata.strategyLog || [];
  
  // Check field extraction success
  const fieldResults = site.expectedFields.map(field => {
    const extracted = extractedFields.includes(field);
    const strategyEntry = strategyLog.find((log: any) => log.field === field);
    const success = strategyEntry?.success || false;
    const confidence = strategyEntry?.confidence || 0;
    
    return {
      field,
      extracted,
      success,
      confidence,
      critical: site.criticalFields.includes(field)
    };
  });
  
  // Calculate pass rates
  const totalFields = fieldResults.length;
  const passedFields = fieldResults.filter(f => f.success && f.confidence > 0.5).length;
  const criticalFields = fieldResults.filter(f => f.critical).length;
  const passedCriticalFields = fieldResults.filter(f => f.critical && f.success && f.confidence > 0.5).length;
  
  const overallPassRate = totalFields > 0 ? passedFields / totalFields : 0;
  const criticalPassRate = criticalFields > 0 ? passedCriticalFields / criticalFields : 1;
  
  // Site passes if critical fields pass AND overall pass rate > 70%
  const sitePass = criticalPassRate >= 1.0 && overallPassRate >= 0.7;
  
  return {
    name: site.name,
    url: site.url,
    passed: sitePass,
    passRate: overallPassRate * 100,
    criticalPassRate: criticalPassRate * 100,
    fieldResults,
    errors: result.errors || [],
    renderMode: result.metadata?.renderMode || 'unknown',
    processingTime: result.metadata?.performance?.totalTime || 0
  };
}

function generateCanarySummary(canaryResults: any[]): any {
  const totalSites = canaryResults.length;
  const passedSites = canaryResults.filter(r => r.passed).length;
  const overallPassRate = totalSites > 0 ? (passedSites / totalSites) * 100 : 0;
  
  const avgFieldPassRate = canaryResults.reduce((sum, r) => sum + r.passRate, 0) / totalSites;
  const avgCriticalPassRate = canaryResults.reduce((sum, r) => sum + r.criticalPassRate, 0) / totalSites;
  
  return {
    timestamp: new Date().toISOString(),
    sitesCount: totalSites,
    passedSites,
    passRate: overallPassRate,
    avgFieldPassRate,
    avgCriticalPassRate,
    details: canaryResults,
    summary: {
      status: overallPassRate >= 95 ? 'PASS' : 'FAIL',
      threshold: 95,
      recommendation: overallPassRate < 95 ? 'Fix failing sites before merging' : 'All canaries passing'
    }
  };
}

function saveSummary(summary: any, outputDir: string): void {
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  
  const summaryPath = path.join(outputDir, 'summary.json');
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));
  
  console.log(`💾 Saved summary to: ${summaryPath}`);
}

function printResults(summary: any): void {
  console.log('\n🐦 CANARY VALIDATION RESULTS');
  console.log('=' .repeat(50));
  
  console.log(`📊 Overall: ${summary.passedSites}/${summary.sitesCount} sites passed (${summary.passRate.toFixed(1)}%)`);
  console.log(`🎯 Field extraction: ${summary.avgFieldPassRate.toFixed(1)}% average`);
  console.log(`🔥 Critical fields: ${summary.avgCriticalPassRate.toFixed(1)}% average`);
  console.log(`⚡ Status: ${summary.summary.status}`);
  
  console.log('\n📋 Site Details:');
  for (const result of summary.details) {
    const status = result.passed ? '✅' : '❌';
    const time = result.processingTime || 0;
    console.log(`${status} ${result.name}: ${result.passRate.toFixed(1)}% (${time}ms, ${result.renderMode})`);
    
    if (!result.passed && result.errors.length > 0) {
      console.log(`   Errors: ${result.errors.slice(0, 2).join(', ')}`);
    }
  }
  
  if (summary.passRate < 95) {
    console.log(`\n⚠️  ${summary.summary.recommendation}`);
  }
}

// Run if called directly
if (require.main === module) {
  main().catch(console.error);
}

export { main as runCanaryTests };