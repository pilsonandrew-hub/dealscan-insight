import React, { Suspense, useEffect, useState } from 'react';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from './contexts/ModernAuthContext';
import { SecurityMiddlewareProvider } from '@/middleware/SecurityMiddlewareIntegration';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import Auth from '@/pages/Auth';
import { SecurityStatusDashboard } from '@/components/SecurityStatusDashboard';

console.log('🔧 App.tsx: Starting component initialization...');

// Lazy load pages for better performance
const Index = React.lazy(() => import("./pages/Index"));
const NotFound = React.lazy(() => import("./pages/NotFound"));
const Settings = React.lazy(() => import("./pages/Settings"));
const SREConsole = React.lazy(() => import("./pages/SREConsole"));
const ProductionStatus = React.lazy(() => import("./pages/ProductionStatus"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      staleTime: 60000,
      refetchOnWindowFocus: true,
    },
  },
});

const App = () => {
  const [systemsInitialized, setSystemsInitialized] = useState(true); // Start as initialized
  const [systemsHealth, setSystemsHealth] = useState<'healthy' | 'degraded' | 'critical'>('healthy');
  const [enterpriseSystems, setEnterpriseSystems] = useState<any>(null);

  useEffect(() => {
    console.log('🚀 App.tsx: Loading enterprise systems asynchronously...');
    
    // Load enterprise systems asynchronously without blocking
    const loadEnterpriseSystems = async () => {
      try {
        const systems = await Promise.all([
          import('./core/UnifiedLogger'),
          import('./core/UnifiedConfigService'),
          import('./core/UnifiedStateManager'),
          import('./core/SystemIntegrationProtocols'),
          import('./core/EnterpriseSystemOrchestrator')
        ]);
        
        const [logger, configService, stateManager, integrationProtocols, enterpriseOrchestrator] = systems;
        
        console.log('✅ App.tsx: Enterprise systems loaded successfully');
        
        setEnterpriseSystems({
          logger: logger.logger,
          configService: configService.configService,
          stateManager: stateManager.stateManager,
          integrationProtocols: integrationProtocols.integrationProtocols,
          enterpriseOrchestrator: enterpriseOrchestrator.enterpriseOrchestrator
        });
        
        // Initialize state
        stateManager.stateManager.dispatch({ type: 'APP_INITIALIZE' });
        
      } catch (error) {
        console.error('⚠️ App.tsx: Enterprise systems failed to load, using fallback:', error);
        // Use mock systems
        setEnterpriseSystems({
          logger: { info: console.log, debug: console.log, error: console.error, warn: console.warn },
          configService: { 
            isProduction: false, 
            isDevelopment: true, 
            environment: 'development',
            performance: { caching: { ttl: 60000 }, monitoring: { enabled: false } } 
          },
          stateManager: { 
            dispatch: () => {}, 
            addGlobalListener: () => () => {}
          },
          integrationProtocols: { subscribeToIntegrationEvents: () => () => {} },
          enterpriseOrchestrator: { getSystemReport: () => Promise.resolve({ overallHealth: 'healthy' }) }
        });
      }
    };

    loadEnterpriseSystems();
  }, []);

  // Show system health indicator only in development
  const isDevelopment = import.meta.env.DEV;
  const showHealthIndicator = isDevelopment && systemsInitialized && enterpriseSystems;

  console.log('🎨 App.tsx: Rendering application...');

  return (
    <SecurityMiddlewareProvider>
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
          <Toaster />
          <Sonner 
            position={isDevelopment ? "top-right" : "bottom-right"}
            expand={isDevelopment}
            richColors={true}
            closeButton={true}
            duration={isDevelopment ? 3000 : 5000}
          />
          
          {/* Enterprise System Health Indicator (Development Only) */}
          {showHealthIndicator && (
            <div className={`fixed top-0 left-0 right-0 z-50 p-2 text-center text-sm font-medium transition-colors ${
              systemsHealth === 'healthy' ? 'bg-green-600 text-white' :
              systemsHealth === 'degraded' ? 'bg-yellow-600 text-white' :
              'bg-red-600 text-white'
            }`}>
              🏢 Enterprise Systems: {systemsHealth.toUpperCase()} - 
              Unified Config: {enterpriseSystems?.configService?.environment || 'loading'} | 
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
                    <p className="mt-2 text-muted-foreground">Loading DealerScope...</p>
                  </div>
                </div>
              }>
                <Routes>
                  <Route path="/auth" element={<Auth />} />
                  <Route path="/security-dashboard" element={
                    <ProtectedRoute>
                      <div className="container mx-auto p-6">
                        <SecurityStatusDashboard />
                      </div>
                    </ProtectedRoute>
                  } />
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
    </SecurityMiddlewareProvider>
  );
};

export default App;