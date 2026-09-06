import { lazy } from 'react';
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { lazyRoute } from './lazy';
import { RootLayout } from '@/app/RootLayout';
import {
  RedirectIfAuthenticated,
  RequireAuth,
  RequireBooted,
  RequireSurface,
} from '@/app/auth/guards';
import { PublicLayout } from '@/app/shell/PublicLayout';
import { WorkspaceLayout } from '@/app/shell/WorkspaceLayout';
import { PlatformLayout } from '@/app/shell/PlatformLayout';
import { AgentLayout } from '@/app/shell/AgentLayout';
import { NotFoundPage } from '@/app/shell/NotFoundPage';
import { ComingSoon } from '@/app/shell/ComingSoon';
import { RequireCapability } from '@/app/auth/RequireCapability';

/* ---------- lazily loaded pages (one chunk per page) ---------- */
const LoginPage = lazyRoute(lazy(() => import('@/features/auth/pages/LoginPage')));
const AgentLoginPage = lazyRoute(lazy(() => import('@/features/auth/pages/AgentLoginPage')));
const RegisterPage = lazyRoute(lazy(() => import('@/features/auth/pages/RegisterPage')));
const ForgotPasswordPage = lazyRoute(
  lazy(() => import('@/features/auth/pages/ForgotPasswordPage')),
);
const ResetPasswordPage = lazyRoute(lazy(() => import('@/features/auth/pages/ResetPasswordPage')));
const AcceptInvitationPage = lazyRoute(
  lazy(() => import('@/features/auth/pages/AcceptInvitationPage')),
);
const SelectTenantPage = lazyRoute(lazy(() => import('@/features/auth/pages/SelectTenantPage')));
const NoAccessPage = lazyRoute(lazy(() => import('@/features/auth/pages/NoAccessPage')));

const DashboardPage = lazyRoute(lazy(() => import('@/features/dashboard/pages/DashboardPage')));
const SessionsPage = lazyRoute(lazy(() => import('@/features/sessions/pages/SessionsPage')));
const PlansPage = lazyRoute(lazy(() => import('@/features/plans/pages/PlansPage')));
const VouchersPage = lazyRoute(lazy(() => import('@/features/vouchers/pages/VouchersPage')));
const GenerateVouchersPage = lazyRoute(
  lazy(() => import('@/features/vouchers/pages/GenerateVouchersPage')),
);
const VoucherDetailPage = lazyRoute(
  lazy(() => import('@/features/vouchers/pages/VoucherDetailPage')),
);

const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: '/__dev/ui',
        Component: lazyRoute(lazy(() => import('@/features/dev/UiGalleryPage'))),
      },
    ]
  : [];

/* ---------- workspace (tenant members + platform staff) ---------- */
const workspaceRoutes: RouteObject[] = [
  { index: true, Component: DashboardPage },
  { path: 'dashboard', element: <Navigate to="/" replace /> },
  {
    element: <RequireCapability capability="sessions.view" />,
    children: [{ path: 'sessions', Component: SessionsPage }],
  },
  {
    element: <RequireCapability capability="plans.view" />,
    children: [{ path: 'plans', Component: PlansPage }],
  },
  {
    element: <RequireCapability capability="vouchers.view" />,
    children: [
      { path: 'vouchers', Component: VouchersPage },
      { path: 'vouchers/:id', Component: VoucherDetailPage },
    ],
  },
  {
    element: <RequireCapability capability="vouchers.generate" />,
    children: [{ path: 'vouchers/generate', Component: GenerateVouchersPage }],
  },
  { path: 'payments/*', element: <ComingSoon title="Payments" phase={6} /> },
  { path: 'routers/*', element: <ComingSoon title="Routers" phase={5} /> },
  { path: 'agents/*', element: <ComingSoon title="Agents" phase={5} /> },
  { path: 'devices', element: <ComingSoon title="Devices" phase={5} /> },
  { path: 'audit', element: <ComingSoon title="Audit log" phase={6} /> },
  { path: 'settings/*', element: <ComingSoon title="Settings" phase={6} /> },
  { path: '*', element: <NotFoundPage /> },
];

/* ---------- platform console (platform admin) ---------- */
const platformRoutes: RouteObject[] = [
  { index: true, element: <ComingSoon title="Platform overview" phase={8} /> },
  { path: 'tenants/*', element: <ComingSoon title="Tenants" phase={8} /> },
  { path: 'routers', element: <ComingSoon title="Router fleet" phase={8} /> },
  { path: 'payments', element: <ComingSoon title="Payments" phase={8} /> },
  { path: 'staff', element: <ComingSoon title="Staff" phase={8} /> },
  { path: 'audit', element: <ComingSoon title="Audit log" phase={8} /> },
  { path: '*', element: <NotFoundPage homePath="/platform" /> },
];

/* ---------- agent portal ---------- */
const agentRoutes: RouteObject[] = [
  { index: true, element: <ComingSoon title="Home" phase={7} /> },
  { path: 'sell', element: <ComingSoon title="Sell vouchers" phase={7} /> },
  { path: 'wallet/*', element: <ComingSoon title="Wallet" phase={7} /> },
  { path: 'vouchers', element: <ComingSoon title="My vouchers" phase={7} /> },
  { path: 'profile', element: <ComingSoon title="Profile" phase={7} /> },
  { path: '*', element: <NotFoundPage homePath="/agent" /> },
];

export const router = createBrowserRouter([
  {
    Component: RootLayout,
    children: [
      /* Public-only auth pages */
      {
        Component: RedirectIfAuthenticated,
        children: [
          {
            Component: PublicLayout,
            children: [
              { path: '/login', Component: LoginPage },
              { path: '/agent/login', Component: AgentLoginPage },
              { path: '/register', Component: RegisterPage },
              { path: '/forgot-password', Component: ForgotPasswordPage },
              { path: '/reset-password', Component: ResetPasswordPage },
            ],
          },
        ],
      },
      /* Public pages that work with or without a session */
      {
        element: (
          <RequireBooted>
            <PublicLayout />
          </RequireBooted>
        ),
        children: [
          { path: '/accept-invitation', Component: AcceptInvitationPage },
          { path: '/s/:slug/*', element: <ComingSoon title="Storefront" phase={7} /> },
          { path: '/pay/result', element: <ComingSoon title="Payment result" phase={7} /> },
          { path: '/pricing', element: <ComingSoon title="Pricing" phase={7} /> },
          ...devRoutes,
        ],
      },
      /* Authenticated */
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
            children: [{ path: '/platform', Component: PlatformLayout, children: platformRoutes }],
          },
          {
            element: <RequireSurface surface="agent" />,
            children: [{ path: '/agent', Component: AgentLayout, children: agentRoutes }],
          },
          {
            element: <RequireSurface surface="workspace" />,
            children: [{ path: '/', Component: WorkspaceLayout, children: workspaceRoutes }],
          },
        ],
      },
    ],
  },
]);
