import { useQuery } from '@tanstack/react-query';
import { routersApi } from './api';

export const routerKeys = {
  all: ['routers'] as const,
  options: () => [...routerKeys.all, 'options'] as const,
};

/** Option list (id + name) for filters; cached for a minute. */
export function useRouterOptions() {
  return useQuery({
    queryKey: routerKeys.options(),
    queryFn: routersApi.listAll,
    staleTime: 60_000,
    select: (rows) => rows.map((r) => ({ id: r.id, name: r.name })),
  });
}
