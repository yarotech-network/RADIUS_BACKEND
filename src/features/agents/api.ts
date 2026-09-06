import { http } from '@/services/api/http';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type {
  AgentCreateRequest,
  AgentEditRequest,
  AgentListParams,
  AgentProfile,
  Paginated,
} from '@/types/api';

/** Manager-side agent (reseller) administration: `tenant/agents/` (IsTenantManager). */
export const agentsApi = {
  list(params: AgentListParams) {
    return http.get<Paginated<AgentProfile>>('/tenant/agents/', { ...params });
  },
  get(id: number) {
    return http.get<AgentProfile>(`/tenant/agents/${id}/`);
  },
  create(payload: AgentCreateRequest, idempotencyKey = newIdempotencyKey('agent')) {
    return http.post<AgentProfile>('/tenant/agents/', payload, { idempotencyKey });
  },
  update(id: number, payload: AgentEditRequest) {
    return http.patch<AgentProfile>(`/tenant/agents/${id}/`, payload);
  },
  approve(id: number, idempotencyKey = newIdempotencyKey('agent-approve')) {
    return http.post<AgentProfile>(`/tenant/agents/${id}/approve/`, undefined, { idempotencyKey });
  },
  suspend(id: number, idempotencyKey = newIdempotencyKey('agent-suspend')) {
    return http.post<AgentProfile>(`/tenant/agents/${id}/suspend/`, undefined, { idempotencyKey });
  },
};
