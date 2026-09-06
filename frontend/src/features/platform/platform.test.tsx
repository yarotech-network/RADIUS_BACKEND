import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route } from 'react-router';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type {
  NasDevice,
  PlatformStats,
  StaffAssignment,
  StaffInvitation,
  Tenant,
  TenantMembership,
} from '@/types/api';
import PlatformOverviewPage from './pages/PlatformOverviewPage';
import TenantsPage from './pages/TenantsPage';
import TenantDetailPage from './pages/TenantDetailPage';
import PlatformRoutersPage from './pages/PlatformRoutersPage';
import PlatformPaymentsPage from './pages/PlatformPaymentsPage';
import StaffPage from './pages/StaffPage';
import PlatformAuditPage from './pages/PlatformAuditPage';
import {
  friendlyAssignmentError,
  friendlyMemberError,
  invitationDisplayStatus,
} from './platformRules';
import { tenantFormToPatch } from './platformSchemas';
import { serviceLabel, slugify } from './platformVocabulary';

const tenant = (extra: Partial<Tenant> = {}): Tenant => ({
  id: 2,
  name: 'Wuse Hotspot',
  slug: 'wuse-hotspot',
  email: 'ops@wuse.example',
  phone: '',
  address: '',
  is_active: true,
  is_platform_admin: false,
  created_at: '2026-08-01T10:00:00Z',
  updated_at: '2026-08-02T10:00:00Z',
  member_count: 3,
  voucher_count: 87,
  ...extra,
});
const platformTenant = tenant({
  id: 1,
  name: 'Yarotech',
  slug: 'yarotech',
  is_platform_admin: true,
  member_count: 1,
  voucher_count: 0,
});
const garki = tenant({
  id: 3,
  name: 'Garki Net',
  slug: 'garki-net',
  member_count: 1,
  voucher_count: 0,
  is_active: false,
});

const stats: PlatformStats = {
  tenants: 4,
  active_tenants: 3,
  routers: 2,
  onboarded_routers: 1,
  agents: 10,
  vouchers: 87,
  successful_payment_amount: 100000,
  pending_payments: 2,
  currency: 'NGN',
  amount_unit: 'kobo',
  successful_wallet_funding_amount: 0,
  successful_subscription_amount: 0,
};

/** Default handlers for the tenant index every platform page consults. */
function tenantHandlers() {
  return [
    http.get(`${API}/tenants/`, ({ request }) => {
      const url = new URL(request.url);
      const kind = url.searchParams.get('is_platform_admin');
      const all = [platformTenant, tenant(), garki];
      const rows = kind === null ? all : all.filter((t) => String(t.is_platform_admin) === kind);
      return HttpResponse.json(paginated(rows));
    }),
    http.get(`${API}/tenants/:id/`, ({ params }) => {
      const found = [platformTenant, tenant(), garki].find((t) => String(t.id) === params.id);
      return found
        ? HttpResponse.json(found)
        : HttpResponse.json({ detail: 'Not found.' }, { status: 404 });
    }),
  ];
}

