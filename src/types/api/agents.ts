import type { IsoDateTime, Kobo, PageParams } from './common';
import type { VoucherStatus } from './vouchers';

export type AgentStatus = 'pending' | 'active' | 'suspended';

export interface AgentProfile {
  id: number;
  user: number;
  username: string;
  tenant: number;
  phone: string;
  shop_name: string;
  status: AgentStatus;
  /** Decimal string, e.g. "10.00". */
  commission_rate: string;
  /** Null when the wallet row has not been created yet (legacy agents). */
  wallet_balance: Kobo | null;
  created_at: IsoDateTime;
}

export interface AgentListParams extends PageParams {
  status?: AgentStatus;
}

export interface AgentCreateRequest {
  username: string;
  email: string;
  password: string;
  phone: string;
  shop_name?: string;
  commission_rate?: string;
}

/** Manager-side edit. */
export interface AgentEditRequest {
  phone?: string;
  shop_name?: string;
  commission_rate?: string;
}

/** Agent self-service edit (`PATCH agents/{id}/`): only phone/shop_name are writable. */
export interface AgentSelfEditRequest {
  phone?: string;
  shop_name?: string;
}

export interface AgentWallet {
  id: number;
  agent: number;
  balance: Kobo;
  updated_at: IsoDateTime;
}

export type FundingStatus = 'pending' | 'success' | 'failed';

export interface AgentFundingPayment {
  id: number;
  reference: string;
  amount: Kobo;
  status: FundingStatus;
  created_at: IsoDateTime;
  completed_at: IsoDateTime | null;
}

export interface FundingListParams extends PageParams {
  status?: FundingStatus;
  reference?: string;
}

/** `platform/wallet-payments/` rows carry the owning tenant and agent ids. */
export interface PlatformWalletPayment extends AgentFundingPayment {
  tenant_id: number;
  agent_id: number;
}

export interface PlatformWalletPaymentListParams extends PageParams {
  status?: FundingStatus;
  wallet__agent__tenant?: number;
  wallet__agent?: number;
}

export interface FundWalletRequest {
  /** ≥ 50 000 kobo (₦500) and ≤ tenant max_funding_amount. */
  amount: Kobo;
}

export type AllocationType = 'wallet' | 'credit' | 'complimentary';

export interface AgentVoucherAllocation {
  id: number;
  agent: number;
  voucher: number;
  voucher_username: string;
  allocation_type: AllocationType;
  amount_charged: Kobo;
  commission_earned: Kobo;
  created_at: IsoDateTime;
}

export interface AllocationListParams extends PageParams {
  status?: VoucherStatus;
}

export interface AgentGenerateRequest {
  plan_id: number;
  quantity?: number;
}

export interface AgentGenerateResponse {
  vouchers: AgentVoucherAllocation[];
}

export interface AgentStats {
  wallet_balance: Kobo;
  vouchers_today: number;
  commission_this_month: Kobo;
  total_vouchers: number;
}
