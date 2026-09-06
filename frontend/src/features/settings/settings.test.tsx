import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route } from 'react-router';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type {
  SubscriptionPlan,
  TenantMembership,
  TenantProfile,
  TenantSetting,
  TenantSubscription,
} from '@/types/api';
import SettingsLayout from './pages/SettingsLayout';
import GeneralSettingsPage from './pages/GeneralSettingsPage';
import BillingSettingsPage from './pages/BillingSettingsPage';
import TeamSettingsPage from './pages/TeamSettingsPage';
import SubscriptionSettingsPage from './pages/SubscriptionSettingsPage';
import {
  billingSettingsSchema,
  profileFormToPatch,
  settingsFormToPatch,
  settingsToForm,
  tenantProfileSchema,
} from './settingsSchemas';

const profile: TenantProfile = {
  id: 5,
  name: 'Wuse Hotspot',
  slug: 'wuse-hotspot',
  phone: '+2348000000001',
  email: 'hello@wuse.ng',
  address: 'Wuse 2, Abuja',
  is_active: true,
  updated_at: '2026-09-01T10:00:00Z',
};
const setting: TenantSetting = {
  id: 1,
  tenant: 5,
  agent_commission_percent: '10.00',
  voucher_prefix: 'WH',
  max_funding_amount: 5000000,
  updated_at: '2026-09-01T10:00:00Z',
};
const member = (extra: Partial<TenantMembership> = {}): TenantMembership => ({
  id: 2,
  user: 42,
  tenant: 5,
  role: 'owner',
  user_display: 'ada',
  tenant_display: 'Wuse Hotspot',
  created_at: '2026-01-01T00:00:00Z',
  ...extra,
});
const plans: SubscriptionPlan[] = [
  {
    id: 1,
    name: 'Starter',
    price: 1500000,
    price_display: '₦15,000',
    duration_days: 30,
    features: ['1 router'],
    is_active: true,
  },
  {
    id: 2,
    name: 'Business',
    price: 4500000,
    price_display: '₦45,000',
    duration_days: 30,
    features: ['5 routers', 'Agents'],
    is_active: true,
  },
];

describe('settings schemas', () => {
  it('patches only changed profile fields', () => {
    const parsed = tenantProfileSchema.parse({
      name: 'Wuse Hotspot',
      email: 'hello@wuse.ng',
      phone: '+2348000000001',
      address: 'New address',
    });
    expect(profileFormToPatch(parsed, profile)).toEqual({ address: 'New address' });
  });
  it('never sends blank Paystack keys and converts naira to kobo', () => {
    const form = settingsToForm(setting);
    expect(form).toMatchObject({
      agent_commission_percent: '10',
      voucher_prefix: 'WH',
      max_funding_amount: '50000',
      paystack_public_key: '',
      paystack_secret_key: '',
    });
    const parsed = billingSettingsSchema.parse({
      ...form,
      max_funding_amount: '75000',
      paystack_secret_key: 'sk_test_abc',
    });
    expect(settingsFormToPatch(parsed, setting)).toEqual({
      max_funding_amount: 7500000,
      paystack_secret_key: 'sk_test_abc',
    });
    expect(
      billingSettingsSchema.safeParse({ ...form, agent_commission_percent: '120' }).success,
    ).toBe(false);
    expect(
      billingSettingsSchema.safeParse({ ...form, voucher_prefix: 'TOO-LONG-PREFIX' }).success,
    ).toBe(false);
  });
});

describe('SettingsLayout', () => {
  it('shows only the tabs the principal can use', async () => {
    server.use(http.get(`${API}/tenants/profile/`, () => HttpResponse.json(profile)));
    renderPage(<SettingsLayout />, {
      path: '/settings',
      route: '/settings',
      role: 'staff',
      extraRoutes: (
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<div>index</div>} />
        </Route>
      ),
    });
    const nav = await screen.findByRole('navigation', { name: 'Settings sections' });
    expect(within(nav).getByRole('link', { name: 'General' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Team' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Subscription' })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Billing & payouts' })).not.toBeInTheDocument();
  });
});

