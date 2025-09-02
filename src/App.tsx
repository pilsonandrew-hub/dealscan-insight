import React, { Suspense, useEffect, useState } from 'react';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from './contexts/ModernAuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import Auth from '@/pages/Auth';

// Import investment-grade enterprise systems
import { logger } from './core/UnifiedLogger';
import { configService } from './core/UnifiedConfigService';
import { stateManager } from './core/UnifiedStateManager';
import { integrationProtocols } from './core/SystemIntegrationProtocols';
import { enterpriseOrchestrator } from './core/EnterpriseSystemOrchestrator';

// Lazy load pages for better performance
const Index = React.lazy(() => import("./pages/Index"));
const NotFound = React.lazy(() => import("./pages/NotFound"));
const Settings = React.lazy(() => import("./pages/Settings"));
const SREConsole = React.lazy(() => import("./pages/SREConsole"));
const ProductionStatus = React.lazy(() => import("./pages/ProductionStatus"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: configService.isProduction ? 3 : 1,
      staleTime: configService.performance.caching.ttl,
      refetchOnWindowFocus: configService.isDevelopment,
    },
  },
});

const App = () => {
  const [systemsInitialized, setSystemsInitialized] = useState(false);
  const [systemsHealth, setSystemsHealth] = useState<'healthy' | 'degraded' | 'critical'>('healthy');

  useEffect(() => {
    // Subscribe to system integration events
    const unsubscribe = integrationProtocols.subscribeToIntegrationEvents('*', async (event) => {
      if (event.type === 'system-health-update') {
        setSystemsHealth(event.payload.health);
      }
    });

    // Subscribe to state management events
    const unsubscribeState = stateManager.addGlobalListener((newState, oldState, action) => {
      if (action.type === 'APP_INITIALIZE') {
        setSystemsInitialized(true);
        logger.info('Application state initialized', { 
          stateSize: JSON.stringify(newState).length,
          action: action.type 
        });
      }
    });

    // Initialize application state
    stateManager.dispatch({ type: 'APP_INITIALIZE' });

    // Monitor system health
    const healthInterval = setInterval(async () => {
      try {
        const report = await enterpriseOrchestrator.getSystemReport();
        setSystemsHealth(report.overallHealth);
        
        if (report.overallHealth === 'critical') {
          logger.error('Critical system health detected', {
            criticalSystems: report.systemsStatus.filter(s => s.status === 'critical')
          });
        }
      } catch (error) {
        logger.error('Health monitoring failed', error);
      }
    }, configService.isProduction ? 30000 : 10000);

    return () => {
      unsubscribe();
      unsubscribeState();
      clearInterval(healthInterval);
    };
  }, []);

  // Show system health indicator in development
  const showHealthIndicator = configService.isDevelopment && systemsInitialized;

  return (
    <AuthProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <Toaster />
          <Sonner 
            position={configService.isDevelopment ? "top-right" : "bottom-right"}
            expand={configService.isDevelopment}
            richColors={true}
            closeButton={true}
            duration={configService.isProduction ? 5000 : 3000}
          />
          
          {/* Enterprise System Health Indicator (Development Only) */}
          {showHealthIndicator && (
            <div className={`fixed top-0 left-0 right-0 z-50 p-2 text-center text-sm font-medium transition-colors ${
              systemsHealth === 'healthy' ? 'bg-green-600 text-white' :
              systemsHealth === 'degraded' ? 'bg-yellow-600 text-white' :
              'bg-red-600 text-white'
            }`}>
              🏢 Enterprise Systems: {systemsHealth.toUpperCase()} - 
              Unified Config: {configService.environment} | 
              State Manager: Active | 
              Integration Protocols: Online
            </div>
          )}
          
          <BrowserRouter>
            <div className={showHealthIndicator ? 'pt-10' : ''}>
              <Suspense fallback={
                <div className="min-h-screen flex items-center justify-center">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
                    <p className="mt-2 text-muted-foreground">Loading enterprise systems...</p>
                  </div>
                </div>
              }>
                <Routes>
                  <Route path="/auth" element={<Auth />} />
                  <Route path="/" element={
                    <ProtectedRoute>
                      <Index />
                    </ProtectedRoute>
                  } />
                  <Route path="/settings" element={
                    <ProtectedRoute>
                      <Settings />
                    </ProtectedRoute>
                  } />
                  <Route path="/sre" element={
                    <ProtectedRoute>
                      <SREConsole />
                    </ProtectedRoute>
                  } />
                  <Route path="/status" element={
                    <ProtectedRoute>
                      <ProductionStatus />
                    </ProtectedRoute>
                  } />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </div>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </AuthProvider>
  );
};

export default App;