import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DeviceListParams, MacDeviceWrite } from '@/types/api';
import { devicesApi } from './api';

export const deviceKeys = {
  all: ['devices'] as const,
  lists: () => [...deviceKeys.all, 'list'] as const,
  list: (params: DeviceListParams) => [...deviceKeys.lists(), params] as const,
};

export function useDevices(params: DeviceListParams) {
  return useQuery({
    queryKey: deviceKeys.list(params),
    queryFn: () => devicesApi.list(params),
    placeholderData: keepPreviousData,
  });
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
