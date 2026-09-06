import { QueryClient } from '@tanstack/react-query';
import { isApiError } from '@/services/api/errors';

/**
 * Caching policy (analysis/03_FRONTEND_ARCHITECTURE.md §3):
 * - lists: 30 s fresh, refetch on window focus
 * - never retry 4xx (auth/permission/validation) — only network + 5xx, max twice
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => {
          if (isApiError(error) && error.status > 0 && error.status < 500) return false;
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
      mutations: {
        retry: false,
      },
    },
  });
}
