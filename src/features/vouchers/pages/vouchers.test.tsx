import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route } from 'react-router';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type { InternetPlan, Voucher } from '@/types/api';
import * as download from '@/lib/utilities/download';
import VouchersPage from './VouchersPage';
import GenerateVouchersPage from './GenerateVouchersPage';
import VoucherDetailPage from './VoucherDetailPage';

const plan: InternetPlan = {
  id: 1,
  name: 'Daily 1GB',
  price: 50000,
  price_display: '₦500',
  duration_hours: 24,
  rate_limit: '5M/10M',
  data_limit: 1024,
  voucher_prefix: 'WH',
  is_active: true,
  created_at: '2026-09-01T10:00:00Z',
};
const voucher = (id: number, extra: Partial<Voucher> = {}): Voucher => ({
  id,
  username: `WH1000${id}`,
  plan: 1,
  plan_name: 'Daily 1GB',
  plan_duration: '24',
  price_display: '₦500',
  tenant: 5,
  tenant_name: 'Wuse Hotspot',
  agent: null,
  agent_name: null,
  status: 'unused',
  generation_source: 'admin',
  device_limit: 1,
  expires_at: null,
  activated_at: null,
  created_at: '2026-09-05T09:00:00Z',
  ...extra,
});
const printPage = (v: Voucher) =>
  `<html><body><h1>YAROTECH Voucher</h1><p><strong>Username:</strong> ${v.username}</p><p><strong>Password:</strong> pw-${v.id}</p><p><strong>Plan:</strong> Daily 1GB</p><p><strong>Duration:</strong> 24 hours</p><p><strong>Status:</strong> unused</p></body></html>`;

let printed: string[] = [];
beforeEach(() => {
  printed = [];
  vi.spyOn(download, 'printHtml').mockImplementation((html) => {
    printed.push(html);
  });
  server.use(http.get(`${API}/plans/`, () => HttpResponse.json(paginated([plan]))));
});
afterEach(() => vi.restoreAllMocks());

