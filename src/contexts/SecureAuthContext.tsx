/**
 * Secure Authentication Context
 * Implements comprehensive authentication with security best practices
 */

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { supabase } from '@/integrations/supabase/client';
import { logger } from '@/utils/secureLogger';

interface AuthContextType {
  user: User | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: any }>;
  signUp: (email: string, password: string, displayName?: string) => Promise<{ error: any }>;
  signOut: () => Promise<{ error: any }>;
  resetPassword: (email: string) => Promise<{ error: any }>;
  updatePassword: (newPassword: string) => Promise<{ error: any }>;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Set up auth state listener FIRST
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        logger.debug('Auth state changed', 'AUTH', { event, userId: session?.user?.id });
        
        setSession(session);
        setUser(session?.user ?? null);
        setLoading(false);

        // Log security events
        if (session?.user) {
          setTimeout(() => {
            logSecurityEvent('user_login', 'success', {
              userId: session.user.id,
              event
            });
          }, 0);
        }
      }
    );

    // THEN check for existing session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const logSecurityEvent = async (action: string, status: string, details: any) => {
    try {
      await supabase.rpc('log_security_event', {
        p_action: action,
        p_resource: 'authentication',
        p_status: status,
        p_details: details
      });
    } catch (error) {
      logger.error('Failed to log security event', 'AUTH', error);
    }
  };

  const signIn = async (email: string, password: string) => {
    try {
      setLoading(true);
      logger.info('Sign in attempt', 'AUTH', { email });

      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        logger.warn('Sign in failed', 'AUTH', { email, error: error.message });
        await logSecurityEvent('user_login', 'failure', {
          email,
          error: error.message
        });
      }

      return { error };
    } catch (error) {
      logger.error('Sign in error', 'AUTH', error);
      return { error };
    } finally {
      setLoading(false);
    }
  };

  const signUp = async (email: string, password: string, displayName?: string) => {
    try {
      setLoading(true);
      logger.info('Sign up attempt', 'AUTH', { email });

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
        logger.warn('Sign up failed', 'AUTH', { email, error: error.message });
        await logSecurityEvent('user_signup', 'failure', {
          email,
          error: error.message
        });
      } else {
        logger.info('Sign up successful', 'AUTH', { email });
        await logSecurityEvent('user_signup', 'success', { email });
      }

      return { error };
    } catch (error) {
      logger.error('Sign up error', 'AUTH', error);
      return { error };
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    try {
      logger.info('Sign out attempt', 'AUTH', { userId: user?.id });
      
      await logSecurityEvent('user_logout', 'success', {
        userId: user?.id
      });

      const { error } = await supabase.auth.signOut();
      
      if (error) {
        logger.error('Sign out failed', 'AUTH', error);
      } else {
        logger.info('Sign out successful', 'AUTH');
      }

      return { error };
    } catch (error) {
      logger.error('Sign out error', 'AUTH', error);
      return { error };
    }
  };

  const resetPassword = async (email: string) => {
    try {
      logger.info('Password reset attempt', 'AUTH', { email });

      const redirectUrl = `${window.location.origin}/auth/reset-password`;
      
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: redirectUrl
      });

      if (error) {
        logger.warn('Password reset failed', 'AUTH', { email, error: error.message });
        await logSecurityEvent('password_reset', 'failure', {
          email,
          error: error.message
        });
      } else {
        await logSecurityEvent('password_reset', 'success', { email });
      }

      return { error };
    } catch (error) {
      logger.error('Password reset error', 'AUTH', error);
      return { error };
    }
  };

  const updatePassword = async (newPassword: string) => {
    try {
      logger.info('Password update attempt', 'AUTH', { userId: user?.id });

      const { error } = await supabase.auth.updateUser({
        password: newPassword
      });

      if (error) {
        logger.warn('Password update failed', 'AUTH', { userId: user?.id, error: error.message });
        await logSecurityEvent('password_update', 'failure', {
          userId: user?.id,
          error: error.message
        });
      } else {
        await logSecurityEvent('password_update', 'success', {
          userId: user?.id
        });
      }

      return { error };
    } catch (error) {
      logger.error('Password update error', 'AUTH', error);
      return { error };
    }
  };

  const value = {
    user,
    session,
    loading,
    signIn,
    signUp,
    signOut,
    resetPassword,
    updatePassword,
    isAuthenticated: !!user
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}