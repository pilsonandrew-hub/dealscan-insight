#!/usr/bin/env tsx

/**
 * Migration Verification Script
 * Verifies all legacy imports have been replaced with unified systems
 */

import * as fs from 'fs';
import * as path from 'path';
import { logger } from '../core/UnifiedLogger';

interface MigrationCheck {
  name: string;
  pattern: RegExp;
  description: string;
}

const MIGRATION_CHECKS: MigrationCheck[] = [
  {
    name: 'Console Statements',
    pattern: /console\.(log|info|warn|error|debug)\(/g,
    description: 'Should use logger instead of console'
  },
  {
    name: 'Old Config Imports',
    pattern: /import.*from.*['"]\.\.\/config\//g,
    description: 'Should use UnifiedConfigService'
  },
  {
    name: 'Old Logger Imports', 
    pattern: /import.*from.*['"].*productionLogger|secureLogger['"]/g,
    description: 'Should use UnifiedLogger'
  },
  {
    name: 'Old Auth Context',
    pattern: /from.*['"].*UnifiedAuthContext['"]/g,
    description: 'Should use ModernAuthContext'
  },
  {
    name: 'createLogger Usage',
    pattern: /createLogger\(/g,
    description: 'Should use unified logger instance'
  }
];

function scanDirectory(dir: string, extensions: string[] = ['.ts', '.tsx']): string[] {
  const files: string[] = [];
  
  function scan(currentDir: string) {
    const items = fs.readdirSync(currentDir);
    
    for (const item of items) {
      const fullPath = path.join(currentDir, item);
      const stat = fs.statSync(fullPath);
      
      if (stat.isDirectory() && !item.startsWith('.') && !['node_modules', 'dist', 'build'].includes(item)) {
        scan(fullPath);
      } else if (stat.isFile() && extensions.some(ext => item.endsWith(ext))) {
        files.push(fullPath);
      }
    }
  }
  
  scan(dir);
  return files;
}

function checkFile(filePath: string): { file: string; issues: Array<{ check: string; matches: number; lines: number[] }> } {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const issues: Array<{ check: string; matches: number; lines: number[] }> = [];
  
  for (const check of MIGRATION_CHECKS) {
    const matches = [...content.matchAll(check.pattern)];
    if (matches.length > 0) {
      const lineNumbers: number[] = [];
      
      for (const match of matches) {
        const index = match.index!;
        const lineNumber = content.substring(0, index).split('\n').length;
        lineNumbers.push(lineNumber);
      }
      
      issues.push({
        check: check.name,
        matches: matches.length,
        lines: lineNumbers
      });
    }
  }
  
  return { file: filePath, issues };
}

async function runMigrationVerification() {
  logger.info('🔍 Starting Migration Verification');
  
  const srcDir = path.join(process.cwd(), 'src');
  const files = scanDirectory(srcDir);
  
  console.log(`\n📂 Scanning ${files.length} source files...`);
  
  let totalIssues = 0;
  const problemFiles: Array<{ file: string; issues: Array<{ check: string; matches: number; lines: number[] }> }> = [];
  
  for (const file of files) {
    // Skip core unified files and test files
    if (file.includes('/core/') || file.includes('.test.') || file.includes('.spec.')) {
      continue;
    }
    
    const result = checkFile(file);
    if (result.issues.length > 0) {
      problemFiles.push(result);
      totalIssues += result.issues.reduce((sum, issue) => sum + issue.matches, 0);
    }
  }
  
  console.log('\n📊 MIGRATION VERIFICATION RESULTS');
  console.log('=====================================');
  
  if (totalIssues === 0) {
    console.log('✅ ALL MIGRATIONS COMPLETED SUCCESSFULLY!');
    console.log('🎉 No legacy imports or patterns found.');
    return true;
  }
  
  console.log(`❌ Found ${totalIssues} migration issues in ${problemFiles.length} files\n`);
  
  for (const { file, issues } of problemFiles) {
    const relativePath = path.relative(process.cwd(), file);
    console.log(`📄 ${relativePath}`);
    
    for (const issue of issues) {
      console.log(`   ❌ ${issue.check}: ${issue.matches} occurrences`);
      console.log(`      Lines: ${issue.lines.join(', ')}`);
    }
    console.log('');
  }
  
  console.log('🔧 RECOMMENDED ACTIONS:');
  console.log('1. Replace console.* with logger methods');
  console.log('2. Update config imports to use UnifiedConfigService');
  console.log('3. Replace old logger imports with UnifiedLogger');
  console.log('4. Update auth context imports to ModernAuthContext');
  console.log('5. Remove createLogger usage in favor of unified logger\n');
  
  return false;
}

// Run verification if this script is executed directly
if (require.main === module) {
  runMigrationVerification()
    .then(success => {
      process.exit(success ? 0 : 1);
    })
    .catch(error => {
      console.error('❌ Verification failed:', error);
      process.exit(1);
    });
}

export { runMigrationVerification };