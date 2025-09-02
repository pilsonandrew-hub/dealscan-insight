import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { logger } from './core/UnifiedLogger';
import { performanceKit } from './core/PerformanceEmergencyKit';
import { CriticalErrorBoundary } from './core/ErrorBoundary';

// Initialize core systems first
logger.info("🚀 DealerScope application starting", {
  environment: import.meta.env.MODE,
  version: '4.9.0',
});

// Start performance monitoring
performanceKit.getMetrics(); // Initialize the performance kit

// Remove debug code in production
if (import.meta.env.MODE === 'production') {
  // Disable console logs in production
  console.log = () => {};
  console.debug = () => {};
  console.info = () => {};
}

createRoot(document.getElementById("root")!).render(
  <CriticalErrorBoundary context="application-root">
    <App />
  </CriticalErrorBoundary>
);