describe('GeneralSettingsPage', () => {
  it('saves the business profile with a partial PATCH and shows the user ID', async () => {
    const patches: Record<string, unknown>[] = [];
    server.use(
      http.get(`${API}/tenants/profile/`, () => HttpResponse.json(profile)),
      http.patch(`${API}/tenants/profile/`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        patches.push(body);
        return HttpResponse.json({ ...profile, ...body });
      }),
    );
    renderPage(<GeneralSettingsPage />, { path: '/settings/general', role: 'manager' });
    const form = await screen.findByRole('form', { name: 'Business profile' });
    const name = within(form).getByLabelText(/Business name/);
    await waitFor(() => expect(name).toHaveValue('Wuse Hotspot'));
    expect(within(form).getByRole('button', { name: 'Save changes' })).toBeDisabled();
    await userEvent.clear(name);
    await userEvent.type(name, 'Wuse Hotspot Ltd');
    await userEvent.click(within(form).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(patches).toEqual([{ name: 'Wuse Hotspot Ltd' }]));
    expect(await screen.findByText('Business profile saved')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy user ID' })).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('hides the business profile from staff and maps a wrong old password to its field', async () => {
    server.use(
      http.post(`${API}/auth/change-password/`, () =>
        HttpResponse.json({ old_password: ['Old password is incorrect.'] }, { status: 400 }),
      ),
    );
    renderPage(<GeneralSettingsPage />, { path: '/settings/general', role: 'staff' });
    expect(screen.queryByRole('form', { name: 'Business profile' })).not.toBeInTheDocument();
    const form = screen.getByRole('form', { name: 'Change password' });
    await userEvent.type(within(form).getByLabelText(/Current password/), 'wrong-old');
    await userEvent.type(within(form).getByLabelText(/^New password/), 'Str0ngPassw0rd');
    await userEvent.type(within(form).getByLabelText(/Confirm new password/), 'Str0ngPassw0rd');
    await userEvent.click(within(form).getByRole('button', { name: 'Change password' }));
    expect(await within(form).findByText('Old password is incorrect.')).toBeInTheDocument();
  });
});

describe('ChangePasswordForm', () => {
  it('re-authenticates with the new password after a successful change (tokens are revoked server-side)', async () => {
    const logins: Record<string, unknown>[] = [];
    server.use(
      http.post(`${API}/auth/change-password/`, () =>
        HttpResponse.json({ message: 'Password changed successfully.' }),
      ),
      http.post(`${API}/auth/login/`, async ({ request }) => {
        logins.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ access: 'a2', refresh: 'r2', user: {} });
      }),
    );
    const { auth } = renderPage(<GeneralSettingsPage />, {
      path: '/settings/general',
      role: 'staff',
    });
    const form = screen.getByRole('form', { name: 'Change password' });
    await userEvent.type(within(form).getByLabelText(/Current password/), 'Passw0rd!2026');
    await userEvent.type(within(form).getByLabelText(/^New password/), 'Str0ngPassw0rd');
    await userEvent.type(within(form).getByLabelText(/Confirm new password/), 'Str0ngPassw0rd');
    await userEvent.click(within(form).getByRole('button', { name: 'Change password' }));
    await waitFor(() => expect(logins).toEqual([{ username: 'ada', password: 'Str0ngPassw0rd' }]));
    await waitFor(() =>
      expect(auth.signIn).toHaveBeenCalledWith(
        expect.objectContaining({ access: 'a2', refresh: 'r2' }),
      ),
    );
    expect(auth.signOut).not.toHaveBeenCalled();
    expect(await screen.findByText('Password changed')).toBeInTheDocument();
  });
});

