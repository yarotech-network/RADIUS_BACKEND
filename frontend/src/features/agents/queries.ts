import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PAGE_SIZE_DEFAULT } from '@/app/config/constants';
import type {
  AgentCreateRequest,
  AgentEditRequest,
  AgentListParams,
  AgentProfile,
} from '@/types/api';
import { agentsApi } from './api';

export const agentKeys = {
  all: ['agents'] as const,
  lists: () => [...agentKeys.all, 'list'] as const,
  list: (params: AgentListParams) => [...agentKeys.lists(), params] as const,
  detail: (id: number) => [...agentKeys.all, 'detail', id] as const,
};

/** Initial `/agents` list params (matches AgentsPage defaults). */
export const AGENTS_LIST_DEFAULT_PARAMS: AgentListParams = {
  page: 1,
  page_size: PAGE_SIZE_DEFAULT,
};

/** Options shared by the hook and navigation prefetch (phase 9). */
export function agentsListQuery(params: AgentListParams) {
  return {
    queryKey: agentKeys.list(params),
    queryFn: () => agentsApi.list(params),
    staleTime: 30_000,
  };
}

export function useAgents(params: AgentListParams) {
  return useQuery({ ...agentsListQuery(params), placeholderData: keepPreviousData });
}

export function useAgent(id: number) {
  return useQuery({
    queryKey: agentKeys.detail(id),
    queryFn: () => agentsApi.get(id),
    enabled: Number.isFinite(id),
  });
}

function useAgentMutation<TVars>(fn: (vars: TVars) => Promise<AgentProfile>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (agent) => {
      client.setQueryData(agentKeys.detail(agent.id), agent);
      void client.invalidateQueries({ queryKey: agentKeys.lists() });
    },
  });
}

export function useCreateAgent() {
  return useAgentMutation(
    ({ payload, idempotencyKey }: { payload: AgentCreateRequest; idempotencyKey: string }) =>
      agentsApi.create(payload, idempotencyKey),
  );
}
export function useUpdateAgent() {
  return useAgentMutation(({ id, payload }: { id: number; payload: AgentEditRequest }) =>
    agentsApi.update(id, payload),
  );
}
export function useApproveAgent() {
  return useAgentMutation((id: number) => agentsApi.approve(id));
}
export function useSuspendAgent() {
  return useAgentMutation((id: number) => agentsApi.suspend(id));
}
