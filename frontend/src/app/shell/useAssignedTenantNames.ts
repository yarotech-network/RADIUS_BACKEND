import { useQuery } from '@tanstack/react-query';
import { http } from '@/services/api/http';
import type { Paginated, Tenant } from '@/types/api';

/**
 * Platform staff see tenant *ids* in their assignments. `GET tenants/` is platform-admin scoped, so
 * we try it once and quietly fall back to "Tenant #id" when it is forbidden (API gap #3 family).
 */
export function useAssignedTenantNames(tenantIds: number[]) {
  return useQuery({
    queryKey: ['tenant-names', tenantIds],
    queryFn: async () => {
      const names = new Map<number, string>();
      try {
        const page = await http.get<Paginated<Tenant>>(
          '/tenants/',
          { page_size: 100 },
          { tenantId: null },
        );
        for (const t of page.results) names.set(t.id, t.name);
      } catch {
        /* not permitted — fall back to ids */
      }
      return names;
    },
    enabled: tenantIds.length > 0,
    staleTime: 10 * 60_000,
  });
}

export function tenantLabel(names: Map<number, string> | undefined, id: number): string {
  return names?.get(id) ?? `Tenant #${id}`;
}
