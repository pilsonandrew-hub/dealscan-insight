#!/usr/bin/env tsx

/**
 * Migration Verification Script
 * Verifies reintroduction of deleted legacy/config-wrapper patterns and other
 * stale migration residue. This is cleanup tooling, not proof that the repo
 * should converge on one grand "unified systems" architecture.
 */

import * as fs from 'fs';
import * as path from 'path';
import { logger } from '../lib/logger';

interface MigrationCheck {
  name: string;
  pattern: RegExp;
  description: string;
}

const MIGRATION_CHECKS: MigrationCheck[] = [
  {
    name: 'Legacy Config Wrapper Imports',
    pattern: /import.*from.*['"].*(environmentManager|productionConfig|deploymentConfig|UnifiedConfigService)['"]/g,
    description: 'Should not reintroduce deleted config-wrapper surfaces'
  },
  {
    name: 'Removed secureLogger Imports',
    pattern: /import.*from.*['"].*secureLogger['"]/g,
    description: 'Should not reintroduce deleted secureLogger imports'
  },
  {
    name: 'Legacy Auth Context Imports',
    pattern: /import.*from.*['"].*(AuthContext|SecureAuth|AuthorizationBoundary|SecureProtectedRoute)['"]/g,
    description: 'Should not reintroduce deleted alternate auth/security surfaces'
  },
  {
    name: 'Legacy UnifiedLogger Imports',
    pattern: /import.*from.*['"].*UnifiedLogger['"]/g,
    description: 'Should not reintroduce deleted UnifiedLogger imports'
  },
  {
    name: 'Dead Sidecar Imports',
    pattern: /import.*from.*['"].*(featureFlags|cloudLogger|pwa-manager|centralizedErrorHandling|playwright|marketAnalysis|roverMLService)['"]/g,
    description: 'Should not reintroduce removed sidecar surfaces'
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
  logger.info('🔍 Starting migration residue verification');
  
  const srcDir = path.join(process.cwd(), 'src');
  const files = scanDirectory(srcDir);
  
  console.log(`\n📂 Scanning ${files.length} source files...`);
  
  let totalIssues = 0;
  const problemFiles: Array<{ file: string; issues: Array<{ check: string; matches: number; lines: number[] }> }> = [];
  
  for (const file of files) {
    if (file.includes('.test.') || file.includes('.spec.')) {
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
    console.log('✅ No configured migration-residue patterns found.');
    console.log('🎉 The current scan did not find banned legacy patterns.');
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
  console.log('1. Remove imports of deleted config-wrapper surfaces');
  console.log('2. Remove imports of deleted secureLogger surfaces');
  console.log('3. Remove imports of deleted alternate auth/security surfaces');
  console.log('4. Remove imports of deleted UnifiedLogger surfaces');
  console.log('5. Remove imports of deleted sidecar surfaces\n');
  
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