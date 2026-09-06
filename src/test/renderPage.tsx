import type { ReactElement, ReactNode } from 'react';
import { render } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router';
import { vi } from 'vitest';
import { ToastProvider } from '@/components/feedback/Toaster';
import { AuthContext, type AuthContextValue } from '@/app/auth/authContext';
import { derivePrincipal, type Principal } from '@/services/auth/principal';
import type { User } from '@/types/api';
import { makeUser } from './fixtures';
import { createTestQueryClient } from './render';

/**
 * Render an authenticated feature page with a fixed principal (no auth bootstrap requests).
 * `path` is the route pattern (e.g. "/vouchers/:id") and `route` the initial URL.
 */
export function renderPage(
  ui: ReactElement,
  options: {
    role?: User['role'];
    principal?: Principal;
    path?: string;
    route?: string;
    extraRoutes?: ReactNode;
  } = {},
) {
  const principal = options.principal ?? derivePrincipal(makeUser(options.role ?? 'manager'));
  const auth: AuthContextValue = {
    status: 'authenticated',
    principal,
    signOutReason: null,
    signIn: vi.fn(),
    refreshPrincipal: vi.fn(),
    signOut: vi.fn(),
    selectTenant: vi.fn(),
  };
  const client = createTestQueryClient();
  const path = options.path ?? '/';
  const route = options.route ?? path;
  const result = render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AuthContext.Provider value={auth}>
          <MemoryRouter initialEntries={[route]}>
            <Routes>
              <Route path={path} element={ui} />
              {options.extraRoutes}
              <Route path="*" element={<div data-testid="location-fallback" />} />
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...result, client, auth };
}
