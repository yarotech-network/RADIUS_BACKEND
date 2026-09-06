import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type {
  AgentFundingPayment,
  AgentProfile,
  AgentVoucherAllocation,
  PublicPlan,
} from '@/types/api';
import AgentHomePage from './pages/AgentHomePage';
import AgentSellPage from './pages/AgentSellPage';
import AgentWalletPage from './pages/AgentWalletPage';
import AgentVouchersPage from './pages/AgentVouchersPage';
import AgentProfilePage from './pages/AgentProfilePage';
import { storeSlugStore, normaliseStoreSlug } from './storeSlug';
import { sellCost, sellSchema } from './sellSchema';
import { fundSchema } from './fundSchema';
import { pendingCheckout } from '@/features/storefront/pendingCheckout';

const profile: AgentProfile = {
  id: 1,
  user: 42,
  username: 'ada',
  tenant: 5,
  phone: '+2348040000001',
  shop_name: 'Chidi Phones',
  status: 'active',
  commission_rate: '10.00',
  wallet_balance: 250000,
  created_at: '2026-09-01T07:27:11Z',
};
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
    id: 3,
    name: 'Monthly 20GB',
    price: 800000,
    duration_hours: 720,
    rate_limit: '20M/50M',
    data_limit: 20480,
  },
];
const allocation = (extra: Partial<AgentVoucherAllocation> = {}): AgentVoucherAllocation => ({
  id: 1,
  agent: 1,
  voucher: 82,
  voucher_username: 'WH84OQ0oKp',
  allocation_type: 'wallet',
  amount_charged: 50000,
  commission_earned: 0,
  created_at: '2026-09-06T10:08:59Z',
  ...extra,
});

function mockAgent(balance = 250000) {
  server.use(
    http.get(`${API}/agents/me/`, () => HttpResponse.json({ ...profile, wallet_balance: balance })),
    http.get(`${API}/agent/dashboard/`, () =>
      HttpResponse.json({
        wallet_balance: balance,
        vouchers_today: 3,
        commission_this_month: 0,
        total_vouchers: 12,
      }),
    ),
    http.get(`${API}/agent/wallet/balance/`, () =>
      HttpResponse.json({ id: 1, agent: 1, balance, updated_at: '2026-09-06T10:00:00Z' }),
    ),
    http.get(`${API}/agent/wallet/payments/`, () => HttpResponse.json(paginated([]))),
    http.get(`${API}/agent/vouchers/history/`, () =>
      HttpResponse.json(
        paginated([allocation(), allocation({ id: 2, voucher_username: 'WHq2PYQtDW' })]),
      ),
    ),
    http.get(`${API}/public/tenants/wuse-hotspot/`, () =>
      HttpResponse.json({ id: 5, slug: 'wuse-hotspot', name: 'Wuse Hotspot' }),
    ),
    http.get(`${API}/public/tenants/wuse-hotspot/plans/`, () =>
      HttpResponse.json(paginated(plans)),
    ),
    http.get(`${API}/public/tenants/:slug/`, () =>
      HttpResponse.json({ detail: 'No Tenant matches the given query.' }, { status: 404 }),
    ),
  );
}

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('store slug helpers', () => {
  it('normalises links, bare slugs and rejects junk', () => {
    expect(normaliseStoreSlug('https://app.example.com/s/wuse-hotspot')).toBe('wuse-hotspot');
    expect(normaliseStoreSlug('  Wuse-Hotspot ')).toBe('wuse-hotspot');
    expect(normaliseStoreSlug('/s/garki-wifi/checkout/2')).toBe('garki-wifi');
    expect(normaliseStoreSlug('not a slug!')).toBeNull();
    expect(normaliseStoreSlug('')).toBeNull();
  });
  it('sell schema + cost mirror the backend limits (1–100, price × quantity)', () => {
    expect(sellSchema.safeParse({ plan_id: 1, quantity: '3' }).success).toBe(true);
    expect(sellSchema.safeParse({ plan_id: 0, quantity: 1 }).success).toBe(false);
    expect(sellSchema.safeParse({ plan_id: 1, quantity: 101 }).success).toBe(false);
    expect(sellCost(50000, 3)).toBe(150000);
    expect(sellCost(50000, 0)).toBe(0);
  });
  it('fund schema enforces the ₦500 floor in naira input', () => {
    expect(fundSchema.safeParse({ amount: '499' }).success).toBe(false);
    expect(fundSchema.safeParse({ amount: '500' })).toMatchObject({
      success: true,
      data: { amount: 50000 },
    });
    expect(fundSchema.safeParse({ amount: '2,000' })).toMatchObject({
      success: true,
      data: { amount: 200000 },
    });
  });
});

