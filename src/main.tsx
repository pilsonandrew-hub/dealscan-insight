import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// Initialize Enterprise System Orchestrator - Investment Grade Architecture
import { enterpriseOrchestrator } from './core/EnterpriseSystemOrchestrator'
import { logger } from './core/UnifiedLogger'

// Enterprise-grade startup sequence
async function initializeApplication() {
  try {
    logger.info('Starting investment-grade application initialization')
    
    // Initialize all sophisticated systems in proper order
    const orchestrationReport = await enterpriseOrchestrator.initialize()
    
    logger.info('Enterprise orchestration completed', {
      overallHealth: orchestrationReport.overallHealth,
      systemsOnline: orchestrationReport.performanceMetrics.systemsOnline,
      totalSystems: orchestrationReport.performanceMetrics.totalSystems,
      startupTime: orchestrationReport.performanceMetrics.startupTime
    })

    if (orchestrationReport.overallHealth === 'critical') {
      logger.error('Critical systems failure detected', {
        criticalAlerts: orchestrationReport.criticalAlerts,
        recommendedActions: orchestrationReport.recommendedActions
      })
      
      // Show enterprise-grade error handling
      const errorDisplay = document.createElement('div')
      errorDisplay.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; background: #dc2626; color: white; padding: 1rem; z-index: 9999;">
          <strong>⚠️ Critical System Failure</strong> - Some enterprise systems failed to initialize. 
          Check console for details. Recommended: ${orchestrationReport.recommendedActions.join(', ')}
        </div>
      `
      document.body.appendChild(errorDisplay)
    }

    // Render application with enterprise systems initialized
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    )

    // Setup graceful shutdown
    window.addEventListener('beforeunload', async () => {
      await enterpriseOrchestrator.shutdown()
    })

  } catch (error) {
    logger.fatal('Enterprise application initialization failed', error)
    
    // Fallback rendering for catastrophic failure
    document.getElementById('root')!.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: center; height: 100vh; font-family: system-ui;">
        <div style="text-align: center; max-width: 600px; padding: 2rem;">
          <h1 style="color: #dc2626; margin-bottom: 1rem;">🚨 System Initialization Failure</h1>
          <p style="margin-bottom: 1rem;">The enterprise-grade application failed to initialize properly.</p>
          <details style="text-align: left; background: #f5f5f5; padding: 1rem; border-radius: 4px;">
            <summary style="cursor: pointer; font-weight: bold;">Technical Details</summary>
            <pre style="margin-top: 0.5rem; font-size: 0.875rem; overflow-x: auto;">${error}</pre>
          </details>
          <p style="margin-top: 1rem; font-size: 0.875rem; color: #666;">
            Please refresh the page or contact system administrators.
          </p>
        </div>
      </div>
    `
  }
}

// Start enterprise initialization
initializeApplication()
