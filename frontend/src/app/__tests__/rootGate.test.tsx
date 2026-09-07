import { http as mswHttp, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/test/server';
import { API, makeUser, paginated } from '@/test/fixtures';
import { createTestQueryClient } from '@/test/render';
import { ToastProvider } from '@/components/feedback/Toaster';
import { AuthProvider } from '@/app/auth/AuthProvider';
import { RequireAuth, RequireBooted } from '@/app/auth/guards';
import { PublicLayout } from '@/app/shell/PublicLayout';
import { tokenStore } from '@/services/auth/tokenStore';
import { RootGate } from '@/app/router/RootGate';

function renderRoot() {
  const router = createMemoryRouter(
    [
      {
        element: (
          <RequireBooted>
            <PublicLayout />
          </RequireBooted>
        ),
        children: [{ path: '/', element: <RootGate /> }],
      },
      {
        Component: RequireAuth,
        children: [{ path: '/dashboard', element: <h1>Dashboard page</h1> }],
      },
    ],
    { initialEntries: ['/'] },
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

function mockPricing() {
  server.use(mswHttp.get(`${API}/pricing/`, () => HttpResponse.json(paginated([]))));
}

beforeEach(() => {
  tokenStore.clear();
  window.localStorage.clear();
});

describe('root gate (/)', () => {
  it('shows the public landing page to anonymous visitors', async () => {
    mockPricing();
    renderRoot();

    expect(
      await screen.findByRole('heading', { name: /run your wi-fi business/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create your workspace/i })).toBeInTheDocument();
  });

  it('redirects signed-in users straight to the workspace dashboard', async () => {
    tokenStore.set({ access: 'A', refresh: 'R' });
    server.use(
      mswHttp.get(`${API}/auth/user/`, () => HttpResponse.json(makeUser('owner'))),
      mswHttp.get(`${API}/staff/assignments/`, () => HttpResponse.json(paginated([]))),
    );

    const router = renderRoot();

    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
  });
});
