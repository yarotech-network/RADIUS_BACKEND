import type { MembershipRole, StaffAssignment, StaffService, User } from '@/types/api';

/**
 * The frontend's view of "who is signed in", derived from `GET auth/user/` (+ staff assignments).
 * Mirrors the backend's `User.role`; see analysis/01_BACKEND_AUDIT.md §5.
 */
export type Principal =
  | { kind: 'platform_admin'; user: User }
  | { kind: 'member'; user: User; role: MembershipRole; tenantId: number; tenantName: string }
  | { kind: 'agent'; user: User }
  | {
      kind: 'platform_staff';
      user: User;
      assignments: StaffAssignment[];
      activeTenantId: number | null;
    }
  | { kind: 'none'; user: User };

export type Surface = 'workspace' | 'platform' | 'agent';

export function derivePrincipal(
  user: User,
  assignments: StaffAssignment[] = [],
  activeTenantId: number | null = null,
): Principal {
  switch (user.role) {
    case 'platform_admin':
      return { kind: 'platform_admin', user };
    case 'owner':
    case 'manager':
    case 'staff':
      return {
        kind: 'member',
        user,
        role: user.role,
        tenantId: user.tenant_id ?? 0,
        tenantName: user.tenant_name ?? '',
      };
    case 'agent':
      return { kind: 'agent', user };
    case 'platform_staff': {
      const valid = assignments.find((a) => a.tenant === activeTenantId) ? activeTenantId : null;
      const single = assignments.length === 1 ? (assignments[0]?.tenant ?? null) : null;
      return { kind: 'platform_staff', user, assignments, activeTenantId: valid ?? single };
    }
    default:
      return { kind: 'none', user };
  }
}

/** Human label of the tenant the principal is working in (members only; staff use tenantLabel()). */
export function workspaceName(principal: Principal | null): string | null {
  if (!principal) return null;
  if (principal.kind === 'member') return principal.tenantName || null;
  if (principal.kind === 'platform_staff' && principal.activeTenantId !== null)
    return `Tenant #${principal.activeTenantId}`;
  return null;
}

/** Where this principal should land after sign-in. */
export function homePathFor(principal: Principal): string {
  switch (principal.kind) {
    case 'platform_admin':
      return '/platform';
    case 'agent':
      return '/agent';
    case 'member':
      return '/';
    case 'platform_staff':
      return principal.activeTenantId ? '/' : '/select-tenant';
    default:
      return '/no-access';
  }
}

export function surfaceOf(principal: Principal): Surface | null {
  switch (principal.kind) {
    case 'platform_admin':
      return 'platform';
    case 'agent':
      return 'agent';
    case 'member':
    case 'platform_staff':
      return 'workspace';
    default:
      return null;
  }
}

/**
 * UX capabilities. Names are frontend concepts; each maps to backend permission classes and
 * viewset actions. THIS IS NOT A SECURITY BOUNDARY — every request is authorised server-side.
 */
export type Capability =
  | 'dashboard.view'
  | 'plans.view'
  | 'plans.manage'
  | 'vouchers.view'
  | 'vouchers.generate'
  | 'vouchers.manage' // manual create / edit / delete / disable
  | 'vouchers.print'
  | 'payments.view'
  | 'payments.recovery.view'
  | 'payments.recovery.act'
  | 'routers.view'
  | 'routers.manage'
  | 'routers.test'
  | 'routers.diagnostics' // audit / checks / health
  | 'sessions.view'
  | 'sessions.disconnect'
  | 'agents.manage'
  | 'devices.view'
  | 'devices.manage'
  | 'whatsapp.view'
  | 'whatsapp.manage'
  | 'settings.profile'
  | 'settings.billing'
  | 'team.view'
  | 'team.manage'
  | 'subscription.view'
  | 'subscription.checkout'
  | 'audit.view'
  | 'platform.admin';

const MEMBER_CAPS: Record<MembershipRole, Set<Capability>> = (() => {
  const staff: Capability[] = [
    'dashboard.view',
    'plans.view',
    'vouchers.view',
    'vouchers.print',
    'payments.view',
    'routers.view',
    'sessions.view',
    'devices.view',
    'whatsapp.view',
    'team.view',
    'subscription.view',
  ];
  const manager: Capability[] = [
    ...staff,
    'plans.manage',
    'vouchers.generate',
    'vouchers.manage',
    'payments.recovery.view',
    'payments.recovery.act',
    'routers.manage',
    'routers.test',
    'routers.diagnostics',
    'sessions.disconnect',
    'agents.manage',
    'devices.manage',
    'whatsapp.manage',
    'settings.profile',
    'settings.billing',
    'audit.view',
  ];
  const owner: Capability[] = [...manager, 'team.manage', 'subscription.checkout'];
  return { staff: new Set(staff), manager: new Set(manager), owner: new Set(owner) };
})();

/** Platform staff grants → capabilities (apps/core/api.py::assigned_tenant). */
const GRANT_CAPS: Record<StaffService, Capability[]> = {
  'routers.view': ['routers.view', 'routers.diagnostics'],
  'routers.test': ['routers.test'],
  'live_sessions.view': ['sessions.view'],
  'live_sessions.disconnect': ['sessions.disconnect'],
  'payments.view': ['payments.view', 'payments.recovery.view'],
  'payments.support': ['payments.recovery.act'],
  'vouchers.generate': ['vouchers.generate', 'plans.view'],
  'vouchers.print': ['vouchers.view', 'vouchers.print'],
};

export function activeGrants(principal: Principal): Set<StaffService> {
  if (principal.kind !== 'platform_staff' || principal.activeTenantId === null) return new Set();
  const assignment = principal.assignments.find((a) => a.tenant === principal.activeTenantId);
  return new Set(assignment?.services ?? []);
}

export function can(principal: Principal | null, capability: Capability): boolean {
  if (!principal) return false;
  switch (principal.kind) {
    case 'platform_admin':
      return capability === 'platform.admin';
    case 'member':
      return MEMBER_CAPS[principal.role].has(capability);
    case 'platform_staff': {
      for (const grant of activeGrants(principal)) {
        if (GRANT_CAPS[grant].includes(capability)) return true;
      }
      return false;
    }
    default:
      return false;
  }
}

export function canAny(principal: Principal | null, capabilities: Capability[]): boolean {
  return capabilities.some((c) => can(principal, c));
}

export function displayName(user: User): string {
  const full = `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim();
  return full || user.username;
}

export function initials(user: User): string {
  const name = displayName(user);
  const parts = name.split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? '';
  const second = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : (parts[0]?.[1] ?? '');
  return (first + second).toUpperCase();
}
