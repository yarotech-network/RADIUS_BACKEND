import { http as mswHttp, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/test/server';
import { API, makeUser, paginated } from '@/test/fixtures';
import { createTestQueryClient } from '@/test/render';
import { ToastProvider } from '@/components/feedback/Toaster';
import { AuthProvider } from '@/app/auth/AuthProvider';
import { RedirectIfAuthenticated, RequireAuth } from '@/app/auth/guards';
import { tokenStore } from '@/services/auth/tokenStore';
import VerifyEmailPage from './VerifyEmailPage';

function renderVerifyEmail(email?: string) {
  const initialEntries = [
    email ? { pathname: '/verify-email', state: { email } } : '/verify-email',
  ];
  const router = createMemoryRouter(
    [
      {
        Component: RedirectIfAuthenticated,
        children: [
          { path: '/verify-email', Component: VerifyEmailPage },
          { path: '/login', element: <h1>Login page</h1> },
        ],
      },
      {
        Component: RequireAuth,
        children: [{ path: '/dashboard', element: <h1>Dashboard page</h1> }],
      },
    ],
    { initialEntries },
  );
  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ToastProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return router;
}

async function typeCode(code: string) {
  for (let i = 0; i < code.length; i++) {
    await userEvent.type(screen.getByLabelText(`Digit ${i + 1} of 6`), code[i]!);
  }
}

const user = makeUser('owner');
const tokens = { access: 'A', refresh: 'R', user };

function mockSessionEndpoints() {
  server.use(
    mswHttp.get(`${API}/auth/user/`, () => HttpResponse.json(user)),
    mswHttp.get(`${API}/staff/assignments/`, () => HttpResponse.json(paginated([]))),
    mswHttp.get(`${API}/tenants/`, () =>
      HttpResponse.json({ detail: 'forbidden' }, { status: 403 }),
    ),
    mswHttp.post(`${API}/auth/logout/`, () => new HttpResponse(null, { status: 205 })),
  );
}

beforeEach(() => {
  tokenStore.clear();
  window.localStorage.clear();
  mockSessionEndpoints();
});

afterEach(() => {
  server.resetHandlers();
});

describe('email verification', () => {
  it('auto-submits the OTP and signs the new owner straight into the workspace', async () => {
    const seen: string[] = [];
    server.use(
      mswHttp.post(`${API}/auth/verify-email/`, async ({ request }) => {
        seen.push(String(((await request.json()) as { code: string }).code));
        return HttpResponse.json(tokens);
      }),
    );

    const router = renderVerifyEmail('owner@example.com');

    expect(await screen.findByDisplayValue('owner@example.com')).toBeInTheDocument();
    await typeCode('123456');

    expect(seen).toEqual(['123456']);
    expect(tokenStore.hasSession()).toBe(true);
    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
    expect(tokenStore.getRefresh()).toBe('R');
  });

  it('shows the server error and clears the boxes on a wrong code', async () => {
    server.use(
      mswHttp.post(
        `${API}/auth/verify-email/`,
        () =>
          HttpResponse.json(
            { detail: 'Incorrect code. 4 attempts left.', code: 'invalid_code' },
            { status: 400 },
          ),
        { once: true },
      ),
    );
    renderVerifyEmail('owner@example.com');

    await screen.findByLabelText('Digit 1 of 6');
    await typeCode('000000');

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect code/i);
    await waitFor(() => expect(screen.getByLabelText('Digit 1 of 6')).toHaveValue(''));
  });

  it('shows the resend countdown while the code is fresh', async () => {
    server.use(
      mswHttp.post(`${API}/auth/resend-verification/`, () =>
        HttpResponse.json({ message: 'If an unverified account exists…' }),
      ),
    );
    renderVerifyEmail('owner@example.com');
    expect(await screen.findByText(/resend available in 60s/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resend code' })).not.toBeInTheDocument();
  });

  it('requests a fresh code via the resend endpoint once the cooldown allows it', async () => {
    const bodies: string[] = [];
    server.use(
      mswHttp.post(`${API}/auth/resend-verification/`, async ({ request }) => {
        bodies.push(String(((await request.json()) as { email: string }).email));
        return HttpResponse.json({ message: 'If an unverified account exists…' });
      }),
    );

    const initialEntries = [{ pathname: '/verify-email', state: { email: 'owner@example.com' } }];
    const router = createMemoryRouter(
      [
        { path: '/verify-email', element: <VerifyEmailPage cooldownSeconds={0} /> },
        { path: '/dashboard', element: <h1>Dashboard page</h1> },
      ],
      { initialEntries },
    );
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <ToastProvider>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Resend code' }));

    expect(await screen.findByRole('status')).toHaveTextContent(/new code is on its way/i);
    expect(bodies).toEqual(['owner@example.com']);
  });
});
