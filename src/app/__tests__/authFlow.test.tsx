import { http as mswHttp, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/test/server';
import { API, makeAssignment, makeUser, paginated } from '@/test/fixtures';
import { createTestQueryClient } from '@/test/render';
import { ToastProvider } from '@/components/feedback/Toaster';
import { AuthProvider } from '@/app/auth/AuthProvider';
import { tokenStore } from '@/services/auth/tokenStore';
import { setActiveTenantHeader } from '@/services/api/http';
import { RedirectIfAuthenticated, RequireAuth, RequireSurface } from '@/app/auth/guards';
import { PublicLayout } from '@/app/shell/PublicLayout';
import { WorkspaceLayout } from '@/app/shell/WorkspaceLayout';
import { PlatformLayout } from '@/app/shell/PlatformLayout';
import { AgentLayout } from '@/app/shell/AgentLayout';
import LoginPage from '@/features/auth/pages/LoginPage';
import RegisterPage from '@/features/auth/pages/RegisterPage';
import VerifyEmailPage from '@/features/auth/pages/VerifyEmailPage';
import AgentLoginPage from '@/features/auth/pages/AgentLoginPage';
import SelectTenantPage from '@/features/auth/pages/SelectTenantPage';
import NoAccessPage from '@/features/auth/pages/NoAccessPage';
import type { User } from '@/types/api';

const routes: RouteObject[] = [
  {
    Component: RedirectIfAuthenticated,
    children: [
      {
        Component: PublicLayout,
        children: [
          { path: '/login', Component: LoginPage },
          { path: '/agent/login', Component: AgentLoginPage },
        ],
      },
      { path: '/register', Component: RegisterPage },
      { path: '/verify-email', Component: VerifyEmailPage },
    ],
  },
  {
    Component: RequireAuth,
    children: [
      {
        Component: PublicLayout,
        children: [
          { path: '/select-tenant', Component: SelectTenantPage },
          { path: '/no-access', Component: NoAccessPage },
        ],
      },
      {
        element: <RequireSurface surface="platform" />,
        children: [
          {
            path: '/platform',
            Component: PlatformLayout,
            children: [{ index: true, element: <h1>Platform overview</h1> }],
          },
        ],
      },
      {
        element: <RequireSurface surface="agent" />,
        children: [
          {
            path: '/agent',
            Component: AgentLayout,
            children: [{ index: true, element: <h1>Agent home</h1> }],
          },
        ],
      },
      {
        element: <RequireSurface surface="workspace" />,
        children: [
          {
            path: '/',
            Component: WorkspaceLayout,
            children: [
              { path: 'dashboard', element: <h1>Dashboard page</h1> },
              { path: 'vouchers', element: <h1>Vouchers page</h1> },
            ],
          },
        ],
      },
    ],
  },
];

function renderApp(initialPath: string) {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  const client = createTestQueryClient();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return router;
}

function mockSession(
  user: User,
  assignments = paginated([] as ReturnType<typeof makeAssignment>[]),
) {
  server.use(
    mswHttp.get(`${API}/auth/user/`, () => HttpResponse.json(user)),
    mswHttp.get(`${API}/staff/assignments/`, () => HttpResponse.json(assignments)),
    mswHttp.get(`${API}/tenants/`, () =>
      HttpResponse.json({ detail: 'forbidden' }, { status: 403 }),
    ),
    mswHttp.post(`${API}/auth/logout/`, () => new HttpResponse(null, { status: 205 })),
  );
}

beforeEach(() => {
  tokenStore.clear();
  setActiveTenantHeader(null);
  window.localStorage.clear();
});

describe('sign in and landing per role', () => {
  it('owner signs in and lands on the workspace dashboard with role-aware navigation', async () => {
    const user = makeUser('owner');
    mockSession(user);
    server.use(
      mswHttp.post(`${API}/auth/login/`, () =>
        HttpResponse.json({ access: 'A', refresh: 'R', user }),
      ),
    );
    const router = renderApp('/login');
    await userEvent.type(await screen.findByLabelText(/username/i), 'ada');
    await userEvent.type(screen.getByLabelText(/^password/i), 'secret123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
    // Owner sees Settings + Agents; nav rendered in sidebar + drawer, so use getAllBy.
    expect(screen.getAllByRole('link', { name: 'Settings' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Agents' }).length).toBeGreaterThan(0);
    expect(tokenStore.getRefresh()).toBe('R');
  });

  it('tenant staff only see read-only navigation', async () => {
    tokenStore.set({ access: 'A', refresh: 'R' });
    mockSession(makeUser('staff'));
    renderApp('/dashboard');
    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Agents' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Audit log' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Vouchers' }).length).toBeGreaterThan(0);
  });

  it('shows a clear message for wrong credentials and a countdown for throttling', async () => {
    server.use(
      mswHttp.post(`${API}/auth/login/`, () =>
        HttpResponse.json({ error: 'Invalid credentials' }, { status: 401 }),
      ),
    );
    renderApp('/login');
    await userEvent.type(await screen.findByLabelText(/username/i), 'ada');
    await userEvent.type(screen.getByLabelText(/^password/i), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect username or password.');

    server.use(
      mswHttp.post(`${API}/auth/login/`, () =>
        HttpResponse.json(
          { detail: 'Request was throttled.' },
          { status: 429, headers: { 'Retry-After': '30' } },
        ),
      ),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/try again in 30 seconds/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled();
  });

  it('platform admin lands on the console and is kept out of the workspace', async () => {
    tokenStore.set({ access: 'A', refresh: 'R' });
    mockSession(makeUser('platform_admin'));
    const router = renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Platform overview' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/platform');
  });

  it('agent login follows up with auth/user and lands in the portal', async () => {
    mockSession(makeUser('agent'));
    server.use(
      mswHttp.post(`${API}/agent/login/`, () =>
        HttpResponse.json({
          access: 'A',
          refresh: 'R',
          agent: { id: 1, username: 'ada', shop_name: 'Shop' },
        }),
      ),
    );
    const router = renderApp('/agent/login');
    await userEvent.type(await screen.findByLabelText(/username/i), 'ada');
    await userEvent.type(screen.getByLabelText(/^password/i), 'secret123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Agent home' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/agent');
  });

  it('agent login explains inactive accounts (403)', async () => {
    server.use(
      mswHttp.post(`${API}/agent/login/`, () =>
        HttpResponse.json({ error: 'Agent account is not active' }, { status: 403 }),
      ),
    );
    renderApp('/agent/login');
    await userEvent.type(await screen.findByLabelText(/username/i), 'ada');
    await userEvent.type(screen.getByLabelText(/^password/i), 'secret123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/not active yet/i);
  });

  it('platform staff with several assignments must pick a tenant, then X-Tenant-ID is sent', async () => {
    tokenStore.set({ access: 'A', refresh: 'R' });
    const assignments = paginated([
      makeAssignment(10, ['routers.view']),
      makeAssignment(11, ['vouchers.generate', 'vouchers.print']),
    ]);
    mockSession(makeUser('platform_staff'), assignments);
    const router = renderApp('/vouchers');
    expect(await screen.findByRole('heading', { name: 'Choose a tenant' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/select-tenant');
    await userEvent.click(screen.getByRole('button', { name: /Tenant #11/ }));
    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument();
    // Vouchers is visible thanks to the vouchers.* grants, Routers is not (different tenant).
    expect(screen.getAllByRole('link', { name: 'Vouchers' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: 'Routers' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem('yr.ctx.tenant.42')).toBe('11');
  });

  it('platform staff with a single assignment skip the picker', async () => {
    tokenStore.set({ access: 'A', refresh: 'R' });
    mockSession(makeUser('platform_staff'), paginated([makeAssignment(10, ['routers.view'])]));
    renderApp('/dashboard');
    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Routers' }).length).toBeGreaterThan(0);
  });

  it('users without any role land on no-access with their user id', async () => {
    tokenStore.set({ access: 'A', refresh: 'R' });
    mockSession(makeUser('user'));
    renderApp('/');
    expect(await screen.findByText(/not linked to a workspace/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy user id 42/i })).toBeInTheDocument();
  });

  it('anonymous visitors are redirected to login and back after signing in', async () => {
    const user = makeUser('manager');
    mockSession(user);
    server.use(
      mswHttp.post(`${API}/auth/login/`, () =>
        HttpResponse.json({ access: 'A', refresh: 'R', user }),
      ),
    );
    const router = renderApp('/vouchers');
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/username/i), 'ada');
    await userEvent.type(screen.getByLabelText(/^password/i), 'secret123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Vouchers page' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/vouchers');
  });

  it('signs out from the account menu and blacklists the refresh token', async () => {
    tokenStore.set({ access: 'A', refresh: 'R' });
    let logoutBody: unknown = null;
    mockSession(makeUser('owner'));
    server.use(
      mswHttp.post(`${API}/auth/logout/`, async ({ request }) => {
        logoutBody = await request.json();
        return new HttpResponse(null, { status: 205 });
      }),
    );
    const router = renderApp('/dashboard');
    await screen.findByRole('heading', { name: 'Dashboard page' });
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    await userEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    expect(logoutBody).toEqual({ refresh: 'R' });
    expect(tokenStore.hasSession()).toBe(false);
  });

  it('new tenant registers, confirms the emailed OTP and lands in the workspace', async () => {
    const user = makeUser('owner');
    const seenCodes: string[] = [];
    mockSession(user);
    server.use(
      mswHttp.post(`${API}/auth/register/`, () =>
        HttpResponse.json(
          { user, detail: 'Verification code sent to your email.' },
          { status: 201 },
        ),
      ),
      mswHttp.post(`${API}/auth/verify-email/`, async ({ request }) => {
        seenCodes.push(String(((await request.json()) as { code: string }).code));
        return HttpResponse.json({ access: 'A', refresh: 'R', user });
      }),
    );

    const router = renderApp('/register');
    await userEvent.type(await screen.findByLabelText(/business name/i), 'New Network');
    await userEvent.type(screen.getByLabelText(/username/i), 'newowner');
    await userEvent.type(screen.getByLabelText(/phone/i), '08012345678');
    await userEvent.type(screen.getByLabelText(/^email/i), 'new@example.com');
    await userEvent.type(screen.getAllByLabelText(/^password/i)[0]!, 'StrongPass-4821');
    await userEvent.type(screen.getAllByLabelText(/confirm password/i)[0]!, 'StrongPass-4821');
    await userEvent.click(screen.getByRole('button', { name: 'Create workspace' }));

    // Registration withholds tokens and moves to the OTP step.
    expect(await screen.findByRole('heading', { name: /verify your email/i })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/verify-email');
    expect(screen.getByDisplayValue('new@example.com')).toBeInTheDocument();
    expect(tokenStore.hasSession()).toBe(false);

    for (let i = 0; i < 6; i++) {
      await userEvent.type(screen.getByLabelText(`Digit ${i + 1} of 6`), String(i + 1));
    }

    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
    expect(seenCodes).toEqual(['123456']);
    expect(tokenStore.getRefresh()).toBe('R');
  });

  it('login with an unverified email is redirected to the verification step', async () => {
    server.use(
      mswHttp.post(`${API}/auth/login/`, () =>
        HttpResponse.json(
          {
            error: 'Verify your email address before signing in.',
            code: 'email_not_verified',
            email: 'pending@example.com',
          },
          { status: 403 },
        ),
      ),
    );

    const router = renderApp('/login');
    await userEvent.type(await screen.findByLabelText(/username/i), 'pending');
    await userEvent.type(screen.getByLabelText(/^password/i), 'secret123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('heading', { name: /verify your email/i })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/verify-email');
    expect(screen.getByDisplayValue('pending@example.com')).toBeInTheDocument();
  });

  it('expired refresh token on bootstrap lands on login without crashing', async () => {
    tokenStore.set({ access: '', refresh: 'dead' });
    window.sessionStorage.clear();
    server.use(
      mswHttp.post(`${API}/auth/token/refresh/`, () =>
        HttpResponse.json(
          { detail: 'Token is invalid or expired', code: 'token_not_valid' },
          { status: 401 },
        ),
      ),
    );
    const router = renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });
});
