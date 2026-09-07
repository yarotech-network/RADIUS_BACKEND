import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LIVE_POLL_INTERVAL_MS } from '@/app/config/constants';
import type { LiveUsersParams } from '@/types/api';
import { dashboardApi } from './api';

export const dashboardKeys = {
  all: ['dashboard'] as const,
  stats: () => [...dashboardKeys.all, 'stats'] as const,
  live: (params: LiveUsersParams) => [...dashboardKeys.all, 'live', params] as const,
};

/** Smallest live list the dashboard attention ticker needs. */
export const DASHBOARD_LIVE_PARAMS = { page: 1, page_size: 1 } as const;

/** Options shared by the hook and navigation prefetch (phase 9). */
export function dashboardStatsQuery() {
  return {
    queryKey: dashboardKeys.stats(),
    queryFn: dashboardApi.stats,
    staleTime: 30_000,
    refetchInterval: 60_000,
  };
}

export function dashboardLiveQuery(params: LiveUsersParams) {
  return {
    queryKey: dashboardKeys.live(params),
    queryFn: () => dashboardApi.liveUsers(params),
    staleTime: 30_000,
  };
}

export function useDashboardStats() {
  return useQuery(dashboardStatsQuery());
}

export function useLiveUsers(params: LiveUsersParams, options: { live?: boolean } = {}) {
  return useQuery({
    ...dashboardLiveQuery(params),
    placeholderData: keepPreviousData,
    refetchInterval: options.live === false ? false : LIVE_POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });
}

export function useDisconnectSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) => dashboardApi.disconnect(sessionId),
    onSuccess: () => client.invalidateQueries({ queryKey: [...dashboardKeys.all, 'live'] }),
  });
}
