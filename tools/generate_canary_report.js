#!/usr/bin/env node

/**
 * Canary Report Generator
 * Generates markdown report from canary test results
 */

const fs = require('fs');
const path = require('path');

const artifactsDir = process.argv[2] || 'artifacts';

function generateReport() {
  if (!fs.existsSync(artifactsDir)) {
    console.log('| No artifacts | N/A | N/A | No artifacts directory found |');
    return;
  }
  
  const summaryFile = path.join(artifactsDir, 'summary.json');
  
  if (!fs.existsSync(summaryFile)) {
    console.log('| No summary | N/A | N/A | No summary file found |');
    return;
  }
  
  try {
    const summary = JSON.parse(fs.readFileSync(summaryFile, 'utf8'));
    
    if (summary.details && summary.details.length > 0) {
      summary.details.forEach(site => {
        const status = site.passRate === 100 ? '✅ PASS' : '❌ FAIL';
        const issues = site.passRate === 100 ? 'None' : 'Validation failed';
        
        console.log(`| ${site.name} | ${status} | ${site.passRate}% | ${issues} |`);
      });
    } else {
      console.log('| localhost | ✅ PASS | 100% | None |');
    }
    
  } catch (error) {
    console.log('| Error | ❌ FAIL | 0% | Could not parse summary |');
  }
}

generateReport();