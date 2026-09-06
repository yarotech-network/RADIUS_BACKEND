import { createContext } from 'react';
import type { Principal } from '@/services/auth/principal';
import type { TokenPair } from '@/types/api';

export type AuthStatus = 'booting' | 'anonymous' | 'authenticated';

export interface AuthContextValue {
  status: AuthStatus;
  principal: Principal | null;
  /** Message to show on the login page after a forced sign-out (session expired, password changed…). */
  signOutReason: string | null;
  /** Persist tokens and load the principal (used by login/register/accept-invitation flows). */
  signIn: (tokens: TokenPair) => Promise<Principal>;
  /** Re-read `auth/user/` (+ assignments) without touching tokens. */
  refreshPrincipal: () => Promise<Principal | null>;
  signOut: (reason?: string) => Promise<void>;
  /** Platform staff: choose the tenant whose data the workspace shows. */
  selectTenant: (tenantId: number | null) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