describe('VouchersPage', () => {
  it('lists vouchers, maps the status tab to ?status= and prints a selection into one sheet', async () => {
    const seen: URL[] = [];
    const rows = [
      voucher(1),
      voucher(2, {
        status: 'active',
        activated_at: '2026-09-05T10:00:00Z',
        expires_at: '2026-09-06T10:00:00Z',
      }),
      voucher(3, { status: 'disabled' }),
    ];
    server.use(
      http.get(`${API}/vouchers/`, ({ request }) => {
        seen.push(new URL(request.url));
        const status = new URL(request.url).searchParams.get('status');
        return HttpResponse.json(
          paginated(status ? rows.filter((r) => r.status === status) : rows),
        );
      }),
      http.get(`${API}/vouchers/:id/print/`, ({ params }) =>
        HttpResponse.text(printPage(voucher(Number(params.id)))),
      ),
    );
    renderPage(<VouchersPage />, { role: 'manager', path: '/vouchers' });
    const table = await screen.findByRole('table', { name: 'Vouchers' });
    expect(await within(table).findByText('WH10001')).toBeInTheDocument();
    expect(seen[0]?.searchParams.get('ordering')).toBe('-created_at');

    await userEvent.click(screen.getByRole('tab', { name: 'Active' }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.get('status')).toBe('active'));
    await waitFor(() => expect(within(table).queryByText('WH10001')).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole('tab', { name: 'All' }));
    await within(table).findByText('WH10001');

    await userEvent.click(within(table).getByLabelText('Select all vouchers on this page'));
    expect(screen.getByText('3 selected')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Print selected' }));
    await waitFor(() => expect(printed).toHaveLength(1));
    expect(printed[0]).toContain('pw-1');
    expect(printed[0]).toContain('pw-3');
    expect(printed[0]).toContain('Wuse Hotspot');
  });

  it('staff can print (backend allows it) but get no generate/disable/edit actions', async () => {
    server.use(http.get(`${API}/vouchers/`, () => HttpResponse.json(paginated([voucher(1)]))));
    renderPage(<VouchersPage />, { role: 'staff', path: '/vouchers' });
    const table = await screen.findByRole('table', { name: 'Vouchers' });
    await within(table).findByText('WH10001');
    expect(screen.queryByRole('button', { name: 'Generate vouchers' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Select all vouchers on this page')).toBeInTheDocument();
    await userEvent.click(within(table).getByRole('button', { name: 'Actions for WH10001' }));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'View details' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Print credentials' })).toBeInTheDocument();
    expect(within(menu).queryByRole('menuitem', { name: 'Disable' })).not.toBeInTheDocument();
    expect(within(menu).queryByRole('menuitem', { name: 'Edit' })).not.toBeInTheDocument();
  });

  it('shows the empty state with a call to action', async () => {
    server.use(http.get(`${API}/vouchers/`, () => HttpResponse.json(paginated([]))));
    renderPage(<VouchersPage />, { role: 'owner', path: '/vouchers' });
    expect(await screen.findByText('No vouchers yet')).toBeInTheDocument();
    // header action + empty-state action
    expect(screen.getAllByRole('button', { name: 'Generate vouchers' })).toHaveLength(2);
  });
});

describe('GenerateVouchersPage', () => {
  it('sends plan/quantity/prefix with an Idempotency-Key, then shows the batch and prints all', async () => {
    const posts: { body: Record<string, unknown>; key: string | null }[] = [];
    server.use(
      http.post(`${API}/vouchers/generate/`, async ({ request }) => {
        posts.push({
          body: (await request.json()) as Record<string, unknown>,
          key: request.headers.get('Idempotency-Key'),
        });
        return HttpResponse.json([voucher(11), voucher(12)], { status: 201 });
      }),
      http.get(`${API}/vouchers/:id/print/`, ({ params }) =>
        HttpResponse.text(printPage(voucher(Number(params.id)))),
      ),
    );
    renderPage(<GenerateVouchersPage />, {
      role: 'manager',
      path: '/vouchers/generate',
      route: '/vouchers/generate?plan=1',
    });
    const planRadio = await screen.findByRole('radio', { name: /Daily 1GB/ });
    expect(planRadio).toHaveAttribute('aria-checked', 'true');
    await userEvent.click(screen.getByRole('radio', { name: '50' }));
    await userEvent.type(screen.getByLabelText(/Username prefix/), 'wk');
    expect(screen.getByText(/25,000/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Generate 50 vouchers/ }));
    expect(await screen.findByRole('heading', { name: '2 vouchers ready' })).toBeInTheDocument();
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toEqual({ plan_id: 1, quantity: 50, prefix: 'wk' });
    expect(posts[0]?.key).toMatch(/^gen-[A-Za-z0-9_.:-]{12,}$/);
    await userEvent.click(screen.getByRole('button', { name: 'Print all' }));
    await waitFor(() => expect(printed).toHaveLength(1));
    expect(printed[0]).toContain('WH100011');
    expect(printed[0]).toContain('pw-12');
  });

  it('surfaces validation errors from the API on the right field', async () => {
    server.use(
      http.post(`${API}/vouchers/generate/`, () =>
        HttpResponse.json(
          {
            problem: {
              code: 'validation_error',
              message: 'Invalid input.',
              fields: { plan_id: ['Plan not found or inactive.'] },
            },
          },
          { status: 400 },
        ),
      ),
    );
    renderPage(<GenerateVouchersPage />, { role: 'manager', path: '/vouchers/generate' });
    await userEvent.click(await screen.findByRole('radio', { name: /Daily 1GB/ }));
    await userEvent.click(screen.getByRole('button', { name: /Generate 20 vouchers/ }));
    expect(await screen.findByText('Plan not found or inactive.')).toBeInTheDocument();
  });
});

describe('VoucherDetailPage', () => {
  it('shows details; disable calls the endpoint and refreshes', async () => {
    let current = voucher(7);
    server.use(
      http.get(`${API}/vouchers/7/`, () => HttpResponse.json(current)),
      http.post(`${API}/vouchers/7/disable/`, () => {
        current = { ...current, status: 'disabled' };
        return HttpResponse.json({ message: 'Voucher disabled.' });
      }),
    );
    renderPage(<VoucherDetailPage />, {
      role: 'owner',
      path: '/vouchers/:id',
      route: '/vouchers/7',
    });
    expect(await screen.findByRole('heading', { name: /WH10007/ })).toBeInTheDocument();
    expect(screen.getByText('Generated by staff', { selector: 'dd' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Disable' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Disable voucher' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /WH10007/ })).toHaveTextContent('Disabled'),
    );
    expect(screen.queryByRole('button', { name: 'Disable' })).not.toBeInTheDocument();
  });

  it('renders a friendly not-found error', async () => {
    server.use(
      http.get(`${API}/vouchers/99/`, () =>
        HttpResponse.json(
          {
            detail: 'No Voucher matches the given query.',
            problem: { code: 'http_404', message: 'No Voucher matches the given query.' },
          },
          { status: 404 },
        ),
      ),
    );
    renderPage(<VoucherDetailPage />, {
      role: 'owner',
      path: '/vouchers/:id',
      route: '/vouchers/99',
      extraRoutes: <Route path="/vouchers" element={<div>list</div>} />,
    });
    expect(await screen.findByText('Voucher not found')).toBeInTheDocument();
  });
});
