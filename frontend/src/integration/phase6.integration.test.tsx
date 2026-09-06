/**
 * Phase 6 feature services (payments, recovery, audit, settings, team, subscription)
 * against the RUNNING backend harness. Run with: npm run test:integration
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { server } from '@/test/server';
import { asLiveUser, liveTokens } from '@/test/liveSession';
import { tokenStore } from '@/services/auth/tokenStore';
import type { ApiError } from '@/services/api/errors';
import { paymentsApi } from '@/features/payments/api';
import { auditApi } from '@/features/audit/api';
import { settingsApi } from '@/features/settings/api';
import { accountApi, authApi } from '@/features/auth/api';
import { canDeliver, needsAttention } from '@/features/payments/paymentRules';
import { actionLabel, parseResource } from '@/features/audit/auditVocabulary';

const PASSWORD = 'Passw0rd!2026';
const OWNER_TENANT = 2;

const fail = (p: Promise<unknown>) =>
  p.then(
    () => null as never,
    (e: unknown) => e as ApiError,
  );

beforeAll(() => {
  server.close();
  tokenStore.set(liveTokens('owner'));
});
afterAll(() => server.listen({ onUnhandledRequest: 'error' }));

describe.runIf(import.meta.env.LIVE_API === '1')('phase 6 against live API', () => {
  it('payments: list/filter/search/detail; staff can read transactions but not the recovery board', async () => {
    const all = await paymentsApi.list({ page_size: 50, ordering: '-created_at' });
    expect(all.count).toBeGreaterThanOrEqual(5);
    const success = await paymentsApi.list({ status: 'success' });
    expect(success.results.every((p) => p.status === 'success')).toBe(true);
    const searched = await paymentsApi.list({ search: 'PAY-FULFILLED-001' });
    expect(searched.results.map((p) => p.reference)).toContain('PAY-FULFILLED-001');
    const fulfilled = searched.results.find((p) => p.reference === 'PAY-FULFILLED-001')!;
    const detail = await paymentsApi.get(fulfilled.id);
    expect(detail.voucher_username).toBeTruthy();

    await asLiveUser('staff', async () => {
      expect((await paymentsApi.list({})).count).toBeGreaterThan(0);
      expect((await fail(paymentsApi.recoveryList({}))).status).toBe(403);
      expect((await fail(auditApi.list({}))).status).toBe(403);
    });
  });

  it('recovery: board rows carry fulfilment/delivery; retry → 503 (no Paystack), deliver honours the 409 guards and 202 idempotency', async () => {
    const board = await paymentsApi.recoveryList({ page_size: 50 });
    const unfulfilled = board.results.find((r) => r.reference === 'PAY-UNFULFILLED-002')!;
    const fulfilled = board.results.find((r) => r.reference === 'PAY-FULFILLED-001')!;
    expect(needsAttention(unfulfilled)).toBe(true);
    expect(canDeliver(fulfilled)).toBe(true);
    expect(canDeliver(unfulfilled)).toBe(false);

    const retry = await fail(paymentsApi.retry(unfulfilled.id));
    expect(retry.status).toBe(503);
    expect(retry.message).toMatch(/verification unavailable/i);

    const notFulfilled = await fail(paymentsApi.deliver(unfulfilled.id, {}));
    expect(notFulfilled.status).toBe(409);
    expect(notFulfilled.message).toMatch(/Only fulfilled payments/);

    let deliveries = await paymentsApi.deliveries({ payment: fulfilled.id });
    if (deliveries.results.length === 0) {
      // Fresh harness: the seeded payment was fulfilled outside the purchase flow, so queue once.
      expect(['pending', 'sending']).toContain(
        (await paymentsApi.deliver(fulfilled.id, {})).status,
      );
      deliveries = await paymentsApi.deliveries({ payment: fulfilled.id });
    }
    expect(deliveries.results.length).toBeGreaterThan(0);
    const latest = deliveries.results[0]!;
    if (latest.status === 'pending' || latest.status === 'sending') {
      // A live delivery is returned as-is (202) — no duplicate created.
      const again = await paymentsApi.deliver(fulfilled.id, {});
      expect(again.id).toBe(latest.id);
    } else {
      const needsAck = await fail(paymentsApi.deliver(fulfilled.id, {}));
      expect(needsAck.status).toBe(409);
      expect(needsAck.message).toMatch(/acknowledge/i);
      const queued = await paymentsApi.deliver(fulfilled.id, { acknowledge_duplicate_risk: true });
      expect(['pending', 'sending']).toContain(queued.status);
    }
  });

  it('audit: filters by action/actor and searches by resource; events parse into links', async () => {
    const page = await auditApi.list({ ordering: '-created_at', page_size: 20 });
    expect(page.count).toBeGreaterThan(0);
    const generated = await auditApi.list({ action: 'vouchers.generated' });
    expect(generated.results.every((e) => e.action === 'vouchers.generated')).toBe(true);
    const first = generated.results[0];
    if (first) {
      expect(parseResource(first.resource)?.model).toBe('voucher');
      expect(actionLabel(first.action)).toBe('Vouchers generated');
      const byActor = await auditApi.list({ actor: first.actor ?? 0 });
      expect(byActor.results.every((e) => e.actor === first.actor)).toBe(true);
    }
    const searched = await auditApi.list({ search: 'voucher' });
    expect(searched.results.every((e) => e.resource.includes('voucher'))).toBe(true);
  });

  it('settings: profile and billing PATCH round-trip; Paystack keys are accepted but never echoed', async () => {
    const profile = await settingsApi.profile();
    const marker = `Integration ${Date.now()}`;
    const updated = await settingsApi.updateProfile({ address: marker });
    expect(updated.address).toBe(marker);
    expect(updated.slug).toBe(profile.slug);
    await settingsApi.updateProfile({ address: profile.address });

    const settings = await settingsApi.settings();
    expect(settings).not.toHaveProperty('paystack_secret_key');
    const saved = await settingsApi.updateSettings({
      paystack_public_key: 'pk_test_integration',
      voucher_prefix: settings.voucher_prefix,
    });
    expect(saved).not.toHaveProperty('paystack_public_key');
    expect(saved.voucher_prefix).toBe(settings.voucher_prefix);
    const bad = await fail(settingsApi.updateSettings({ agent_commission_percent: '150' }));
    expect(bad.status).toBe(400);
    expect(bad.fieldMessage('agent_commission_percent')).toBeTruthy();

    // manager may edit settings; staff may not
    await asLiveUser('staff', async () =>
      expect((await fail(settingsApi.settings())).status).toBe(403),
    );
  });

  it('team: owner adds/changes/removes a member (tenant required in body); last-owner guard; manager is read-only', async () => {
    const before = await settingsApi.memberships({ page_size: 50 });
    expect(before.results.some((m) => m.role === 'owner')).toBe(true);
    const owner = before.results.find((m) => m.role === 'owner')!;

    const missingTenant = await fail(settingsApi.addMember({ user: 10, role: 'staff' } as never));
    expect(missingTenant.status).toBe(400);
    expect(missingTenant.fieldMessage('tenant')).toMatch(/required/);

    const added = await settingsApi.addMember({ user: 10, role: 'staff', tenant: OWNER_TENANT });
    expect(added.role).toBe('staff');
    try {
      const promoted = await settingsApi.changeRole(added.id, 'manager');
      expect(promoted.role).toBe('manager');
      const managers = await settingsApi.memberships({ role: 'manager', page_size: 50 });
      expect(managers.results.some((m) => m.id === added.id)).toBe(true);

      const duplicate = await fail(
        settingsApi.addMember({ user: 10, role: 'staff', tenant: OWNER_TENANT }),
      );
      expect(duplicate.status).toBe(400);
      expect(duplicate.fieldMessage('user')).toMatch(/already exists/);

      const lastOwner = await fail(settingsApi.changeRole(owner.id, 'manager'));
      expect(lastOwner.status).toBe(400);
      expect(lastOwner.message).toMatch(/final tenant owner/);

      await asLiveUser('manager', async () => {
        expect((await settingsApi.memberships({})).count).toBeGreaterThan(0);
        expect((await fail(settingsApi.changeRole(added.id, 'staff'))).status).toBe(403);
      });
    } finally {
      await settingsApi.removeMember(added.id);
    }
    const after = await settingsApi.memberships({ page_size: 50 });
    expect(after.results.some((m) => m.id === added.id)).toBe(false);
  });

  it('subscription: 404 when none, pricing lists active plans, checkout → 503 with a trackable pending reference (owner-only)', async () => {
    const none = await fail(settingsApi.subscription());
    expect(none.status).toBe(404);
    const pricing = await settingsApi.pricing();
    expect(pricing.results.length).toBeGreaterThan(0);
    const plan = pricing.results[0]!;

    const checkout = await fail(settingsApi.checkout({ plan_id: plan.id }));
    expect(checkout.status).toBe(503);
    const reference = (checkout.body as { reference?: string } | null)?.reference;
    expect(reference).toMatch(/^subscription-/);
    const payment = await settingsApi.subscriptionPayment(reference!);
    expect(payment.status).toBe('pending');
    expect(payment.plan).toBe(plan.id);

    await asLiveUser('manager', async () =>
      expect((await fail(settingsApi.checkout({ plan_id: plan.id }))).status).toBe(403),
    );
  });

  it('account: wrong current password is a field error; a real change round-trips', async () => {
    const wrong = await fail(
      accountApi.changePassword({ old_password: 'nope', new_password: 'Another!Pass2026' }),
    );
    expect(wrong.status).toBe(400);
    expect(wrong.fieldMessage('old_password')).toMatch(/incorrect/i);
    await asLiveUser('nobody', async () => {
      const temp = 'Temp!Pass2026xyz';
      await accountApi.changePassword({ old_password: PASSWORD, new_password: temp });
      // SimpleJWT CHECK_REVOKE_TOKEN: every token issued before the change is now rejected (401),
      // which is why the settings form re-authenticates with the new password right away.
      const stale = await fail(
        accountApi.changePassword({ old_password: temp, new_password: PASSWORD }),
      );
      expect(stale.status).toBe(401);
      tokenStore.set(await authApi.login('nobody', temp));
      await accountApi.changePassword({ old_password: temp, new_password: PASSWORD });
    });
  });
});
