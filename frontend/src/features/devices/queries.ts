import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PAGE_SIZE_DEFAULT } from '@/app/config/constants';
import type { DeviceListParams, MacDeviceWrite } from '@/types/api';
import { devicesApi } from './api';

export const deviceKeys = {
  all: ['devices'] as const,
  lists: () => [...deviceKeys.all, 'list'] as const,
  list: (params: DeviceListParams) => [...deviceKeys.lists(), params] as const,
};

/** Initial `/devices` list params (matches DevicesPage defaults). */
export const DEVICES_LIST_DEFAULT_PARAMS: DeviceListParams = {
  page: 1,
  page_size: PAGE_SIZE_DEFAULT,
};

/** Options shared by the hook and navigation prefetch (phase 9). */
export function devicesListQuery(params: DeviceListParams) {
  return {
    queryKey: deviceKeys.list(params),
    queryFn: () => devicesApi.list(params),
    staleTime: 30_000,
  };
}

export function useDevices(params: DeviceListParams) {
  return useQuery({ ...devicesListQuery(params), placeholderData: keepPreviousData });
}

function useInvalidateDevices() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: deviceKeys.all });
}

export function useCreateDevice() {
  const invalidate = useInvalidateDevices();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: MacDeviceWrite;
      idempotencyKey: string;
    }) => devicesApi.create(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}
export function useUpdateDevice() {
  const invalidate = useInvalidateDevices();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<MacDeviceWrite> }) =>
      devicesApi.update(id, payload),
    onSuccess: () => void invalidate(),
  });
}
export function useDeleteDevice() {
  const invalidate = useInvalidateDevices();
  return useMutation({
    mutationFn: (id: number) => devicesApi.remove(id),
    onSuccess: () => void invalidate(),
  });
}
