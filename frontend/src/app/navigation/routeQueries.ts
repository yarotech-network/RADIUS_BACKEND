import type { QueryClient } from '@tanstack/react-query';
import { PAGE_SIZE_DEFAULT } from '@/app/config/constants';
import {
  DASHBOARD_LIVE_PARAMS,
  dashboardLiveQuery,
  dashboardStatsQuery,
} from '@/features/dashboard/queries';
import { AUDIT_LIST_DEFAULT_PARAMS, auditListQuery } from '@/features/audit/queries';
import {
  AGENT_FUNDINGS_DEFAULT_PARAMS,
  AGENT_HISTORY_DEFAULT_PARAMS,
  AGENT_RECENT_HISTORY_PARAMS,
  agentFundingsQuery,
  agentHistoryQuery,
  agentMeQuery,
  agentStatsQuery,
  agentWalletQuery,
} from '@/features/agent/queries';
import { AGENTS_LIST_DEFAULT_PARAMS, agentsListQuery } from '@/features/agents/queries';
import { DEVICES_LIST_DEFAULT_PARAMS, devicesListQuery } from '@/features/devices/queries';
import { PAYMENTS_LIST_DEFAULT_PARAMS, paymentsListQuery } from '@/features/payments/queries';
import {
  PLANS_LIST_DEFAULT_PARAMS,
  planOptionsQuery,
  plansListQuery,
} from '@/features/plans/queries';
import {
  PLATFORM_RECENT_TENANTS_PARAMS,
  TENANTS_LIST_DEFAULT_PARAMS,
  platformStatsQuery,
  tenantsListQuery,
} from '@/features/platform/queries';
import {
  ROUTERS_LIST_DEFAULT_PARAMS,
  routerOptionsQuery,
  routersListQuery,
} from '@/features/routers/queries';
import { VOUCHERS_LIST_DEFAULT_PARAMS, vouchersListQuery } from '@/features/vouchers/queries';

/**
 * Query prefetchers for the top navigation routes (phase 9). Each entry reuses
 * the feature's query factory and its DEFAULT_* params — the exact key the
 * page's first render produces — so the prefetched cache entry is a hit, never
 * a duplicate request.
 */
export const queryPrefetchers: Record<string, (client: QueryClient) => void> = {
  '/dashboard': (client) => {
    void client.prefetchQuery(dashboardStatsQuery());
    void client.prefetchQuery(dashboardLiveQuery(DASHBOARD_LIVE_PARAMS));
  },
  '/sessions': (client) => {
    void client.prefetchQuery(dashboardLiveQuery({ page: 1, page_size: PAGE_SIZE_DEFAULT }));
    void client.prefetchQuery(routerOptionsQuery());
  },
  '/plans': (client) => void client.prefetchQuery(plansListQuery(PLANS_LIST_DEFAULT_PARAMS)),
  '/vouchers': (client) => {
    void client.prefetchQuery(vouchersListQuery(VOUCHERS_LIST_DEFAULT_PARAMS));
    void client.prefetchQuery(planOptionsQuery(false));
  },
  '/payments': (client) =>
    void client.prefetchQuery(paymentsListQuery(PAYMENTS_LIST_DEFAULT_PARAMS)),
  '/agents': (client) => void client.prefetchQuery(agentsListQuery(AGENTS_LIST_DEFAULT_PARAMS)),
  '/routers': (client) => void client.prefetchQuery(routersListQuery(ROUTERS_LIST_DEFAULT_PARAMS)),
  '/devices': (client) => {
    void client.prefetchQuery(devicesListQuery(DEVICES_LIST_DEFAULT_PARAMS));
    void client.prefetchQuery(planOptionsQuery(false));
  },
  '/audit': (client) => void client.prefetchQuery(auditListQuery(AUDIT_LIST_DEFAULT_PARAMS)),
  '/platform': (client) => {
    void client.prefetchQuery(platformStatsQuery());
    void client.prefetchQuery(tenantsListQuery(PLATFORM_RECENT_TENANTS_PARAMS));
  },
  '/platform/tenants': (client) =>
    void client.prefetchQuery(tenantsListQuery(TENANTS_LIST_DEFAULT_PARAMS)),
  '/agent': (client) => {
    void client.prefetchQuery(agentMeQuery());
    void client.prefetchQuery(agentStatsQuery());
    void client.prefetchQuery(agentHistoryQuery(AGENT_RECENT_HISTORY_PARAMS));
  },
  '/agent/wallet': (client) => {
    void client.prefetchQuery(agentWalletQuery());
    void client.prefetchQuery(agentFundingsQuery(AGENT_FUNDINGS_DEFAULT_PARAMS));
  },
  '/agent/vouchers': (client) =>
    void client.prefetchQuery(agentHistoryQuery(AGENT_HISTORY_DEFAULT_PARAMS)),
};

export function prefetchQueries(path: string, client: QueryClient): void {
  queryPrefetchers[path]?.(client);
}
