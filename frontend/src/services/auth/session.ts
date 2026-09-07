import { STORAGE_KEYS } from '@/app/config/constants';
import { http, refreshAccessToken, setActiveTenantHeader } from '@/services/api/http';
import type {
  AgentLoginResponse,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  ResendVerificationResponse,
  StaffAssignment,
  User,
  Paginated,
  VerifyEmailRequest,
} from '@/types/api';
import { tokenStore } from './tokenStore';
import { derivePrincipal, type Principal } from './principal';

export const authApi = {
  login(username: string, password: string) {
    return http.post<LoginResponse>(
      '/auth/login/',
      { username, password },
      { anonymous: true, tenantId: null },
    );
  },
  agentLogin(username: string, password: string) {
    return http.post<AgentLoginResponse>(
      '/agent/login/',
      { username, password },
      { anonymous: true, tenantId: null },
    );
  },
  register(payload: RegisterRequest) {
    return http.post<RegisterResponse>('/auth/register/', payload, {
      anonymous: true,
      tenantId: null,
    });
  },
  /** Confirms the emailed OTP. Returns tokens — the account is active on success. */
  verifyEmail(payload: VerifyEmailRequest) {
    return http.post<LoginResponse>('/auth/verify-email/', payload, {
      anonymous: true,
      tenantId: null,
    });
  },
  resendVerification(email: string) {
    return http.post<ResendVerificationResponse>(
      '/auth/resend-verification/',
      { email },
      { anonymous: true, tenantId: null },
    );
  },
  me() {
    return http.get<User>('/auth/user/', undefined, { tenantId: null });
  },
  myAssignments() {
    return http.get<Paginated<StaffAssignment>>(
      '/staff/assignments/',
      { page_size: 100 },
      { tenantId: null },
    );
  },
  async logout(refresh: string) {
    await http.post<void>('/auth/logout/', { refresh }, { responseType: 'void', tenantId: null });
  },
};

function storedTenantFor(userId: number): number | null {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEYS.activeTenant}.${userId}`);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

export function rememberTenantFor(userId: number, tenantId: number | null) {
  try {
    const key = `${STORAGE_KEYS.activeTenant}.${userId}`;
    if (tenantId === null) localStorage.removeItem(key);
    else localStorage.setItem(key, String(tenantId));
  } catch {
    /* ignore */
  }
}

/** Resolve the full principal for the current tokens (always re-reads `auth/user/`). */
export async function loadPrincipal(): Promise<Principal> {
  setActiveTenantHeader(null);
  const user = await authApi.me();
  if (user.role === 'platform_staff') {
    const assignments = (await authApi.myAssignments()).results;
    const principal = derivePrincipal(user, assignments, storedTenantFor(user.id));
    if (principal.kind === 'platform_staff') setActiveTenantHeader(principal.activeTenantId);
    return principal;
  }
  return derivePrincipal(user);
}

/** Called on app start: silently refresh (if we have a refresh token) then load the principal. */
export async function bootstrapSession(): Promise<Principal | null> {
  if (!tokenStore.hasSession()) return null;
  if (!tokenStore.getAccess()) {
    const access = await refreshAccessToken();
    if (!access) return null;
  }
  try {
    return await loadPrincipal();
  } catch {
    return null;
  }
}

export async function endSession(): Promise<void> {
  const refresh = tokenStore.getRefresh();
  tokenStore.clear();
  setActiveTenantHeader(null);
  if (refresh) {
    try {
      await authApi.logout(refresh);
    } catch {
      /* token already invalid — nothing to do */
    }
  }
}
