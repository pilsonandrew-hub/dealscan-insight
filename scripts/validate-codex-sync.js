#!/usr/bin/env node

/**
 * Codex Sync Validation Script
 * Validates that the correct production-ready version is available for Codex analysis
 */

const fs = require('fs');
const path = require('path');

class CodexSyncValidator {
  constructor() {
    this.errors = [];
    this.warnings = [];
    this.successes = [];
  }

  log(message, type = 'info') {
    const colors = {
      error: '\x1b[31m❌',
      warning: '\x1b[33m⚠️ ',
      success: '\x1b[32m✅',
      info: '\x1b[34m📋'
    };
    
    console.log(`${colors[type]} ${message}\x1b[0m`);
    
    switch(type) {
      case 'error': this.errors.push(message); break;
      case 'warning': this.warnings.push(message); break;
      case 'success': this.successes.push(message); break;
    }
  }

  checkFileExists(filePath, required = true) {
    if (fs.existsSync(filePath)) {
      this.log(`Found: ${filePath}`, 'success');
      return true;
    } else {
      this.log(`Missing: ${filePath}`, required ? 'error' : 'warning');
      return false;
    }
  }

  checkDirectoryExists(dirPath, required = true) {
    if (fs.existsSync(dirPath) && fs.statSync(dirPath).isDirectory()) {
      const files = fs.readdirSync(dirPath);
      this.log(`Found directory: ${dirPath} (${files.length} files)`, 'success');
      return true;
    } else {
      this.log(`Missing directory: ${dirPath}`, required ? 'error' : 'warning');
      return false;
    }
  }

  validatePackageJson() {
    this.log('\n🔍 Validating package.json...', 'info');
    
    if (!this.checkFileExists('package.json')) return false;
    
    try {
      const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
      
      // Check for key dependencies
      const requiredDeps = [
        'react',
        'react-dom',
        'typescript',
        '@supabase/supabase-js',
        'tailwindcss',
        'vite'
      ];
      
      const missing = requiredDeps.filter(dep => 
        !pkg.dependencies?.[dep] && !pkg.devDependencies?.[dep]
      );
      
      if (missing.length === 0) {
        this.log('All required dependencies found', 'success');
      } else {
        this.log(`Missing dependencies: ${missing.join(', ')}`, 'warning');
      }
      
      // Check scripts
      const requiredScripts = ['dev', 'build', 'test'];
      const missingScripts = requiredScripts.filter(script => !pkg.scripts?.[script]);
      
      if (missingScripts.length === 0) {
        this.log('All required scripts found', 'success');
      } else {
        this.log(`Missing scripts: ${missingScripts.join(', ')}`, 'warning');
      }
      
      return true;
    } catch (error) {
      this.log(`Invalid package.json: ${error.message}`, 'error');
      return false;
    }
  }

  validateProjectStructure() {
    this.log('\n🏗️  Validating project structure...', 'info');
    
    const requiredFiles = [
      'src/App.tsx',
      'src/main.tsx',
      'src/index.css',
      'tailwind.config.ts',
      'vite.config.ts',
      'tsconfig.json'
    ];
    
    const requiredDirs = [
      'src/components',
      'src/utils',
      'src/hooks'
    ];
    
    let allFilesExist = true;
    let allDirsExist = true;
    
    requiredFiles.forEach(file => {
      if (!this.checkFileExists(file)) allFilesExist = false;
    });
    
    requiredDirs.forEach(dir => {
      if (!this.checkDirectoryExists(dir)) allDirsExist = false;
    });
    
    return allFilesExist && allDirsExist;
  }

