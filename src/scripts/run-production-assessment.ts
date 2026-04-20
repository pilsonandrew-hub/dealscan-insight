#!/usr/bin/env tsx

/**
 * Legacy production-readiness heuristic runner.
 * This script is non-authoritative and must not be used as deployment approval.
 * It exists only to surface local/browser heuristic signals for debugging.
 * Run: npm run assessment
 */

import { productionGate } from '../core/ProductionReadinessGate';
import { logger } from '../core/UnifiedLogger';
import { configService } from '../core/UnifiedConfigService';

async function runAssessment() {
  logger.info('🚀 Starting production readiness assessment heuristic', {
    environment: configService.environment,
    timestamp: new Date().toISOString()
  });

  try {
    const report = await productionGate.runFullAssessment();
    
    console.log('\n📊 LEGACY PRODUCTION READINESS HEURISTIC REPORT');
    console.log('==================================');
    console.log(`Overall Score: ${report.overallScore}/100`);
    console.log(`Status: ${report.passed ? '✅ READY' : '❌ NOT READY'}`);
    console.log(`Timestamp: ${new Date(report.timestamp).toLocaleString()}`);
    
    console.log('\n📈 GATE RESULTS:');
    report.gates.forEach(result => {
      const icon = result.passed ? '✅' : '❌';
      const score = result.score !== undefined ? ` (${result.score}/100)` : '';
      console.log(`${icon} ${result.name}${score}`);
      if (result.message) {
        console.log(`   ${result.message}`);
      }
    });

    if (report.blockers.length > 0) {
      console.log('\n🚫 DEPLOYMENT BLOCKERS:');
      report.blockers.forEach((blocker, i) => {
        console.log(`${i + 1}. ${blocker}`);
      });
    }

    if (report.criticalIssues.length > 0) {
      console.log('\n⚠️  CRITICAL ISSUES:');
      report.criticalIssues.slice(0, 10).forEach((issue, i) => {
        console.log(`${i + 1}. ${issue}`);
      });
      
      if (report.criticalIssues.length > 10) {
        console.log(`   ... and ${report.criticalIssues.length - 10} more issues`);
      }
    }

    if (report.nextSteps.length > 0) {
      console.log('\n💡 NEXT STEPS:');
      report.nextSteps.slice(0, 5).forEach((step, i) => {
        console.log(`${i + 1}. ${step}`);
      });
    }

    if (report.warnings.length > 0) {
      console.log('\n⚠️  WARNINGS:');
      report.warnings.slice(0, 5).forEach((warning, i) => {
        console.log(`${i + 1}. ${warning}`);
      });
    }

    console.log('\n==================================');
    
    if (!report.passed) {
      console.log('❌ LEGACY HEURISTIC REPORTED FAILURES');
      console.log('Do not treat this output as deployment authority. Re-verify against live code, workflows, routes, and CI artifacts.');
      process.exit(1);
    } else {
      console.log('✅ LEGACY HEURISTIC COMPLETED WITHOUT FAILURES');
      console.log('This is still not deployment authority or standalone production proof.');
    }

  } catch (error) {
    logger.error('Production readiness assessment failed', { error });
    console.error('❌ Assessment failed:', error);
    process.exit(1);
  }
}

// Run assessment if this script is executed directly
if (require.main === module) {
  runAssessment().catch(console.error);
}

export { runAssessment };