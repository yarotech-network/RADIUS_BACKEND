import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router';
import { useAuth } from './useAuth';
import { homePathFor, surfaceOf, type Surface } from '@/services/auth/principal';
import { AppSplash } from '@/app/shell/AppSplash';
import { safeRedirectPath } from './safeRedirectPath';

/** Blocks rendering until the session bootstrap has settled. */
export function RequireBooted({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === 'booting') return <AppSplash />;
  return <>{children}</>;
}

/** Redirects anonymous users to the right sign-in page, preserving the destination. */
export function RequireAuth({ loginPath = '/login' }: { loginPath?: string }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'booting') return <AppSplash />;
  if (status === 'anonymous') {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={loginPath} replace state={{ from: next }} />;
  }
  return <Outlet />;
}

/** Only principals belonging to `surface` may enter; others go to their own home. */
export function RequireSurface({ surface }: { surface: Surface }) {
  const { principal } = useAuth();
  if (!principal) return <Navigate to="/login" replace />;
  const own = surfaceOf(principal);
  if (own !== surface) return <Navigate to={homePathFor(principal)} replace />;
  if (principal.kind === 'platform_staff' && principal.activeTenantId === null) {
    return <Navigate to="/select-tenant" replace />;
  }
  return <Outlet />;
}

/**
 * Public-only pages (login/register): signed-in users are sent to the page they originally asked
 * for (`location.state.from`, set by RequireAuth) or to their home. The sign-in pages themselves do
 * not navigate — this guard is the single source of truth, which avoids duplicate navigations.
 * Surface mismatches (e.g. an agent asking for /vouchers) are corrected by RequireSurface.
 */
export function RedirectIfAuthenticated() {
  const { status, principal } = useAuth();
  const location = useLocation();
  if (status === 'booting') return <AppSplash />;
  if (status === 'authenticated' && principal) {
    const from = safeRedirectPath((location.state as { from?: unknown } | null)?.from);
    return <Navigate to={from ?? homePathFor(principal)} replace />;
  }
  return <Outlet />;
}
