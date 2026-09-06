import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type { InternetPlan } from '@/types/api';
import PlansPage from './PlansPage';

const plans: InternetPlan[] = [
  {
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
  },
  {
    id: 2,
    name: 'Weekly Unlimited',
    price: 250000,
    price_display: '₦2,500',
    duration_hours: 168,
    rate_limit: '10M/20M',
    data_limit: 0,
    voucher_prefix: '',
    is_active: false,
    created_at: '2026-09-02T10:00:00Z',
  },
];

describe('PlansPage', () => {
  it('shows a skeleton, then the plan list with filters reflected in the query string', async () => {
    const seen: URL[] = [];
    server.use(
      http.get(`${API}/plans/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(paginated(plans));
      }),
    );
    renderPage(<PlansPage />, { role: 'manager', path: '/plans' });
    expect(screen.getByRole('heading', { name: 'Plans' })).toBeInTheDocument();
    // DataTable renders a table (≥md) and a card list (<md); assert inside the table.
    const table = await screen.findByRole('table', { name: 'Internet plans' });
    expect(await within(table).findByText('Daily 1GB')).toBeInTheDocument();
    expect(within(table).getByText('Weekly Unlimited')).toBeInTheDocument();
    expect(within(table).getByText('Inactive')).toBeInTheDocument();
    expect(seen[0]?.searchParams.get('ordering')).toBe('price');

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'true');
    await waitFor(() => expect(seen.at(-1)?.searchParams.get('is_active')).toBe('true'));
    await userEvent.type(screen.getByLabelText('Search plans'), 'week');
    await waitFor(() => expect(seen.at(-1)?.searchParams.get('search')).toBe('week'), {
      timeout: 2000,
    });
  });

  it('renders an error state with retry', async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/plans/`, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              { problem: { code: 'http_503', message: 'Database unavailable' } },
              { status: 503 },
            )
          : HttpResponse.json(paginated(plans));
      }),
    );
    renderPage(<PlansPage />, { path: '/plans' });
    expect(await screen.findByText(/Database unavailable/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findAllByText('Daily 1GB')).not.toHaveLength(0);
  });

  it('staff see no management actions; managers can create a plan (with field errors mapped)', async () => {
    server.use(http.get(`${API}/plans/`, () => HttpResponse.json(paginated([]))));
    const { unmount } = renderPage(<PlansPage />, { role: 'staff', path: '/plans' });
    expect(await screen.findByText('No plans yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New plan' })).not.toBeInTheDocument();
    unmount();

    let posted: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API}/plans/`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        if (posted.name === 'dup')
          return HttpResponse.json(
            {
              problem: {
                code: 'validation_error',
                message: 'Invalid input.',
                fields: { name: ['Plan with this name already exists.'] },
              },
            },
            { status: 400 },
          );
        return HttpResponse.json(
          { ...plans[0], id: 9, name: String(posted.name) },
          { status: 201 },
        );
      }),
    );
    renderPage(<PlansPage />, { role: 'owner', path: '/plans' });
    await userEvent.click(await screen.findByRole('button', { name: 'Create a plan' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/Plan name/), 'dup');
    await userEvent.type(within(dialog).getByLabelText(/Price/), '500');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create plan' }));
    expect(
      await within(dialog).findByText('Plan with this name already exists.'),
    ).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText(/Plan name/));
    await userEvent.type(within(dialog).getByLabelText(/Plan name/), 'Night Owl');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create plan' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posted).toMatchObject({
      name: 'Night Owl',
      price: 50000,
      duration_hours: 24,
      rate_limit: '5M/10M',
      data_limit: 0,
      is_active: true,
    });
    expect(await screen.findByText('Plan created')).toBeInTheDocument();
  });
});
