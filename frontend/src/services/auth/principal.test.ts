import { describe, expect, it } from 'vitest';
import type { StaffAssignment, User } from '@/types/api';
import { can, derivePrincipal, displayName, homePathFor, initials } from './principal';

const user = (role: User['role'], extra: Partial<User> = {}): User => ({
  id: 1,
  username: 'ada',
  email: 'ada@example.com',
  first_name: 'Ada',
  last_name: 'Obi',
  phone: '',
  role,
  tenant_name: 'Shop',
  tenant_id: 5,
  ...extra,
});

const assignment = (tenant: number, services: StaffAssignment['services']): StaffAssignment => ({
  id: tenant,
  user: 1,
  tenant,
  services,
  is_active: true,
  created_at: '',
});

describe('derivePrincipal + can()', () => {
  it('owner has everything a manager has plus team & subscription checkout', () => {
    const owner = derivePrincipal(user('owner'));
    const manager = derivePrincipal(user('manager'));
    expect(can(owner, 'team.manage')).toBe(true);
    expect(can(owner, 'subscription.checkout')).toBe(true);
    expect(can(manager, 'team.manage')).toBe(false);
    expect(can(manager, 'vouchers.generate')).toBe(true);
    expect(can(manager, 'routers.manage')).toBe(true);
    expect(can(owner, 'platform.admin')).toBe(false);
  });

  it('tenant staff are read-only', () => {
    const staff = derivePrincipal(user('staff'));
    expect(can(staff, 'vouchers.view')).toBe(true);
    expect(can(staff, 'vouchers.print')).toBe(true);
    expect(can(staff, 'vouchers.generate')).toBe(false);
    expect(can(staff, 'sessions.disconnect')).toBe(false);
    expect(can(staff, 'agents.manage')).toBe(false);
  });

  it('platform admin only has the platform console', () => {
    const admin = derivePrincipal(user('platform_admin', { tenant_id: null, tenant_name: null }));
    expect(can(admin, 'platform.admin')).toBe(true);
    expect(can(admin, 'vouchers.view')).toBe(false);
    expect(homePathFor(admin)).toBe('/platform');
  });

  it('agents have no workspace capabilities and go to the agent portal', () => {
    const agent = derivePrincipal(user('agent'));
    expect(can(agent, 'vouchers.view')).toBe(false);
    expect(homePathFor(agent)).toBe('/agent');
  });

  it('platform staff capabilities follow the active assignment grants', () => {
    const assignments = [
      assignment(10, ['routers.view', 'live_sessions.view']),
      assignment(11, ['payments.view', 'payments.support', 'vouchers.generate']),
    ];
    const onTen = derivePrincipal(user('platform_staff', { tenant_id: null }), assignments, 10);
    expect(onTen.kind).toBe('platform_staff');
    expect(can(onTen, 'routers.view')).toBe(true);
    expect(can(onTen, 'routers.diagnostics')).toBe(true);
    expect(can(onTen, 'routers.test')).toBe(false);
    expect(can(onTen, 'sessions.view')).toBe(true);
    expect(can(onTen, 'payments.view')).toBe(false);
    expect(homePathFor(onTen)).toBe('/');

    const onEleven = derivePrincipal(user('platform_staff', { tenant_id: null }), assignments, 11);
    expect(can(onEleven, 'payments.recovery.act')).toBe(true);
    expect(can(onEleven, 'vouchers.generate')).toBe(true);
    expect(can(onEleven, 'plans.view')).toBe(true);
    expect(can(onEleven, 'routers.view')).toBe(false);
  });

  it('platform staff with an invalid stored tenant fall back to the single assignment or the selector', () => {
    const single = derivePrincipal(user('platform_staff'), [assignment(10, ['routers.view'])], 999);
    expect(single.kind === 'platform_staff' && single.activeTenantId).toBe(10);
    const multi = derivePrincipal(
      user('platform_staff'),
      [assignment(10, ['routers.view']), assignment(11, ['routers.view'])],
      999,
    );
    expect(multi.kind === 'platform_staff' && multi.activeTenantId).toBeNull();
    expect(homePathFor(multi)).toBe('/select-tenant');
  });

  it('users without a role land on no-access', () => {
    const none = derivePrincipal(user('user'));
    expect(none.kind).toBe('none');
    expect(homePathFor(none)).toBe('/no-access');
    expect(can(null, 'vouchers.view')).toBe(false);
  });

  it('formats display names and initials', () => {
    expect(displayName(user('owner'))).toBe('Ada Obi');
    expect(initials(user('owner'))).toBe('AO');
    expect(displayName(user('owner', { first_name: '', last_name: '' }))).toBe('ada');
    expect(initials(user('owner', { first_name: '', last_name: '' }))).toBe('AD');
  });
});
