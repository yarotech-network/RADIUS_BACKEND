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
import { PaymentRedirect } from '@/features/payments/pages/PaymentRedirect';

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
const RoutersPage = lazyRoute(lazy(() => import('@/features/routers/pages/RoutersPage')));
const NewRouterPage = lazyRoute(lazy(() => import('@/features/routers/pages/NewRouterPage')));
const RouterOperationsPage = lazyRoute(
  lazy(() => import('@/features/routers/pages/RouterOperationsPage')),
);
const RouterDetailPage = lazyRoute(lazy(() => import('@/features/routers/pages/RouterDetailPage')));
const AgentsPage = lazyRoute(lazy(() => import('@/features/agents/pages/AgentsPage')));
const AgentDetailPage = lazyRoute(lazy(() => import('@/features/agents/pages/AgentDetailPage')));
const DevicesPage = lazyRoute(lazy(() => import('@/features/devices/pages/DevicesPage')));
const PaymentsPage = lazyRoute(lazy(() => import('@/features/payments/pages/PaymentsPage')));
const RecoveryPage = lazyRoute(lazy(() => import('@/features/payments/pages/RecoveryPage')));
const AuditPage = lazyRoute(lazy(() => import('@/features/audit/pages/AuditPage')));
const StorefrontPage = lazyRoute(lazy(() => import('@/features/storefront/pages/StorefrontPage')));
const PaymentResultPage = lazyRoute(
  lazy(() => import('@/features/storefront/pages/PaymentResultPage')),
);
const PricingPage = lazyRoute(lazy(() => import('@/features/storefront/pages/PricingPage')));
const AgentHomePage = lazyRoute(lazy(() => import('@/features/agent/pages/AgentHomePage')));
const AgentSellPage = lazyRoute(lazy(() => import('@/features/agent/pages/AgentSellPage')));
const AgentWalletPage = lazyRoute(lazy(() => import('@/features/agent/pages/AgentWalletPage')));
const AgentVouchersPage = lazyRoute(lazy(() => import('@/features/agent/pages/AgentVouchersPage')));
const AgentProfilePage = lazyRoute(lazy(() => import('@/features/agent/pages/AgentProfilePage')));
const SettingsLayout = lazyRoute(lazy(() => import('@/features/settings/pages/SettingsLayout')));
const GeneralSettingsPage = lazyRoute(
  lazy(() => import('@/features/settings/pages/GeneralSettingsPage')),
);
const BillingSettingsPage = lazyRoute(
  lazy(() => import('@/features/settings/pages/BillingSettingsPage')),
);
const TeamSettingsPage = lazyRoute(
  lazy(() => import('@/features/settings/pages/TeamSettingsPage')),
);
const SubscriptionSettingsPage = lazyRoute(
  lazy(() => import('@/features/settings/pages/SubscriptionSettingsPage')),
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
  {
    element: <RequireCapability capability="payments.view" />,
    children: [
      { path: 'payments', Component: PaymentsPage },
      { path: 'payments/:id', element: <PaymentRedirect /> },
    ],
  },
  {
    element: <RequireCapability capability="payments.recovery.view" />,
    children: [{ path: 'payments/recovery', Component: RecoveryPage }],
  },
  {
    element: <RequireCapability capability="routers.view" />,
    children: [
      { path: 'routers', Component: RoutersPage },
      { path: 'routers/:id', Component: RouterDetailPage },
    ],
  },
  {
    element: <RequireCapability capability="routers.manage" />,
    children: [
      { path: 'routers/new', Component: NewRouterPage },
      { path: 'routers/operations', Component: RouterOperationsPage },
    ],
  },
  {
    element: <RequireCapability capability="agents.manage" />,
    children: [
      { path: 'agents', Component: AgentsPage },
      { path: 'agents/:id', Component: AgentDetailPage },
    ],
  },
  {
    element: <RequireCapability capability="devices.view" />,
    children: [{ path: 'devices', Component: DevicesPage }],
  },
  {
    element: <RequireCapability capability="audit.view" />,
    children: [{ path: 'audit', Component: AuditPage }],
  },
  {
    element: <RequireCapability anyOf={['settings.profile', 'team.view', 'subscription.view']} />,
    children: [
      {
        path: 'settings',
        Component: SettingsLayout,
        children: [
          { index: true, element: <Navigate to="/settings/general" replace /> },
          { path: 'profile', element: <Navigate to="/settings/general" replace /> },
          { path: 'general', Component: GeneralSettingsPage },
          {
            element: <RequireCapability capability="settings.billing" />,
            children: [{ path: 'billing', Component: BillingSettingsPage }],
          },
          {
            element: <RequireCapability capability="team.view" />,
            children: [{ path: 'team', Component: TeamSettingsPage }],
          },
          {
            element: <RequireCapability capability="subscription.view" />,
            children: [{ path: 'subscription', Component: SubscriptionSettingsPage }],
          },
        ],
      },
    ],
  },
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
  { index: true, Component: AgentHomePage },
  { path: 'sell', Component: AgentSellPage },
  { path: 'wallet/*', Component: AgentWalletPage },
  { path: 'vouchers', Component: AgentVouchersPage },
  { path: 'profile', Component: AgentProfilePage },
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
          { path: '/s/:slug/*', Component: StorefrontPage },
          { path: '/pay/result', Component: PaymentResultPage },
          { path: '/pricing', Component: PricingPage },
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
