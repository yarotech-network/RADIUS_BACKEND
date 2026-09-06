import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route } from 'react-router';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type { NasDevice, RouterOperation } from '@/types/api';
import RoutersPage from './RoutersPage';
import RouterDetailPage from './RouterDetailPage';
import NewRouterPage from './NewRouterPage';

const router = (extra: Partial<NasDevice> = {}): NasDevice => ({
  id: 'd856aee7-5ca8-471f-ad58-9250e94f8e44',
  name: 'mikrotik-wuse-01',
  ip_address: '10.100.100.12',
  wireguard_ip: null,
  wireguard_public_key: '',
  wireguard_port: 51820,
  routeros_username: '',
  location: 'Wuse 2',
  tenant: 5,
  tenant_name: 'Wuse Hotspot',
  onboarding_state: 'waiting_for_vpn',
  deployment_status: 'not_deployed',
  is_active: true,
  last_seen_at: null,
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-02T10:00:00Z',
  ...extra,
});
const emptyDetailEndpoints = (r: NasDevice) => [
  http.get(`${API}/routers/:id/`, () => HttpResponse.json(r)),
  http.get(`${API}/routers/:id/checks/`, () => HttpResponse.json([])),
  http.get(`${API}/routers/:id/health/`, () =>
    HttpResponse.json({
      router: r.id,
      is_active: true,
      onboarding_state: r.onboarding_state,
      deployment_status: r.deployment_status,
      last_seen_at: null,
      observed_at: '2026-09-02T10:00:00Z',
      checks: [],
      online: null,
      telemetry_available: false,
    }),
  ),
  http.get(`${API}/routers/:id/audit/`, () => HttpResponse.json(paginated([]))),
  http.get(`${API}/router-operations/`, () => HttpResponse.json(paginated([]))),
];