describe('platform rules + vocabulary', () => {
  it('translates backend validation strings', () => {
    expect(friendlyMemberError('tenant membership with this user already exists.')).toMatch(
      /already belongs/,
    );
    expect(friendlyMemberError('Use a dedicated tenant account for memberships.')).toMatch(
      /cannot be workspace members/,
    );
    expect(friendlyAssignmentError('The fields user, tenant must make a unique set.')).toMatch(
      /already has an assignment/,
    );
    expect(friendlyAssignmentError('Staff assignments require a dedicated staff account.')).toMatch(
      /dedicated platform-staff account/,
    );
    expect(friendlyAssignmentError('Other')).toBe('Other');
  });
  it('derives expired invitations client-side', () => {
    const now = Date.parse('2026-09-06T12:00:00Z');
    expect(
      invitationDisplayStatus({ status: 'pending', expires_at: '2026-09-01T00:00:00Z' }, now),
    ).toBe('expired');
    expect(
      invitationDisplayStatus({ status: 'pending', expires_at: '2026-09-09T00:00:00Z' }, now),
    ).toBe('pending');
    expect(
      invitationDisplayStatus({ status: 'revoked', expires_at: '2026-09-01T00:00:00Z' }, now),
    ).toBe('revoked');
  });
  it('slugifies names and labels services', () => {
    expect(slugify('  Garki Net & Sons! ')).toBe('garki-net-sons');
    expect(serviceLabel('vouchers.print')).toBe('View & print vouchers');
    expect(serviceLabel('unknown.thing')).toBe('unknown.thing');
  });
  it('diffs tenant edits into a PATCH', () => {
    const t = tenant();
    expect(
      tenantFormToPatch(t, {
        name: t.name,
        slug: t.slug,
        email: 'new@x.io',
        phone: '',
        address: '',
        is_active: false,
      }),
    ).toEqual({
      email: 'new@x.io',
      is_active: false,
    });
  });
});

