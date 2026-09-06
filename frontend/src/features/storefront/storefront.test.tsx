import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderWithProviders } from '@/test/render';
import type { PublicPlan } from '@/types/api';
import StorefrontPage from './pages/StorefrontPage';
import PaymentResultPage from './pages/PaymentResultPage';
import PricingPage from './pages/PricingPage';
import { pendingCheckout } from './pendingCheckout';
import { Route, Routes } from 'react-router';

const plans: PublicPlan[] = [
  {
    id: 1,
    name: 'Daily 1GB',
    price: 50000,
    duration_hours: 24,
    rate_limit: '5M/10M',
    data_limit: 1024,
  },
  {
    id: 2,
    name: 'Weekly Unlimited',
    price: 250000,
    duration_hours: 168,
    rate_limit: '10M/20M',
    data_limit: 0,
  },
];

function mockStore() {
  server.use(
    http.get(`${API}/public/tenants/wuse-hotspot/`, () =>
      HttpResponse.json({ id: 2, slug: 'wuse-hotspot', name: 'Wuse Hotspot' }),
    ),
    http.get(`${API}/public/tenants/wuse-hotspot/plans/`, () =>
      HttpResponse.json(paginated(plans)),
    ),
    http.get(`${API}/public/tenants/:slug/`, () =>
      HttpResponse.json({ detail: 'No Tenant matches the given query.' }, { status: 404 }),
    ),
  );
}

