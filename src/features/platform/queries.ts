import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isApiError } from '@/services/api/errors';
import type {
  AuditListParams,
  MembershipListParams,
  MembershipRole,
  PaymentListParams,
  PlatformWalletPaymentListParams,
  RouterListParams,
  StaffAssignmentListParams,
  StaffAssignmentWrite,
  StaffInvitationListParams,
  StaffInvitationWrite,
  SubscriptionPaymentListParams,
  Tenant,
  TenantListParams,
  TenantMembershipWrite,
  TenantWrite,
} from '@/types/api';
import { platformApi } from './api';

export const platformKeys = {
  all: ['platform'] as const,
  stats: () => [...platformKeys.all, 'stats'] as const,
  tenants: () => [...platformKeys.all, 'tenants'] as const,
  tenantList: (params: TenantListParams) => [...platformKeys.tenants(), 'list', params] as const,
  tenant: (id: number) => [...platformKeys.tenants(), 'detail', id] as const,
  /** Every tenant (paged through) for name lookups + pickers. */
  tenantIndex: () => [...platformKeys.tenants(), 'index'] as const,
  memberships: (params: MembershipListParams) =>
    [...platformKeys.all, 'memberships', params] as const,
  routers: (params: RouterListParams) => [...platformKeys.all, 'routers', params] as const,
  payments: (params: PaymentListParams) => [...platformKeys.all, 'payments', params] as const,
  walletPayments: (params: PlatformWalletPaymentListParams) =>
    [...platformKeys.all, 'wallet-payments', params] as const,
  subscriptionPayments: (params: SubscriptionPaymentListParams) =>
    [...platformKeys.all, 'subscription-payments', params] as const,
  audit: (params: AuditListParams) => [...platformKeys.all, 'audit', params] as const,
  invitations: (params: StaffInvitationListParams) =>
    [...platformKeys.all, 'invitations', params] as const,
  assignments: (params: StaffAssignmentListParams) =>
    [...platformKeys.all, 'assignments', params] as const,
};

const notFound = (error: unknown) => isApiError(error) && error.status === 404;

export function usePlatformStats() {
  return useQuery({
    queryKey: platformKeys.stats(),
    queryFn: platformApi.stats,
    staleTime: 30_000,
  });
}

export function useTenants(params: TenantListParams) {
  return useQuery({
    queryKey: platformKeys.tenantList(params),
    queryFn: () => platformApi.tenants(params),
    placeholderData: keepPreviousData,
  });
}

export function useTenant(id: number | null) {
  return useQuery({
    queryKey: platformKeys.tenant(id ?? 0),
    queryFn: () => platformApi.tenant(id ?? 0),
    enabled: id !== null,
    retry: (count, error) => !notFound(error) && count < 2,
  });
}

/**
 * Names for tenant ids (the platform list endpoints return ids only — gap #23/#20 family).
 * Pages through `tenants/` once (≤ 100 per page) and caches for 5 minutes.
 */
export function useTenantIndex(enabled = true) {
  return useQuery({
    queryKey: platformKeys.tenantIndex(),
    enabled,
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const all: Tenant[] = [];
      let page = 1;
      for (;;) {
        const res = await platformApi.tenants({ page, page_size: 100 });
        all.push(...res.results);
        if (page >= res.total_pages || all.length >= 2000) break;
        page += 1;
      }
      return all.sort((a, b) => a.name.localeCompare(b.name));
    },
  });
}

/** `id → name` helper on top of the index; falls back to `Tenant #id`. */
export function useTenantName() {
  const index = useTenantIndex();
  const byId = new Map((index.data ?? []).map((t) => [t.id, t.name]));
  return (id: number | null | undefined) =>
    id === null || id === undefined ? null : (byId.get(id) ?? `Tenant #${id}`);
}

function useInvalidateTenants() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: platformKeys.tenants() }),
      qc.invalidateQueries({ queryKey: platformKeys.stats() }),
    ]);
}

export function useCreateTenant() {
  const invalidate = useInvalidateTenants();
  return useMutation({
    mutationFn: ({ payload, idempotencyKey }: { payload: TenantWrite; idempotencyKey: string }) =>
      platformApi.createTenant(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdateTenant() {
  const qc = useQueryClient();
  const invalidate = useInvalidateTenants();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<TenantWrite> }) =>
      platformApi.updateTenant(id, payload),
    onSuccess: (tenant) => {
      qc.setQueryData(platformKeys.tenant(tenant.id), tenant);
      void invalidate();
    },
  });
}

