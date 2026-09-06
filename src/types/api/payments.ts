import type { IsoDateTime, Kobo, PageParams } from './common';
import type { PaymentStatus } from './vouchers';

export type FulfillmentStatus = 'fulfilled' | 'paid_unfulfilled' | 'unverified';
export type DeliveryStatus =
  'not_requested' | 'pending' | 'sending' | 'accepted' | 'failed' | 'unknown';

export interface PaymentRecovery {
  id: number;
  reference: string;
  amount: Kobo;
  status: PaymentStatus;
  verified_at: IsoDateTime | null;
  voucher: number | null;
  fulfillment_status: FulfillmentStatus;
  delivery_status: DeliveryStatus;
}

export interface RecoveryListParams extends PageParams {
  status?: PaymentStatus;
  plan?: number;
}

export interface PaymentDelivery {
  id: string;
  payment: number;
  status: Exclude<DeliveryStatus, 'not_requested'>;
  error_code: string;
  created_at: IsoDateTime;
  started_at: IsoDateTime | null;
  completed_at: IsoDateTime | null;
}

export interface DeliveryListParams extends PageParams {
  payment?: number;
  status?: string;
}

export interface DeliverRequest {
  acknowledge_duplicate_risk?: boolean;
}

export interface PublicBuyRequest {
  plan_id: number;
  email: string;
  name?: string;
  phone?: string;
}

export interface PaymentCallbackResponse {
  status: PaymentStatus;
  reference: string;
  voucher: string | null;
}
