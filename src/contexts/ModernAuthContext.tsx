/**
 * Updated Authentication Context using UnifiedStateManager
 * Replaces multiple auth contexts with a single, robust implementation
 */

import React, { createContext, useContext, useEffect, ReactNode } from 'react';
import { User, Session, AuthError } from '@supabase/supabase-js';
import { supabase } from '@/integrations/supabase/client';
import { logger } from '../core/UnifiedLogger';
import { stateManager, StateSlice, Action } from '../core/UnifiedStateManager';

interface AuthState {
  user: User | null;
  session: Session | null;
  loading: boolean;
  isAdmin: boolean;
  lastActivity: number;
  sessionExpiresAt: number | null;
  loginAttempts: number;
  lockedUntil: number | null;
}

interface AuthContextType extends AuthState {
  // Actions
  signIn: (email: string, password: string) => Promise<{ error?: AuthError }>;
  signUp: (email: string, password: string) => Promise<{ error?: AuthError }>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ error?: AuthError }>;
  updateProfile: (updates: { email?: string; password?: string }) => Promise<{ error?: AuthError }>;
  refreshSession: () => Promise<void>;
  checkAdminStatus: () => Promise<boolean>;
}

const initialState: AuthState = {
  user: null,
  session: null,
  loading: true,
  isAdmin: false,
  lastActivity: Date.now(),
  sessionExpiresAt: null,
  loginAttempts: 0,
  lockedUntil: null,
};

// Auth slice for unified state manager
const authSlice: StateSlice<AuthState> = {
  name: 'auth',
  initialState,
  reducer: (state: AuthState, action: Action): AuthState => {
    switch (action.type) {
      case 'AUTH_LOADING':
        return { ...state, loading: action.payload };
      
      case 'AUTH_SET_SESSION':
        const { session, user } = action.payload;
        return {
          ...state,
          session,
          user,
          loading: false,
          lastActivity: Date.now(),
          sessionExpiresAt: session?.expires_at ? new Date(session.expires_at).getTime() : null,
          loginAttempts: 0, // Reset on successful auth
          lockedUntil: null,
        };
      
      case 'AUTH_SET_ADMIN':
        return { ...state, isAdmin: action.payload };
      
      case 'AUTH_UPDATE_ACTIVITY':
        return { ...state, lastActivity: Date.now() };
      
      case 'AUTH_SIGN_OUT':
        return {
          ...initialState,
          loading: false,
        };
      
      case 'AUTH_LOGIN_ATTEMPT':
        const attempts = state.loginAttempts + 1;
        const lockDuration = attempts >= 5 ? 15 * 60 * 1000 : 0; // 15 minutes after 5 attempts
        return {
          ...state,
          loginAttempts: attempts,
          lockedUntil: lockDuration > 0 ? Date.now() + lockDuration : null,
        };
      
      case 'AUTH_RESET_ATTEMPTS':
        return {
          ...state,
          loginAttempts: 0,
          lockedUntil: null,
        };
      
      default:
        return state;
    }
  },
};

