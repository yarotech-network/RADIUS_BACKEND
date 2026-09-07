import type { IsoDateTime, PageParams } from './common';

/** Computed server-side by `User.role`. */
export type UserRole =
  'platform_admin' | 'owner' | 'manager' | 'staff' | 'agent' | 'platform_staff' | 'user';

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  role: UserRole;
  tenant_name: string | null;
  tenant_id: number | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface LoginResponse extends TokenPair {
  user: User;
}

export interface AgentLoginResponse extends TokenPair {
  agent: { id: number; username: string; shop_name: string };
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  tenant_name: string;
  phone: string;
}

/** Registration no longer returns tokens: the account unlocks after the emailed OTP is confirmed. */
export interface RegisterResponse {
  user: User;
  detail: string;
}

export interface VerifyEmailRequest {
  email: string;
  code: string;
}

export interface ResendVerificationResponse {
  message: string;
}

export interface RefreshRequest {
  refresh: string;
}

/** ROTATE_REFRESH_TOKENS=True: a new refresh token is returned and the old one is blacklisted. */
export interface RefreshResponse {
  access: string;
  refresh: string;
}

export interface UpdateUserRequest {
  username?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
}

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  uid: string;
  token: string;
  password: string;
  password_confirm: string;
}

/** Service grants available to platform staff (apps/accounts/staff_api.py::SERVICES). */
export type StaffService =
  | 'routers.view'
  | 'routers.test'
  | 'live_sessions.view'
  | 'live_sessions.disconnect'
  | 'payments.view'
  | 'payments.support'
  | 'vouchers.generate'
  | 'vouchers.print';

export const STAFF_SERVICES: readonly StaffService[] = [
  'routers.view',
  'routers.test',
  'live_sessions.view',
  'live_sessions.disconnect',
  'payments.view',
  'payments.support',
  'vouchers.generate',
  'vouchers.print',
] as const;

export interface StaffAssignment {
  id: number;
  user: number;
  tenant: number;
  services: StaffService[];
  is_active: boolean;
  created_at: IsoDateTime;
}

export interface StaffAssignmentWrite {
  user: number;
  tenant: number;
  services: StaffService[];
  is_active?: boolean;
}

export type StaffInvitationStatus = 'pending' | 'accepted' | 'revoked';

export interface StaffInvitation {
  id: string;
  email: string;
  tenant: number;
  services: StaffService[];
  expires_at: IsoDateTime;
  status: StaffInvitationStatus;
  created_at: IsoDateTime;
}

/** The plaintext token is returned exactly once, on creation. */
export interface CreatedStaffInvitation extends StaffInvitation {
  token: string;
}

export interface StaffInvitationWrite {
  email: string;
  tenant: number;
  services: StaffService[];
}

export interface StaffInvitationListParams extends PageParams {
  tenant?: number;
  status?: StaffInvitationStatus;
}

export interface StaffAssignmentListParams extends PageParams {
  user?: number;
  tenant?: number;
  is_active?: boolean;
}

export interface AcceptInvitationRequest {
  token: string;
  username?: string;
  password?: string;
}
