/**
 * Updated Authentication Context using UnifiedStateManager
 * Replaces multiple auth contexts with a single, robust implementation
 */

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { User, Session, AuthError } from '@supabase/supabase-js';
import { supabase } from '@/integrations/supabase/client';

interface AuthContextType {
  user: User | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error?: AuthError }>;
  signUp: (email: string, password: string) => Promise<{ error?: AuthError }>;
  signOut: () => Promise<void>;
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
    console.log('🔐 ModernAuthContext: Initializing authentication...');
    
    // Set up auth state change listener FIRST
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        console.log(`🔄 Auth state changed: ${event}`, { userId: session?.user?.id });
        setSession(session);
        setUser(session?.user ?? null);
        setLoading(false);
      }
    );

    // THEN check for existing session
    supabase.auth.getSession().then(({ data: { session }, error }) => {
      if (error) {
        console.error('❌ Error getting session:', error);
        // Don't treat this as a fatal error - just means user is not logged in
      }
      console.log('✅ Initial session check:', { hasSession: !!session, userId: session?.user?.id });
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);


  const signIn = async (email: string, password: string) => {
    try {
      console.log('🔐 Starting sign in for:', email);
      setLoading(true);
      
      const { error } = await supabase.auth.signInWithPassword({ 
        email, 
        password 
      });

      if (error) {
        console.error('❌ Sign in error:', error);
        return { error };
      }

      console.log('✅ Sign in successful');
      return { error: undefined };
      
    } catch (error) {
      console.error('❌ Sign in exception:', error);
      return { error: error as AuthError };
    } finally {
      setLoading(false);
    }
  };

  const signUp = async (email: string, password: string) => {
    try {
      console.log('📝 Starting sign up for:', email);
      setLoading(true);
      
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${window.location.origin}/`,
        },
      });

      if (error) {
        console.error('❌ Sign up error:', error);
        return { error };
      }

      console.log('✅ Sign up successful');
      return { error: undefined };
      
    } catch (error) {
      console.error('❌ Sign up exception:', error);
      return { error: error as AuthError };
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    try {
      console.log('🚪 Signing out user');
      await supabase.auth.signOut();
    } catch (error) {
      console.error('❌ Sign out error:', error);
    }
  };


  const value: AuthContextType = {
    user,
    session,
    loading,
    signIn,
    signUp,
    signOut,
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