import { useContext } from 'react';
import { AuthContext, type AuthContextValue } from './authContext';
import type { Principal } from '@/services/auth/principal';

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}

/** For screens rendered behind RequireAuth: the principal is guaranteed. */
export function usePrincipal(): Principal {
  const { principal } = useAuth();
  if (!principal) throw new Error('usePrincipal used outside an authenticated route');
  return principal;
}
