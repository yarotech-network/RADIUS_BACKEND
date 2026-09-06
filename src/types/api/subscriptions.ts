import type { IsoDateTime, Kobo, PageParams } from './common';

export interface SubscriptionPlan {
  id: number;
  name: string;
  price: Kobo;
  price_display: string;
  duration_days: number;
  features: unknown[];
  is_active: boolean;
}

export type SubscriptionStatus = 'trial' | 'active' | 'expired' | 'cancelled';

export interface TenantSubscription {
  id: number;
  tenant: number;
  plan: number;
  plan_name: string;
  status: SubscriptionStatus;
  started_at: IsoDateTime;
  expires_at: IsoDateTime;
  is_trial: boolean;
  is_expired: boolean;
}

export interface SubscriptionCheckoutRequest {
  plan_id: number;
}

export type SubscriptionPaymentStatus = 'pending' | 'success' | 'failed';

export interface SubscriptionPayment {
  reference: string;
  amount: Kobo;
  status: SubscriptionPaymentStatus;
  plan: number;
  subscription: number | null;
  created_at: IsoDateTime;
  completed_at: IsoDateTime | null;
}

export interface PlatformSubscriptionPayment extends SubscriptionPayment {
  id: number;
  tenant: number;
}

export interface SubscriptionPaymentListParams extends PageParams {
  tenant?: number;
  status?: SubscriptionPaymentStatus;
  plan?: number;
}
