/**
 * Phase 5 feature services (routers, agents, devices) against the RUNNING backend harness.
 * Run with: npm run test:integration
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { server } from '@/test/server';
import { liveTokens } from '@/test/liveSession';
import { tokenStore } from '@/services/auth/tokenStore';
import type { ApiError } from '@/services/api/errors';
import { routersApi } from '@/features/routers/api';
import { agentsApi } from '@/features/agents/api';
import { devicesApi } from '@/features/devices/api';
import { plansApi } from '@/features/plans/api';
import { checkRows, nextStates } from '@/features/routers/routerRules';

const PASSWORD = 'Passw0rd!2026';
const stamp = Date.now();

beforeAll(() => {
  server.close();
  tokenStore.set(liveTokens('manager'));
});
afterAll(() => server.listen({ onUnhandledRequest: 'error' }));

describe.runIf(import.meta.env.LIVE_API === '1')('phase 5 against live API', () => {
  it('routers: create → transitions follow the state machine → health/checks/audit → edit → delete', async () => {
    const created = await routersApi.create({
      name: `it-router-${stamp}`,
      ip_address: `10.200.${Math.floor(stamp / 1000) % 250}.${stamp % 250}`,
      nas_secret: 'integration-secret',
      location: 'Integration',
      wireguard_ip: null,
      wireguard_public_key: '',
      wireguard_port: 51820,
      routeros_username: '',
      is_active: true,
    });
    expect(created.onboarding_state).toBe('pending');
    expect(created).not.toHaveProperty('nas_secret');

    // Invalid transition is rejected with a readable message.
    const bad = await routersApi
      .transition(created.id, { to_state: 'active' })
      .catch((e: unknown) => e);
    expect((bad as ApiError).status).toBe(400);
    expect((bad as ApiError).message).toMatch(/Invalid transition/);

    // Walk pending → reviewed → approved → waiting_for_vpn using only allowed next states.
    let state = created.onboarding_state;
    for (const to of ['reviewed', 'approved', 'waiting_for_vpn'] as const) {
      expect(nextStates(state)).toContain(to);
      const res = await routersApi.transition(created.id, { to_state: to });
      expect(res.correlation_id).toBeTruthy();
      state = to;
    }
    const fetched = await routersApi.get(created.id);
    expect(fetched.onboarding_state).toBe('waiting_for_vpn');

    // Provisioning is refused without WireGuard details (400, not 500).
    const noVpn = await routersApi
      .provisioning(created.id, { action: 'provision' })
      .catch((e: unknown) => e);
    expect((noVpn as ApiError).status).toBe(400);
    expect((noVpn as ApiError).message).toMatch(/WireGuard/);

    const health = await routersApi.health(created.id);
    expect(health.telemetry_available).toBe(false);
    expect(health.online).toBeNull();
    expect(checkRows(await routersApi.checks(created.id)).every((r) => r.status === 'never')).toBe(
      true,
    );

    const audit = await routersApi.audit(created.id, { page: 1, page_size: 20 });
    expect(audit.results.length).toBeGreaterThanOrEqual(3);
    expect(audit.results.some((e) => e.to_state === 'waiting_for_vpn')).toBe(true);

    const patched = await routersApi.update(created.id, { location: 'Integration 2' });
    expect(patched.location).toBe('Integration 2');
    const secretOnPatch = await routersApi
      .update(created.id, { nas_secret: 'x'.repeat(10) } as never)
      .catch((e: unknown) => e);
    expect((secretOnPatch as ApiError).status).toBe(400);

    const stale = await routersApi
      .replaceSecrets(created.id, {
        current_password: PASSWORD,
        nas_secret: 'another-secret',
        expected_updated_at: created.updated_at,
      })
      .catch((e: unknown) => e);
    expect((stale as ApiError).status).toBe(409);
    const wrongPw = await routersApi
      .replaceSecrets(created.id, {
        current_password: 'nope',
        nas_secret: 'another-secret',
        expected_updated_at: patched.updated_at,
      })
      .catch((e: unknown) => e);
    expect((wrongPw as ApiError).status).toBe(400);
    const rotated = await routersApi.replaceSecrets(created.id, {
      current_password: PASSWORD,
      nas_secret: 'another-secret',
      expected_updated_at: patched.updated_at,
    });
    expect(rotated.id).toBe(created.id);

    await routersApi.remove(created.id);
    const gone = await routersApi.get(created.id).catch((e: unknown) => e);
    expect((gone as ApiError).status).toBe(404);
  }, 30_000);

  it('routers: operations list is manager-only and the deployed router refuses deletion', async () => {
    const ops = await routersApi.operations({ page: 1, page_size: 5 });
    expect(ops).toHaveProperty('results');
    const all = await routersApi.listAll();
    const deployed = all.find((r) => r.deployment_status === 'deployed');
    if (deployed) {
      const refused = await routersApi.remove(deployed.id).catch((e: unknown) => e);
      expect((refused as ApiError).status).toBe(409);
    }
  });

  it('agents: create (pending) → approve → edit → suspend → list filter/search', async () => {
    const username = `itagent${stamp}`;
    const created = await agentsApi.create({
      username,
      email: `${username}@example.com`,
      password: 'Agent!Passw0rd',
      phone: '+2348099900000',
      shop_name: 'IT Shop',
      commission_rate: '12.50',
    });
    expect(created.status).toBe('pending');
    expect(created.commission_rate).toBe('12.50');
    const dup = await agentsApi
      .create({
        username,
        email: `${username}@example.com`,
        password: 'Agent!Passw0rd',
        phone: '+2348099900000',
      })
      .catch((e: unknown) => e);
    expect((dup as ApiError).status).toBe(400);
    expect((dup as ApiError).fieldMessage('username')).toMatch(/taken/);

    const approved = await agentsApi.approve(created.id);
    expect(approved.status).toBe('active');
    const edited = await agentsApi.update(created.id, { shop_name: 'IT Shop 2' });
    expect(edited.shop_name).toBe('IT Shop 2');
    const suspended = await agentsApi.suspend(created.id);
    expect(suspended.status).toBe('suspended');

    const listed = await agentsApi.list({
      page: 1,
      page_size: 50,
      status: 'suspended',
      search: 'IT Shop',
    });
    expect(listed.results.some((a) => a.id === created.id)).toBe(true);
  });

  it('devices: create normalises the MAC → filter by plan/is_active → patch → delete', async () => {
    const [plan] = await plansApi.listAll({ activeOnly: true });
    expect(plan).toBeDefined();
    const mac = `02-${(stamp % 0xffffffffff).toString(16).padStart(10, '0').match(/.{2}/g)!.join('-')}`;
    const created = await devicesApi.create({
      device_name: `IT device ${stamp}`,
      mac_address: mac,
      plan: plan!.id,
      is_active: true,
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    });
    expect(created.mac_address).toBe(mac.toUpperCase().replace(/-/g, ':'));
    expect(created.plan_name).toBe(plan!.name);

    const listed = await devicesApi.list({
      page: 1,
      page_size: 50,
      plan: plan!.id,
      is_active: true,
      search: 'IT device',
    });
    expect(listed.results.some((d) => d.id === created.id)).toBe(true);
    const patched = await devicesApi.update(created.id, { is_active: false });
    expect(patched.is_active).toBe(false);
    const inactiveOnly = await devicesApi.list({ page: 1, page_size: 50, is_active: false });
    expect(inactiveOnly.results.some((d) => d.id === created.id)).toBe(true);

    const badMac = await devicesApi
      .create({
        device_name: 'bad',
        mac_address: 'zz:zz',
        plan: plan!.id,
        expires_at: new Date().toISOString(),
      })
      .catch((e: unknown) => e);
    expect((badMac as ApiError).fieldMessage('mac_address')).toMatch(/MAC/);

    await devicesApi.remove(created.id);
    const gone = await devicesApi.get(created.id).catch((e: unknown) => e);
    expect((gone as ApiError).status).toBe(404);
  });

  it('staff cannot reach manager-only agent/operation endpoints (403 surfaces as forbidden)', async () => {
    const previous = {
      access: tokenStore.getAccess() ?? '',
      refresh: tokenStore.getRefresh() ?? '',
    };
    tokenStore.set(liveTokens('staff'));
    try {
      const agents = await agentsApi.list({ page: 1 }).catch((e: unknown) => e);
      expect((agents as ApiError).kind).toBe('forbidden');
      const ops = await routersApi.operations({ page: 1 }).catch((e: unknown) => e);
      expect((ops as ApiError).kind).toBe('forbidden');
      const devices = await devicesApi.list({ page: 1 });
      expect(devices).toHaveProperty('results');
    } finally {
      tokenStore.set(previous);
    }
  });
});
