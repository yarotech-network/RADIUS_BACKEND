import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderWithProviders } from '@/test/render';
import LandingPage from './LandingPage';

const plans = [
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

function mockPricing() {
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
            features: ['1 router', 'Vouchers'],
            is_active: true,
          },
        ]),
      ),
    ),
  );
}

afterEach(() => {
  server.resetHandlers();
  vi.unstubAllEnvs();
});

describe('public landing page', () => {
  it('renders hero, business plans and about for visitors', async () => {
    mockPricing();
    renderWithProviders(<LandingPage />);

    expect(screen.getByRole('heading', { name: /run your wi-fi business/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create your workspace/i })).toHaveAttribute(
      'href',
      '/register',
    );
    expect(screen.getByRole('link', { name: /see business pricing/i })).toHaveAttribute(
      'href',
      '/pricing',
    );
    expect(await screen.findByRole('heading', { name: 'Starter' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /built for west african hotspot businesses/i }),
    ).toBeInTheDocument();
    // No featured storefront configured → the customer section stays hidden.
    expect(
      screen.queryByRole('heading', { name: /buy a wi-fi access code/i }),
    ).not.toBeInTheDocument();
  });

  it('shows the featured storefront plans when a slug is configured', async () => {
    vi.stubEnv('VITE_FEATURED_STOREFRONT_SLUG', 'wuse-hotspot');
    server.use(
      http.get(`${API}/public/tenants/wuse-hotspot/`, () =>
        HttpResponse.json({ id: 2, slug: 'wuse-hotspot', name: 'Wuse Hotspot' }),
      ),
      http.get(`${API}/public/tenants/wuse-hotspot/plans/`, () =>
        HttpResponse.json(paginated(plans)),
      ),
      http.get(`${API}/pricing/`, () => HttpResponse.json(paginated([]))),
    );

    renderWithProviders(<LandingPage />);

    const section = await screen.findByRole('region', { name: /buy a wi-fi access code/i });
    expect(await within(section).findByRole('heading', { name: 'Daily 1GB' })).toBeInTheDocument();
    expect(
      await within(section).findByRole('heading', { name: 'Weekly Unlimited' }),
    ).toBeInTheDocument();
    const buyLinks = within(section).getAllByRole('link', { name: 'Buy access code' });
    expect(buyLinks).toHaveLength(2);
    expect(buyLinks[0]).toHaveAttribute('href', '/s/wuse-hotspot/checkout/1');
    expect(
      within(section).getByRole('link', { name: /all plans and business details/i }),
    ).toHaveAttribute('href', '/s/wuse-hotspot');
  });
});
