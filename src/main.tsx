import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { validateDealerScopeEnv } from './utils/envValidator'

// Initialize production logger to override console methods
import '@/utils/productionLogger';

// Initialize secure configuration
import '@/config/secureConfig';

// Validate environment before app initialization
try {
  validateDealerScopeEnv();
} catch (error) {
  console.error('Environment validation failed:', error);
  // In production, you might want to show a config error page instead
}

createRoot(document.getElementById("root")!).render(<App />);
