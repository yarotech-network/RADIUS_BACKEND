/**
 * Phase 7 — agent portal + public storefront against the RUNNING backend harness.
 * Run with: npm run test:integration (agent session comes from `agent/login/`, see vitest.liveSetup.ts).
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import { server } from '@/test/server';
import { asLiveUser, liveTokens } from '@/test/liveSession';
import { renderPage } from '@/test/renderPage';
import { renderWithProviders } from '@/test/render';
import { tokenStore } from '@/services/auth/tokenStore';
import { http } from '@/services/api/http';
import { loadPrincipal } from '@/services/auth/session';
import type { Principal } from '@/services/auth/principal';
import type { ApiError } from '@/services/api/errors';
import { agentPortalApi } from '@/features/agent/api';
import { storefrontApi } from '@/features/storefront/api';
import { storeSlugStore } from '@/features/agent/storeSlug';
import AgentHomePage from '@/features/agent/pages/AgentHomePage';
import AgentSellPage from '@/features/agent/pages/AgentSellPage';
import StorefrontPage from '@/features/storefront/pages/StorefrontPage';
import PaymentResultPage from '@/features/storefront/pages/PaymentResultPage';

const SLUG = 'wuse-hotspot';
const fail = (p: Promise<unknown>) =>
  p.then(
    () => null as never,
    (e: unknown) => e as ApiError,
  );

let principal: Principal;

beforeAll(async () => {
  server.close();
  tokenStore.set(liveTokens('agent'));
  principal = await loadPrincipal();
});
afterAll(() => server.listen({ onUnhandledRequest: 'error' }));

describe.runIf(import.meta.env.LIVE_API === '1')('phase 7 against live API', () => {
  it('agent session: profile, stats, wallet and history share one balance figure', async () => {
    expect(principal.kind).toBe('agent');
    const [me, stats, wallet, history] = await Promise.all([
      agentPortalApi.me(),
      agentPortalApi.stats(),
      agentPortalApi.wallet(),
      agentPortalApi.history({ page_size: 5 }),
    ]);
    expect(me.status).toBe('active');
    expect(me.wallet_balance).toBe(wallet.balance);
    expect(stats.wallet_balance).toBe(wallet.balance);
    expect(stats.total_vouchers).toBeGreaterThanOrEqual(history.count > 5 ? 5 : history.count);
    expect(history.results.every((a) => typeof a.voucher_username === 'string')).toBe(true);
    expect(history.results[0]).not.toHaveProperty('password');
  });

  it('public storefront: tenant + plans resolve for the agent tenant; unknown slug → 404; pricing is anonymous', async () => {
    tokenStore.clear();
    try {
      const tenant = await storefrontApi.tenant(SLUG);
      expect(tenant).toMatchObject({ id: 2, slug: SLUG, name: 'Wuse Hotspot' });
      const plans = await storefrontApi.plans(SLUG);
      expect(plans.results.map((p) => p.name)).toContain('Daily 1GB');
      expect(plans.results.map((p) => p.price)).toEqual(
        [...plans.results.map((p) => p.price)].sort((a, b) => a - b),
      );
      const searched = await storefrontApi.plans(SLUG, { search: 'weekly', ordering: '-price' });
      expect(searched.results.map((p) => p.name)).toEqual(['Weekly Unlimited']);
      expect((await fail(storefrontApi.tenant('nope'))).status).toBe(404);
      const pricing = await storefrontApi.pricing();
      expect(pricing.results.some((p) => p.name === 'Starter')).toBe(true);
    } finally {
      tokenStore.set(liveTokens('agent'));
    }
  });

  it('agent generate: debits wallet, returns the single access code, replays on the same Idempotency-Key, and rejects foreign plans', async () => {
    const before = await agentPortalApi.wallet();
    const key = `agent-gen-live-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    const first = await agentPortalApi.generate({ plan_id: 1, quantity: 1 }, key);
    expect(first.vouchers).toHaveLength(1);
    // tenant prefix "WH" + 8-char code from the unambiguous alphabet; the code is the password too
    expect(first.vouchers[0]!.voucher_username).toMatch(/^WH[ABCDEFGHJKMNPQRTUVWXYZ234678]{8}$/);
    expect(first.vouchers[0]!.access_code).toBe(first.vouchers[0]!.voucher_username);
    expect(first.vouchers[0]).not.toHaveProperty('voucher_password');
    const replay = await agentPortalApi.generate({ plan_id: 1, quantity: 1 }, key);
    expect(replay.vouchers[0]!.id).toBe(first.vouchers[0]!.id);
    const after = await agentPortalApi.wallet();
    expect(before.balance - after.balance).toBe(50000);

    const foreign = await fail(agentPortalApi.generate({ plan_id: 4, quantity: 1 }));
    expect(foreign.status).toBe(400);
    expect(foreign.fields.plan_id?.[0]).toMatch(/not found or inactive/i);
    const tooMany = await fail(agentPortalApi.generate({ plan_id: 1, quantity: 101 }));
    expect(tooMany.status).toBe(400);
  });

  it('agent funding: floor/ceiling validation, 503 without Paystack still records a pending top-up findable by reference', async () => {
    expect((await fail(agentPortalApi.fund({ amount: 1000 }))).fields.amount?.[0]).toMatch(/50000/);
    expect((await fail(agentPortalApi.fund({ amount: 999_999_999 }))).fields.amount?.[0]).toMatch(
      /funding limit/,
    );
    const down = await fail(agentPortalApi.fund({ amount: 100000 }));
    expect(down.status).toBe(503);
    const reference = (down.body as { reference: string }).reference;
    expect(reference).toMatch(/^agent-fund-/);
    const found = await agentPortalApi.fundings({ reference, page_size: 1 });
    expect(found.results[0]).toMatchObject({ reference, amount: 100000, status: 'pending' });
  });

  it('public checkout: buy → 503 (no Paystack) with a reference the result endpoint reports as pending; known references resolve', async () => {
    tokenStore.clear();
    try {
      const down = await fail(
        storefrontApi.buy({ plan_id: 1, email: 'buyer@example.com', name: 'Live Buyer' }),
      );
      expect(down.status).toBe(503);
      const reference = (down.body as { reference: string }).reference;
      expect(reference).toMatch(/^yarotech-/);
      expect(await storefrontApi.result(reference)).toMatchObject({
        status: 'pending',
        reference,
        voucher: null,
        access_code: null,
        code_revealed: false,
        plan: null,
      });
      // Seeded legacy voucher (separate password): username is reported, never a code.
      expect(await storefrontApi.result('PAY-FULFILLED-001')).toMatchObject({
        status: 'success',
        voucher: '2ju2AUqb',
        access_code: null,
        code_revealed: false,
        plan: { name: 'Daily 1GB' },
        tenant_name: 'Wuse Hotspot',
      });
      // Fulfilled single-code purchase (seeded by the harness): code revealed while unused.
      const fresh = await storefrontApi.result('PAY-FULFILLED-CODE-001');
      expect(fresh.status).toBe('success');
      expect(fresh.code_revealed).toBe(true);
      expect(fresh.access_code).toBe(fresh.voucher);
      expect(fresh.access_code).toMatch(/^[ABCDEFGHJKMNPQRTUVWXYZ234678]{8}$/);
      expect(fresh.customer_email_masked).toMatch(/^.•••@/);
      expect((await fail(storefrontApi.result('zzz'))).status).toBe(404);
      expect(
        (await fail(storefrontApi.buy({ plan_id: 999, email: 'x@example.com' }))).fields.plan_id,
      ).toBeTruthy();
    } finally {
      tokenStore.set(liveTokens('agent'));
    }
  });

  it('agent self-service PATCH touches only phone/shop_name; other agents are invisible; workspace endpoints stay 403', async () => {
    const me = await agentPortalApi.me();
    const updated = await agentPortalApi.updateMe(me.id, { shop_name: `${me.shop_name} ✓` });
    expect(updated.shop_name).toBe(`${me.shop_name} ✓`);
    const restored = await agentPortalApi.updateMe(me.id, { shop_name: me.shop_name });
    expect(restored.shop_name).toBe(me.shop_name);
    expect((await fail(agentPortalApi.updateMe(me.id + 1, { shop_name: 'x' }))).status).toBe(404);
    // Gap #1: the agent surface must never lean on tenant_for() endpoints such as plans/.
    expect((await fail(http.get('/plans/'))).status).toBe(403);
    // A workspace user is not an agent.
    await asLiveUser('manager', async () => {
      expect((await fail(agentPortalApi.stats())).status).toBe(403);
    });
  });

  it('pages: agent home + sell render live data; storefront + result pages work unauthenticated', async () => {
    storeSlugStore.write(SLUG);
    renderPage(<AgentHomePage />, { principal, path: '/agent' });
    expect(await screen.findByRole('heading', { name: 'Chidi' })).toBeInTheDocument();
    expect(await screen.findByText('Sold today')).toBeInTheDocument();
    expect((await screen.findAllByText(/^WH/)).length).toBeGreaterThan(0);

    const { unmount } = renderPage(<AgentSellPage />, { principal, path: '/agent/sell' });
    expect(await screen.findByRole('radio', { name: 'Daily 1GB' })).toBeInTheDocument();
    unmount();

    renderWithProviders(
      <Routes>
        <Route path="/s/:slug/*" element={<StorefrontPage />} />
        <Route path="/pay/result" element={<PaymentResultPage />} />
      </Routes>,
      { route: `/s/${SLUG}` },
    );
    expect(await screen.findByRole('heading', { name: 'Wuse Hotspot' })).toBeInTheDocument();
    const weekly = await screen.findByRole('article', { name: 'Weekly Unlimited' });
    expect(within(weekly).getByText('₦2,500.00')).toBeInTheDocument();

    renderWithProviders(<PaymentResultPage />, {
      route: '/pay/result?reference=PAY-FULFILLED-001',
    });
    expect(await screen.findByText('Payment successful')).toBeInTheDocument();
    expect(await screen.findByText('2ju2AUqb')).toBeInTheDocument();
  });
});