describe('BillingSettingsPage', () => {
  it('sends only changed fields and typed keys, never echoing stored keys', async () => {
    const patches: Record<string, unknown>[] = [];
    server.use(
      http.get(`${API}/tenants/settings/`, () => HttpResponse.json(setting)),
      http.patch(`${API}/tenants/settings/`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        patches.push(body);
        return HttpResponse.json({
          ...setting,
          voucher_prefix: String(body.voucher_prefix ?? setting.voucher_prefix),
        });
      }),
    );
    renderPage(<BillingSettingsPage />, { path: '/settings/billing', role: 'manager' });
    const form = await screen.findByRole('form', { name: 'Billing and payouts' });
    const prefix = within(form).getByLabelText(/Voucher prefix/);
    await waitFor(() => expect(prefix).toHaveValue('WH'));
    expect(within(form).getByLabelText(/Public key/)).toHaveValue('');
    await userEvent.clear(prefix);
    await userEvent.type(prefix, 'WZ');
    await userEvent.type(within(form).getByLabelText(/Secret key/), 'sk_test_new');
    await userEvent.click(within(form).getByRole('button', { name: 'Save changes' }));
    await waitFor(() =>
      expect(patches).toEqual([{ voucher_prefix: 'WZ', paystack_secret_key: 'sk_test_new' }]),
    );
    await waitFor(() => expect(within(form).getByLabelText(/Secret key/)).toHaveValue(''));
  });
});