describe('agent home', () => {
  it('shows balance, sales counters, recent sales and hides the (never computed) commission card', async () => {
    mockAgent();
    storeSlugStore.write('wuse-hotspot');
    renderPage(<AgentHomePage />, { role: 'agent', path: '/agent' });
    expect(await screen.findByRole('heading', { name: 'Ada' })).toBeInTheDocument();
    expect(await screen.findByText('₦2,500.00')).toBeInTheDocument();
    expect(screen.getByText('Sold today')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.queryByText('Commission this month')).not.toBeInTheDocument();
    expect(await screen.findByText('WH84OQ0oKp')).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Connect storefront' })).not.toBeInTheDocument();
  });

  it('asks to connect a storefront when none is remembered and verifies the slug', async () => {
    mockAgent();
    const user = userEvent.setup();
    renderPage(<AgentHomePage />, { role: 'agent', path: '/agent' });
    const form = await screen.findByRole('form', { name: 'Connect storefront' });
    await user.type(
      within(form).getByLabelText(/storefront link or name/i),
      'https://x.test/s/nope',
    );
    await user.click(within(form).getByRole('button', { name: 'Connect' }));
    expect(await screen.findByText(/No storefront found at that address/)).toBeInTheDocument();
    await user.clear(within(form).getByLabelText(/storefront link or name/i));
    await user.type(within(form).getByLabelText(/storefront link or name/i), 'wuse-hotspot');
    await user.click(within(form).getByRole('button', { name: 'Connect' }));
    await waitFor(() => expect(storeSlugStore.read()).toBe('wuse-hotspot'));
    expect(screen.queryByRole('form', { name: 'Connect storefront' })).not.toBeInTheDocument();
  });
});

