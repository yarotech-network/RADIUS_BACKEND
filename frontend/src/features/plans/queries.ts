import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { InternetPlanWrite, PlanListParams } from '@/types/api';
import { plansApi } from './api';

export const planKeys = {
  all: ['plans'] as const,
  lists: () => [...planKeys.all, 'list'] as const,
  list: (params: PlanListParams) => [...planKeys.lists(), params] as const,
  options: (activeOnly: boolean) => [...planKeys.all, 'options', activeOnly] as const,
  detail: (id: number) => [...planKeys.all, 'detail', id] as const,
};

export function usePlans(params: PlanListParams) {
  return useQuery({
    queryKey: planKeys.list(params),
    queryFn: () => plansApi.list(params),
    placeholderData: keepPreviousData,
  });
}

/** Lightweight option list for selects (vouchers generate, filters, devices…). */
export function usePlanOptions(activeOnly = true) {
  return useQuery({
    queryKey: planKeys.options(activeOnly),
    queryFn: () => plansApi.listAll({ activeOnly }),
    staleTime: 60_000,
  });
}

export function usePlan(id: number) {
  return useQuery({
    queryKey: planKeys.detail(id),
    queryFn: () => plansApi.get(id),
    enabled: Number.isFinite(id),
  });
}

export function useCreatePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: InternetPlanWrite;
      idempotencyKey: string;
    }) => plansApi.create(payload, idempotencyKey),
    onSuccess: () => client.invalidateQueries({ queryKey: planKeys.all }),
  });
}

export function useUpdatePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<InternetPlanWrite> }) =>
      plansApi.update(id, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: planKeys.all }),
  });
}

export function useDeletePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => plansApi.remove(id),
    onSuccess: () => client.invalidateQueries({ queryKey: planKeys.all }),
  });
}