  validateProductionFeatures() {
    this.log('\n🚀 Validating production features...', 'info');
    
    const productionFiles = [
      'Dockerfile.prod',
      'docker-compose.prod.yml',
      'nginx.prod.conf',
      'docker-healthcheck.sh'
    ];
    
    const productionDirs = [
      'src/monitoring',
      'src/security',
      'src/testing',
      '.github/workflows'
    ];
    
    const productionUtils = [
      'src/utils/productionLogger.ts',
      'src/utils/memoryManager.ts',
      'src/monitoring/metricsCollector.ts',
      'src/testing/testSuite.ts'
    ];
    
    let score = 0;
    const total = productionFiles.length + productionDirs.length + productionUtils.length;
    
    productionFiles.forEach(file => {
      if (this.checkFileExists(file, false)) score++;
    });
    
    productionDirs.forEach(dir => {
      if (this.checkDirectoryExists(dir, false)) score++;
    });
    
    productionUtils.forEach(file => {
      if (this.checkFileExists(file, false)) score++;
    });
    
    const percentage = Math.round((score / total) * 100);
    
    if (percentage >= 80) {
      this.log(`Production readiness: ${score}/${total} (${percentage}%) - EXCELLENT`, 'success');
    } else if (percentage >= 60) {
      this.log(`Production readiness: ${score}/${total} (${percentage}%) - GOOD`, 'warning');
    } else {
      this.log(`Production readiness: ${score}/${total} (${percentage}%) - NEEDS WORK`, 'error');
    }
    
    return percentage;
  }

  validateGitRepository() {
    this.log('\n📋 Validating Git repository...', 'info');
    
    if (!this.checkDirectoryExists('.git')) {
      this.log('Not a Git repository - GitHub sync not possible', 'error');
      return false;
    }
    
    // Check for .gitignore
    this.checkFileExists('.gitignore', false);
    
    // Check for README
    const hasReadme = this.checkFileExists('README.md', false) || 
                     this.checkFileExists('README.rst', false) ||
                     this.checkFileExists('README.txt', false);
    
    if (!hasReadme) {
      this.log('No README file found', 'warning');
    }
    
    return true;
  }

  generateValidationReport() {
    this.log('\n📊 Generating validation report...', 'info');
    
    const report = {
      timestamp: new Date().toISOString(),
      validation_results: {
        total_checks: this.successes.length + this.warnings.length + this.errors.length,
        passed: this.successes.length,
        warnings: this.warnings.length,
        errors: this.errors.length
      },
      project_type: 'React/TypeScript Web Application',
      github_sync_ready: this.errors.length === 0,
      codex_analysis_ready: this.errors.length === 0 && this.warnings.length < 5,
      issues: {
        errors: this.errors,
        warnings: this.warnings
      },
      recommendations: []
    };
    
    // Add recommendations based on findings
    if (this.errors.length > 0) {
      report.recommendations.push('Fix critical errors before Codex analysis');
    }
    
    if (this.warnings.length > 5) {
      report.recommendations.push('Address warnings to improve analysis accuracy');
    }
    
    if (!fs.existsSync('.github/workflows')) {
      report.recommendations.push('Add CI/CD workflows for comprehensive analysis');
    }
    
    // Write report
    fs.writeFileSync('CODEX_VALIDATION_REPORT.json', JSON.stringify(report, null, 2));
    this.log('Validation report saved: CODEX_VALIDATION_REPORT.json', 'success');
    
    return report;
  }

  run() {
    console.log('🔄 DealerScope Codex Sync Validation');
    console.log('=====================================\n');
    
    // Run all validations
    this.validatePackageJson();
    this.validateProjectStructure();
    const productionScore = this.validateProductionFeatures();
    this.validateGitRepository();
    
    // Generate report
    const report = this.generateValidationReport();
    
    // Final summary
    this.log('\n🎯 Validation Summary', 'info');
    this.log('====================');
    
    if (report.codex_analysis_ready) {
      this.log('✅ READY FOR CODEX ANALYSIS', 'success');
      this.log('This appears to be a complete, production-ready application', 'success');
    } else {
      this.log('❌ NOT READY FOR CODEX ANALYSIS', 'error');
      this.log(`Found ${this.errors.length} critical errors and ${this.warnings.length} warnings`, 'warning');
    }
    
    // Instructions
    this.log('\n📋 Next Steps:', 'info');
    this.log('1. Ensure all validations pass (green checkmarks)');
    this.log('2. Commit and push any changes to GitHub');
    this.log('3. Verify GitHub repository shows complete codebase');
    this.log('4. Provide correct GitHub repository URL to Codex');
    this.log('5. Reference CODEX_VALIDATION_REPORT.json for detailed analysis');
    
    return report.codex_analysis_ready;
  }
}

// Run validation if called directly
if (require.main === module) {
  const validator = new CodexSyncValidator();
  const isReady = validator.run();
  process.exit(isReady ? 0 : 1);
}

module.exports = CodexSyncValidator;