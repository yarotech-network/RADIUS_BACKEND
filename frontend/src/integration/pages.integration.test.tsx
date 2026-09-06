/** Real pages + real API (harness): catches contract drift the MSW mocks cannot. */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { server } from '@/test/server';
import { renderPage } from '@/test/renderPage';
import { tokenStore } from '@/services/auth/tokenStore';
import { authApi, loadPrincipal } from '@/services/auth/session';
import type { Principal } from '@/services/auth/principal';
import VouchersPage from '@/features/vouchers/pages/VouchersPage';
import PlansPage from '@/features/plans/pages/PlansPage';
import SessionsPage from '@/features/sessions/pages/SessionsPage';
import DashboardPage from '@/features/dashboard/pages/DashboardPage';

let principal: Principal;

beforeAll(async () => {
  server.close();
  tokenStore.set(await authApi.login('manager', 'Passw0rd!2026'));
  principal = await loadPrincipal();
});
afterAll(() => server.listen({ onUnhandledRequest: 'error' }));

describe.runIf(import.meta.env.LIVE_API === '1')('pages render live data', () => {
  it('dashboard', async () => {
    renderPage(<DashboardPage />, { principal, path: '/' });
    expect(
      await screen.findByRole('heading', { name: 'Wuse Hotspot overview' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Active / registered')).toBeInTheDocument();
    expect(await screen.findByText(/^Updated /)).toBeInTheDocument();
  });

  it('vouchers list with a status filter', async () => {
    renderPage(<VouchersPage />, {
      principal,
      path: '/vouchers',
      route: '/vouchers?status=active',
    });
    const table = await screen.findByRole('table', { name: 'Vouchers' });
    const badges = await within(table).findAllByText('Active');
    expect(badges.length).toBeGreaterThan(0);
    expect(within(table).queryByText('Unused')).not.toBeInTheDocument();
  });

  it('plans', async () => {
    renderPage(<PlansPage />, { principal, path: '/plans' });
    const table = await screen.findByRole('table', { name: 'Internet plans' });
    expect(await within(table).findByText('Daily 1GB')).toBeInTheDocument();
    expect(within(table).getByText('₦500.00')).toBeInTheDocument();
  });

  it('live sessions', async () => {
    renderPage(<SessionsPage />, { principal, path: '/sessions' });
    const table = await screen.findByRole('table', { name: 'Live sessions' });
    expect(await within(table).findByText('WH10002')).toBeInTheDocument();
    expect(within(table).getAllByText('mikrotik-wuse-01').length).toBeGreaterThan(0);
  });
});
