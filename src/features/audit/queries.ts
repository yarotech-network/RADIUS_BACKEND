import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { AuditListParams } from '@/types/api';
import { auditApi } from './api';

export const auditKeys = {
  all: ['audit'] as const,
  list: (params: AuditListParams) => [...auditKeys.all, 'list', params] as const,
};

export function useAuditEvents(params: AuditListParams) {
  return useQuery({
    queryKey: auditKeys.list(params),
    queryFn: () => auditApi.list(params),
    placeholderData: keepPreviousData,
  });
}
