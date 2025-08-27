/**
 * Unified Authentication Context
 * Single source of truth for authentication state and operations
 * Addresses Issue #3: Authentication Security Gaps
 */

import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { supabase } from '@/integrations/supabase/client';
import { logger } from '@/utils/secureLogger';
import { globalErrorHandler } from '@/utils/globalErrorHandler';

interface AuthContextType {
  // State
  user: User | null;
  session: Session | null;
  loading: boolean;
  isAuthenticated: boolean;
  
  // Authentication methods
  signIn: (email: string, password: string) => Promise<{ error: any }>;
  signUp: (email: string, password: string, displayName?: string) => Promise<{ error: any }>;
  signOut: () => Promise<{ error: any }>;
  resetPassword: (email: string) => Promise<{ error: any }>;
  updatePassword: (newPassword: string) => Promise<{ error: any }>;
  
  // Utility methods
  refreshAuth: () => Promise<void>;
  isAdmin: () => boolean;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Unified Authentication Provider
 * Consolidates all authentication logic into a single context
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  // Initialize authentication state
  useEffect(() => {
    let mounted = true;

    const initAuth = async () => {
      try {
        // Set up auth state listener FIRST (prevents race conditions)
        const { data: { subscription } } = supabase.auth.onAuthStateChange(
          async (event, session) => {
            if (!mounted) return;

            logger.debug('Auth state changed', 'AUTH', { 
              event, 
              userId: session?.user?.id,
              timestamp: new Date().toISOString()
            });
            
            setSession(session);
            setUser(session?.user ?? null);
            
            // Only set loading to false after initial auth check
            if (event !== 'INITIAL_SESSION') {
              setLoading(false);
            }

            // Log security events asynchronously
            if (session?.user && event === 'SIGNED_IN') {
              setTimeout(() => {
                logSecurityEvent('user_login', 'success', {
                  userId: session.user.id,
                  method: 'password',
                  timestamp: new Date().toISOString()
                });
              }, 0);
            } else if (event === 'SIGNED_OUT') {
              setTimeout(() => {
                logSecurityEvent('user_logout', 'success', {
                  timestamp: new Date().toISOString()
                });
              }, 0);
            }
          }
        );

        // THEN check for existing session
        const { data: { session }, error } = await supabase.auth.getSession();
        
        if (error) {
          logger.error('Failed to get initial session', 'AUTH', error);
          globalErrorHandler.handleError(error, { 
            component: 'AuthProvider', 
            operation: 'getSession' 
          });
        }

        if (mounted) {
          setSession(session);
          setUser(session?.user ?? null);
          setLoading(false);
        }

        // Return cleanup function
        return () => {
          mounted = false;
          subscription.unsubscribe();
        };
      } catch (error) {
        if (mounted) {
          logger.error('Auth initialization failed', 'AUTH', error);
          globalErrorHandler.handleError(error as Error, { 
            component: 'AuthProvider', 
            operation: 'initAuth' 
          });
          setLoading(false);
        }
      }
    };

    const cleanup = initAuth();
    
    return () => {
      cleanup.then(cleanupFn => cleanupFn?.());
    };
  }, []);

  /**
   * Log security events to audit trail
   */
  const logSecurityEvent = useCallback(async (action: string, status: string, details: any) => {
    try {
      await supabase.rpc('log_security_event', {
        p_action: action,
        p_resource: 'authentication',
        p_status: status,
        p_details: details
      });
    } catch (error) {
      logger.error('Failed to log security event', 'AUTH', { action, status, error });
    }
  }, []);

