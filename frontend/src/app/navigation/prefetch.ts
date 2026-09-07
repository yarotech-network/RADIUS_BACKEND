import type { QueryClient } from '@tanstack/react-query';

/**
 * Navigation prefetch (phase 9 — performance).
 *
 * - Every nav destination preloads its route chunk on hover/focus. The dynamic
 *   import specifiers are identical to the router's, so Vite dedupes them into
 *   the same chunks: hovering warms exactly the code the route will load.
 * - Top routes additionally prefetch the queries the page fires on mount, using
 *   the same query factories and default list params as the page (see
 *   ./routeQueries). Staleness is identical, so mounting the page never
 *   refetches what the prefetch just fetched (no duplicate requests).
 *
 * The query registry is itself imported lazily so the feature query modules
 * stay out of the initial entry chunk.
 */

/** Route chunk loaders — specifiers must match src/app/router/index.tsx. */
const routeChunks: Record<string, () => Promise<unknown>> = {
  /* workspace */
  '/': () => import('@/features/dashboard/pages/DashboardPage'),
  '/sessions': () => import('@/features/sessions/pages/SessionsPage'),
  '/plans': () => import('@/features/plans/pages/PlansPage'),
  '/vouchers': () => import('@/features/vouchers/pages/VouchersPage'),
  '/payments': () => import('@/features/payments/pages/PaymentsPage'),
  '/agents': () => import('@/features/agents/pages/AgentsPage'),
  '/routers': () => import('@/features/routers/pages/RoutersPage'),
  '/devices': () => import('@/features/devices/pages/DevicesPage'),
  '/audit': () => import('@/features/audit/pages/AuditPage'),
  '/settings': () => import('@/features/settings/pages/SettingsLayout'),
  /* platform console */
  '/platform': () => import('@/features/platform/pages/PlatformOverviewPage'),
  '/platform/tenants': () => import('@/features/platform/pages/TenantsPage'),
  '/platform/routers': () => import('@/features/platform/pages/PlatformRoutersPage'),
  '/platform/payments': () => import('@/features/platform/pages/PlatformPaymentsPage'),
  '/platform/staff': () => import('@/features/platform/pages/StaffPage'),
  '/platform/audit': () => import('@/features/platform/pages/PlatformAuditPage'),
  /* agent portal */
  '/agent': () => import('@/features/agent/pages/AgentHomePage'),
  '/agent/sell': () => import('@/features/agent/pages/AgentSellPage'),
  '/agent/wallet': () => import('@/features/agent/pages/AgentWalletPage'),
  '/agent/vouchers': () => import('@/features/agent/pages/AgentVouchersPage'),
  '/agent/profile': () => import('@/features/agent/pages/AgentProfilePage'),
};

export const ROUTE_CHUNK_PATHS: readonly string[] = Object.keys(routeChunks);

/** Routes whose data (not just their chunk) is prefetched on hover/focus. */
export const QUERY_ROUTE_PATHS: readonly string[] = [
  '/',
  '/sessions',
  '/plans',
  '/vouchers',
  '/payments',
  '/agents',
  '/routers',
  '/devices',
  '/audit',
  '/platform',
  '/platform/tenants',
  '/agent',
  '/agent/wallet',
  '/agent/vouchers',
] as const;

/** Loaded lazily so the feature query modules stay out of the entry chunk. */
function loadRouteQueries() {
  return import('./routeQueries');
}

let routeQueriesModule: ReturnType<typeof loadRouteQueries> | null = null;

/**
 * Warm a nav destination: its route chunk (always) and its first queries
 * (top routes, when a QueryClient is supplied). Fire-and-forget — never throws.
 */
export function prefetchRoute(path: string, client?: QueryClient): void {
  routeChunks[path]?.().catch(() => undefined);
  if (!client || !QUERY_ROUTE_PATHS.includes(path)) return;
  routeQueriesModule ??= loadRouteQueries();
  routeQueriesModule.then((module) => module.prefetchQueries(path, client)).catch(() => undefined);
}