describe('agent sell', () => {
  it('sells from the public catalogue, previews the wallet charge and shows usernames only', async () => {
    mockAgent();
    storeSlugStore.write('wuse-hotspot');
    let received: { body: unknown; key: string | null } | null = null;
    server.use(
      http.post(`${API}/agent/vouchers/generate/`, async ({ request }) => {
        received = { body: await request.json(), key: request.headers.get('Idempotency-Key') };
        return HttpResponse.json(
          { vouchers: [allocation(), allocation({ id: 2, voucher_username: 'WHq2PYQtDW' })] },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderPage(<AgentSellPage />, { role: 'agent', path: '/agent/sell' });
    expect(await screen.findByText('Wuse Hotspot')).toBeInTheDocument();
    const sell = screen.getByRole('button', { name: 'Sell voucher' });
    expect(sell).toBeDisabled();
    await user.click(await screen.findByRole('radio', { name: 'Daily 1GB' }));
    await user.clear(screen.getByLabelText(/how many/i));
    await user.type(screen.getByLabelText(/how many/i), '2');
    expect(screen.getByText('₦1,000.00')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Sell 2 vouchers' }));
    expect(await screen.findByRole('heading', { name: '2 vouchers sold' })).toBeInTheDocument();
    expect(received!.body).toEqual({ plan_id: 1, quantity: 2 });
    expect(received!.key).toMatch(/^agent-gen-/);
    expect(screen.getByText('WH84OQ0oKp')).toBeInTheDocument();
    expect(
      screen.getByText(/password for each voucher is issued by the operator/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy all usernames' })).toBeInTheDocument();
  });

  it('blocks a sale that exceeds the balance and points to funding', async () => {
    mockAgent(60000);
    storeSlugStore.write('wuse-hotspot');
    const user = userEvent.setup();
    renderPage(<AgentSellPage />, { role: 'agent', path: '/agent/sell' });
    await user.click(await screen.findByRole('radio', { name: 'Monthly 20GB' }));
    expect(await screen.findByText(/Exceeds your balance by ₦7,400.00/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sell voucher' })).toBeDisabled();
  });

  it('surfaces the backend insufficient-balance error even when the local preview allowed it', async () => {
    mockAgent();
    storeSlugStore.write('wuse-hotspot');
    server.use(
      http.post(`${API}/agent/vouchers/generate/`, () =>
        HttpResponse.json({ error: 'Insufficient wallet balance' }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderPage(<AgentSellPage />, { role: 'agent', path: '/agent/sell' });
    await user.click(await screen.findByRole('radio', { name: 'Daily 1GB' }));
    await user.click(screen.getByRole('button', { name: 'Sell voucher' }));
    expect(await screen.findByText('Not enough in your wallet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Fund wallet' })).toHaveAttribute(
      'href',
      '/agent/wallet?fund=1',
    );
  });

  it('maps a plan rejection onto the plan field', async () => {
    mockAgent();
    storeSlugStore.write('wuse-hotspot');
    server.use(
      http.post(`${API}/agent/vouchers/generate/`, () =>
        HttpResponse.json({ plan_id: ['Plan not found or inactive.'] }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderPage(<AgentSellPage />, { role: 'agent', path: '/agent/sell' });
    await user.click(await screen.findByRole('radio', { name: 'Daily 1GB' }));
    await user.click(screen.getByRole('button', { name: 'Sell voucher' }));
    expect(await screen.findByText(/Plan not found or inactive/)).toBeInTheDocument();
  });

  it('asks for the storefront first when none is connected', async () => {
    mockAgent();
    renderPage(<AgentSellPage />, { role: 'agent', path: '/agent/sell' });
    expect(await screen.findByRole('form', { name: 'Connect storefront' })).toBeInTheDocument();
  });
});

describe('agent wallet', () => {
  const funding = (extra: Partial<AgentFundingPayment> = {}): AgentFundingPayment => ({
    id: 1,
    reference: 'agent-fund-abc',
    amount: 100000,
    status: 'pending',
    created_at: '2026-09-06T10:08:59Z',
    completed_at: null,
    ...extra,
  });

  it('lists top-ups, opens the fund dialog from ?fund=1 and starts a Paystack payment', async () => {
    mockAgent();
    server.use(
      http.get(`${API}/agent/wallet/payments/`, ({ request }) => {
        const ref = new URL(request.url).searchParams.get('reference');
        if (ref)
          return HttpResponse.json(
            paginated([
              funding({ reference: ref, status: 'success', completed_at: '2026-09-06T10:10:00Z' }),
            ]),
          );
        return HttpResponse.json(paginated([funding({ status: 'failed' })]));
      }),
    );
    let received: { body: unknown; key: string | null } | null = null;
    server.use(
      http.post(`${API}/agent/wallet/fund/`, async ({ request }) => {
        received = { body: await request.json(), key: request.headers.get('Idempotency-Key') };
        return HttpResponse.json({
          authorization_url: 'https://checkout.paystack.com/fund',
          reference: 'agent-fund-new',
        });
      }),
    );
    const assign = vi.fn();
    vi.spyOn(window, 'location', 'get').mockReturnValue({
      ...window.location,
      assign,
    } as unknown as Location);
    const user = userEvent.setup();
    renderPage(<AgentWalletPage />, {
      role: 'agent',
      path: '/agent/wallet/*',
      route: '/agent/wallet?fund=1',
    });
    expect(await screen.findByText('₦2,500.00')).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Top-ups' });
    expect(await within(table).findByText('agent-fund-abc')).toBeInTheDocument();
    expect(within(table).getByText('Failed')).toBeInTheDocument();

    const dialog = await screen.findByRole('dialog', { name: 'Fund wallet' });
    await user.click(within(dialog).getByRole('button', { name: '₦2,000' }));
    expect(within(dialog).getByRole('button', { name: 'Pay ₦2,000.00' })).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Pay ₦2,000.00' }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://checkout.paystack.com/fund'));
    expect(received!.body).toEqual({ amount: 200000 });
    expect(received!.key).toMatch(/^fund-/);
    expect(pendingCheckout.load()).toMatchObject({ kind: 'wallet', reference: 'agent-fund-new' });
    // the tracker for the new reference appears and resolves via ?reference= lookup
    expect(await screen.findByText(/Top-up of ₦1,000.00 received/)).toBeInTheDocument();
  });

  it('rejects amounts under ₦500 locally and shows the tenant ceiling from the API', async () => {
    mockAgent();
    server.use(
      http.post(`${API}/agent/wallet/fund/`, () =>
        HttpResponse.json(
          { amount: ['Amount exceeds the tenant funding limit of 100000 kobo.'] },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage(<AgentWalletPage />, {
      role: 'agent',
      path: '/agent/wallet/*',
      route: '/agent/wallet?fund=1',
    });
    const dialog = await screen.findByRole('dialog', { name: 'Fund wallet' });
    const amount = within(dialog).getByLabelText(/^Amount \(₦\)/);
    await user.type(amount, '200');
    await user.click(within(dialog).getByRole('button', { name: /pay|continue/i }));
    expect(await screen.findByText('Minimum top-up is ₦500')).toBeInTheDocument();
    await user.clear(amount);
    await user.type(amount, '5000');
    await user.click(within(dialog).getByRole('button', { name: 'Pay ₦5,000.00' }));
    expect(await screen.findByText(/exceeds the tenant funding limit/)).toBeInTheDocument();
  });

  it('on return from Paystack polls the remembered reference until it settles', async () => {
    mockAgent();
    let calls = 0;
    server.use(
      http.get(`${API}/agent/wallet/payments/`, ({ request }) => {
        const ref = new URL(request.url).searchParams.get('reference');
        if (!ref) return HttpResponse.json(paginated([]));
        calls += 1;
        return HttpResponse.json(
          paginated([
            funding({
              reference: ref,
              status: calls < 2 ? 'pending' : 'success',
              completed_at: calls < 2 ? null : '2026-09-06T10:10:00Z',
            }),
          ]),
        );
      }),
    );
    pendingCheckout.save({ kind: 'wallet', reference: 'agent-fund-back', amount: 100000 });
    const user = userEvent.setup();
    renderPage(<AgentWalletPage />, {
      role: 'agent',
      path: '/agent/wallet/*',
      route: '/agent/wallet/return',
    });
    expect(
      await screen.findByText('Waiting for Paystack to confirm your top-up'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Check now' }));
    expect(await screen.findByText(/Top-up of ₦1,000.00 received/)).toBeInTheDocument();
  });
});

describe('agent vouchers + profile', () => {
  it('lists sold vouchers with a status filter that maps to the API', async () => {
    mockAgent();
    let lastStatus: string | null = null;
    server.use(
      http.get(`${API}/agent/vouchers/history/`, ({ request }) => {
        lastStatus = new URL(request.url).searchParams.get('status');
        return HttpResponse.json(paginated(lastStatus === 'expired' ? [] : [allocation()]));
      }),
    );
    const user = userEvent.setup();
    renderPage(<AgentVouchersPage />, { role: 'agent', path: '/agent/vouchers' });
    const table = await screen.findByRole('table', { name: 'Vouchers sold' });
    expect(await within(table).findByText('WH84OQ0oKp')).toBeInTheDocument();
    expect(within(table).getByText('Paid from wallet')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Voucher status'), 'expired');
    expect(await screen.findByText('No vouchers with that status')).toBeInTheDocument();
    expect(lastStatus).toBe('expired');
  });

  it('edits shop details with a diff-only PATCH and shows the connected storefront', async () => {
    mockAgent();
    storeSlugStore.write('wuse-hotspot');
    let received: unknown = null;
    server.use(
      http.patch(`${API}/agents/1/`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ ...profile, shop_name: 'Chidi Phones & Data' });
      }),
    );
    const user = userEvent.setup();
    renderPage(<AgentProfilePage />, { role: 'agent', path: '/agent/profile' });
    const form = await screen.findByRole('form', { name: 'Shop details' });
    const shop = within(form).getByLabelText(/shop name/i);
    await waitFor(() => expect(shop).toHaveValue('Chidi Phones'));
    expect(within(form).getByRole('button', { name: 'Save' })).toBeDisabled();
    await user.clear(shop);
    await user.type(shop, 'Chidi Phones & Data');
    await user.click(within(form).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(received).toEqual({ shop_name: 'Chidi Phones & Data' }));
    expect(await screen.findByText('Shop details saved')).toBeInTheDocument();
    expect(screen.getByText('10.00%')).toBeInTheDocument();
    expect(screen.getByText('/s/wuse-hotspot')).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'Change password' })).toBeInTheDocument();
  });
});