describe('RoutersPage', () => {
  it('lists routers with state badges and forwards filters to the API', async () => {
    const seen: URL[] = [];
    server.use(
      http.get(`${API}/routers/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(
          paginated([
            router(),
            router({
              id: 'r2',
              name: 'mikrotik-wuse-02',
              onboarding_state: 'active',
              deployment_status: 'deployed',
            }),
          ]),
        );
      }),
    );
    renderPage(<RoutersPage />, { path: '/routers' });
    const table = await screen.findByRole('table', { name: 'Routers' });
    expect(await within(table).findByText('mikrotik-wuse-01')).toBeInTheDocument();
    expect(within(table).getByText('mikrotik-wuse-02')).toBeInTheDocument();
    expect(within(table).getByText('Waiting for VPN')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Onboarding state'), 'active');
    await waitFor(() => expect(seen.at(-1)?.searchParams.get('onboarding_state')).toBe('active'));
    expect(seen[0]?.searchParams.get('ordering')).toBe('name');
  });

  it('hides management actions from staff', async () => {
    server.use(http.get(`${API}/routers/`, () => HttpResponse.json(paginated([router()]))));
    renderPage(<RoutersPage />, { path: '/routers', role: 'staff' });
    await screen.findByRole('table', { name: 'Routers' });
    expect(screen.queryByRole('link', { name: /add router/i })).not.toBeInTheDocument();
  });
});

describe('RouterDetailPage', () => {
  it('shows only the transitions the state machine allows and applies one', async () => {
    let current = router();
    const posted: unknown[] = [];
    server.use(
      // Overrides must precede the defaults: MSW uses the first matching handler.
      http.get(`${API}/routers/:id/`, () => HttpResponse.json(current)),
      http.post(`${API}/routers/:id/transition/`, async ({ request }) => {
        const body = (await request.json()) as { to_state: NasDevice['onboarding_state'] };
        posted.push(body);
        current = router({ onboarding_state: body.to_state });
        return HttpResponse.json({ correlation_id: 'c1' });
      }),
      ...emptyDetailEndpoints(current),
    );
    renderPage(<RouterDetailPage />, { path: '/routers/:id', route: `/routers/${current.id}` });
    await screen.findByRole('heading', { name: /mikrotik-wuse-01/ });
    expect(await screen.findByText('Telemetry not available')).toBeInTheDocument();
    // waiting_for_vpn → [vpn_failed, testing_radius]
    expect(screen.getByRole('button', { name: /Mark as Testing RADIUS/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Record VPN failed/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Mark as Active/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Mark as Testing RADIUS/ }));
    await waitFor(() => expect(posted).toEqual([{ to_state: 'testing_radius' }]));
    await screen.findByRole('button', { name: /Mark as Active/ });
  });

  it('surfaces a 409 from provisioning as a busy notice and shows the operation list', async () => {
    const r = router({ wireguard_ip: '10.100.100.12', wireguard_public_key: 'a'.repeat(43) + '=' });
    const op: RouterOperation = {
      id: 'op-1',
      router: r.id,
      action: 'provision',
      status: 'failed',
      attempts: 3,
      error_code: 'ssh_unreachable',
      created_at: '2026-09-02T10:00:00Z',
      completed_at: '2026-09-02T10:05:00Z',
    };
    server.use(
      http.get(`${API}/router-operations/`, () => HttpResponse.json(paginated([op]))),
      http.post(`${API}/routers/:id/provisioning/`, () =>
        HttpResponse.json({ error: 'A router operation is already pending.' }, { status: 409 }),
      ),
      ...emptyDetailEndpoints(r),
    );
    renderPage(<RouterDetailPage />, { path: '/routers/:id', route: `/routers/${r.id}?tab=vpn` });
    expect(await screen.findByText('ssh_unreachable')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Provision' }));
    expect(await screen.findByText(/already pending/)).toBeInTheDocument();
  });

  it('prompts to reload when secrets replacement hits a stale version (409)', async () => {
    const r = router();
    server.use(
      http.post(`${API}/routers/:id/replace-secrets/`, () =>
        HttpResponse.json(
          { error: 'Router changed; reload before replacing secrets.' },
          { status: 409 },
        ),
      ),
      ...emptyDetailEndpoints(r),
    );
    renderPage(<RouterDetailPage />, {
      path: '/routers/:id',
      route: `/routers/${r.id}?tab=secrets`,
    });
    await userEvent.click(await screen.findByRole('button', { name: /Replace secrets/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Replace secrets' });
    await userEvent.type(
      within(dialog).getByLabelText(/New RADIUS shared secret/),
      'brand-new-secret',
    );
    await userEvent.type(within(dialog).getByLabelText(/Your password/), 'Passw0rd!2026');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Replace secrets' }));
    expect(await within(dialog).findByText(/changed since you opened it/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Reload router' })).toBeInTheDocument();
  });

  it('shows the RADIUS test outcome and handles the service being down', async () => {
    const r = router();
    let calls = 0;
    server.use(
      http.post(`${API}/routers/:id/test/`, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ passed: false })
          : HttpResponse.json(
              { error: 'RADIUS authentication service unavailable.' },
              { status: 503 },
            );
      }),
      ...emptyDetailEndpoints(r),
    );
    renderPage(<RouterDetailPage />, { path: '/routers/:id', route: `/routers/${r.id}?tab=test` });
    await userEvent.type(await screen.findByLabelText(/Username/), 'WH10001');
    await userEvent.type(screen.getByLabelText(/^Password/), 'pw');
    await userEvent.click(screen.getByRole('button', { name: 'Run test' }));
    expect(await screen.findByText('Access rejected')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/^Password/), 'pw');
    await userEvent.click(screen.getByRole('button', { name: 'Run test' }));
    expect(await screen.findByText('RADIUS service unavailable')).toBeInTheDocument();
  });
});

describe('NewRouterPage', () => {
  it('walks through the steps, validates per step and posts once with an Idempotency-Key', async () => {
    const requests: { key: string | null; body: Record<string, unknown> }[] = [];
    server.use(
      http.post(`${API}/routers/`, async ({ request }) => {
        requests.push({
          key: request.headers.get('Idempotency-Key'),
          body: (await request.json()) as Record<string, unknown>,
        });
        return HttpResponse.json(
          router({ id: 'new-1', name: 'mikrotik-garki-01', onboarding_state: 'pending' }),
          { status: 201 },
        );
      }),
    );
    renderPage(<NewRouterPage />, {
      path: '/routers/new',
      extraRoutes: <Route path="/routers/:id" element={<div>router detail</div>} />,
    });
    await userEvent.click(screen.getByRole('button', { name: /Continue/ }));
    expect(await screen.findByText('Give the router a name')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/^Name/), 'mikrotik-garki-01');
    await userEvent.type(screen.getByLabelText(/NAS IP address/), '10.100.100.14');
    await userEvent.click(screen.getByRole('button', { name: /Continue/ }));
    await userEvent.type(await screen.findByLabelText(/RADIUS shared secret/), 'sharedsecret123');
    await userEvent.click(screen.getByRole('button', { name: /Continue/ }));
    await screen.findByText(/Step 3 of 4/);
    await userEvent.click(screen.getByRole('button', { name: /Continue/ }));
    await screen.findByText(/Step 4 of 4/);
    await userEvent.click(screen.getByRole('button', { name: 'Register router' }));
    expect(await screen.findByText('router detail')).toBeInTheDocument();
    expect(requests).toHaveLength(1);
    expect(requests[0]?.key).toMatch(/^[A-Za-z0-9_.:-]{16,128}$/);
    expect(requests[0]?.body).toMatchObject({
      name: 'mikrotik-garki-01',
      ip_address: '10.100.100.14',
      nas_secret: 'sharedsecret123',
      wireguard_port: 51820,
      wireguard_ip: null,
      wireguard_public_key: '',
    });
    // Secrets are only sent when provided.
    expect(requests[0]?.body).not.toHaveProperty('routeros_password_encrypted');
  });
});