describe('PlatformOverviewPage', () => {
  it('shows KPIs, revenue and newest tenants', async () => {
    server.use(
      http.get(`${API}/platform/dashboard/`, () => HttpResponse.json(stats)),
      ...tenantHandlers(),
    );
    renderPage(<PlatformOverviewPage />, { path: '/platform', role: 'platform_admin' });
    expect(await screen.findByText('3 active')).toBeInTheDocument();
    expect(screen.getByText('₦1,000.00')).toBeInTheDocument();
    expect(screen.getByText('2 pending')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Wuse Hotspot' })).toHaveAttribute(
      'href',
      '/platform/tenants/2',
    );
    // The platform's own tenant is excluded from "newest tenants".
    expect(screen.queryByRole('link', { name: 'Yarotech' })).not.toBeInTheDocument();
  });
  it('shows an error state when the stats endpoint fails', async () => {
    server.use(
      http.get(`${API}/platform/dashboard/`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
      ...tenantHandlers(),
    );
    renderPage(<PlatformOverviewPage />, { path: '/platform', role: 'platform_admin' });
    expect(await screen.findByText('Could not load platform figures')).toBeInTheDocument();
  });
});

describe('TenantsPage', () => {
  it('lists operators (hiding the platform tenant by default) and creates a tenant', async () => {
    const seen: URL[] = [];
    const bodies: unknown[] = [];
    server.use(
      http.post(`${API}/tenants/`, async ({ request }) => {
        bodies.push(await request.json());
        expect(request.headers.get('Idempotency-Key')).toMatch(/^tenant/);
        return HttpResponse.json(tenant({ id: 9, name: 'Probe WiFi', slug: 'probe-wifi' }), {
          status: 201,
        });
      }),
      http.get(`${API}/tenants/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(paginated([tenant(), garki]));
      }),
    );
    renderPage(<TenantsPage />, {
      path: '/platform/tenants',
      role: 'platform_admin',
      extraRoutes: <Route path="/platform/tenants/:id" element={<div>detail page</div>} />,
    });
    const table = await screen.findByRole('table', { name: 'Tenants' });
    expect(await within(table).findByText('Wuse Hotspot')).toBeInTheDocument();
    expect(seen[0]?.searchParams.get('is_platform_admin')).toBe('false');

    await userEvent.click(screen.getByRole('button', { name: 'New tenant' }));
    const form = await screen.findByRole('form', { name: 'New tenant' });
    await userEvent.type(within(form).getByLabelText(/^Business name/), 'Probe WiFi');
    // slug suggested from the name
    expect(within(form).getByLabelText(/^Storefront slug/)).toHaveValue('probe-wifi');
    await userEvent.click(within(form).getByRole('button', { name: 'Create tenant' }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ name: 'Probe WiFi', slug: 'probe-wifi', is_active: true });
    expect(await screen.findByText('detail page')).toBeInTheDocument();
  });

  it('maps slug conflicts onto the field', async () => {
    server.use(
      http.post(`${API}/tenants/`, () =>
        HttpResponse.json(
          {
            problem: {
              code: 'validation_error',
              message: 'Invalid input.',
              fields: { slug: ['tenant with this slug already exists.'] },
            },
          },
          { status: 400 },
        ),
      ),
      http.get(`${API}/tenants/`, () => HttpResponse.json(paginated([tenant()]))),
    );
    renderPage(<TenantsPage />, { path: '/platform/tenants', role: 'platform_admin' });
    await userEvent.click(await screen.findByRole('button', { name: 'New tenant' }));
    const form = await screen.findByRole('form', { name: 'New tenant' });
    await userEvent.type(within(form).getByLabelText(/^Business name/), 'Wuse Hotspot');
    await userEvent.click(within(form).getByRole('button', { name: 'Create tenant' }));
    expect(
      await within(form).findByText('tenant with this slug already exists.'),
    ).toBeInTheDocument();
  });
});

describe('TenantDetailPage', () => {
  it('shows the profile, toggles activation and deletes with typed confirmation', async () => {
    const patches: unknown[] = [];
    let deleted = false;
    server.use(
      ...tenantHandlers(),
      http.patch(`${API}/tenants/2/`, async ({ request }) => {
        const body = (await request.json()) as Partial<Tenant>;
        patches.push(body);
        return HttpResponse.json(tenant({ ...body }));
      }),
      http.delete(`${API}/tenants/2/`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage(<TenantDetailPage />, {
      path: '/platform/tenants/:id',
      route: '/platform/tenants/2',
      role: 'platform_admin',
      extraRoutes: <Route path="/platform/tenants" element={<div>tenant list</div>} />,
    });
    expect(await screen.findByRole('heading', { name: 'Wuse Hotspot' })).toBeInTheDocument();
    expect(screen.getByText('ops@wuse.example')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^Routers/ })).toHaveAttribute(
      'href',
      '/platform/routers?tenant=2',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Deactivate tenant' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Deactivate' }));
    await waitFor(() => expect(patches).toEqual([{ is_active: false }]));

    await userEvent.click(screen.getByRole('button', { name: 'Delete tenant' }));
    const confirm = await screen.findByRole('button', { name: 'Delete permanently' });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/wuse-hotspot/), 'wuse-hotspot');
    await userEvent.click(confirm);
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText('tenant list')).toBeInTheDocument();
  });

  it('renders not-found for unknown ids', async () => {
    server.use(...tenantHandlers());
    renderPage(<TenantDetailPage />, {
      path: '/platform/tenants/:id',
      route: '/platform/tenants/999',
      role: 'platform_admin',
    });
    expect(await screen.findByText('Tenant not found')).toBeInTheDocument();
  });

  it('manages members: add, guard the last owner, remove', async () => {
    const member = (extra: Partial<TenantMembership>): TenantMembership => ({
      id: 1,
      user: 2,
      user_display: 'owner (owner@example.com)',
      tenant: 2,
      tenant_display: 'Wuse Hotspot',
      role: 'owner',
      created_at: '2026-08-01T00:00:00Z',
      ...extra,
    });
    const posts: unknown[] = [];
    server.use(
      ...tenantHandlers(),
      http.get(`${API}/tenant-memberships/`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('tenant')).toBe('2');
        return HttpResponse.json(
          paginated([
            member({}),
            member({ id: 2, user: 3, user_display: 'manager (m@example.com)', role: 'manager' }),
          ]),
        );
      }),
      http.post(`${API}/tenant-memberships/`, async ({ request }) => {
        posts.push(await request.json());
        return HttpResponse.json(
          member({ id: 3, user: 10, user_display: 'nobody (n@example.com)', role: 'staff' }),
          { status: 201 },
        );
      }),
    );
    renderPage(<TenantDetailPage />, {
      path: '/platform/tenants/:id',
      route: '/platform/tenants/2?tab=members',
      role: 'platform_admin',
    });
    const table = await screen.findByRole('table', { name: 'Members of Wuse Hotspot' });
    expect(await within(table).findByText('owner (owner@example.com)')).toBeInTheDocument();
    // sole owner: role select + remove button disabled
    expect(within(table).getByLabelText('Role for owner (owner@example.com)')).toBeDisabled();
    expect(
      within(table).getByRole('button', { name: 'Remove owner (owner@example.com)' }),
    ).toBeDisabled();
    expect(
      within(table).getByRole('button', { name: 'Remove manager (m@example.com)' }),
    ).toBeEnabled();

    await userEvent.click(screen.getAllByRole('button', { name: 'Add member' })[0]!);
    const form = await screen.findByRole('form', { name: 'Add member' });
    await userEvent.type(within(form).getByLabelText(/^User ID/), '10');
    await userEvent.click(within(form).getByRole('button', { name: 'Add member' }));
    await waitFor(() => expect(posts).toEqual([{ user: 10, tenant: 2, role: 'staff' }]));
  });
});

describe('PlatformRoutersPage', () => {
  it('lists the fleet with tenant links and forwards the tenant filter', async () => {
    const seen: URL[] = [];
    const router: NasDevice = {
      id: 'r-1',
      name: 'Wuse Core',
      ip_address: '10.0.0.1',
      secret: '',
      location: 'Wuse',
      wireguard_ip: null,
      wireguard_public_key: null,
      routeros_username: null,
      tenant: 2,
      tenant_name: 'Wuse Hotspot',
      onboarding_state: 'active',
      deployment_status: 'deployed',
      is_active: true,
      last_seen_at: null,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    } as unknown as NasDevice;
    server.use(
      ...tenantHandlers(),
      http.get(`${API}/platform/routers/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(paginated([router]));
      }),
    );
    renderPage(<PlatformRoutersPage />, {
      path: '/platform/routers',
      route: '/platform/routers?tenant=2',
      role: 'platform_admin',
    });
    const table = await screen.findByRole('table', { name: 'Router fleet' });
    expect(await within(table).findByText('Wuse Core')).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'Wuse Hotspot' })).toHaveAttribute(
      'href',
      '/platform/tenants/2',
    );
    expect(seen[0]?.searchParams.get('tenant')).toBe('2');
    expect(await screen.findByLabelText('Tenant')).toHaveValue('2');
  });
});

