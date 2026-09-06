import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type { PaymentDelivery, PaymentRecovery, PaymentTransaction } from '@/types/api';
import PaymentsPage from './PaymentsPage';
import RecoveryPage from './RecoveryPage';
import {
  canDeliver,
  canRetry,
  deliveryNeedsAcknowledgement,
  needsAttention,
} from '../paymentRules';

const payment = (extra: Partial<PaymentTransaction> = {}): PaymentTransaction => ({
  id: 1,
  reference: 'PAY-FULFILLED-001',
  paystack_reference: 'ps_1',
  customer_email: 'ada@example.com',
  customer_phone: '+2348000000000',
  customer_name: 'Ada Obi',
  amount: 50000,
  status: 'success',
  plan: 1,
  tenant: 5,
  voucher: 56,
  voucher_username: '2ju2AUqb',
  created_at: '2026-09-01T10:00:00Z',
  paid_at: '2026-09-01T10:01:00Z',
  ...extra,
});

const recovery = (extra: Partial<PaymentRecovery> = {}): PaymentRecovery => ({
  id: 2,
  reference: 'PAY-UNFULFILLED-002',
  amount: 50000,
  status: 'success',
  voucher: null,
  fulfillment_status: 'paid_unfulfilled',
  delivery_status: 'not_requested',
  verified_at: null,
  ...extra,
});

const delivery = (extra: Partial<PaymentDelivery> = {}): PaymentDelivery => ({
  id: 'd1',
  payment: 1,
  status: 'accepted',
  error_code: '',
  created_at: '2026-09-01T10:05:00Z',
  started_at: '2026-09-01T10:05:10Z',
  completed_at: '2026-09-01T10:05:30Z',
  ...extra,
});

describe('payment rules', () => {
  it('flags paid-without-voucher and failed deliveries as needing attention', () => {
    expect(needsAttention(recovery())).toBe(true);
    expect(
      needsAttention(
        recovery({ fulfillment_status: 'fulfilled', voucher: 56, delivery_status: 'failed' }),
      ),
    ).toBe(true);
    expect(
      needsAttention(
        recovery({ fulfillment_status: 'fulfilled', voucher: 56, delivery_status: 'accepted' }),
      ),
    ).toBe(false);
    expect(needsAttention(recovery({ status: 'pending', fulfillment_status: 'unverified' }))).toBe(
      false,
    );
  });
  it('mirrors the server rules for retry, deliver and acknowledgement', () => {
    expect(canRetry(recovery())).toBe(true);
    expect(canRetry(recovery({ fulfillment_status: 'fulfilled', voucher: 56 }))).toBe(false);
    expect(canDeliver(recovery())).toBe(false);
    expect(canDeliver(recovery({ voucher: 56 }))).toBe(true);
    expect(deliveryNeedsAcknowledgement(recovery({ delivery_status: 'accepted' }))).toBe(true);
    expect(deliveryNeedsAcknowledgement(recovery({ delivery_status: 'failed' }))).toBe(false);
  });
});

