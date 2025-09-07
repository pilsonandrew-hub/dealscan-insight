# ProtectedRoute Component Testing Guide

## Overview

The `ProtectedRoute` component is a crucial security component that controls access to protected areas of the application based on user authentication status and role-based permissions.

## Component Features

### Default Export
The component is exported as a default export to maintain consistency with React component conventions:

```tsx
import ProtectedRoute from '@/components/ProtectedRoute'
```

### Data Test IDs
The component includes `data-testid` attributes for reliable testing:

- `protected-route-loader`: Loading spinner shown during authentication checks

### Props Interface

```tsx
interface ProtectedRouteProps {
  children: React.ReactNode
  requireAdmin?: boolean
}
```

## Testing Strategy

### Test Coverage Requirements
- Branch coverage: 80% minimum
- All authentication states must be tested
- All role-based access scenarios must be covered

### Test Scenarios

#### 1. Authenticated User Access
```tsx
it('renders child component when user is authenticated', () => {
  mockUseAuth.mockReturnValue({
    user: { id: 1, username: 'testuser', email: 'test@example.com', is_admin: false },
    isLoading: false,
  });
  // Test implementation...
});
```

#### 2. Loading State
```tsx
it('shows loading spinner with data-testid when authentication is loading', () => {
  mockUseAuth.mockReturnValue({
    user: null,
    isLoading: true,
  });
  // Test implementation...
});
```

#### 3. Unauthenticated Access
```tsx
it('redirects to login when user is not authenticated', () => {
  mockUseAuth.mockReturnValue({
    user: null,
    isLoading: false,
  });
  // Test implementation...
});
```

#### 4. Admin-Only Access
```tsx
it('allows access for admin user when requireAdmin is true', () => {
  mockUseAuth.mockReturnValue({
    user: { id: 1, username: 'admin', email: 'admin@example.com', is_admin: true },
    isLoading: false,
  });
  // Test implementation...
});
```

#### 5. Non-Admin Restriction
```tsx
it('redirects non-admin user to dashboard when requireAdmin is true', () => {
  mockUseAuth.mockReturnValue({
    user: { id: 1, username: 'user', email: 'user@example.com', is_admin: false },
    isLoading: false,
  });
  // Test implementation...
});
```

#### 6. Location State Preservation
```tsx
it('preserves location state for redirect after login', async () => {
  // Test that location state is preserved for post-login redirects
});
```

## Mock Setup

### useAuth Hook Mocking
```tsx
const mockUseAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));
```

### Test Utilities
- Use `MemoryRouter` for route testing
- Mock authentication states with `mockUseAuth`
- Use `waitFor` for async navigation testing
- Verify `data-testid` attributes for reliable element selection

## Best Practices

### ESLint Rules
The following ESLint rules are enforced to prevent incorrect import usage:

1. **Consistent Default Imports**: Use default import syntax for ProtectedRoute
2. **Type Import Separation**: Use type-only imports when importing types
3. **Import Pattern Validation**: Patterns are checked to ensure correct import syntax

### Security Testing
- Always test both authenticated and unauthenticated states
- Verify proper redirection behavior
- Test role-based access control thoroughly
- Ensure sensitive content is not exposed during loading states

### Performance Considerations
- Mock external dependencies to avoid network calls
- Use `vi.clearAllMocks()` in `beforeEach` to ensure test isolation
- Test loading states to verify user experience during authentication checks

## Running Tests

```bash
# Run all tests
npx vitest run

# Run with coverage
npx vitest run --coverage

# Run ProtectedRoute tests specifically
npx vitest run src/components/__tests__/ProtectedRoute.test.tsx
```

## Coverage Requirements

The component must maintain:
- 80% branch coverage minimum
- 100% of authentication paths tested
- All user role scenarios covered
- Loading states verified

## Integration Notes

### Router Integration
- Works with React Router DOM v6+
- Preserves location state for post-login redirects
- Uses `Navigate` component for declarative redirects

### Auth Context Integration
- Depends on `useAuth` hook from AuthContext
- Requires proper authentication provider setup
- Handles loading and error states gracefully