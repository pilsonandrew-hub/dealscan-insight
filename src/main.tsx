import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

console.log('🚀 DealerScope v4.8: Starting investment-grade application...')

// Simplified and robust initialization
async function initializeApplication() {
  try {
    console.log('🎯 main.tsx: Starting basic application render...')
    
    // Render the application immediately for better UX
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    )
    
    console.log('✅ main.tsx: Application rendered successfully')
    
    // Initialize enterprise systems asynchronously after render
    console.log('🔧 main.tsx: Initializing enterprise systems in background...')
    
    setTimeout(async () => {
      try {
        const { enterpriseOrchestrator } = await import('./core/EnterpriseSystemOrchestrator')
        const { logger } = await import('./core/UnifiedLogger')
        
        console.log('📊 main.tsx: Starting enterprise orchestration...')
        const orchestrationReport = await enterpriseOrchestrator.initialize()
        
        console.log('✅ main.tsx: Enterprise orchestration completed:', {
          overallHealth: orchestrationReport.overallHealth,
          systemsOnline: orchestrationReport.performanceMetrics.systemsOnline,
          totalSystems: orchestrationReport.performanceMetrics.totalSystems,
          startupTime: orchestrationReport.performanceMetrics.startupTime
        })
        
        logger.info('Enterprise orchestration completed', {
          overallHealth: orchestrationReport.overallHealth,
          systemsOnline: orchestrationReport.performanceMetrics.systemsOnline,
          totalSystems: orchestrationReport.performanceMetrics.totalSystems,
          startupTime: orchestrationReport.performanceMetrics.startupTime
        })

        if (orchestrationReport.overallHealth === 'critical') {
          console.warn('⚠️ main.tsx: Critical systems detected but application is functional')
          
          // Show non-blocking warning for enterprise-grade visibility
          const warningElement = document.createElement('div')
          warningElement.innerHTML = `
            <div style="position: fixed; top: 0; left: 0; right: 0; background: #f59e0b; color: white; padding: 0.5rem; z-index: 9999; text-align: center; font-size: 0.875rem;">
              ⚠️ Some enterprise systems are degraded - Application is functional but monitoring recommended
              <button onclick="this.parentElement.remove()" style="margin-left: 1rem; background: transparent; border: 1px solid white; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; cursor: pointer;">×</button>
            </div>
          `
          document.body.appendChild(warningElement)
          
          // Auto-remove after 10 seconds
          setTimeout(() => {
            if (warningElement.parentElement) {
              warningElement.remove()
            }
          }, 10000)
        }

        // Setup graceful shutdown
        window.addEventListener('beforeunload', async () => {
          await enterpriseOrchestrator.shutdown()
        })

      } catch (enterpriseError) {
        console.warn('⚠️ main.tsx: Enterprise systems initialization failed but app is functional:', enterpriseError)
      }
    }, 100) // Small delay to let initial render complete

  } catch (error) {
    console.error('❌ main.tsx: Critical application failure:', error)
    
    // Ultimate fallback rendering for catastrophic failure
    document.getElementById('root')!.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: center; height: 100vh; font-family: system-ui;">
        <div style="text-align: center; max-width: 600px; padding: 2rem;">
          <h1 style="color: #dc2626; margin-bottom: 1rem;">🚨 DealerScope Initialization Failure</h1>
          <p style="margin-bottom: 1rem;">The application failed to initialize properly.</p>
          <details style="text-align: left; background: #f5f5f5; padding: 1rem; border-radius: 4px; margin-bottom: 1rem;">
            <summary style="cursor: pointer; font-weight: bold;">Technical Details</summary>
            <pre style="margin-top: 0.5rem; font-size: 0.875rem; overflow-x: auto;">${error}</pre>
          </details>
          <button onclick="window.location.reload()" style="background: #3b82f6; color: white; padding: 0.5rem 1rem; border: none; border-radius: 4px; cursor: pointer;">
            Reload Application
          </button>
        </div>
      </div>
    `
  }
}

// Start the application
console.log('🔥 main.tsx: Launching DealerScope...')
initializeApplication()