describe('TeamSettingsPage', () => {
  it('lets owners add by user ID (sending their tenant), change roles and remove members', async () => {
    const posts: Record<string, unknown>[] = [];
    const patches: { id: string; body: Record<string, unknown> }[] = [];
    const deleted: string[] = [];
    server.use(
      http.get(`${API}/tenant-memberships/`, () =>
        HttpResponse.json(
          paginated([
            member(),
            member({ id: 3, user: 3, role: 'manager', user_display: 'manager' }),
            member({ id: 4, user: 4, role: 'staff', user_display: 'staff' }),
          ]),
        ),
      ),
      http.post(`${API}/tenant-memberships/`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        posts.push(body);
        return HttpResponse.json(
          member({ id: 7, user: 10, role: 'staff', user_display: 'nobody' }),
          { status: 201 },
        );
      }),
      http.patch(`${API}/tenant-memberships/:id/`, async ({ request, params }) => {
        const body = (await request.json()) as Record<string, unknown>;
        patches.push({ id: String(params.id), body });
        return HttpResponse.json(
          member({ id: 4, user: 4, role: 'manager', user_display: 'staff' }),
        );
      }),
      http.delete(`${API}/tenant-memberships/:id/`, ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage(<TeamSettingsPage />, { path: '/settings/team', role: 'owner' });
    const table = await screen.findByRole('table', { name: 'Team members' });
    expect(await within(table).findByText('(you)')).toBeInTheDocument();
    // sole owner cannot be demoted or removed
    expect(within(table).getByLabelText('Role for ada')).toBeDisabled();
    expect(within(table).getByRole('button', { name: 'Remove ada' })).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: 'Add member' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add team member' });
    await userEvent.type(within(dialog).getByLabelText(/User ID/), '10');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add member' }));
    await waitFor(() => expect(posts).toEqual([{ user: 10, role: 'staff', tenant: 5 }]));

    await userEvent.selectOptions(within(table).getByLabelText('Role for staff'), 'manager');
    await waitFor(() => expect(patches).toEqual([{ id: '4', body: { role: 'manager' } }]));

    await userEvent.click(within(table).getByRole('button', { name: 'Remove manager' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(deleted).toEqual(['3']));
  });

  it('shows server guard messages and is read-only for managers', async () => {
    server.use(
      http.get(`${API}/tenant-memberships/`, () =>
        HttpResponse.json(
          paginated([
            member(),
            member({ id: 3, user: 3, role: 'manager', user_display: 'manager' }),
          ]),
        ),
      ),
      http.post(`${API}/tenant-memberships/`, () =>
        HttpResponse.json(
          { user: ['tenant membership with this user already exists.'] },
          { status: 400 },
        ),
      ),
    );
    const { unmount } = renderPage(<TeamSettingsPage />, { path: '/settings/team', role: 'owner' });
    await screen.findByRole('table', { name: 'Team members' });
    await userEvent.click(screen.getByRole('button', { name: 'Add member' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add team member' });
    await userEvent.type(within(dialog).getByLabelText(/User ID/), '3');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add member' }));
    expect(await within(dialog).findByText(/already belongs to a workspace/)).toBeInTheDocument();
    unmount();

    renderPage(<TeamSettingsPage />, { path: '/settings/team', role: 'manager' });
    const table = await screen.findByRole('table', { name: 'Team members' });
    expect(await within(table).findByText('owner')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add member' })).not.toBeInTheDocument();
    expect(within(table).queryByLabelText(/Role for/)).not.toBeInTheDocument();
  });
});

describe('SubscriptionSettingsPage', () => {
  it('treats 404 as "no subscription", lists plans and handles a 503 checkout by tracking the reference', async () => {
    const posts: Record<string, unknown>[] = [];
    const paymentPolls: string[] = [];
    server.use(
      http.get(`${API}/subscriptions/`, () =>
        HttpResponse.json({ detail: 'Subscription not found.' }, { status: 404 }),
      ),
      http.get(`${API}/pricing/`, () => HttpResponse.json(paginated(plans))),
      http.post(`${API}/subscriptions/checkout/`, async ({ request }) => {
        posts.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(
          { error: 'Payment provider unavailable', reference: 'subscription-abc' },
          { status: 503 },
        );
      }),
      http.get(`${API}/subscriptions/payments/:reference/`, ({ params }) => {
        paymentPolls.push(String(params.reference));
        return HttpResponse.json({
          reference: params.reference,
          amount: 1500000,
          status: 'pending',
          plan: 1,
          subscription: null,
          created_at: '2026-09-01T10:00:00Z',
          completed_at: null,
        });
      }),
    );
    renderPage(<SubscriptionSettingsPage />, { path: '/settings/subscription', role: 'owner' });
    expect(await screen.findByText('No active subscription')).toBeInTheDocument();
    expect(await screen.findByText('Business')).toBeInTheDocument();
    const subscribe = screen.getAllByRole('button', { name: /Subscribe/ });
    expect(subscribe).toHaveLength(2);
    await userEvent.click(subscribe[0]!);
    await waitFor(() => expect(posts).toEqual([{ plan_id: 1 }]));
    expect(await screen.findByText(/payment provider is unavailable/)).toBeInTheDocument();
    expect(await screen.findByText('Waiting for Paystack')).toBeInTheDocument();
    expect(paymentPolls).toEqual(['subscription-abc']);
  });

  it('shows the current plan and hides checkout from non-owners', async () => {
    const sub: TenantSubscription = {
      id: 1,
      tenant: 5,
      plan: 2,
      plan_name: 'Business',
      status: 'active',
      started_at: '2026-08-15T00:00:00Z',
      expires_at: '2099-09-14T00:00:00Z',
      is_trial: false,
      is_expired: false,
    };
    server.use(
      http.get(`${API}/subscriptions/`, () => HttpResponse.json(sub)),
      http.get(`${API}/pricing/`, () => HttpResponse.json(paginated(plans))),
    );
    renderPage(<SubscriptionSettingsPage />, { path: '/settings/subscription', role: 'manager' });
    expect(await screen.findByText('Current')).toBeInTheDocument();
    expect(screen.getAllByText('Business').length).toBeGreaterThan(0);
    expect(
      screen.queryByRole('button', { name: /Subscribe|Renew|Switch/ }),
    ).not.toBeInTheDocument();
  });
});
