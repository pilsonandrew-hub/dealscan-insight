/**
 * Global Error Boundary System
 * Catches React errors and prevents full application crashes
 */

import React, { Component, ReactNode } from 'react';
import { logger } from './UnifiedLogger';
import { configService } from './UnifiedConfigService';

interface ErrorInfo {
  componentStack: string;
  errorBoundary?: string;
  errorBoundaryStack?: string;
}

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  level?: 'page' | 'component' | 'critical';
  context?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  errorId: string | null;
}

class ErrorBoundary extends Component<Props, State> {
  private retryCount = 0;
  private maxRetries = 3;

  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return {
      hasError: true,
      error,
      errorId: `error_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const { onError, level = 'component', context } = this.props;
    
    // Log the error
    logger
      .setContext('system')
      .error('React Error Boundary caught error', {
        error: error.message,
        stack: error.stack,
        componentStack: errorInfo.componentStack,
        level,
        context,
        errorId: this.state.errorId,
        retryCount: this.retryCount,
        userAgent: navigator.userAgent,
        url: window.location.href,
      });

    // Store error info in state
    this.setState({ errorInfo });

    // Call custom error handler
    if (onError) {
      onError(error, errorInfo);
    }

    // Report to external error tracking service
    this.reportToErrorService(error, errorInfo);

    // Auto-retry for non-critical errors
    if (level !== 'critical' && this.retryCount < this.maxRetries) {
      setTimeout(() => {
        this.retryCount++;
        this.setState({
          hasError: false,
          error: null,
          errorInfo: null,
          errorId: null,
        });
      }, 1000 * this.retryCount); // Exponential backoff
    }
  }

  private reportToErrorService(error: Error, errorInfo: ErrorInfo): void {
    if (configService.isProduction) {
      // Report to external service (Sentry, LogRocket, etc.)
      try {
        fetch('/api/errors', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            error: {
              message: error.message,
              stack: error.stack,
              name: error.name,
            },
            errorInfo,
            metadata: {
              url: window.location.href,
              userAgent: navigator.userAgent,
              timestamp: new Date().toISOString(),
              errorId: this.state.errorId,
              level: this.props.level,
              context: this.props.context,
            },
          }),
        }).catch((reportError) => {
          logger.error('Failed to report error to service', {
            originalError: error.message,
            reportError: reportError.message,
          });
        });
      } catch (reportError) {
        logger.error('Failed to report error', { reportError });
      }
    }
  }

  private handleRetry = (): void => {
    this.retryCount++;
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    });
  };

  private handleReload = (): void => {
    window.location.reload();
  };

  private renderFallback(): ReactNode {
    const { fallback, level = 'component' } = this.props;
    const { error, errorId } = this.state;

    if (fallback) {
      return fallback;
    }

    // Default fallback UI based on error level
    if (level === 'critical') {
      return (
        <div className="min-h-screen flex items-center justify-center bg-red-50">
          <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
            <div className="flex items-center mb-4">
              <div className="flex-shrink-0">
                <svg className="h-8 w-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 19.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-lg font-medium text-red-800">
                  Application Error
                </h3>
              </div>
            </div>
            <div className="mb-4">
              <p className="text-sm text-red-700">
                A critical error occurred that prevented the application from loading properly.
              </p>
              {configService.isDevelopment && error && (
                <details className="mt-2">
                  <summary className="text-sm text-red-600 cursor-pointer">
                    Error Details
                  </summary>
                  <pre className="mt-2 text-xs text-red-500 bg-red-50 p-2 rounded overflow-auto">
                    {error.message}
                    {'\n\n'}
                    {error.stack}
                  </pre>
                </details>
              )}
            </div>
            <div className="flex space-x-3">
              <button
                onClick={this.handleReload}
                className="flex-1 bg-red-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
              >
                Reload Page
              </button>
              {errorId && (
                <button
                  onClick={() => navigator.clipboard.writeText(errorId)}
                  className="px-4 py-2 border border-red-300 rounded-md text-sm font-medium text-red-700 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500"
                >
                  Copy Error ID
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (level === 'page') {
      return (
        <div className="min-h-96 flex items-center justify-center">
          <div className="text-center">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">Page Error</h3>
            <p className="mt-1 text-sm text-gray-500">
              This page encountered an error and couldn't load properly.
            </p>
            <div className="mt-6">
              <button
                onClick={this.handleRetry}
                className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      );
    }

    // Component level fallback
    return (
      <div className="p-4 border border-yellow-300 rounded-md bg-yellow-50">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 19.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-yellow-800">
              Component Error
            </h3>
            <p className="mt-1 text-sm text-yellow-700">
              This component encountered an error. 
              {this.retryCount < this.maxRetries && (
                <button
                  onClick={this.handleRetry}
                  className="ml-2 underline hover:no-underline"
                >
                  Try again
                </button>
              )}
            </p>
          </div>
        </div>
      </div>
    );
  }

  render() {
    if (this.state.hasError) {
      return this.renderFallback();
    }

    return this.props.children;
  }
}

// Specialized error boundaries for different contexts
export const CriticalErrorBoundary: React.FC<Omit<Props, 'level'>> = ({ children, ...props }) => (
  <ErrorBoundary level="critical" {...props}>
    {children}
  </ErrorBoundary>
);

export const PageErrorBoundary: React.FC<Omit<Props, 'level'>> = ({ children, ...props }) => (
  <ErrorBoundary level="page" {...props}>
    {children}
  </ErrorBoundary>
);

export const ComponentErrorBoundary: React.FC<Omit<Props, 'level'>> = ({ children, ...props }) => (
  <ErrorBoundary level="component" {...props}>
    {children}
  </ErrorBoundary>
);

export default ErrorBoundary;