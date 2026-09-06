import { http } from '@/services/api/http';
import type { AuditEvent, AuditListParams, Paginated } from '@/types/api';

/** `audit-events/` — tenant-scoped, manager+ read-only. `search` matches the resource key. */
export const auditApi = {
  list(params: AuditListParams) {
    return http.get<Paginated<AuditEvent>>('/audit-events/', { ...params });
  },
};
