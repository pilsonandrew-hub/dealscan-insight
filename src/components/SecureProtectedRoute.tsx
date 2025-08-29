/**
 * Protected Route Component
 * Ensures only authenticated users can access protected pages
 */

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/ModernAuthContext';
import { logger } from '@/utils/secureLogger';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: string;
}

export function SecureProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const isAuthenticated = !!user;
  const location = useLocation();

  // Show loading state while checking authentication
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Verifying authentication...</p>
        </div>
      </div>
    );
  }

  // Redirect to auth if not authenticated
  if (!isAuthenticated) {
    logger.warn('Unauthorized access attempt', 'AUTH', {
      path: location.pathname,
      requiredRole
    });
    
    return (
      <Navigate 
        to="/auth" 
        state={{ from: location }} 
        replace 
      />
    );
  }

  // Role-based access control (if implemented)
  if (requiredRole && user) {
    // This would check user roles from the database
    // For now, we'll allow all authenticated users
    logger.info('Authorized access', 'AUTH', {
      userId: user.id,
      path: location.pathname,
      requiredRole
    });
  }

  return <>{children}</>;
}