export function useDeleteTenant() {
  const invalidate = useInvalidateTenants();
  return useMutation({
    mutationFn: (id: number) => platformApi.deleteTenant(id),
    onSuccess: () => void invalidate(),
  });
}

export function useMemberships(params: MembershipListParams) {
  return useQuery({
    queryKey: platformKeys.memberships(params),
    queryFn: () => platformApi.memberships(params),
    placeholderData: keepPreviousData,
  });
}

function useInvalidateMemberships() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: [...platformKeys.all, 'memberships'] }),
      qc.invalidateQueries({ queryKey: platformKeys.tenants() }),
    ]);
}

export function useAddMembership() {
  const invalidate = useInvalidateMemberships();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: TenantMembershipWrite;
      idempotencyKey: string;
    }) => platformApi.addMembership(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}

export function useChangeMembershipRole() {
  const invalidate = useInvalidateMemberships();
  return useMutation({
    mutationFn: ({ id, role }: { id: number; role: MembershipRole }) =>
      platformApi.changeMembershipRole(id, role),
    onSuccess: () => void invalidate(),
  });
}

export function useRemoveMembership() {
  const invalidate = useInvalidateMemberships();
  return useMutation({
    mutationFn: (id: number) => platformApi.removeMembership(id),
    onSuccess: () => void invalidate(),
  });
}

export function usePlatformRouters(params: RouterListParams) {
  return useQuery({
    queryKey: platformKeys.routers(params),
    queryFn: () => platformApi.routers(params),
    placeholderData: keepPreviousData,
  });
}

export function usePlatformPayments(params: PaymentListParams, enabled = true) {
  return useQuery({
    queryKey: platformKeys.payments(params),
    queryFn: () => platformApi.payments(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function usePlatformWalletPayments(params: PlatformWalletPaymentListParams, enabled = true) {
  return useQuery({
    queryKey: platformKeys.walletPayments(params),
    queryFn: () => platformApi.walletPayments(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function usePlatformSubscriptionPayments(
  params: SubscriptionPaymentListParams,
  enabled = true,
) {
  return useQuery({
    queryKey: platformKeys.subscriptionPayments(params),
    queryFn: () => platformApi.subscriptionPayments(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function usePlatformAudit(params: AuditListParams) {
  return useQuery({
    queryKey: platformKeys.audit(params),
    queryFn: () => platformApi.audit(params),
    placeholderData: keepPreviousData,
  });
}

export function useInvitations(params: StaffInvitationListParams) {
  return useQuery({
    queryKey: platformKeys.invitations(params),
    queryFn: () => platformApi.invitations(params),
    placeholderData: keepPreviousData,
  });
}

export function useInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: StaffInvitationWrite;
      idempotencyKey: string;
    }) => platformApi.invite(payload, idempotencyKey),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...platformKeys.all, 'invitations'] }),
  });
}

export function useRevokeInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => platformApi.revokeInvitation(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...platformKeys.all, 'invitations'] }),
  });
}

export function useAssignments(params: StaffAssignmentListParams) {
  return useQuery({
    queryKey: platformKeys.assignments(params),
    queryFn: () => platformApi.assignments(params),
    placeholderData: keepPreviousData,
  });
}

function useInvalidateAssignments() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: [...platformKeys.all, 'assignments'] });
}

export function useCreateAssignment() {
  const invalidate = useInvalidateAssignments();
  return useMutation({
    mutationFn: ({
      payload,
      idempotencyKey,
    }: {
      payload: StaffAssignmentWrite;
      idempotencyKey: string;
    }) => platformApi.createAssignment(payload, idempotencyKey),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdateAssignment() {
  const invalidate = useInvalidateAssignments();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number;
      payload: Partial<Pick<StaffAssignmentWrite, 'services' | 'is_active'>>;
    }) => platformApi.updateAssignment(id, payload),
    onSuccess: () => void invalidate(),
  });
}

export function useRevokeAssignment() {
  const invalidate = useInvalidateAssignments();
  return useMutation({
    mutationFn: (id: number) => platformApi.revokeAssignment(id),
    onSuccess: () => void invalidate(),
  });
}
