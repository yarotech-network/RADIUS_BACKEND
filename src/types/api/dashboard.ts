import type { IsoDateTime, Kobo, PageParams } from './common';

export interface DashboardStats {
  total_vouchers: number;
  active_vouchers: number;
  total_revenue: Kobo;
  total_agents: number;
  total_routers: number;
  active_routers: number;
  currency: string;
  amount_unit: string;
  observed_at: IsoDateTime;
  pending_payments: number;
  paid_unfulfilled_payments: number;
}

export interface LiveUser {
  session_id: number;
  username: string;
  ip_address: string;
  client_ip: string | null;
  /** seconds */
  session_time: number;
  bytes_in: number;
  bytes_out: number;
  connected_at: IsoDateTime | null;
  router_id: string | null;
  router_name: string | null;
}

/** Non-standard envelope: `users` instead of `results`. */
export interface LiveUsersResponse {
  users: LiveUser[];
  count: number;
  current_page: number;
  total_pages: number;
  observed_at: IsoDateTime;
  source: string;
}

export interface LiveUsersParams extends Pick<PageParams, 'page' | 'page_size'> {
  username?: string;
  router?: string;
}

export interface DisconnectResult {
  acknowledged: boolean;
}

export interface PlatformStats {
  tenants: number;
  active_tenants: number;
  routers: number;
  onboarded_routers: number;
  agents: number;
  vouchers: number;
  successful_payment_amount: Kobo;
  pending_payments: number;
  currency: string;
  amount_unit: string;
  successful_wallet_funding_amount: Kobo;
  successful_subscription_amount: Kobo;
}

export interface AuditEvent {
  id: string;
  tenant: number | null;
  actor: number | null;
  action: string;
  /** "app.model:pk" */
  resource: string;
  details: Record<string, unknown>;
  created_at: IsoDateTime;
}

export interface AuditListParams extends PageParams {
  /** Exact action key, e.g. `vouchers.generated`. */
  action?: string;
  actor?: number;
  tenant?: number;
}
