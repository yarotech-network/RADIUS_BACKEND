import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dashboardKeys } from '@/features/dashboard/queries';
import type {
  NasDeviceCreate,
  NasDeviceUpdate,
  OperationListParams,
  ProvisionRequest,
  ReplaceSecretsRequest,
  RouterListParams,
  RouterRadiusTestRequest,
  RouterTransitionRequest,
} from '@/types/api';
import { routersApi } from './api';
import { isOperationOpen } from './routerRules';

export const routerKeys = {
  all: ['routers'] as const,
  lists: () => [...routerKeys.all, 'list'] as const,
  list: (params: RouterListParams) => [...routerKeys.lists(), params] as const,
  options: () => [...routerKeys.all, 'options'] as const,
  detail: (id: string) => [...routerKeys.all, 'detail', id] as const,
  checks: (id: string) => [...routerKeys.all, 'checks', id] as const,
  health: (id: string) => [...routerKeys.all, 'health', id] as const,
  audit: (id: string, page: number) => [...routerKeys.all, 'audit', id, page] as const,
  operations: (params: OperationListParams) => [...routerKeys.all, 'operations', params] as const,
  operation: (id: string) => [...routerKeys.all, 'operation', id] as const,
};

export function useRouters(params: RouterListParams) {
  return useQuery({
    queryKey: routerKeys.list(params),
    queryFn: () => routersApi.list(params),
    placeholderData: keepPreviousData,
  });
}

/** Option list (id + name) for filters; cached for a minute. */
export function useRouterOptions() {
  return useQuery({
    queryKey: routerKeys.options(),
    queryFn: routersApi.listAll,
    staleTime: 60_000,
    select: (rows) => rows.map((r) => ({ id: r.id, name: r.name })),
  });
}

export function useRouter(id: string) {
  return useQuery({
    queryKey: routerKeys.detail(id),
    queryFn: () => routersApi.get(id),
    enabled: Boolean(id),
  });
}

export function useRouterChecks(id: string) {
  return useQuery({
    queryKey: routerKeys.checks(id),
    queryFn: () => routersApi.checks(id),
    enabled: Boolean(id),
  });
}

export function useRouterHealth(id: string, enabled = true) {
  return useQuery({
    queryKey: routerKeys.health(id),
    queryFn: () => routersApi.health(id),
    enabled: Boolean(id) && enabled,
  });
}

export function useRouterAudit(id: string, page: number) {
  return useQuery({
    queryKey: routerKeys.audit(id, page),
    queryFn: () => routersApi.audit(id, { page, page_size: 20 }),
    placeholderData: keepPreviousData,
    enabled: Boolean(id),
  });
}

/** Operations for one router (or all); polls every 5 s while any operation is still open. */
/** Operations are manager-only on the backend; pass `enabled=false` for read-only viewers. */
export function useRouterOperations(params: OperationListParams, enabled = true) {
  return useQuery({
    queryKey: routerKeys.operations(params),
    queryFn: () => routersApi.operations(params),
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.results.some(isOperationOpen) ? 5_000 : false),
  });
}

function useInvalidateRouter() {
  const client = useQueryClient();
  return (id?: string) =>
    Promise.all([
      client.invalidateQueries({ queryKey: routerKeys.all }),
      client.invalidateQueries({ queryKey: dashboardKeys.all }),
      ...(id ? [client.invalidateQueries({ queryKey: routerKeys.detail(id) })] : []),
    ]);
}

export function useCreateRouter() {
  const invalidate = useInvalidateRouter();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: NasDeviceCreate;
      idempotencyKey: string;
    }) => routersApi.create(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdateRouter() {
  const invalidate = useInvalidateRouter();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: NasDeviceUpdate }) =>
      routersApi.update(id, payload),
    onSuccess: (_data, vars) => void invalidate(vars.id),
  });
}

export function useDeleteRouter() {
  const invalidate = useInvalidateRouter();
  return useMutation({
    mutationFn: (id: string) => routersApi.remove(id),
    onSuccess: () => void invalidate(),
  });
}

export function useTransitionRouter() {
  const invalidate = useInvalidateRouter();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RouterTransitionRequest }) =>
      routersApi.transition(id, payload),
    onSuccess: (_data, vars) => void invalidate(vars.id),
  });
}

export function useProvisionRouter() {
  const invalidate = useInvalidateRouter();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProvisionRequest }) =>
      routersApi.provisioning(id, payload),
    onSuccess: (_data, vars) => void invalidate(vars.id),
  });
}

export function useReplaceSecrets() {
  const invalidate = useInvalidateRouter();
  return useMutation({
    mutationFn: ({
      id,
      payload,
      idempotencyKey,
    }: {
      id: string;
      payload: ReplaceSecretsRequest;
      idempotencyKey?: string;
    }) => routersApi.replaceSecrets(id, payload, idempotencyKey),
    onSuccess: (_data, vars) => void invalidate(vars.id),
  });
}

export function useRadiusTest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RouterRadiusTestRequest }) =>
      routersApi.test(id, payload),
    onSettled: (_data, _err, vars) => {
      void client.invalidateQueries({ queryKey: routerKeys.checks(vars.id) });
      void client.invalidateQueries({ queryKey: routerKeys.health(vars.id) });
      void client.invalidateQueries({ queryKey: [...routerKeys.all, 'audit', vars.id] });
    },
  });
}