  /**
   * Sign in with email and password
   */
  const signIn = useCallback(async (email: string, password: string) => {
    return globalErrorHandler.wrapAsync(async () => {
      setLoading(true);
      logger.info('Sign in attempt', 'AUTH', { email: email.substring(0, 3) + '***' });

      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        logger.warn('Sign in failed', 'AUTH', { 
          email: email.substring(0, 3) + '***', 
          error: error.message 
        });
        
        await logSecurityEvent('user_login', 'failure', {
          email: email.substring(0, 3) + '***',
          error: error.message,
          timestamp: new Date().toISOString()
        });
      }

      setLoading(false);
      return { error };
    }, { component: 'AuthProvider', operation: 'signIn' });
  }, [logSecurityEvent]);

  /**
   * Sign up with email and password
   */
  const signUp = useCallback(async (email: string, password: string, displayName?: string) => {
    return globalErrorHandler.wrapAsync(async () => {
      setLoading(true);
      logger.info('Sign up attempt', 'AUTH', { email: email.substring(0, 3) + '***' });

      const redirectUrl = `${window.location.origin}/`;
      
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: redirectUrl,
          data: {
            display_name: displayName || email.split('@')[0]
          }
        }
      });

      if (error) {
        logger.warn('Sign up failed', 'AUTH', { 
          email: email.substring(0, 3) + '***', 
          error: error.message 
        });
        
        await logSecurityEvent('user_signup', 'failure', {
          email: email.substring(0, 3) + '***',
          error: error.message,
          timestamp: new Date().toISOString()
        });
      } else {
        logger.info('Sign up successful', 'AUTH', { email: email.substring(0, 3) + '***' });
        
        await logSecurityEvent('user_signup', 'success', { 
          email: email.substring(0, 3) + '***',
          timestamp: new Date().toISOString()
        });
      }

      setLoading(false);
      return { error };
    }, { component: 'AuthProvider', operation: 'signUp' });
  }, [logSecurityEvent]);

  /**
   * Sign out current user
   */
  const signOut = useCallback(async () => {
    return globalErrorHandler.wrapAsync(async () => {
      logger.info('Sign out attempt', 'AUTH', { userId: user?.id });
      
      const { error } = await supabase.auth.signOut();
      
      if (error) {
        logger.error('Sign out failed', 'AUTH', error);
      } else {
        logger.info('Sign out successful', 'AUTH');
      }

      return { error };
    }, { component: 'AuthProvider', operation: 'signOut' });
  }, [user?.id]);

  /**
   * Reset password via email
   */
  const resetPassword = useCallback(async (email: string) => {
    return globalErrorHandler.wrapAsync(async () => {
      logger.info('Password reset attempt', 'AUTH', { email: email.substring(0, 3) + '***' });

      const redirectUrl = `${window.location.origin}/auth/reset-password`;
      
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: redirectUrl
      });

      const logData = {
        email: email.substring(0, 3) + '***',
        timestamp: new Date().toISOString()
      };

      if (error) {
        logger.warn('Password reset failed', 'AUTH', { ...logData, error: error.message });
        await logSecurityEvent('password_reset', 'failure', { ...logData, error: error.message });
      } else {
        await logSecurityEvent('password_reset', 'success', logData);
      }

      return { error };
    }, { component: 'AuthProvider', operation: 'resetPassword' });
  }, [logSecurityEvent]);

  /**
   * Update current user's password
   */
  const updatePassword = useCallback(async (newPassword: string) => {
    return globalErrorHandler.wrapAsync(async () => {
      logger.info('Password update attempt', 'AUTH', { userId: user?.id });

      const { error } = await supabase.auth.updateUser({
        password: newPassword
      });

      const logData = {
        userId: user?.id,
        timestamp: new Date().toISOString()
      };

      if (error) {
        logger.warn('Password update failed', 'AUTH', { ...logData, error: error.message });
        await logSecurityEvent('password_update', 'failure', { ...logData, error: error.message });
      } else {
        await logSecurityEvent('password_update', 'success', logData);
      }

      return { error };
    }, { component: 'AuthProvider', operation: 'updatePassword' });
  }, [user?.id, logSecurityEvent]);

  /**
   * Refresh authentication state
   */
  const refreshAuth = useCallback(async () => {
    return globalErrorHandler.wrapAsync(async () => {
      const { data: { session }, error } = await supabase.auth.getSession();
      
      if (error) {
        logger.error('Failed to refresh auth', 'AUTH', error);
        throw error;
      }
      
      setSession(session);
      setUser(session?.user ?? null);
    }, { component: 'AuthProvider', operation: 'refreshAuth' });
  }, []);

  /**
   * Check if current user is admin
   */
  const isAdmin = useCallback(() => {
    return user?.user_metadata?.role === 'admin' || 
           user?.app_metadata?.role === 'admin' ||
           false;
  }, [user]);

  /**
   * Check if user has specific permission
   */
  const hasPermission = useCallback((permission: string) => {
    if (!user) return false;
    
    // Admin has all permissions
    if (isAdmin()) return true;
    
    // Check user permissions (extend as needed)
    const userPermissions = user.user_metadata?.permissions || [];
    return userPermissions.includes(permission);
  }, [user, isAdmin]);

  const value: AuthContextType = {
    // State
    user,
    session,
    loading,
    isAuthenticated: !!user,
    
    // Methods
    signIn,
    signUp,
    signOut,
    resetPassword,
    updatePassword,
    refreshAuth,
    isAdmin,
    hasPermission,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to access unified authentication context
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

/**
 * HOC for components that require authentication
 */
export function withAuth<P extends object>(Component: React.ComponentType<P>) {
  return function AuthenticatedComponent(props: P) {
    const { isAuthenticated, loading } = useAuth();
    
    if (loading) {
      return <div>Loading...</div>; // Or your loading component
    }
    
    if (!isAuthenticated) {
      return <div>Please sign in to access this feature.</div>;
    }
    
    return <Component {...props} />;
  };
}

/**
 * HOC for components that require admin privileges
 */
export function withAdmin<P extends object>(Component: React.ComponentType<P>) {
  return function AdminComponent(props: P) {
    const { isAdmin, loading, isAuthenticated } = useAuth();
    
    if (loading) {
      return <div>Loading...</div>;
    }
    
    if (!isAuthenticated) {
      return <div>Please sign in to access this feature.</div>;
    }
    
    if (!isAdmin()) {
      return <div>Admin access required.</div>;
    }
    
    return <Component {...props} />;
  };
}