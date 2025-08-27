/**
 * Test Helper Utilities
 */

import { render, RenderOptions } from '@testing-library/react';
import { ReactElement, ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';

const AllProviders = ({ children }: { children: ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

const customRender = (ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) =>
  render(ui, { wrapper: AllProviders, ...options });

const createMockUser = (overrides = {}) => ({
  id: 'test-user-id',
  email: 'test@example.com',
  ...overrides,
});

const createMockSession = (user?: any) => ({
  access_token: 'mock-token',
  user: user || createMockUser(),
});

export const testUtils = {
  createMockUser,
  createMockSession,
};

export * from '@testing-library/react';
export { customRender as render };