describe('PlatformPaymentsPage', () => {
  it('switches between voucher, wallet and subscription sources', async () => {
    const calls: string[] = [];
    server.use(
      ...tenantHandlers(),
      http.get(`${API}/pricing/`, () =>
        HttpResponse.json(paginated([{ id: 1, name: 'Starter', price: 1500000, is_active: true }])),
      ),
      http.get(`${API}/platform/payments/`, () => {
        calls.push('vouchers');
        return HttpResponse.json(
          paginated([
            {
              id: 1,
              reference: 'PAY-1',
              amount: 50000,
              status: 'success',
              tenant: 2,
              plan: 1,
              voucher_username: '2ju2AUqb',
              customer_email: 'c@example.com',
              customer_phone: '',
              created_at: '2026-09-01T00:00:00Z',
              paid_at: '2026-09-01T00:00:00Z',
            },
          ]),
        );
      }),
      http.get(`${API}/platform/wallet-payments/`, ({ request }) => {
        calls.push('wallet');
        expect(new URL(request.url).searchParams.get('wallet__agent__tenant')).toBe('2');
        return HttpResponse.json(
          paginated([
            {
              id: 5,
              reference: 'WAL-5',
              amount: 200000,
              status: 'pending',
              created_at: '2026-09-01T00:00:00Z',
              completed_at: null,
              tenant_id: 2,
              agent_id: 1,
            },
          ]),
        );
      }),
      http.get(`${API}/platform/subscription-payments/`, () => {
        calls.push('subscriptions');
        return HttpResponse.json(
          paginated([
            {
              id: 7,
              tenant: 3,
              reference: 'SUB-7',
              amount: 1500000,
              status: 'success',
              plan: 1,
              subscription: 1,
              created_at: '2026-09-01T00:00:00Z',
              completed_at: '2026-09-01T00:00:00Z',
            },
          ]),
        );
      }),
    );
    renderPage(<PlatformPaymentsPage />, {
      path: '/platform/payments',
      route: '/platform/payments?tenant=2',
      role: 'platform_admin',
    });
    const vouchers = await screen.findByRole('table', { name: 'Voucher sales' });
    expect(await within(vouchers).findByText('PAY-1')).toBeInTheDocument();
    expect(within(vouchers).getByText('₦500.00')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Agent wallet top-ups' }));
    const wallet = await screen.findByRole('table', { name: 'Agent wallet top-ups' });
    expect(await within(wallet).findByText('WAL-5')).toBeInTheDocument();
    expect(within(wallet).getByText('Agent #1')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Subscriptions' }));
    const subs = await screen.findByRole('table', { name: 'Subscription payments' });
    expect(await within(subs).findByText('SUB-7')).toBeInTheDocument();
    expect(await within(subs).findByText('Starter')).toBeInTheDocument();
    expect(calls).toEqual(['vouchers', 'wallet', 'subscriptions']);
  });
});

describe('StaffPage', () => {
  const assignment: StaffAssignment = {
    id: 1,
    user: 6,
    tenant: 2,
    services: ['routers.view', 'payments.view'],
    is_active: true,
    created_at: '2026-08-01T00:00:00Z',
  };
  const invitation: StaffInvitation = {
    id: 'inv-1',
    email: 'newstaff@example.com',
    tenant: 3,
    services: ['vouchers.print'],
    expires_at: '2099-01-01T00:00:00Z',
    status: 'pending',
    created_at: '2026-09-01T00:00:00Z',
  };

  it('lists assignments, edits grants and creates an invitation showing the one-time link', async () => {
    const patches: unknown[] = [];
    const invites: unknown[] = [];
    server.use(
      ...tenantHandlers(),
      http.get(`${API}/platform/staff-assignments/`, () =>
        HttpResponse.json(paginated([assignment])),
      ),
      http.patch(`${API}/platform/staff-assignments/1/`, async ({ request }) => {
        const body = (await request.json()) as Partial<StaffAssignment>;
        patches.push(body);
        return HttpResponse.json({ ...assignment, ...body });
      }),
      http.get(`${API}/platform/staff-invitations/`, () =>
        HttpResponse.json(paginated([invitation])),
      ),
      http.post(`${API}/platform/staff-invitations/`, async ({ request }) => {
        invites.push(await request.json());
        return HttpResponse.json(
          { ...invitation, id: 'inv-2', email: 'x@example.com', tenant: 2, token: 'SECRET-TOKEN' },
          { status: 201 },
        );
      }),
    );
    renderPage(<StaffPage />, { path: '/platform/staff', role: 'platform_admin' });
    const table = await screen.findByRole('table', { name: 'Staff assignments' });
    expect(await within(table).findByText('User #6')).toBeInTheDocument();
    expect(within(table).getByText('View routers')).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'Wuse Hotspot' })).toHaveAttribute(
      'href',
      '/platform/tenants/2',
    );

    await userEvent.click(within(table).getByRole('button', { name: 'Edit grants for user 6' }));
    const grants = await screen.findByRole('form', { name: 'Edit grants' });
    expect(within(grants).getByRole('checkbox', { name: /^View routers/ })).toBeChecked();
    await userEvent.click(within(grants).getByRole('checkbox', { name: /^Run RADIUS tests/ }));
    await userEvent.click(within(grants).getByRole('button', { name: 'Save grants' }));
    await waitFor(() =>
      expect(patches).toEqual([{ services: ['routers.view', 'routers.test', 'payments.view'] }]),
    );

    await userEvent.click(screen.getByRole('button', { name: 'Invite staff' }));
    const invite = await screen.findByRole('form', { name: 'Invite staff' });
    await userEvent.click(within(invite).getByRole('button', { name: 'Create invitation' }));
    expect(await within(invite).findByText('Enter a valid email address')).toBeInTheDocument();
    expect(within(invite).getByText('Pick at least one service')).toBeInTheDocument();
    await userEvent.type(within(invite).getByLabelText(/^Email/), 'x@example.com');
    await userEvent.selectOptions(within(invite).getByLabelText(/^Tenant/), '2');
    await userEvent.click(within(invite).getByRole('checkbox', { name: /^View & print vouchers/ }));
    await userEvent.click(within(invite).getByRole('button', { name: 'Create invitation' }));
    await waitFor(() =>
      expect(invites).toEqual([
        { email: 'x@example.com', tenant: 2, services: ['vouchers.print'] },
      ]),
    );
    expect(await screen.findByText('This link is shown once')).toBeInTheDocument();
    expect(screen.getByLabelText('Invitation link')).toHaveValue(
      `${window.location.origin}/accept-invitation?token=SECRET-TOKEN`,
    );
  });

  it('lists invitations and revokes a pending one', async () => {
    let revoked = false;
    server.use(
      ...tenantHandlers(),
      http.get(`${API}/platform/staff-assignments/`, () => HttpResponse.json(paginated([]))),
      http.get(`${API}/platform/staff-invitations/`, () =>
        HttpResponse.json(
          paginated([
            invitation,
            {
              ...invitation,
              id: 'inv-old',
              email: 'old@example.com',
              expires_at: '2020-01-01T00:00:00Z',
            },
          ]),
        ),
      ),
      http.post(`${API}/platform/staff-invitations/inv-1/revoke/`, () => {
        revoked = true;
        return HttpResponse.json({ ...invitation, status: 'revoked' });
      }),
    );
    renderPage(<StaffPage />, {
      path: '/platform/staff',
      route: '/platform/staff?view=invitations',
      role: 'platform_admin',
    });
    const table = await screen.findByRole('table', { name: 'Staff invitations' });
    expect(await within(table).findByText('newstaff@example.com')).toBeInTheDocument();
    expect(within(table).getByText('Expired')).toBeInTheDocument();
    await userEvent.click(
      within(table).getByRole('button', { name: 'Revoke invitation for newstaff@example.com' }),
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Revoke invitation' }));
    await waitFor(() => expect(revoked).toBe(true));
  });
});

