/**
 * Phase 8 — platform admin console against the RUNNING backend harness (admin session).
 * Run with: npm run test:integration. Side effects are cleaned up: a probe tenant is created and
 * hard-deleted, one staff invitation is created then revoked (invitations cannot be deleted), and
 * one assignment for `pstaff1` (id 7) on tenant `garki-net` is created then revoked.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { server } from '@/test/server';
import { asLiveUser, liveTokens } from '@/test/liveSession';
import { renderPage } from '@/test/renderPage';
import { tokenStore } from '@/services/auth/tokenStore';
import { loadPrincipal } from '@/services/auth/session';
import type { Principal } from '@/services/auth/principal';
import type { ApiError } from '@/services/api/errors';
import { platformApi } from '@/features/platform/api';
import PlatformOverviewPage from '@/features/platform/pages/PlatformOverviewPage';
import TenantsPage from '@/features/platform/pages/TenantsPage';
import StaffPage from '@/features/platform/pages/StaffPage';

const fail = (p: Promise<unknown>) =>
  p.then(
    () => null as never,
    (e: unknown) => e as ApiError,
  );
const stamp = Date.now().toString(36);

let principal: Principal;

beforeAll(async () => {
  server.close();
  tokenStore.set(liveTokens('admin'));
  principal = await loadPrincipal();
});
afterAll(() => server.listen({ onUnhandledRequest: 'error' }));

describe.runIf(import.meta.env.LIVE_API === '1')('phase 8 against live API', () => {
  it('admin session sees platform stats, every tenant and the read-only fleet/money views', async () => {
    expect(principal.kind).toBe('platform_admin');
    const [stats, tenants, routers, payments, wallet, subs, audit] = await Promise.all([
      platformApi.stats(),
      platformApi.tenants({ page_size: 100 }),
      platformApi.routers({ page_size: 5 }),
      platformApi.payments({ page_size: 5 }),
      platformApi.walletPayments({ page_size: 5 }),
      platformApi.subscriptionPayments({ page_size: 5 }),
      platformApi.audit({ page_size: 5 }),
    ]);
    expect(stats.amount_unit).toBe('kobo');
    expect(stats.tenants).toBe(tenants.count);
    // The platform's own tenant is in the list and flagged.
    expect(tenants.results.some((t) => t.is_platform_admin)).toBe(true);
    expect(tenants.results.find((t) => t.slug === 'wuse-hotspot')?.member_count).toBeGreaterThan(0);
    expect(routers.results.every((r) => typeof r.tenant_name === 'string')).toBe(true);
    expect(payments.count).toBeGreaterThan(0);
    expect(Array.isArray(wallet.results)).toBe(true);
    expect(Array.isArray(subs.results)).toBe(true);
    expect(audit.count).toBeGreaterThan(0);
    // Tenant-scoped filters are honoured.
    const wuse = tenants.results.find((t) => t.slug === 'wuse-hotspot')!;
    const scoped = await platformApi.payments({ tenant: wuse.id, page_size: 100 });
    expect(scoped.results.every((p) => p.tenant === wuse.id)).toBe(true);
  });

  it('non-admin sessions are rejected by platform/* (frontend guards are UX only)', async () => {
    const owner = await asLiveUser('owner', () => fail(platformApi.stats()));
    expect(owner.status).toBe(403);
    const pstaff = await asLiveUser('pstaff', () => fail(platformApi.assignments()));
    expect(pstaff.status).toBe(403);
  });

  it('tenant lifecycle: create → patch → members guard → hard delete', async () => {
    const slug = `probe-${stamp}`;
    const created = await platformApi.createTenant({
      name: `Probe ${stamp}`,
      slug,
      email: '',
      phone: '',
      address: '',
      is_active: true,
    });
    try {
      expect(created.slug).toBe(slug);
      expect(created.member_count).toBe(0);
      const dup = await fail(
        platformApi.createTenant({
          name: 'Dup',
          slug,
          email: '',
          phone: '',
          address: '',
          is_active: true,
        }),
      );
      expect(dup.status).toBe(400);
      expect(dup.fields.slug?.[0]).toMatch(/already exists/);

      const patched = await platformApi.updateTenant(created.id, { is_active: false });
      expect(patched.is_active).toBe(false);

      // Only dedicated tenant accounts may be members; user `agent` (id 8) is an agent.
      const bad = await fail(
        platformApi.addMembership({ user: 8, tenant: created.id, role: 'staff' }),
      );
      expect(bad.status).toBe(400);
      expect(bad.fields.user?.[0]).toMatch(/dedicated tenant account/);

      const members = await platformApi.memberships({ tenant: created.id });
      expect(members.count).toBe(0);
    } finally {
      await platformApi.deleteTenant(created.id);
    }
    const gone = await fail(platformApi.tenant(created.id));
    expect(gone.status).toBe(404);
  });

  it('the last owner of a tenant is protected', async () => {
    const tenants = await platformApi.tenants({ search: 'wuse', page_size: 10 });
    const wuse = tenants.results.find((t) => t.slug === 'wuse-hotspot')!;
    const members = await platformApi.memberships({
      tenant: wuse.id,
      role: 'owner',
      page_size: 100,
    });
    if (members.count !== 1) return; // harness drift: guard only meaningful with a single owner
    const owner = members.results[0]!;
    const demote = await fail(platformApi.changeMembershipRole(owner.id, 'manager'));
    expect(demote.status).toBe(400);
    expect(demote.message).toMatch(/final tenant owner/i);
    const remove = await fail(platformApi.removeMembership(owner.id));
    expect(remove.status).toBe(400);
  });

  it('staff: invitation token is returned once, revoke is idempotent, delete is not allowed', async () => {
    const tenants = await platformApi.tenants({ search: 'garki', page_size: 10 });
    const garki = tenants.results.find((t) => t.slug === 'garki-net')!;
    const invitation = await platformApi.invite({
      email: `probe-${stamp}@example.com`,
      tenant: garki.id,
      services: ['vouchers.print'],
    });
    expect(invitation.token.length).toBeGreaterThan(20);
    expect(invitation.status).toBe('pending');
    // Retrieve/list never expose the token again.
    const listed = await platformApi.invitations({
      tenant: garki.id,
      status: 'pending',
      page_size: 100,
    });
    const row = listed.results.find((i) => i.id === invitation.id) as unknown as
      Record<string, unknown> | undefined;
    expect(row).toBeDefined();
    expect(row).not.toHaveProperty('token');

    const invalidService = await fail(
      platformApi.invite({ email: 'x@example.com', tenant: garki.id, services: ['nope' as never] }),
    );
    expect(invalidService.status).toBe(400);

    const revoked = await platformApi.revokeInvitation(invitation.id);
    expect(revoked.status).toBe('revoked');
    const again = await platformApi.revokeInvitation(invitation.id);
    expect(again.status).toBe('revoked');
  });

  it('staff: assignment create → grants patch → identity immutable → revoke', async () => {
    const tenants = await platformApi.tenants({ page_size: 100 });
    const garki = tenants.results.find((t) => t.slug === 'garki-net')!;
    const wuse = tenants.results.find((t) => t.slug === 'wuse-hotspot')!;
    // pstaff1 (id 7) already has an assignment on tenant 2 in the harness; use tenant 3 for the probe.
    const existing = await platformApi.assignments({ user: 7, tenant: garki.id, page_size: 10 });
    for (const a of existing.results) await platformApi.revokeAssignment(a.id);

    const created = await platformApi.createAssignment({
      user: 7,
      tenant: garki.id,
      services: ['routers.view'],
    });
    try {
      expect(created.is_active).toBe(true);
      const dup = await fail(
        platformApi.createAssignment({ user: 7, tenant: garki.id, services: ['routers.view'] }),
      );
      expect(dup.status).toBe(400);
      expect(dup.message).toMatch(/unique set/);

      // Member accounts cannot be staff.
      const member = await fail(
        platformApi.createAssignment({ user: 2, tenant: wuse.id, services: ['routers.view'] }),
      );
      expect(member.status).toBe(400);
      expect(member.message).toMatch(/dedicated staff account/);

      const patched = await platformApi.updateAssignment(created.id, {
        services: ['routers.view', 'payments.view'],
        is_active: false,
      });
      expect(patched.services).toEqual(['routers.view', 'payments.view']);
      expect(patched.is_active).toBe(false);
    } finally {
      await platformApi.revokeAssignment(created.id);
    }
    const after = await platformApi.assignments({ user: 7, tenant: garki.id });
    expect(after.count).toBe(0);
  });

  it('pages render live data: overview KPIs, tenant list, staff assignments', async () => {
    renderPage(<PlatformOverviewPage />, { path: '/platform', principal });
    expect(await screen.findByText(/active$/)).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Wuse Hotspot' })).toBeInTheDocument();

    renderPage(<TenantsPage />, { path: '/platform/tenants', principal });
    const table = await screen.findByRole('table', { name: 'Tenants' });
    expect(await within(table).findByText('Garki Net')).toBeInTheDocument();
    expect(within(table).queryByText('platform')).not.toBeInTheDocument();

    renderPage(<StaffPage />, { path: '/platform/staff', principal });
    const staff = await screen.findByRole('table', { name: 'Staff assignments' });
    expect((await within(staff).findAllByText('User #6')).length).toBeGreaterThan(0);
    expect(
      (await within(staff).findAllByRole('link', { name: 'Wuse Hotspot' })).length,
    ).toBeGreaterThan(0);
  });
});
