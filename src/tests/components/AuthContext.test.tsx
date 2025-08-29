/**
 * Basic Auth Context Tests
 * Simple test to verify auth context works
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { AuthProvider, useAuth } from '@/contexts/ModernAuthContext';

// Simple test component
const TestComponent = () => {
  const { loading, user } = useAuth();
  const isAuthenticated = !!user;
  
  if (loading) return <div>Loading...</div>;
  
  return (
    <div>
      <div data-testid="auth-status">
        {isAuthenticated ? 'Authenticated' : 'Not Authenticated'}
      </div>
    </div>
  );
};

describe('UnifiedAuthContext', () => {
  it('should provide auth context correctly', () => {
    const { getByTestId } = render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );
    
    // Should eventually show auth status (not authenticated initially)
    expect(getByTestId('auth-status')).toBeInTheDocument();
  });
});