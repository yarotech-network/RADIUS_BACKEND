import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PAGE_SIZE_DEFAULT } from '@/app/config/constants';
import type { InternetPlanWrite, PlanListParams } from '@/types/api';
import { plansApi } from './api';

export const planKeys = {
  all: ['plans'] as const,
  lists: () => [...planKeys.all, 'list'] as const,
  list: (params: PlanListParams) => [...planKeys.lists(), params] as const,
  options: (activeOnly: boolean) => [...planKeys.all, 'options', activeOnly] as const,
  detail: (id: number) => [...planKeys.all, 'detail', id] as const,
};

/** Initial `/plans` list params (ordering matches PlansPage). */
export const PLANS_DEFAULT_ORDERING = 'price';
export const PLANS_LIST_DEFAULT_PARAMS: PlanListParams = {
  page: 1,
  page_size: PAGE_SIZE_DEFAULT,
  ordering: PLANS_DEFAULT_ORDERING,
};

/** Options shared by the hook and navigation prefetch (phase 9). */
export function plansListQuery(params: PlanListParams) {
  return {
    queryKey: planKeys.list(params),
    queryFn: () => plansApi.list(params),
    staleTime: 30_000,
  };
}

export function planOptionsQuery(activeOnly: boolean) {
  return {
    queryKey: planKeys.options(activeOnly),
    queryFn: () => plansApi.listAll({ activeOnly }),
    staleTime: 60_000,
  };
}

export function usePlans(params: PlanListParams) {
  return useQuery({ ...plansListQuery(params), placeholderData: keepPreviousData });
}

/** Lightweight option list for selects (vouchers generate, filters, devices…). */
export function usePlanOptions(activeOnly = true) {
  return useQuery(planOptionsQuery(activeOnly));
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
