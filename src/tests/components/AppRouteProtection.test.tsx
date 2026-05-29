import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Location } from 'react-router-dom';
import App from '@/App';
import Auth from '@/pages/Auth';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { AuthContext, type AuthContextType } from '@/contexts/auth-context-core';
import { testUtils } from '@/tests/setup';

vi.mock('@/pages/DealDetail', () => ({
  default: () => <div data-testid="deal-detail-route">DealDetail rendered</div>,
}));


function renderAuthenticatedAuthRoute(from: Partial<Location>) {
  const authValue: AuthContextType = {
    user: testUtils.createMockUser(),
    session: testUtils.createMockSession(),
    loading: false,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
  };

  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/auth',
            state: {
              from: {
                pathname: '/deal/auth-return-proof',
                search: '',
                hash: '',
                state: null,
                key: 'from',
                ...from,
              },
            },
          },
        ]}
      >
        <Routes>
          <Route path="/auth" element={<Auth />} />
          <Route path="/deal/:id" element={<div data-testid="returned-deal-route">Returned deal route</div>} />
          <Route path="/" element={<div data-testid="root-route">Root route</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe('App route access control', () => {
  it('keeps direct deal detail links behind ProtectedRoute', () => {
    const appSource = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8');

    expect(appSource).toMatch(/<Route\s+path="\/deal\/:id"\s+element=\{/);
    expect(appSource).toMatch(
      /<Route\s+path="\/deal\/:id"\s+element=\{[\s\S]*?<ProtectedRoute>[\s\S]*?<DealDetail\s*\/>[\s\S]*?<\/ProtectedRoute>[\s\S]*?\}\s*\/>/
    );
  });

  it('does not mount DealDetail while auth state is still loading', () => {
    const authValue: AuthContextType = {
      user: null,
      session: null,
      loading: true,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={['/deal/loading-proof']}>
          <ProtectedRoute>
            <div data-testid="deal-detail-route">DealDetail rendered</div>
          </ProtectedRoute>
        </MemoryRouter>
      </AuthContext.Provider>
    );

    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.queryByTestId('deal-detail-route')).not.toBeInTheDocument();
  });

  it('redirects unauthenticated direct deal detail navigation to auth without rendering DealDetail', async () => {
    window.history.pushState({}, '', '/deal/runtime-route-proof');

    render(<App />);

    await waitFor(() => {
      expect(window.location.pathname).toBe('/auth');
    });

    expect(screen.getByRole('heading', { name: 'DealerScope' })).toBeInTheDocument();
    expect(screen.queryByTestId('deal-detail-route')).not.toBeInTheDocument();
  });

  it('returns authenticated users to the protected deal detail route captured by ProtectedRoute state.from', async () => {
    renderAuthenticatedAuthRoute({ pathname: '/deal/auth-return-proof' });

    expect(await screen.findByTestId('returned-deal-route')).toBeInTheDocument();
    expect(screen.queryByTestId('root-route')).not.toBeInTheDocument();
  });
});
