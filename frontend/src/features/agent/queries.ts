import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  AgentGenerateRequest,
  AgentSelfEditRequest,
  AllocationListParams,
  FundingListParams,
} from '@/types/api';
import { agentPortalApi } from './api';

export const agentKeys = {
  all: ['agent-portal'] as const,
  me: () => [...agentKeys.all, 'me'] as const,
  stats: () => [...agentKeys.all, 'stats'] as const,
  wallet: () => [...agentKeys.all, 'wallet'] as const,
  fundings: (params: FundingListParams) => [...agentKeys.all, 'fundings', params] as const,
  funding: (reference: string) => [...agentKeys.all, 'funding', reference] as const,
  history: (params: AllocationListParams) => [...agentKeys.all, 'history', params] as const,
};

export function useAgentMe() {
  return useQuery({ queryKey: agentKeys.me(), queryFn: agentPortalApi.me, staleTime: 5 * 60_000 });
}

export function useAgentStats() {
  return useQuery({
    queryKey: agentKeys.stats(),
    queryFn: agentPortalApi.stats,
    staleTime: 30_000,
  });
}

export function useAgentWallet() {
  return useQuery({
    queryKey: agentKeys.wallet(),
    queryFn: agentPortalApi.wallet,
    staleTime: 30_000,
  });
}

export function useFundings(params: FundingListParams) {
  return useQuery({
    queryKey: agentKeys.fundings(params),
    queryFn: () => agentPortalApi.fundings(params),
    placeholderData: keepPreviousData,
  });
}

/** One funding payment looked up by reference; polls every 5 s while it is still pending. */
export function useFundingByReference(reference: string | null) {
  return useQuery({
    queryKey: agentKeys.funding(reference ?? ''),
    queryFn: async () =>
      (await agentPortalApi.fundings({ reference: reference ?? '', page_size: 1 })).results[0] ??
      null,
    enabled: Boolean(reference),
    refetchInterval: (query) =>
      query.state.data === undefined || query.state.data?.status === 'pending' ? 5_000 : false,
  });
}

export function useAllocationHistory(params: AllocationListParams) {
  return useQuery({
    queryKey: agentKeys.history(params),
    queryFn: () => agentPortalApi.history(params),
    placeholderData: keepPreviousData,
  });
}

/** Invalidate everything that a wallet debit/credit changes. */
function useInvalidateMoney() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: agentKeys.stats() }),
      qc.invalidateQueries({ queryKey: agentKeys.wallet() }),
      qc.invalidateQueries({ queryKey: agentKeys.me() }),
      qc.invalidateQueries({ queryKey: [...agentKeys.all, 'history'] }),
      qc.invalidateQueries({ queryKey: [...agentKeys.all, 'fundings'] }),
    ]);
}

export function useGenerateVouchers() {
  const invalidate = useInvalidateMoney();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: AgentGenerateRequest;
      idempotencyKey: string;
    }) => agentPortalApi.generate(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}

export function useFundWallet() {
  const invalidate = useInvalidateMoney();
  return useMutation({
    mutationFn: ({ amount, idempotencyKey }: { amount: number; idempotencyKey: string }) =>
      agentPortalApi.fund({ amount }, idempotencyKey),
    onSettled: () => void invalidate(),
  });
}

export function useUpdateAgentMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AgentSelfEditRequest }) =>
      agentPortalApi.updateMe(id, payload),
    onSuccess: (profile) => qc.setQueryData(agentKeys.me(), profile),
  });
}
