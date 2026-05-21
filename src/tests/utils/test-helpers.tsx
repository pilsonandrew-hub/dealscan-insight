/**
 * Test Helper Utilities
 */

/* eslint-disable react-refresh/only-export-components -- Test helper module intentionally exports render wrappers and utility factories. */
import { render, RenderOptions } from '@testing-library/react';
import type { User } from '@supabase/supabase-js';
import { ReactElement, ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';

const AllProviders = ({ children }: { children: ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

const customRender = (ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) =>
  render(ui, { wrapper: AllProviders, ...options });

const createMockUser = (overrides: Partial<User> = {}) => ({
  aud: 'authenticated',
  app_metadata: {},
  user_metadata: {},
  created_at: '2026-01-01T00:00:00Z',
  id: 'test-user-id',
  email: 'test@example.com',
  ...overrides,
});

const createMockSession = (user?: Partial<User>) => ({
  access_token: 'mock-token',
  user: user || createMockUser(),
});

export const testUtils = {
  createMockUser,
  createMockSession,
};

export * from '@testing-library/react';
export { customRender as render };