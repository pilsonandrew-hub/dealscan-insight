/**
 * Production Error Boundary with Comprehensive Error Handling
 * Catches React errors and provides graceful fallbacks
 */

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { createLogger } from '@/utils/productionLogger';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

const logger = createLogger('ErrorBoundary');

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  showDetails?: boolean;
  isolate?: boolean;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  errorId: string | null;
  retryCount: number;
}

export class ErrorBoundary extends Component<Props, State> {
  private maxRetries = 3;

  constructor(props: Props) {
    super(props);
    
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
      retryCount: 0
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      error,
      errorId: `error_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const errorId = this.state.errorId || `error_${Date.now()}`;
    
    // Log error with full context
    logger.error('React Error Boundary caught error', {
      errorId,
      errorName: error.name,
      errorMessage: error.message,
      errorStack: error.stack,
      componentStack: errorInfo.componentStack,
      retryCount: this.state.retryCount
    }, error);

    // Store error info in state
    this.setState({
      errorInfo,
      errorId
    });

    // Call custom error handler if provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }

    // Report to external error tracking service if available
    this.reportError(error, errorInfo, errorId);
  }

  private async reportError(error: Error, errorInfo: ErrorInfo, errorId: string) {
    try {
      // Store in database for analysis
      const { supabase } = await import('@/integrations/supabase/client');
      
      await supabase.from('error_reports').insert({
        error_id: errorId,
        message: error.message,
        category: 'react_error',
        severity: 'error',
        timestamp: new Date().toISOString(),
        context: {
          name: error.name,
          stack: error.stack,
          componentStack: errorInfo.componentStack,
          retryCount: this.state.retryCount,
          userAgent: navigator.userAgent,
          url: window.location.href
        },
        stack_trace: error.stack,
        user_message: 'A React component error occurred'
      });
    } catch (reportError) {
      logger.error('Failed to report error', {}, reportError as Error);
    }
  }

  private handleRetry = () => {
    const newRetryCount = this.state.retryCount + 1;
    
    logger.info('Retrying after error', { 
      errorId: this.state.errorId,
      retryCount: newRetryCount 
    });

    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
      retryCount: newRetryCount
    });
  };

  private handleReload = () => {
    logger.info('Reloading page after error', { 
      errorId: this.state.errorId 
    });
    
    window.location.reload();
  };

  private handleGoHome = () => {
    logger.info('Navigating home after error', { 
      errorId: this.state.errorId 
    });
    
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      // Show custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Show default error UI
      return (
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <Card className="max-w-2xl w-full">
            <CardHeader className="text-center">
              <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center">
                <AlertTriangle className="h-6 w-6 text-destructive" />
              </div>
              <CardTitle className="text-2xl">Something went wrong</CardTitle>
              <CardDescription>
                We encountered an unexpected error. Our team has been notified and is working on a fix.
              </CardDescription>
            </CardHeader>
            
            <CardContent className="space-y-6">
              {/* Error ID for support */}
              <div className="text-center text-sm text-muted-foreground">
                Error ID: <code className="font-mono">{this.state.errorId}</code>
              </div>

              {/* Action buttons */}
              <div className="flex flex-wrap gap-3 justify-center">
                {this.state.retryCount < this.maxRetries && (
                  <Button onClick={this.handleRetry} variant="default">
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Try Again
                  </Button>
                )}
                
                <Button onClick={this.handleReload} variant="outline">
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Reload Page
                </Button>
                
                <Button onClick={this.handleGoHome} variant="outline">
                  <Home className="mr-2 h-4 w-4" />
                  Go Home
                </Button>
              </div>

              {/* Error details for development */}
              {(this.props.showDetails || process.env.NODE_ENV === 'development') && this.state.error && (
                <details className="mt-6">
                  <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
                    Error Details (for developers)
                  </summary>
                  <div className="mt-3 p-4 bg-muted rounded-lg">
                    <div className="text-sm space-y-3">
                      <div>
                        <strong>Error:</strong>
                        <pre className="mt-1 text-xs overflow-auto whitespace-pre-wrap">
                          {this.state.error.message}
                        </pre>
                      </div>
                      
                      {this.state.error.stack && (
                        <div>
                          <strong>Stack Trace:</strong>
                          <pre className="mt-1 text-xs overflow-auto whitespace-pre-wrap max-h-32">
                            {this.state.error.stack}
                          </pre>
                        </div>
                      )}
                      
                      {this.state.errorInfo?.componentStack && (
                        <div>
                          <strong>Component Stack:</strong>
                          <pre className="mt-1 text-xs overflow-auto whitespace-pre-wrap max-h-32">
                            {this.state.errorInfo.componentStack}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                </details>
              )}

              {/* Help text */}
              <div className="text-center text-sm text-muted-foreground">
                If this problem persists, please contact support with the error ID above.
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

// Higher-order component for wrapping components with error boundary
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  errorBoundaryProps?: Omit<Props, 'children'>
) {
  const WrappedComponent = (props: P) => (
    <ErrorBoundary {...errorBoundaryProps}>
      <Component {...props} />
    </ErrorBoundary>
  );

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name})`;
  
  return WrappedComponent;
}

// Hook for programmatic error reporting
export function useErrorReporting() {
  const reportError = React.useCallback((error: Error, context?: Record<string, any>) => {
    const errorId = `manual_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    logger.error('Manual error report', {
      errorId,
      context,
      userAgent: navigator.userAgent,
      url: window.location.href
    }, error);

    // Could also show a toast notification
    return errorId;
  }, []);

  return { reportError };
}