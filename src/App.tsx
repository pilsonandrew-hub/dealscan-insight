import React, { Suspense } from 'react';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { PageErrorBoundary } from "./core/ErrorBoundary";
import { AuthProvider } from './contexts/ModernAuthContext';
import { SecureProtectedRoute } from '@/components/SecureProtectedRoute';
import { AuthPage } from '@/pages/SecureAuth';
import { logger } from './core/UnifiedLogger';
import { configService } from './core/UnifiedConfigService';
import { performanceKit } from './core/PerformanceEmergencyKit';

// Lazy load pages for better performance
const Index = React.lazy(() => import("./pages/Index"));
const NotFound = React.lazy(() => import("./pages/NotFound"));
const Settings = React.lazy(() => import("./pages/Settings"));
const SREConsole = React.lazy(() => import("./pages/SREConsole"));
const ProductionStatus = React.lazy(() => import("./pages/ProductionStatus"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error: any) => {
        // Don't retry on 4xx errors except 408, 429
        if (error?.status >= 400 && error?.status < 500 && ![408, 429].includes(error?.status)) {
          return false;
        }
        return failureCount < 3;
      },
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      staleTime: 5 * 60 * 1000, // 5 minutes
      refetchOnWindowFocus: false,
      gcTime: 10 * 60 * 1000, // 10 minutes garbage collection
    },
    mutations: {
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    },
  },
});

// Performance monitoring component
const PerformanceMonitor: React.FC = () => {
  React.useEffect(() => {
    logger.info('App performance monitor initialized');
    
    // Initialize performance monitoring
    const metrics = performanceKit.getMetrics();
    logger.performance('Initial performance metrics', metrics);
    
    // Monitor memory usage periodically
    const interval = setInterval(() => {
      const currentMetrics = performanceKit.getMetrics();
      if (currentMetrics.pendingRequests > 10) {
        logger.warn('High number of pending requests', currentMetrics);
      }
    }, 60000); // Check every minute
    
    return () => clearInterval(interval);
  }, []);
  
  return null;
};

const App = () => {
  React.useEffect(() => {
    logger.info('DealerScope App component mounted', {
      environment: configService.environment,
      version: configService.deployment.version,
    });
  }, []);

  return (
    <PageErrorBoundary context="application-root">
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <PerformanceMonitor />
            <Toaster />
            <Sonner />
            <BrowserRouter>
              <Suspense fallback={
                <div className="min-h-screen flex items-center justify-center">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
                    <p className="mt-2 text-muted-foreground">Loading application...</p>
                  </div>
                </div>
              }>
                <Routes>
                  <Route path="/auth" element={<AuthPage />} />
                  <Route path="/" element={
                    <SecureProtectedRoute>
                      <Index />
                    </SecureProtectedRoute>
                  } />
                  <Route path="/settings" element={
                    <SecureProtectedRoute>
                      <Settings />
                    </SecureProtectedRoute>
                  } />
                  <Route path="/sre" element={
                    <SecureProtectedRoute>
                      <SREConsole />
                    </SecureProtectedRoute>
                  } />
                  <Route path="/status" element={
                    <SecureProtectedRoute>
                      <ProductionStatus />
                    </SecureProtectedRoute>
                  } />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
          </TooltipProvider>
        </QueryClientProvider>
      </AuthProvider>
    </PageErrorBoundary>
  );
};

export default App;