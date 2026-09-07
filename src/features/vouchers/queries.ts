import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PAGE_SIZE_DEFAULT } from '@/app/config/constants';
import type { VoucherGenerateRequest, VoucherListParams, VoucherManualWrite } from '@/types/api';
import { vouchersApi } from './api';
import { dashboardKeys } from '@/features/dashboard/queries';

export const voucherKeys = {
  all: ['vouchers'] as const,
  lists: () => [...voucherKeys.all, 'list'] as const,
  list: (params: VoucherListParams) => [...voucherKeys.lists(), params] as const,
  detail: (id: number) => [...voucherKeys.all, 'detail', id] as const,
};

/** Initial `/vouchers` list params (ordering matches VouchersPage). */
export const VOUCHERS_DEFAULT_ORDERING = '-created_at';
export const VOUCHERS_LIST_DEFAULT_PARAMS: VoucherListParams = {
  page: 1,
  page_size: PAGE_SIZE_DEFAULT,
  ordering: VOUCHERS_DEFAULT_ORDERING,
};

/** Options shared by the hook and navigation prefetch (phase 9). */
export function vouchersListQuery(params: VoucherListParams) {
  return {
    queryKey: voucherKeys.list(params),
    queryFn: () => vouchersApi.list(params),
    staleTime: 30_000,
  };
}

export function useVouchers(params: VoucherListParams) {
  return useQuery({ ...vouchersListQuery(params), placeholderData: keepPreviousData });
}

export function useVoucher(id: number) {
  return useQuery({
    queryKey: voucherKeys.detail(id),
    queryFn: () => vouchersApi.get(id),
    enabled: Number.isFinite(id),
  });
}

function useInvalidateVouchers() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: voucherKeys.all }),
      client.invalidateQueries({ queryKey: dashboardKeys.all }),
    ]);
}

export function useGenerateVouchers() {
  const invalidate = useInvalidateVouchers();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: VoucherGenerateRequest;
      idempotencyKey: string;
    }) => vouchersApi.generate(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}

export function useCreateManualVoucher() {
  const invalidate = useInvalidateVouchers();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: VoucherManualWrite;
      idempotencyKey: string;
    }) => vouchersApi.createManual(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdateVoucher() {
  const invalidate = useInvalidateVouchers();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<VoucherManualWrite> }) =>
      vouchersApi.update(id, payload),
    onSuccess: () => void invalidate(),
  });
}

export function useDisableVoucher() {
  const invalidate = useInvalidateVouchers();
  return useMutation({
    mutationFn: (id: number) => vouchersApi.disable(id),
    onSuccess: () => void invalidate(),
  });
}

export function useDeleteVoucher() {
  const invalidate = useInvalidateVouchers();
  return useMutation({
    mutationFn: (id: number) => vouchersApi.remove(id),
    onSuccess: () => void invalidate(),
  });
}
