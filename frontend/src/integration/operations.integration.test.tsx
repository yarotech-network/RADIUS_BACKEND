/**
 * Phase 4 feature services against the RUNNING backend harness. Run with: npm run test:integration
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { server } from '@/test/server';
import { liveTokens } from '@/test/liveSession';
import { tokenStore } from '@/services/auth/tokenStore';
import { ApiError } from '@/services/api/errors';
import { plansApi } from '@/features/plans/api';
import { vouchersApi } from '@/features/vouchers/api';
import { dashboardApi } from '@/features/dashboard/api';
import { routersApi } from '@/features/routers/api';
import { parsePrintHtml } from '@/features/vouchers/printing';

beforeAll(() => {
  server.close();
  tokenStore.set(liveTokens('manager'));
});
afterAll(() => server.listen({ onUnhandledRequest: 'error' }));

describe.runIf(import.meta.env.LIVE_API === '1')('operations against live API', () => {
  it('plans: create → list (ordering/filter/search) → patch → delete', async () => {
    const name = `IT Plan ${Date.now()}`;
    const created = await plansApi.create({
      name,
      price: 12345,
      duration_hours: 6,
      rate_limit: '2M/4M',
      data_limit: 512,
      voucher_prefix: 'IT',
      is_active: true,
    });
    expect(created.price_display).toMatch(/₦/);
    const listed = await plansApi.list({
      page: 1,
      page_size: 100,
      search: 'IT Plan',
      ordering: '-price',
      is_active: true,
    });
    expect(listed.results.some((p) => p.id === created.id)).toBe(true);
    const patched = await plansApi.update(created.id, { is_active: false });
    expect(patched.is_active).toBe(false);
    const options = await plansApi.listAll({ activeOnly: true });
    expect(options.some((p) => p.id === created.id)).toBe(false);
    await plansApi.remove(created.id);
    const gone = await plansApi.get(created.id).catch((e: unknown) => e);
    expect((gone as ApiError).status).toBe(404);
  });

  it('vouchers: generate → list by plan/status → print parses → disable → edit/delete rules', async () => {
    const [plan] = await plansApi.listAll({ activeOnly: true });
    expect(plan).toBeDefined();
    const { vouchers, replayed } = await vouchersApi.generate({
      plan_id: plan!.id,
      quantity: 3,
      prefix: 'IT',
    });
    expect(replayed).toBe(false);
    expect(vouchers).toHaveLength(3);
    expect(vouchers[0]!.username.startsWith('IT')).toBe(true);
    expect(vouchers[0]).not.toHaveProperty('password');

    const listed = await vouchersApi.list({
      page: 1,
      page_size: 5,
      plan: plan!.id,
      status: 'unused',
      ordering: '-created_at',
    });
    expect(listed.results.map((v) => v.id)).toEqual(
      expect.arrayContaining(vouchers.map((v) => v.id)),
    );

    const parsed = parsePrintHtml(vouchers[0]!.id, await vouchersApi.printHtml(vouchers[0]!.id));
    expect(parsed?.username).toBe(vouchers[0]!.username);
    expect(parsed?.password.length).toBeGreaterThanOrEqual(8);

    const pdf = await vouchersApi.pdf(vouchers[0]!.id).catch((e: unknown) => e);
    expect(pdf instanceof Blob || (pdf instanceof ApiError && pdf.status === 503)).toBe(true);

    const updated = await vouchersApi.update(vouchers[1]!.id, { device_limit: 3 });
    expect(updated.device_limit).toBe(3);

    await vouchersApi.disable(vouchers[0]!.id);
    const disabled = await vouchersApi.get(vouchers[0]!.id);
    expect(disabled.status).toBe('disabled');
    const editDisabled = await vouchersApi
      .update(vouchers[0]!.id, { device_limit: 2 })
      .catch((e: unknown) => e);
    expect((editDisabled as ApiError).status).toBe(400);
    expect((editDisabled as ApiError).message).toMatch(/cannot be edited/i);

    await vouchersApi.remove(vouchers[2]!.id);
    const gone = await vouchersApi.get(vouchers[2]!.id).catch((e: unknown) => e);
    expect((gone as ApiError).status).toBe(404);
  });

  it('manual voucher create maps field errors', async () => {
    const [plan] = await plansApi.listAll({ activeOnly: true });
    const dup = await vouchersApi
      .createManual({ username: 'WH10000', password: 'whatever1', plan: plan!.id })
      .catch((e: unknown) => e);
    expect(dup).toBeInstanceOf(ApiError);
    expect(Object.keys((dup as ApiError).fields)).toContain('username');
  });

  it('dashboard stats + live users + router options', async () => {
    const stats = await dashboardApi.stats();
    expect(stats.amount_unit).toBe('kobo');
    expect(stats.total_vouchers).toBeGreaterThan(0);
    const live = await dashboardApi.liveUsers({ page: 1, page_size: 2 });
    expect(live.users.length).toBeLessThanOrEqual(2);
    expect(live.source).toBe('radius_accounting');
    const routers = await routersApi.listAll();
    expect(routers.length).toBeGreaterThan(0);
    if (live.users.length > 0 && routers[0]) {
      const filtered = await dashboardApi.liveUsers({
        page: 1,
        page_size: 10,
        router: routers[0].id,
      });
      expect(filtered.users.every((u) => u.router_id === routers[0]!.id)).toBe(true);
      const bad = await dashboardApi
        .liveUsers({ page: 1, page_size: 10, router: '00000000-0000-0000-0000-000000000000' })
        .catch((e: unknown) => e);
      expect((bad as ApiError).fields.router).toBeDefined();
    }
  });

  it('disconnect surfaces 503 when RADIUS CoA is unreachable (no live router in harness)', async () => {
    const live = await dashboardApi.liveUsers({ page: 1, page_size: 1 });
    if (live.users.length === 0) return;
    const res = await dashboardApi.disconnect(live.users[0]!.session_id).catch((e: unknown) => e);
    expect(
      res instanceof ApiError
        ? [503, 404].includes(res.status)
        : typeof (res as { acknowledged: boolean }).acknowledged === 'boolean',
    ).toBe(true);
  }, 20_000);
});
