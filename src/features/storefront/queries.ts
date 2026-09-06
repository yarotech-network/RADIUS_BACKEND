import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import type { PublicBuyRequest } from '@/types/api';
import { storefrontApi, type PublicPlanParams } from './api';

export const storefrontKeys = {
  all: ['storefront'] as const,
  tenant: (slug: string) => [...storefrontKeys.all, 'tenant', slug] as const,
  plans: (slug: string, params: PublicPlanParams) =>
    [...storefrontKeys.all, 'plans', slug, params] as const,
  result: (reference: string) => [...storefrontKeys.all, 'result', reference] as const,
  pricing: () => [...storefrontKeys.all, 'pricing'] as const,
};

export function usePublicTenant(slug: string | null) {
  return useQuery({
    queryKey: storefrontKeys.tenant(slug ?? ''),
    queryFn: () => storefrontApi.tenant(slug ?? ''),
    enabled: Boolean(slug),
    staleTime: 5 * 60_000,
    retry: (count, error) =>
      !(error instanceof Error && 'status' in error && error.status === 404) && count < 2,
  });
}

export function usePublicPlans(slug: string | null, params: PublicPlanParams = {}) {
  return useQuery({
    queryKey: storefrontKeys.plans(slug ?? '', params),
    queryFn: () => storefrontApi.plans(slug ?? '', params),
    enabled: Boolean(slug),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useStartCheckout() {
  return useMutation({ mutationFn: (payload: PublicBuyRequest) => storefrontApi.buy(payload) });
}

/** Polls the Paystack return endpoint every 5 s while the payment is still pending. */
export function usePaymentResult(reference: string | null) {
  return useQuery({
    queryKey: storefrontKeys.result(reference ?? ''),
    queryFn: () => storefrontApi.result(reference ?? ''),
    enabled: Boolean(reference),
    refetchInterval: (query) => (query.state.data?.status === 'pending' ? 5_000 : false),
  });
}

export function usePlatformPricing() {
  return useQuery({
    queryKey: storefrontKeys.pricing(),
    queryFn: storefrontApi.pricing,
    select: (page) => page.results.filter((p) => p.is_active),
    staleTime: 5 * 60_000,
  });
}
