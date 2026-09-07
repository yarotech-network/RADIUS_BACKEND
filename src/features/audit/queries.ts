import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { PAGE_SIZE_DEFAULT } from '@/app/config/constants';
import type { AuditListParams } from '@/types/api';
import { auditApi } from './api';

export const auditKeys = {
  all: ['audit'] as const,
  list: (params: AuditListParams) => [...auditKeys.all, 'list', params] as const,
};

/** Initial `/audit` list params (ordering matches AuditPage). */
export const AUDIT_LIST_DEFAULT_PARAMS: AuditListParams = {
  page: 1,
  page_size: PAGE_SIZE_DEFAULT,
  ordering: '-created_at',
};

/** Options shared by the hook and navigation prefetch (phase 9). */
export function auditListQuery(params: AuditListParams) {
  return {
    queryKey: auditKeys.list(params),
    queryFn: () => auditApi.list(params),
    staleTime: 30_000,
  };
}

export function useAuditEvents(params: AuditListParams) {
  return useQuery({ ...auditListQuery(params), placeholderData: keepPreviousData });
}