// Register the auth slice with the state manager
stateManager.registerSlice(authSlice);

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  // Get auth state from unified state manager
  const authState = stateManager.select<AuthState, AuthState>('auth');

  useEffect(() => {
    let mounted = true;

    const initializeAuth = async () => {
      try {
        logger.setContext('auth').info('Initializing authentication');
        
        // Get initial session
        const { data: { session }, error } = await supabase.auth.getSession();
        
        if (error) {
          logger.error('Failed to get initial session', { error: error.message });
        }
        
        if (mounted) {
          stateManager.dispatch({
            type: 'AUTH_SET_SESSION',
            payload: { session, user: session?.user || null },
          });
          
          // Check admin status if user is logged in
          if (session?.user) {
            checkAdminStatus();
          }
        }
      } catch (error) {
        logger.error('Auth initialization error', { error });
        if (mounted) {
          stateManager.dispatch({ type: 'AUTH_LOADING', payload: false });
        }
      }
    };

    // Set up auth state change listener
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (!mounted) return;

        logger.debug('Auth state changed', { event, userId: session?.user?.id });

        stateManager.dispatch({
          type: 'AUTH_SET_SESSION',
          payload: { session, user: session?.user || null },
        });

        // Handle specific events
        switch (event) {
          case 'SIGNED_IN':
            logger.info('User signed in', { userId: session?.user?.id });
            stateManager.dispatch({ type: 'AUTH_RESET_ATTEMPTS' });
            if (session?.user) {
              checkAdminStatus();
            }
            break;
          
          case 'SIGNED_OUT':
            logger.info('User signed out');
            stateManager.dispatch({ type: 'AUTH_SIGN_OUT' });
            break;
          
          case 'TOKEN_REFRESHED':
            logger.debug('Token refreshed');
            stateManager.dispatch({ type: 'AUTH_UPDATE_ACTIVITY' });
            break;
        }
      }
    );

    initializeAuth();

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  // Set up session monitoring
  useEffect(() => {
    const currentAuthState = stateManager.select<AuthState, AuthState>('auth');
    if (!currentAuthState.session) return;

    const checkSession = () => {
      const now = Date.now();
      const expiresAt = currentAuthState.sessionExpiresAt;
      
      if (expiresAt && now > expiresAt) {
        logger.warn('Session expired, signing out');
        signOut();
        return;
      }

      // Check for inactivity (10 minutes - reduced from 30)
      const inactivityLimit = 10 * 60 * 1000;
      if (now - currentAuthState.lastActivity > inactivityLimit) {
        logger.warn('Session inactive, signing out');
        signOut();
        return;
      }
    };

    const interval = setInterval(checkSession, 60000); // Check every minute
    return () => clearInterval(interval);
  }, [authState]);

  const signIn = async (email: string, password: string) => {
    try {
      console.log('🔐 ModernAuthContext: Starting sign in for:', email);
      
      const currentAuthState = stateManager.select<AuthState, AuthState>('auth');
      
      // Check if account is locked
      if (currentAuthState.lockedUntil && Date.now() < currentAuthState.lockedUntil) {
        const remainingMs = currentAuthState.lockedUntil - Date.now();
        const remainingMin = Math.ceil(remainingMs / 60000);
        throw new Error(`Account locked. Try again in ${remainingMin} minutes.`);
      }

      stateManager.dispatch({ type: 'AUTH_LOADING', payload: true });
      
      console.log('🌐 ModernAuthContext: Calling Supabase signInWithPassword...');
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });

      if (error) {
        console.error('❌ ModernAuthContext: Supabase auth error:', error);
        const currentAuthState = stateManager.select<AuthState, AuthState>('auth');
        stateManager.dispatch({ type: 'AUTH_LOGIN_ATTEMPT' });
        logger.setContext('auth').warn('Sign in failed', { 
          email, 
          error: error.message,
          attempts: currentAuthState.loginAttempts + 1 
        });
        return { error };
      }

      console.log('✅ ModernAuthContext: Supabase auth successful, user:', data.user?.id);
      logger.setContext('auth').info('User signed in successfully', { userId: data.user?.id });
      return { error: undefined };
      
    } catch (error) {
      console.error('❌ ModernAuthContext: Sign in exception:', error);
      logger.error('Sign in error', { error });
      return { error: error as AuthError };
    } finally {
      stateManager.dispatch({ type: 'AUTH_LOADING', payload: false });
    }
  };

  const signUp = async (email: string, password: string) => {
    try {
      console.log('📝 ModernAuthContext: Starting sign up for:', email);
      stateManager.dispatch({ type: 'AUTH_LOADING', payload: true });
      
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${window.location.origin}/`,
        },
      });

      if (error) {
        console.error('❌ ModernAuthContext: Sign up error:', error);
        logger.setContext('auth').warn('Sign up failed', { email, error: error.message });
        return { error };
      }

      console.log('✅ ModernAuthContext: Sign up successful, user:', data.user?.id);
      logger.setContext('auth').info('User signed up successfully', { userId: data.user?.id });
      return { error: undefined };
      
    } catch (error) {
      console.error('❌ ModernAuthContext: Sign up exception:', error);
      logger.error('Sign up error', { error });
      return { error: error as AuthError };
    } finally {
      stateManager.dispatch({ type: 'AUTH_LOADING', payload: false });
    }
  };

  const signOut = async () => {
    try {
      logger.setContext('auth').info('Signing out user');
      await supabase.auth.signOut();
      stateManager.dispatch({ type: 'AUTH_SIGN_OUT' });
    } catch (error) {
      logger.error('Sign out error', { error });
    }
  };

  const resetPassword = async (email: string) => {
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/reset`,
      });

      if (error) {
        logger.setContext('auth').warn('Password reset failed', { email, error: error.message });
        return { error };
      }

      logger.setContext('auth').info('Password reset email sent', { email });
      return { error: undefined };
      
    } catch (error) {
      logger.error('Password reset error', { error });
      return { error: error as AuthError };
    }
  };

  const updateProfile = async (updates: { email?: string; password?: string }) => {
    try {
      const { error } = await supabase.auth.updateUser(updates);

      if (error) {
        logger.setContext('auth').warn('Profile update failed', { error: error.message });
        return { error };
      }

      logger.setContext('auth').info('Profile updated successfully');
      return { error: undefined };
      
    } catch (error) {
      logger.error('Profile update error', { error });
      return { error: error as AuthError };
    }
  };

  const refreshSession = async () => {
    try {
      const { data, error } = await supabase.auth.refreshSession();
      
      if (error) {
        logger.setContext('auth').warn('Session refresh failed', { error: error.message });
        return;
      }

      logger.debug('Session refreshed successfully');
      stateManager.dispatch({ type: 'AUTH_UPDATE_ACTIVITY' });
      
    } catch (error) {
      logger.error('Session refresh error', { error });
    }
  };

  const checkAdminStatus = async (): Promise<boolean> => {
    try {
      const currentAuthState = stateManager.select<AuthState, AuthState>('auth');
      if (!currentAuthState.user) return false;

      // Check is_admin claim from JWT token
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.access_token) return false;

      // Parse JWT to get is_admin claim
      try {
        const payload = JSON.parse(atob(session.access_token.split('.')[1]));
        const isAdmin = Boolean(payload.is_admin);
        stateManager.dispatch({ type: 'AUTH_SET_ADMIN', payload: isAdmin });
        
        logger.debug('Admin status checked', { isAdmin, userId: currentAuthState.user.id });
        return isAdmin;
      } catch (jwtError) {
        logger.warn('Failed to parse JWT for admin check', { error: jwtError });
        return false;
      }
      
    } catch (error) {
      logger.error('Admin status check error', { error });
      return false;
    }
  };

  // Track user activity
  useEffect(() => {
    const currentAuthState = stateManager.select<AuthState, AuthState>('auth');
    if (!currentAuthState.user) return;

    const trackActivity = () => {
      stateManager.dispatch({ type: 'AUTH_UPDATE_ACTIVITY' });
    };

    const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'];
    events.forEach(event => {
      document.addEventListener(event, trackActivity, { passive: true });
    });

    return () => {
      events.forEach(event => {
        document.removeEventListener(event, trackActivity);
      });
    };
  }, [authState]);

  const value: AuthContextType = {
    ...authState,
    signIn,
    signUp,
    signOut,
    resetPassword,
    updateProfile,
    refreshSession,
    checkAdminStatus,
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