function renderStore(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/s/:slug/*" element={<StorefrontPage />} />
      <Route path="/pay/result" element={<PaymentResultPage />} />
    </Routes>,
    { route },
  );
}

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('storefront catalogue', () => {
  it('lists the operator plans with customer-friendly details and a Buy link', async () => {
    mockStore();
    renderStore('/s/wuse-hotspot');
    expect(await screen.findByRole('heading', { name: 'Wuse Hotspot' })).toBeInTheDocument();
    const weekly = await screen.findByRole('article', { name: 'Weekly Unlimited' });
    expect(within(weekly).getByText('₦2,500.00')).toBeInTheDocument();
    expect(within(weekly).getByText('7 days')).toBeInTheDocument();
    expect(within(weekly).getByText('Unlimited data')).toBeInTheDocument();
    expect(within(weekly).getByRole('link', { name: 'Buy' })).toHaveAttribute(
      'href',
      '/s/wuse-hotspot/checkout/2',
    );
  });

  it('shows a not-found screen for an unknown slug', async () => {
    mockStore();
    renderStore('/s/nope');
    expect(
      await screen.findByRole('heading', { name: 'This storefront does not exist' }),
    ).toBeInTheDocument();
  });

  it('shows an empty state when no plans are published', async () => {
    mockStore();
    server.use(
      http.get(`${API}/public/tenants/wuse-hotspot/plans/`, () => HttpResponse.json(paginated([]))),
    );
    renderStore('/s/wuse-hotspot');
    expect(await screen.findByText('No plans available right now')).toBeInTheDocument();
  });
});

describe('checkout', () => {
  it('validates the email, posts the order with an Idempotency-Key and redirects to Paystack', async () => {
    mockStore();
    let received: { body: unknown; key: string | null } | null = null;
    server.use(
      http.post(`${API}/buy/`, async ({ request }) => {
        received = { body: await request.json(), key: request.headers.get('Idempotency-Key') };
        return HttpResponse.json({
          authorization_url: 'https://checkout.paystack.com/abc',
          reference: 'yarotech-abc',
        });
      }),
    );
    const assign = vi.fn();
    vi.spyOn(window, 'location', 'get').mockReturnValue({
      ...window.location,
      assign,
    } as unknown as Location);
    const user = userEvent.setup();
    renderStore('/s/wuse-hotspot/checkout/1');
    expect(await screen.findByRole('heading', { name: 'Checkout' })).toBeInTheDocument();
    // the order summary shows the chosen plan
    expect(await screen.findByRole('article', { name: 'Daily 1GB' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /pay with paystack/i }));
    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument();
    expect(received).toBeNull();

    await user.type(screen.getByLabelText(/email address/i), 'buyer@example.com');
    await user.type(screen.getByLabelText(/^name/i), 'Buyer One');
    await user.click(screen.getByRole('button', { name: /pay with paystack/i }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://checkout.paystack.com/abc'));
    expect(received!.body).toEqual({ plan_id: 1, email: 'buyer@example.com', name: 'Buyer One' });
    expect(received!.key).toMatch(/^buy-/);
    expect(pendingCheckout.load()).toMatchObject({
      kind: 'voucher',
      reference: 'yarotech-abc',
      slug: 'wuse-hotspot',
    });
  });

  it('explains a 503 from the provider without pretending the order went through', async () => {
    mockStore();
    server.use(
      http.post(`${API}/buy/`, () =>
        HttpResponse.json(
          { error: 'Payment provider unavailable', reference: 'yarotech-dead' },
          { status: 503 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderStore('/s/wuse-hotspot/checkout/1');
    await user.type(await screen.findByLabelText(/email address/i), 'buyer@example.com');
    await user.click(screen.getByRole('button', { name: /pay with paystack/i }));
    expect(await screen.findByText('Payments are temporarily unavailable')).toBeInTheDocument();
    expect(screen.getByText('yarotech-dead')).toBeInTheDocument();
  });

  it('handles a plan that no longer exists', async () => {
    mockStore();
    renderStore('/s/wuse-hotspot/checkout/999');
    expect(await screen.findByText('This plan is no longer available')).toBeInTheDocument();
  });
});

describe('payment result', () => {
  it('polls while pending and then shows the voucher username with a copy button', async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/payments/callback/`, ({ request }) => {
        const ref = new URL(request.url).searchParams.get('reference');
        calls += 1;
        return HttpResponse.json(
          calls < 2
            ? { status: 'pending', reference: ref, voucher: null }
            : { status: 'success', reference: ref, voucher: 'WH84OQ0oKp' },
        );
      }),
    );
    pendingCheckout.save({ kind: 'voucher', reference: 'yarotech-abc', slug: 'wuse-hotspot' });
    const user = userEvent.setup();
    renderStore('/pay/result?reference=yarotech-abc');
    expect(await screen.findByText('Waiting for confirmation')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Check again' }));
    expect(await screen.findByText('Payment successful')).toBeInTheDocument();
    expect(screen.getByText('WH84OQ0oKp')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy username' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to plans' })).toHaveAttribute(
      'href',
      '/s/wuse-hotspot',
    );
    // settled → the remembered checkout is cleared
    await waitFor(() => expect(pendingCheckout.load()).toBeNull());
  });

  it('falls back to the remembered reference when Paystack drops the query string', async () => {
    server.use(
      http.get(`${API}/payments/callback/`, ({ request }) =>
        HttpResponse.json({
          status: 'failed',
          reference: new URL(request.url).searchParams.get('reference'),
          voucher: null,
        }),
      ),
    );
    pendingCheckout.save({ kind: 'voucher', reference: 'yarotech-lost', slug: 'wuse-hotspot' });
    renderStore('/pay/result');
    expect(await screen.findByText('Payment failed')).toBeInTheDocument();
    expect(screen.getByText('yarotech-lost')).toBeInTheDocument();
  });

  it('shows a clear message for an unknown reference and when there is nothing to check', async () => {
    server.use(
      http.get(`${API}/payments/callback/`, () =>
        HttpResponse.json({ error: 'Payment not found' }, { status: 404 }),
      ),
    );
    const { unmount } = renderStore('/pay/result?reference=zzz');
    expect(await screen.findByText('We could not find this payment')).toBeInTheDocument();
    unmount();
    renderStore('/pay/result');
    expect(await screen.findByText('No payment to check')).toBeInTheDocument();
  });
});

describe('pricing', () => {
  it('renders active platform plans only', async () => {
    server.use(
      http.get(`${API}/pricing/`, () =>
        HttpResponse.json(
          paginated([
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
              name: 'Legacy',
              price: 1,
              price_display: '₦0.01',
              duration_days: 30,
              features: [],
              is_active: false,
            },
          ]),
        ),
      ),
    );
    renderWithProviders(<PricingPage />, { route: '/pricing' });
    expect(await screen.findByRole('heading', { name: 'Starter' })).toBeInTheDocument();
    expect(screen.getByText('₦15,000.00')).toBeInTheDocument();
    expect(screen.getByText('1 router')).toBeInTheDocument();
    expect(screen.queryByText('Legacy')).not.toBeInTheDocument();
  });
});
