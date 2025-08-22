/**
 * Optimized Loading Fallback Components
 * Provides smooth loading states with performance monitoring
 */

import React from 'react';
import { Skeleton } from '@/components/ui/skeleton';

interface LoadingFallbackProps {
  type?: 'dashboard' | 'table' | 'card' | 'full';
  message?: string;
}

export const OptimizedLoadingFallback: React.FC<LoadingFallbackProps> = ({ 
  type = 'full', 
  message = 'Loading...' 
}) => {
  switch (type) {
    case 'dashboard':
      return (
        <div className="space-y-6 p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="p-4 border rounded-lg">
                <Skeleton className="h-4 w-20 mb-2" />
                <Skeleton className="h-8 w-16" />
              </div>
            ))}
          </div>
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          </div>
        </div>
      );
    
    case 'table':
      return (
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </div>
      );
    
    case 'card':
      return (
        <div className="p-4 border rounded-lg space-y-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      );
    
    default:
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent mx-auto"></div>
            <p className="text-muted-foreground">{message}</p>
          </div>
        </div>
      );
  }
};

export default OptimizedLoadingFallback;