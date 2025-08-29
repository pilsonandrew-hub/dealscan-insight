import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { configService } from './core/UnifiedConfigService';
import { logger } from './core/UnifiedLogger';
import { performanceKit } from './core/PerformanceEmergencyKit';
import { CriticalErrorBoundary } from './core/ErrorBoundary';
import { productionGate } from './core/ProductionReadinessGate';

// Initialize core systems first
logger.info("🚀 DealerScope application starting", {
  environment: configService.environment,
  version: configService.deployment.version,
  buildHash: configService.deployment.buildHash,
});

// Start performance monitoring
performanceKit.getMetrics(); // Initialize the performance kit

// Remove debug code in production
if (configService.isProduction) {
  // Disable console logs in production
  console.log = () => {};
  console.debug = () => {};
  console.info = () => {};
}

// Run production readiness assessment in development
if (configService.isDevelopment) {
  // Run assessment after a delay to allow app initialization
  setTimeout(async () => {
    try {
      const report = await productionGate.runFullAssessment();
      logger.info('Production readiness assessment completed', {
        overallScore: report.overallScore,
        passed: report.passed,
        blockers: report.blockers.length,
        criticalIssues: report.criticalIssues.length,
      });
      
      if (!report.passed) {
        logger.warn('Production readiness issues detected', {
          blockers: report.blockers,
          criticalIssues: report.criticalIssues.slice(0, 5), // First 5 issues
        });
      }
    } catch (error) {
      logger.error('Production readiness assessment failed', { error });
    }
  }, 5000); // Run after 5 seconds
}

createRoot(document.getElementById("root")!).render(
  <CriticalErrorBoundary context="application-root">
    <App />
  </CriticalErrorBoundary>
);
