import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dashboardKeys } from '@/features/dashboard/queries';
import type { DeliverRequest, PaymentListParams, RecoveryListParams } from '@/types/api';
import { paymentsApi } from './api';
import { isDeliveryLive } from './paymentRules';

export const paymentKeys = {
  all: ['payments'] as const,
  lists: () => [...paymentKeys.all, 'list'] as const,
  list: (params: PaymentListParams) => [...paymentKeys.lists(), params] as const,
  detail: (id: number) => [...paymentKeys.all, 'detail', id] as const,
  recoveryLists: () => [...paymentKeys.all, 'recovery'] as const,
  recoveryList: (params: RecoveryListParams) => [...paymentKeys.recoveryLists(), params] as const,
  recovery: (id: number) => [...paymentKeys.all, 'recovery-detail', id] as const,
  deliveries: (paymentId: number) => [...paymentKeys.all, 'deliveries', paymentId] as const,
};

export function usePayments(params: PaymentListParams) {
  return useQuery({
    queryKey: paymentKeys.list(params),
    queryFn: () => paymentsApi.list(params),
    placeholderData: keepPreviousData,
  });
}

export function usePayment(id: number) {
  return useQuery({
    queryKey: paymentKeys.detail(id),
    queryFn: () => paymentsApi.get(id),
    enabled: Number.isFinite(id),
  });
}

export function useRecoveryList(params: RecoveryListParams, enabled = true) {
  return useQuery({
    queryKey: paymentKeys.recoveryList(params),
    queryFn: () => paymentsApi.recoveryList(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useRecovery(id: number, enabled = true) {
  return useQuery({
    queryKey: paymentKeys.recovery(id),
    queryFn: () => paymentsApi.recovery(id),
    enabled: enabled && Number.isFinite(id),
  });
}

/** Polls every 5 s while a delivery is pending/sending. */
export function useDeliveries(paymentId: number, enabled = true) {
  return useQuery({
    queryKey: paymentKeys.deliveries(paymentId),
    queryFn: () => paymentsApi.deliveries({ payment: paymentId, page_size: 20 }),
    enabled: enabled && Number.isFinite(paymentId),
    refetchInterval: (query) => (query.state.data?.results.some(isDeliveryLive) ? 5_000 : false),
  });
}

function useInvalidatePayment() {
  const client = useQueryClient();
  return (id: number) =>
    Promise.all([
      client.invalidateQueries({ queryKey: paymentKeys.all }),
      client.invalidateQueries({ queryKey: dashboardKeys.all }),
      client.invalidateQueries({ queryKey: paymentKeys.detail(id) }),
    ]);
}

export function useRetryFulfillment() {
  const invalidate = useInvalidatePayment();
  return useMutation({
    mutationFn: (id: number) => paymentsApi.retry(id),
    onSuccess: (_d, id) => void invalidate(id),
  });
}

export function useDeliverCredentials() {
  const invalidate = useInvalidatePayment();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: DeliverRequest }) =>
      paymentsApi.deliver(id, payload),
    onSuccess: (_d, vars) => void invalidate(vars.id),
  });
}
