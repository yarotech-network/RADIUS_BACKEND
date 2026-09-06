import { http } from '@/services/api/http';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type {
  AgentFundingPayment,
  AgentGenerateRequest,
  AgentGenerateResponse,
  AgentProfile,
  AgentSelfEditRequest,
  AgentStats,
  AgentVoucherAllocation,
  AgentWallet,
  AllocationListParams,
  FundWalletRequest,
  FundingListParams,
  Paginated,
} from '@/types/api';

export interface FundingStart {
  authorization_url: string;
  reference: string;
}

/** Agent (reseller) self-service endpoints — all guarded by `IsAgent` on the backend. */
export const agentPortalApi = {
  me: () => http.get<AgentProfile>('/agents/me/', undefined, { tenantId: null }),
  updateMe: (id: number, payload: AgentSelfEditRequest) =>
    http.patch<AgentProfile>(`/agents/${id}/`, payload, { tenantId: null }),
  stats: () => http.get<AgentStats>('/agent/dashboard/', undefined, { tenantId: null }),
  wallet: () => http.get<AgentWallet>('/agent/wallet/balance/', undefined, { tenantId: null }),
  fundings: (params: FundingListParams = {}) =>
    http.get<Paginated<AgentFundingPayment>>(
      '/agent/wallet/payments/',
      { ...params },
      { tenantId: null },
    ),
  /** 200 → Paystack URL; 503 → provider down (pending row + reference still created). */
  fund: (payload: FundWalletRequest, idempotencyKey = newIdempotencyKey('fund')) =>
    http.post<FundingStart>('/agent/wallet/fund/', payload, { idempotencyKey, tenantId: null }),
  generate: (payload: AgentGenerateRequest, idempotencyKey = newIdempotencyKey('agent-gen')) =>
    http.post<AgentGenerateResponse>('/agent/vouchers/generate/', payload, {
      idempotencyKey,
      tenantId: null,
    }),
  history: (params: AllocationListParams = {}) =>
    http.get<Paginated<AgentVoucherAllocation>>(
      '/agent/vouchers/history/',
      { ...params },
      { tenantId: null },
    ),
};
