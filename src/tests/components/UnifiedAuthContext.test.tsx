/**
 * Unified Auth Context Tests
 * Comprehensive testing for authentication functionality
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '@/contexts/UnifiedAuthContext';
import { testUtils } from '@/tests/utils/test-helpers';

// Mock Supabase client
const mockSupabase = {
  auth: {
    onAuthStateChange: vi.fn(() => ({ 
      data: { subscription: { unsubscribe: vi.fn() } } 
    })),
    getSession: vi.fn(() => Promise.resolve({ data: { session: null }, error: null })),
    signInWithPassword: vi.fn(() => Promise.resolve({ error: null })),
    signUp: vi.fn(() => Promise.resolve({ error: null })),
    signOut: vi.fn(() => Promise.resolve({ error: null })),
    resetPasswordForEmail: vi.fn(() => Promise.resolve({ error: null })),
    updateUser: vi.fn(() => Promise.resolve({ error: null })),
  },
  rpc: vi.fn(() => Promise.resolve({ error: null })),
};

vi.mock('@/integrations/supabase/client', () => ({
  supabase: mockSupabase,
}));

// Test component that uses auth
const TestComponent = () => {
  const { 
    user, 
    loading, 
    isAuthenticated, 
    signIn, 
    signUp, 
    signOut,
    isAdmin,
    hasPermission 
  } = useAuth();

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <div data-testid="auth-status">
        {isAuthenticated ? 'Authenticated' : 'Not Authenticated'}
      </div>
      <div data-testid="user-email">{user?.email || 'No User'}</div>
      <div data-testid="is-admin">{isAdmin() ? 'Admin' : 'Not Admin'}</div>
      <div data-testid="has-permission">
        {hasPermission('read') ? 'Has Permission' : 'No Permission'}
      </div>
      <button onClick={() => signIn('test@example.com', 'password')}>
        Sign In
      </button>
      <button onClick={() => signUp('test@example.com', 'password')}>
        Sign Up
      </button>
      <button onClick={() => signOut()}>Sign Out</button>
    </div>
  );
};

describe('UnifiedAuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Provider Setup', () => {
    it('should render children correctly', () => {
      render(
        <AuthProvider>
          <div>Test Child</div>
        </AuthProvider>
      );

      expect(screen.getByText('Test Child')).toBeInTheDocument();
    });

    it('should throw error when useAuth is used outside provider', () => {
      // Suppress error boundary logs for this test
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      expect(() => {
        render(<TestComponent />);
      }).toThrow('useAuth must be used within an AuthProvider');

      consoleSpy.mockRestore();
    });

    it('should initialize with loading state', () => {
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });

  describe('Authentication State', () => {
    it('should handle no user state correctly', async () => {
      mockSupabase.auth.getSession.mockResolvedValueOnce({
        data: { session: null },
        error: null
      });

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Not Authenticated');
        expect(screen.getByTestId('user-email')).toHaveTextContent('No User');
        expect(screen.getByTestId('is-admin')).toHaveTextContent('Not Admin');
      });
    });

    it('should handle authenticated user state', async () => {
      const mockUser = testUtils.createMockUser({
        email: 'test@example.com',
        user_metadata: { role: 'user' }
      });
      const mockSession = testUtils.createMockSession(mockUser);

      mockSupabase.auth.getSession.mockResolvedValueOnce({
        data: { session: mockSession },
        error: null
      });

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
        expect(screen.getByTestId('user-email')).toHaveTextContent('test@example.com');
      });
    });

    it('should handle admin user correctly', async () => {
      const mockUser = testUtils.createMockUser({
        email: 'admin@example.com',
        user_metadata: { role: 'admin' }
      });
      const mockSession = testUtils.createMockSession(mockUser);

      mockSupabase.auth.getSession.mockResolvedValueOnce({
        data: { session: mockSession },
        error: null
      });

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('is-admin')).toHaveTextContent('Admin');
      });
    });
  });

  describe('Authentication Methods', () => {
    beforeEach(() => {
      mockSupabase.auth.getSession.mockResolvedValue({
        data: { session: null },
        error: null
      });
    });

    it('should handle sign in correctly', async () => {
      const user = userEvent.setup();
      
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Sign In')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Sign In'));

      expect(mockSupabase.auth.signInWithPassword).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password',
      });
    });

    it('should handle sign up correctly', async () => {
      const user = userEvent.setup();
      
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Sign Up')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Sign Up'));

      expect(mockSupabase.auth.signUp).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password',
        options: {
          emailRedirectTo: expect.stringContaining('/'),
          data: {
            display_name: 'test'
          }
        }
      });
    });

    it('should handle sign out correctly', async () => {
      const user = userEvent.setup();
      
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Sign Out')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Sign Out'));

      expect(mockSupabase.auth.signOut).toHaveBeenCalled();
    });

    it('should handle sign in error', async () => {
      const user = userEvent.setup();
      const mockError = { message: 'Invalid credentials' };
      
      mockSupabase.auth.signInWithPassword.mockResolvedValueOnce({
        error: mockError
      });

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Sign In')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Sign In'));

      expect(mockSupabase.rpc).toHaveBeenCalledWith('log_security_event', {
        p_action: 'user_login',
        p_resource: 'authentication',
        p_status: 'failure',
        p_details: expect.objectContaining({
          email: 'tes***',
          error: 'Invalid credentials'
        })
      });
    });
  });

  describe('Permission System', () => {
    it('should handle permissions for regular user', async () => {
      const mockUser = testUtils.createMockUser({
        user_metadata: { 
          role: 'user',
          permissions: ['read', 'write']
        }
      });
      const mockSession = testUtils.createMockSession(mockUser);

      mockSupabase.auth.getSession.mockResolvedValueOnce({
        data: { session: mockSession },
        error: null
      });

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('has-permission')).toHaveTextContent('Has Permission');
        expect(screen.getByTestId('is-admin')).toHaveTextContent('Not Admin');
      });
    });

    it('should handle permissions for admin user', async () => {
      const mockUser = testUtils.createMockUser({
        user_metadata: { role: 'admin' }
      });
      const mockSession = testUtils.createMockSession(mockUser);

      mockSupabase.auth.getSession.mockResolvedValueOnce({
        data: { session: mockSession },
        error: null
      });

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('has-permission')).toHaveTextContent('Has Permission');
        expect(screen.getByTestId('is-admin')).toHaveTextContent('Admin');
      });
    });
  });

  describe('Auth State Changes', () => {
    it('should handle auth state change events', async () => {
      let authStateCallback: (event: string, session: any) => void;
      
      mockSupabase.auth.onAuthStateChange.mockImplementation((callback) => {
        authStateCallback = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      });

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      // Simulate sign in event
      const mockUser = testUtils.createMockUser();
      const mockSession = testUtils.createMockSession(mockUser);

      act(() => {
        authStateCallback('SIGNED_IN', mockSession);
      });

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });

      // Simulate sign out event
      act(() => {
        authStateCallback('SIGNED_OUT', null);
      });

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Not Authenticated');
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle initialization errors gracefully', async () => {
      mockSupabase.auth.getSession.mockRejectedValueOnce(
        new Error('Network error')
      );

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Not Authenticated');
      });
    });
  });
});