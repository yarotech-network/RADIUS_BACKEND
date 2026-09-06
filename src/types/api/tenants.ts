import type { IsoDateTime, Kobo } from './common';

export interface Tenant {
  id: number;
  name: string;
  slug: string;
  phone: string;
  email: string;
  address: string;
  is_active: boolean;
  is_platform_admin: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
  member_count: number;
  voucher_count: number;
}

export interface TenantWrite {
  name: string;
  slug: string;
  phone?: string;
  email?: string;
  address?: string;
  is_active?: boolean;
  is_platform_admin?: boolean;
}

/** `GET/PATCH tenants/profile/` — a manager's own tenant contact record. */
export interface TenantProfile {
  id: number;
  name: string;
  slug: string;
  phone: string;
  email: string;
  address: string;
  is_active: boolean;
  updated_at: IsoDateTime;
}

export interface TenantProfileWrite {
  name?: string;
  phone?: string;
  email?: string;
  address?: string;
}

export type MembershipRole = 'owner' | 'manager' | 'staff';

export interface TenantMembership {
  id: number;
  user: number;
  tenant: number;
  role: MembershipRole;
  user_display: string;
  tenant_display: string;
  created_at: IsoDateTime;
}

export interface TenantMembershipWrite {
  user: number;
  /** Ignored for owners (forced to own tenant); required for platform admins. */
  tenant?: number;
  role: MembershipRole;
}

/** Paystack keys are write-only and never returned. */
export interface TenantSetting {
  id: number;
  tenant: number;
  agent_commission_percent: string;
  voucher_prefix: string;
  max_funding_amount: Kobo;
  updated_at: IsoDateTime;
}

export interface TenantSettingWrite {
  paystack_secret_key?: string;
  paystack_public_key?: string;
  agent_commission_percent?: string;
  voucher_prefix?: string;
  max_funding_amount?: Kobo;
}

export interface PublicTenant {
  id: number;
  slug: string;
  name: string;
}

export interface PublicPlan {
  id: number;
  name: string;
  price: Kobo;
  duration_hours: number;
  rate_limit: string;
  data_limit: number;
}