describe('PaymentsPage', () => {
  it('lists payments, filters by status and opens the detail drawer from the URL', async () => {
    const seen: URL[] = [];
    server.use(
      http.get(`${API}/payments/transactions/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(
          paginated([
            payment(),
            payment({
              id: 3,
              reference: 'PAY-PENDING-003',
              status: 'pending',
              voucher: null,
              voucher_username: null,
              paid_at: null,
            }),
          ]),
        );
      }),
      http.get(`${API}/payments/transactions/:id/`, ({ params }) =>
        HttpResponse.json(payment({ id: Number(params.id) })),
      ),
    );
    renderPage(<PaymentsPage />, { path: '/payments', role: 'staff' });
    const table = await screen.findByRole('table', { name: 'Payments' });
    expect(await within(table).findByText('PAY-FULFILLED-001')).toBeInTheDocument();
    expect(within(table).getByText('PAY-PENDING-003')).toBeInTheDocument();
    // staff cannot see the recovery board
    expect(screen.queryByRole('link', { name: /Recovery/ })).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'success');
    await waitFor(() => expect(seen.at(-1)?.searchParams.get('status')).toBe('success'));
    expect(seen.at(-1)?.searchParams.get('ordering')).toBe('-created_at');

    await userEvent.click(within(table).getByText('PAY-FULFILLED-001'));
    const dialog = await screen.findByRole('dialog', { name: 'Payment' });
    expect(await within(dialog).findByText('₦500.00')).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: '2ju2AUqb' })).toHaveAttribute(
      'href',
      '/vouchers/56',
    );
    expect(
      within(dialog).queryByRole('button', { name: /Resend credentials/ }),
    ).not.toBeInTheDocument();
  });

  it('offers the recovery hand-off to managers for successful payments', async () => {
    server.use(
      http.get(`${API}/payments/transactions/`, () => HttpResponse.json(paginated([payment()]))),
      http.get(`${API}/payments/transactions/:id/`, () => HttpResponse.json(payment())),
    );
    renderPage(<PaymentsPage />, {
      path: '/payments',
      route: '/payments?payment=1',
      role: 'manager',
    });
    const dialog = await screen.findByRole('dialog', { name: 'Payment' });
    expect(
      await within(dialog).findByRole('button', { name: /Resend credentials/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Recovery/ })).toHaveAttribute(
      'href',
      '/payments/recovery',
    );
  });

  it('shows an empty state and an error state', async () => {
    server.use(http.get(`${API}/payments/transactions/`, () => HttpResponse.json(paginated([]))));
    const { unmount } = renderPage(<PaymentsPage />, { path: '/payments' });
    expect(await screen.findByText('No payments yet')).toBeInTheDocument();
    unmount();
    server.use(
      http.get(`${API}/payments/transactions/`, () =>
        HttpResponse.json({ problem: { code: 'server_error', message: 'boom' } }, { status: 500 }),
      ),
    );
    renderPage(<PaymentsPage />, { path: '/payments' });
    expect(await screen.findByRole('button', { name: /Try again/ })).toBeInTheDocument();
  });
});

describe('RecoveryPage', () => {
  it('highlights payments needing attention, retries with idempotency and explains a 503', async () => {
    const retries: string[] = [];
    server.use(
      http.get(`${API}/plans/`, () => HttpResponse.json(paginated([]))),
      http.get(`${API}/payment-recovery/`, () =>
        HttpResponse.json(
          paginated([
            recovery(),
            recovery({
              id: 1,
              reference: 'PAY-FULFILLED-001',
              voucher: 56,
              fulfillment_status: 'fulfilled',
              delivery_status: 'accepted',
              verified_at: '2026-09-01T10:01:00Z',
            }),
          ]),
        ),
      ),
      http.get(`${API}/payment-recovery/:id/`, ({ params }) =>
        HttpResponse.json(
          params.id === '1'
            ? recovery({
                id: 1,
                reference: 'PAY-FULFILLED-001',
                voucher: 56,
                fulfillment_status: 'fulfilled',
                delivery_status: 'accepted',
              })
            : recovery(),
        ),
      ),
      http.get(`${API}/payment-deliveries/`, () => HttpResponse.json(paginated([]))),
      http.post(`${API}/payment-recovery/:id/retry/`, ({ request }) => {
        retries.push(request.headers.get('Idempotency-Key') ?? '');
        return HttpResponse.json(
          {
            error: 'Payment verification unavailable.',
            problem: { code: 'unavailable', message: 'Payment verification unavailable.' },
          },
          { status: 503 },
        );
      }),
    );
    renderPage(<RecoveryPage />, { path: '/payments/recovery', role: 'manager' });
    expect(await screen.findByText(/1 payment needs attention/)).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Payment recovery' });
    await userEvent.click(within(table).getByText('PAY-UNFULFILLED-002'));
    const dialog = await screen.findByRole('dialog', { name: 'Recover payment' });
    const retryButton = await within(dialog).findByRole('button', {
      name: /Re-verify & issue voucher/,
    });
    expect(within(dialog).getByRole('button', { name: /Email credentials/ })).toBeDisabled();
    await userEvent.click(retryButton);
    expect(
      await within(dialog).findByText('Could not reach the payment provider'),
    ).toBeInTheDocument();
    expect(retries).toHaveLength(1);
    expect(retries[0]).toMatch(/^retry[-_.:A-Za-z0-9]{15,}$/);
  });

  it('asks for duplicate-risk acknowledgement on a 409 and resends with the flag', async () => {
    const bodies: Record<string, unknown>[] = [];
    const row = recovery({
      id: 1,
      reference: 'PAY-FULFILLED-001',
      voucher: 56,
      fulfillment_status: 'fulfilled',
      delivery_status: 'accepted',
      verified_at: '2026-09-01T10:01:00Z',
    });
    server.use(
      http.get(`${API}/plans/`, () => HttpResponse.json(paginated([]))),
      http.get(`${API}/payment-recovery/`, () => HttpResponse.json(paginated([row]))),
      http.get(`${API}/payment-recovery/:id/`, () => HttpResponse.json(row)),
      http.get(`${API}/payment-deliveries/`, () =>
        HttpResponse.json(
          paginated([
            delivery(),
            delivery({
              id: 'd0',
              status: 'failed',
              error_code: 'smtp_timeout',
              created_at: '2026-09-01T10:02:00Z',
            }),
          ]),
        ),
      ),
      http.post(`${API}/payment-recovery/:id/deliver/`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        if (!body.acknowledge_duplicate_risk) {
          return HttpResponse.json(
            {
              error:
                'Delivery may already have occurred. Explicitly acknowledge duplicate delivery risk to resend.',
            },
            { status: 409 },
          );
        }
        return HttpResponse.json(delivery({ id: 'd2', status: 'pending', completed_at: null }), {
          status: 202,
        });
      }),
    );
    renderPage(<RecoveryPage />, {
      path: '/payments/recovery',
      route: '/payments/recovery?payment=1',
      role: 'owner',
    });
    const dialog = await screen.findByRole('dialog', { name: 'Recover payment' });
    expect(await within(dialog).findByText('smtp_timeout')).toBeInTheDocument();
    expect(
      within(dialog).getByRole('button', { name: /Re-verify & issue voucher/ }),
    ).toBeDisabled();
    // Accepted delivery → the UI asks for acknowledgement up front (no wasted request).
    await userEvent.click(within(dialog).getByRole('button', { name: /Resend credentials/ }));
    const resend = await within(dialog).findByRole('button', { name: 'Resend anyway' });
    expect(resend).toBeDisabled();
    await userEvent.click(within(dialog).getByLabelText(/I understand this may be a duplicate/));
    await userEvent.click(resend);
    await waitFor(() => expect(bodies).toEqual([{ acknowledge_duplicate_risk: true }]));
    expect(await screen.findByText('Email queued')).toBeInTheDocument();
  });

  it('hides actions from platform staff without the support grant', async () => {
    const row = recovery();
    server.use(
      http.get(`${API}/plans/`, () => HttpResponse.json(paginated([]))),
      http.get(`${API}/payment-recovery/`, () => HttpResponse.json(paginated([row]))),
      http.get(`${API}/payment-recovery/:id/`, () => HttpResponse.json(row)),
      http.get(`${API}/payment-deliveries/`, () => HttpResponse.json(paginated([]))),
    );
    const { makeAssignment, makeUser } = await import('@/test/fixtures');
    const { derivePrincipal } = await import('@/services/auth/principal');
    const principal = derivePrincipal(
      makeUser('platform_staff'),
      [makeAssignment(5, ['payments.view'])],
      5,
    );
    renderPage(<RecoveryPage />, {
      path: '/payments/recovery',
      route: '/payments/recovery?payment=2',
      principal,
    });
    const dialog = await screen.findByRole('dialog', { name: 'Recover payment' });
    expect(await within(dialog).findByText(/need the payments-support role/)).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: /Re-verify/ })).not.toBeInTheDocument();
  });
});
