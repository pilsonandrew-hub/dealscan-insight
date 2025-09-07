import React, { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/ModernAuthContext';

export interface AuthorizationBoundaryProps {
  children: ReactNode;
  requireAuth?: boolean;
  allowedRoles?: string[];
  requiredPermissions?: string[];
  requireAdmin?: boolean;
  allowAdminImplicit?: boolean;
  disableAdminBypass?: boolean;
  authRedirectPath?: string;
  unauthorizedRedirectPath?: string;
  loadingRenderer?: ReactNode;
  fallback?: ReactNode;
  extraCheck?: (ctx: {
    user: any;
    roles: string[];
    permissions: string[];
    attributes: Record<string, any>;
  }) => boolean;
  testIds?: { loading?: string; container?: string; };
}

const DefaultLoading = () => (
  <div className="min-h-screen flex items-center justify-center" data-testid="auth-loading" role="status">
    <Loader2 className="h-8 w-8 animate-spin text-primary" />
  </div>
);

function normalizeStringArray(arr: unknown): string[] {
  if (!Array.isArray(arr)) return [];
  return arr.filter(v => typeof v === 'string').map(v => v.toLowerCase().trim()).filter(Boolean);
}

export const AuthorizationBoundary: React.FC<AuthorizationBoundaryProps> = ({
  children,
  requireAuth = true,
  allowedRoles,
  requiredPermissions,
  requireAdmin = false,
  allowAdminImplicit = true,
  disableAdminBypass = false,
  authRedirectPath = '/auth',
  unauthorizedRedirectPath = '/',
  loadingRenderer,
  fallback = null,
  extraCheck,
  testIds,
}) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div data-testid={testIds?.loading ?? 'auth-loading'}>{loadingRenderer ?? <DefaultLoading />}</div>
    );
  }

  if (requireAuth && !user) {
    return <Navigate to={authRedirectPath} state={{ from: location }} replace />;
  }

  if (!requireAuth && !user) {
    return <div data-testid={testIds?.container ?? 'auth-boundary'}>{children ?? fallback}</div>;
  }

  const roles = normalizeStringArray(user?.roles);
  const permissions = normalizeStringArray(user?.permissions);
  const attributes: Record<string, any> = user?.attributes || {};
  const isAdmin = !!user?.is_admin;
  const adminBypass = isAdmin && allowAdminImplicit && !disableAdminBypass;
  const adminRequirementOk = requireAdmin ? isAdmin : true;
  const roleAllowed = allowedRoles?.length ? allowedRoles.map(r => r.toLowerCase()).some(r => roles.includes(r)) : true;
  const permissionsSatisfied = requiredPermissions?.length ? requiredPermissions.map(p => p.toLowerCase()).every(p => permissions.includes(p)) : true;
  const extraCheckResult = extraCheck ? extraCheck({ user, roles, permissions, attributes }) : true;
  const authorized = (roleAllowed && permissionsSatisfied && adminRequirementOk && extraCheckResult) || adminBypass;

  if (!authorized) {
    if (typeof window !== 'undefined') {
      (window as any).SECURITY_EVENTS?.push({
        type: 'auth.denied',
        severity: 'low',
        timestamp: Date.now(),
        meta: { path: location.pathname, reason: { roleAllowed, permissionsSatisfied, adminRequirementOk, extraCheckResult, adminBypass } },
      });
    }
    return <Navigate to={unauthorizedRedirectPath} replace state={{ denied: location.pathname }} />;
  }

  if (typeof window !== 'undefined') {
    (window as any).SECURITY_EVENTS?.push({
      type: 'auth.granted',
      severity: 'low',
      timestamp: Date.now(),
      meta: { path: location.pathname },
    });
  }
  return <div data-testid={testIds?.container ?? 'auth-boundary'}>{children ?? fallback}</div>;
};

export default AuthorizationBoundary;