describe('PlatformAuditPage', () => {
  it('shows tenant names, platform-level events and forwards the tenant filter', async () => {
    const seen: URL[] = [];
    server.use(
      ...tenantHandlers(),
      http.get(`${API}/platform/audit-events/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(
          paginated([
            {
              id: 'e1',
              tenant: 2,
              actor: 1,
              action: 'nasdevice.created',
              resource: 'routers.nasdevice:r-1',
              details: {},
              created_at: '2026-09-01T00:00:00Z',
            },
            {
              id: 'e2',
              tenant: 3,
              actor: 42,
              action: 'staff.invited',
              resource: 'accounts.staffinvitation:inv-1',
              details: { email: 'x' },
              created_at: '2026-09-01T00:00:00Z',
            },
          ]),
        );
      }),
    );
    renderPage(<PlatformAuditPage />, {
      path: '/platform/audit',
      route: '/platform/audit?tenant=3',
      role: 'platform_admin',
    });
    const table = await screen.findByRole('table', { name: 'Audit events' });
    expect(await within(table).findByText('Router added')).toBeInTheDocument();
    expect(await within(table).findByRole('link', { name: 'Garki Net' })).toHaveAttribute(
      'href',
      '/platform/tenants/3',
    );
    expect(within(table).getByRole('link', { name: 'staffinvitation #inv-1' })).toHaveAttribute(
      'href',
      '/platform/staff?view=invitations',
    );
    expect(within(table).getByText('You')).toBeInTheDocument();
    expect(seen[0]?.searchParams.get('tenant')).toBe('3');
  });
});
