import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { setActiveTenantHeader, setSessionExpiredHandler } from '@/services/api/http';
import { tokenStore } from '@/services/auth/tokenStore';
import {
  bootstrapSession,
  endSession,
  loadPrincipal,
  rememberTenantFor,
} from '@/services/auth/session';
import { derivePrincipal, type Principal } from '@/services/auth/principal';
import type { TokenPair } from '@/types/api';
import { AuthContext, type AuthContextValue, type AuthStatus } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>('booting');
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [signOutReason, setSignOutReason] = useState<string | null>(null);
  const principalRef = useRef<Principal | null>(null);
  useEffect(() => {
    principalRef.current = principal;
  }, [principal]);

  const applyPrincipal = useCallback((next: Principal | null) => {
    setPrincipal(next);
    setStatus(next ? 'authenticated' : 'anonymous');
  }, []);

  // Initial bootstrap.
  useEffect(() => {
    let cancelled = false;
    bootstrapSession().then((p) => {
      if (!cancelled) applyPrincipal(p);
    });
    return () => {
      cancelled = true;
    };
  }, [applyPrincipal]);

  const signOut = useCallback(
    async (reason?: string) => {
      applyPrincipal(null);
      setSignOutReason(reason ?? null);
      queryClient.clear();
      await endSession();
    },
    [applyPrincipal, queryClient],
  );

  // The http client reports irrecoverable 401s (refresh rejected).
  useEffect(() => {
    setSessionExpiredHandler(() => {
      if (principalRef.current) void signOut('Your session has expired. Please sign in again.');
    });
    return () => setSessionExpiredHandler(null);
  }, [signOut]);

  // Another tab signed out (refresh token removed) → mirror it.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || (event.key === 'yr.auth.refresh' && event.newValue === null)) {
        if (principalRef.current) void signOut('You were signed out in another tab.');
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [signOut]);

  const signIn = useCallback(
    async (tokens: TokenPair) => {
      tokenStore.set(tokens);
      setSignOutReason(null);
      queryClient.clear();
      const next = await loadPrincipal();
      applyPrincipal(next);
      return next;
    },
    [applyPrincipal, queryClient],
  );

  const refreshPrincipal = useCallback(async () => {
    if (!tokenStore.hasSession()) return null;
    try {
      const next = await loadPrincipal();
      applyPrincipal(next);
      return next;
    } catch {
      return principalRef.current;
    }
  }, [applyPrincipal]);

  const selectTenant = useCallback(
    (tenantId: number | null) => {
      const current = principalRef.current;
      if (!current || current.kind !== 'platform_staff') return;
      const next = derivePrincipal(current.user, current.assignments, tenantId);
      if (next.kind === 'platform_staff') {
        setActiveTenantHeader(next.activeTenantId);
        rememberTenantFor(current.user.id, next.activeTenantId);
      }
      queryClient.clear();
      setPrincipal(next);
    },
    [queryClient],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, principal, signOutReason, signIn, refreshPrincipal, signOut, selectTenant }),
    [status, principal, signOutReason, signIn, refreshPrincipal, signOut, selectTenant],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
