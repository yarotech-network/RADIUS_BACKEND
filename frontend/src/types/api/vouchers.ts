import type { IsoDateTime, Kobo, PageParams } from './common';

export interface InternetPlan {
  id: number;
  name: string;
  price: Kobo;
  /** Pre-formatted by the server, e.g. "₦1,000". */
  price_display: string;
  duration_hours: number;
  /** e.g. "5M/10M" (up/down). */
  rate_limit: string;
  /** MB; 0 = unlimited. */
  data_limit: number;
  voucher_prefix: string;
  is_active: boolean;
  created_at: IsoDateTime;
}

export interface InternetPlanWrite {
  name: string;
  price: Kobo;
  duration_hours: number;
  rate_limit: string;
  data_limit?: number;
  voucher_prefix?: string;
  is_active?: boolean;
}

export interface PlanListParams extends PageParams {
  is_active?: boolean;
  duration_hours?: number;
}

export type VoucherStatus = 'unused' | 'active' | 'expired' | 'disabled';
export type VoucherSource = 'admin' | 'agent' | 'customer';

/** `password` is write-only; credentials are only readable through print/pdf. */
export interface Voucher {
  id: number;
  username: string;
  plan: number;
  plan_name: string;
  plan_duration: string;
  price_display: string;
  tenant: number;
  tenant_name: string;
  agent: number | null;
  agent_name: string | null;
  status: VoucherStatus;
  generation_source: VoucherSource;
  device_limit: number;
  expires_at: IsoDateTime | null;
  activated_at: IsoDateTime | null;
  created_at: IsoDateTime;
}

export interface VoucherListParams extends PageParams {
  status?: VoucherStatus;
  plan?: number;
  created_after?: string;
  created_before?: string;
}

export interface VoucherGenerateRequest {
  plan_id: number;
  /** 1–100 */
  quantity: number;
  /** ≤ 10 chars */
  prefix?: string;
}

export interface VoucherManualWrite {
  username: string;
  password: string;
  plan: number;
  device_limit?: number;
}

export type PaymentStatus = 'pending' | 'success' | 'failed' | 'abandoned';

export interface PaymentTransaction {
  id: number;
  reference: string;
  amount: Kobo;
  status: PaymentStatus;
  customer_email: string;
  customer_name: string;
  customer_phone: string;
  voucher: number | null;
  voucher_username: string | null;
  tenant: number;
  plan: number | null;
  paystack_reference: string;
  created_at: IsoDateTime;
  paid_at: IsoDateTime | null;
}

export interface PaymentListParams extends PageParams {
  status?: PaymentStatus;
  tenant?: number;
  plan?: number;
}
