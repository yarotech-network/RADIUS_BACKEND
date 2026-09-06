/**
 * Integration checks against a RUNNING backend (the SQLite verification harness on :8000).
 * Skipped automatically when the API is not reachable. Run with: npm run test:integration
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { server } from '@/test/server';
import { request, http, refreshAccessToken } from '@/services/api/http';
import { tokenStore } from '@/services/auth/tokenStore';
import { authApi, loadPrincipal } from '@/services/auth/session';
import { ApiError } from '@/services/api/errors';
import { can } from '@/services/auth/principal';
import type { Paginated, Voucher } from '@/types/api';

const PASSWORD = 'Passw0rd!2026';
let reachable = false;

beforeAll(async () => {
  server.close(); // let real fetch through
  try {
    const res = await fetch('http://127.0.0.1:8000/health/live/');
    reachable = res.ok;
  } catch {
    reachable = false;
  }
});
afterAll(() => server.listen({ onUnhandledRequest: 'error' }));

describe.runIf(import.meta.env.LIVE_API === '1')('live API', () => {
  it('backend is reachable', () => {
    expect(reachable).toBe(true);
  });

  it('owner login → principal → capability map', async () => {
    const tokens = await authApi.login('owner', PASSWORD);
    expect(tokens.user.role).toBe('owner');
    tokenStore.set(tokens);
    const principal = await loadPrincipal();
    expect(principal.kind).toBe('member');
    expect(can(principal, 'team.manage')).toBe(true);
    const vouchers = await http.get<Paginated<Voucher>>('/vouchers/', {
      page_size: 5,
      status: 'active',
    });
    expect(vouchers.results.length).toBeGreaterThan(0);
    expect(vouchers.results.every((v) => v.status === 'active')).toBe(true);
    expect(vouchers.results[0]).not.toHaveProperty('password');
  });

  it('refresh rotates and blacklists the previous token', async () => {
    const tokens = await authApi.login('manager', PASSWORD);
    tokenStore.set(tokens);
    const oldRefresh = tokenStore.getRefresh()!;
    const access = await refreshAccessToken();
    expect(access).toBeTruthy();
    expect(tokenStore.getRefresh()).not.toBe(oldRefresh);
    const reuse = await fetch('http://127.0.0.1:8000/api/v1/auth/token/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: oldRefresh }),
    });
    expect(reuse.status).toBe(401);
  });

  it('platform staff: assignments, X-Tenant-ID gating, grants → capabilities', async () => {
    const tokens = await authApi.login('pstaff', PASSWORD);
    tokenStore.set(tokens);
    const principal = await loadPrincipal();
    expect(principal.kind).toBe('platform_staff');
    if (principal.kind !== 'platform_staff') return;
    expect(principal.assignments.length).toBe(2);
    // No tenant header → 403 with the problem envelope.
    const noHeader = await http
      .get('/routers/', undefined, { tenantId: null })
      .catch((e: unknown) => e);
    expect(noHeader).toBeInstanceOf(ApiError);
    expect((noHeader as ApiError).status).toBe(403);
    expect((noHeader as ApiError).code).toBe('http_403');
    const wuse = principal.assignments.find((a) => a.services.includes('routers.view'))!;
    const routers = await http.get<Paginated<unknown>>('/routers/', undefined, {
      tenantId: wuse.tenant,
    });
    expect(routers.count).toBeGreaterThan(0);
    const garki = principal.assignments.find((a) => a.services.includes('payments.view'))!;
    const forbidden = await http
      .get('/vouchers/', undefined, { tenantId: garki.tenant })
      .catch((e: unknown) => e);
    expect((forbidden as ApiError).status).toBe(403);
  });

  it('agent login shape + follow-up auth/user', async () => {
    const res = await authApi.agentLogin('agent', PASSWORD);
    expect(res.agent.shop_name).toBe('Chidi Phones');
    tokenStore.set(res);
    const principal = await loadPrincipal();
    expect(principal.kind).toBe('agent');
    const pending = await authApi.agentLogin('agent2', PASSWORD).catch((e: unknown) => e);
    expect((pending as ApiError).status).toBe(403);
    expect((pending as ApiError).message).toMatch(/not active/i);
  });

  it('validation errors map to fields (register with taken username)', async () => {
    const err = await authApi
      .register({
        username: 'owner',
        email: 'owner@wuse.test',
        password: 'short',
        password_confirm: 'short',
        tenant_name: 'X',
        phone: '1',
      })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.kind).toBe('validation');
    expect(Object.keys(apiErr.fields)).toEqual(
      expect.arrayContaining(['username', 'password', 'tenant_name', 'phone']),
    );
  });

  it('idempotent command replays with Idempotency-Replayed', async () => {
    const tokens = await authApi.login('manager', PASSWORD);
    tokenStore.set(tokens);
    const plans = await http.get<Paginated<{ id: number }>>('/plans/', { page_size: 1 });
    const key = `it-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    const first = await request<unknown[]>({
      method: 'POST',
      path: '/vouchers/generate/',
      body: { plan_id: plans.results[0]!.id, quantity: 2 },
      idempotencyKey: key,
    });
    expect(first.status).toBe(201);
    expect(first.replayed).toBe(false);
    const second = await request<unknown[]>({
      method: 'POST',
      path: '/vouchers/generate/',
      body: { plan_id: plans.results[0]!.id, quantity: 2 },
      idempotencyKey: key,
    });
    expect(second.replayed).toBe(true);
    expect(second.data).toEqual(first.data);
    const conflict = await request({
      method: 'POST',
      path: '/vouchers/generate/',
      body: { plan_id: plans.results[0]!.id, quantity: 3 },
      idempotencyKey: key,
    }).catch((e: unknown) => e);
    expect((conflict as ApiError).status).toBe(409);
  });

  // Consumes the 10/min login budget — opt in with LIVE_API_THROTTLE=1 so re-runs stay green.
  it.runIf(import.meta.env.LIVE_API_THROTTLE === '1')(
    'login throttle yields 429 with Retry-After',
    async () => {
      let throttled: ApiError | null = null;
      for (let i = 0; i < 12; i += 1) {
        const err = await authApi.login('nobody', 'wrong-password').catch((e: unknown) => e);
        if (err instanceof ApiError && err.status === 429) {
          throttled = err;
          break;
        }
      }
      expect(throttled).not.toBeNull();
      expect(throttled!.kind).toBe('throttled');
      expect(throttled!.retryAfterSeconds).toBeGreaterThan(0);
    },
  );
});
