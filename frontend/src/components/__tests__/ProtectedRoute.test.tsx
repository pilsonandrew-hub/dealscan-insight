import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import ProtectedRoute from '../ProtectedRoute';

// Mock the useAuth hook to control authentication status in tests
vi.mock('../../hooks/useAuth', () => ({
  __esModule: true,
  default: () => ({
    user: { id: '123', email: 'test@example.com' }, // Simulate an authenticated user
    isLoading: false,
  }),
}));

describe('ProtectedRoute', () => {
  it('renders child component when user is authenticated', () => {
    const TestComponent = () => <div>Protected Content</div>;

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <TestComponent />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    // Check if the protected content is visible
    expect(screen.getByText('Protected Content')).toBeInTheDocument();
  });
});
