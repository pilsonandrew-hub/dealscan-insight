#!/usr/bin/env node

/**
 * Package.json Script Helper
 * Adds evaluation scripts to package.json automatically
 */

import fs from 'fs/promises';
import path from 'path';

const SCRIPT_DIR = path.dirname(process.argv[1]);
const PROJECT_ROOT = path.dirname(SCRIPT_DIR);
const PACKAGE_JSON_PATH = path.join(PROJECT_ROOT, 'package.json');

async function addEvaluationScripts() {
  try {
    console.log('📝 Adding evaluation scripts to package.json...');
    
    // Read current package.json
    const packageJsonContent = await fs.readFile(PACKAGE_JSON_PATH, 'utf8');
    const packageJson = JSON.parse(packageJsonContent);
    
    // Ensure scripts object exists
    if (!packageJson.scripts) {
      packageJson.scripts = {};
    }
    
    // Add evaluation scripts
    const evaluationScripts = {
      'eval': 'chmod +x scripts/run-evaluation.sh && ./scripts/run-evaluation.sh',
      'eval:verbose': 'chmod +x scripts/run-evaluation.sh && ./scripts/run-evaluation.sh --verbose',
      'eval:frontend': 'node scripts/ai-evaluation-suite.js --suite frontend-functionality',
      'eval:backend': 'node scripts/ai-evaluation-suite.js --suite backend-api',
      'eval:security': 'node scripts/ai-evaluation-suite.js --suite security-compliance',
      'eval:performance': 'node scripts/ai-evaluation-suite.js --suite performance-metrics',
      'eval:report': 'open ./evaluation-reports/$(ls -t evaluation-reports | head -1)/final-report.html || xdg-open ./evaluation-reports/$(ls -t evaluation-reports | head -1)/final-report.html'
    };
    
    // Add missing dependencies for evaluation
    const evaluationDependencies = {
      'node-fetch': '^3.3.2',
      'commander': '^11.1.0'
    };
    
    // Update scripts
    let scriptsAdded = 0;
    Object.entries(evaluationScripts).forEach(([key, value]) => {
      if (!packageJson.scripts[key]) {
        packageJson.scripts[key] = value;
        scriptsAdded++;
      }
    });
    
    // Update devDependencies
    if (!packageJson.devDependencies) {
      packageJson.devDependencies = {};
    }
    
    let depsAdded = 0;
    Object.entries(evaluationDependencies).forEach(([key, value]) => {
      if (!packageJson.devDependencies[key] && !packageJson.dependencies?.[key]) {
        packageJson.devDependencies[key] = value;
        depsAdded++;
      }
    });
    
    // Write updated package.json
    await fs.writeFile(PACKAGE_JSON_PATH, JSON.stringify(packageJson, null, 2) + '\n');
    
    console.log(`✅ Added ${scriptsAdded} evaluation scripts to package.json`);
    console.log(`✅ Added ${depsAdded} development dependencies`);
    
    if (depsAdded > 0) {
      console.log('\n📦 Run "npm install" to install new dependencies');
    }
    
    console.log('\n🚀 Available evaluation commands:');
    Object.keys(evaluationScripts).forEach(script => {
      console.log(`   npm run ${script}`);
    });
    
  } catch (error) {
    console.error('❌ Failed to update package.json:', error.message);
    process.exit(1);
  }
}

// CLI execution
if (import.meta.url === `file://${process.argv[1]}`) {
  addEvaluationScripts();
}

export default addEvaluationScripts;