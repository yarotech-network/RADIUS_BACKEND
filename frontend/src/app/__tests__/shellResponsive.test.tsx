import { http as mswHttp, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/test/server';
import { API, makeUser } from '@/test/fixtures';
import { createTestQueryClient } from '@/test/render';
import { ToastProvider } from '@/components/feedback/Toaster';
import { AuthProvider } from '@/app/auth/AuthProvider';
import { tokenStore } from '@/services/auth/tokenStore';
import { RequireAuth, RequireSurface } from '@/app/auth/guards';
import { WorkspaceLayout } from '@/app/shell/WorkspaceLayout';
import { AgentLayout } from '@/app/shell/AgentLayout';

function mount(path: string) {
  const router = createMemoryRouter(
    [
      {
        Component: RequireAuth,
        children: [
          {
            element: <RequireSurface surface="workspace" />,
            children: [
              {
                path: '/',
                Component: WorkspaceLayout,
                children: [
                  { index: true, element: <h1>Dashboard page</h1> },
                  { path: 'plans', element: <h1>Plans page</h1> },
                ],
              },
            ],
          },
          {
            element: <RequireSurface surface="agent" />,
            children: [
              {
                path: '/agent',
                Component: AgentLayout,
                children: [
                  { index: true, element: <h1>Agent home</h1> },
                  { path: 'wallet', element: <h1>Wallet page</h1> },
                ],
              },
            ],
          },
        ],
      },
    ],
    { initialEntries: [path] },
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

beforeEach(() => {
  tokenStore.set({ access: 'A', refresh: 'R' });
  window.localStorage.clear();
  window.localStorage.setItem('yr.auth.refresh', 'R');
});

describe('workspace shell', () => {
  it('renders sidebar groups, the mobile bottom bar, and a "More" drawer with the full navigation', async () => {
    server.use(mswHttp.get(`${API}/auth/user/`, () => HttpResponse.json(makeUser('owner'))));
    mount('/');
    await screen.findByRole('heading', { name: 'Dashboard page' });
    const navs = screen.getAllByRole('navigation', { name: 'Primary' });
    expect(navs.length).toBe(2); // sidebar + mobile bottom bar
    const bottom = navs[1]!;
    expect(within(bottom).getAllByRole('link').length).toBeLessThanOrEqual(4);
    await userEvent.click(within(bottom).getByRole('button', { name: 'More' }));
    const drawer = screen.getByRole('dialog', { name: 'Navigation' });
    expect(within(drawer).getByRole('link', { name: 'Audit log' })).toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole('link', { name: 'Plans' }));
    expect(await screen.findByRole('heading', { name: 'Plans page' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Navigation' })).not.toBeInTheDocument();
  });

  it('remembers the collapsed sidebar preference', async () => {
    server.use(mswHttp.get(`${API}/auth/user/`, () => HttpResponse.json(makeUser('manager'))));
    mount('/');
    await screen.findByRole('heading', { name: 'Dashboard page' });
    await userEvent.click(screen.getByRole('button', { name: /collapse navigation/i }));
    expect(window.localStorage.getItem('yr.ui.sidebar')).toBe('1');
    expect(screen.getByRole('button', { name: /expand navigation/i })).toBeInTheDocument();
  });

  it('has a skip link and a main landmark', async () => {
    server.use(mswHttp.get(`${API}/auth/user/`, () => HttpResponse.json(makeUser('staff'))));
    mount('/');
    await screen.findByRole('heading', { name: 'Dashboard page' });
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
  });
});

describe('agent shell', () => {
  it('renders five bottom tabs and navigates', async () => {
    server.use(mswHttp.get(`${API}/auth/user/`, () => HttpResponse.json(makeUser('agent'))));
    mount('/agent');
    await screen.findByRole('heading', { name: 'Agent home' });
    const navs = screen.getAllByRole('navigation', { name: 'Primary' });
    const bottom = navs[navs.length - 1]!;
    expect(within(bottom).getAllByRole('link')).toHaveLength(5);
    await userEvent.click(within(bottom).getByRole('link', { name: 'Wallet' }));
    expect(await screen.findByRole('heading', { name: 'Wallet page' })).toBeInTheDocument();
  });
});
