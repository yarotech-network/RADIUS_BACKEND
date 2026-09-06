import type { IsoDateTime, PageParams } from './common';

export type OnboardingState =
  | 'pending'
  | 'reviewed'
  | 'approved'
  | 'waiting_for_vpn'
  | 'vpn_failed'
  | 'testing_radius'
  | 'radius_failed'
  | 'accounting_failed'
  | 'active'
  | 'suspended';

export type DeploymentStatus = 'not_deployed' | 'deploying' | 'deployed' | 'failed';

/** Mirror of RouterStateMachine.VALID_TRANSITIONS (apps/routers/state_machine.py). */
export const ROUTER_TRANSITIONS: Readonly<Record<OnboardingState, readonly OnboardingState[]>> = {
  pending: ['reviewed'],
  reviewed: ['approved', 'pending'],
  approved: ['waiting_for_vpn'],
  waiting_for_vpn: ['vpn_failed', 'testing_radius'],
  vpn_failed: ['waiting_for_vpn', 'suspended'],
  testing_radius: ['radius_failed', 'accounting_failed', 'active'],
  radius_failed: ['testing_radius', 'suspended'],
  accounting_failed: ['testing_radius', 'suspended'],
  active: ['suspended'],
  suspended: ['active', 'pending'],
};

/** Secrets (`nas_secret`, `routeros_password_encrypted`) are write-only. */
export interface NasDevice {
  id: string;
  name: string;
  ip_address: string;
  wireguard_ip: string | null;
  wireguard_public_key: string;
  wireguard_port: number;
  routeros_username: string;
  location: string;
  tenant: number;
  tenant_name: string;
  onboarding_state: OnboardingState;
  deployment_status: DeploymentStatus;
  is_active: boolean;
  last_seen_at: IsoDateTime | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface NasDeviceCreate {
  name: string;
  ip_address: string;
  nas_secret: string;
  wireguard_ip?: string | null;
  wireguard_public_key?: string;
  wireguard_port?: number;
  routeros_username?: string;
  routeros_password_encrypted?: string;
  location?: string;
  is_active?: boolean;
}

/** Regular PATCH must not include secrets (400) — use replace-secrets. */
export type NasDeviceUpdate = Partial<
  Omit<NasDeviceCreate, 'nas_secret' | 'routeros_password_encrypted'>
>;

export interface RouterListParams extends PageParams {
  is_active?: boolean;
  onboarding_state?: OnboardingState;
  deployment_status?: DeploymentStatus;
  tenant?: number;
}

export interface RouterTransitionRequest {
  to_state: OnboardingState;
}

export interface RouterTransitionResult {
  correlation_id: string;
}

export interface RouterAuditEvent {
  id: string;
  router: string;
  action: string;
  from_state: OnboardingState | null;
  to_state: OnboardingState | null;
  correlation_id: string;
  details: Record<string, unknown>;
  created_at: IsoDateTime;
}

export type CheckType =
  'ping' | 'routeros_api' | 'wireguard_peer' | 'radius_auth' | 'radius_acct' | 'firewall';

export const CHECK_TYPES: readonly CheckType[] = [
  'ping',
  'routeros_api',
  'wireguard_peer',
  'radius_auth',
  'radius_acct',
  'firewall',
] as const;

export interface RouterOnboardingCheck {
  id: number;
  router: string;
  check_type: CheckType;
  passed: boolean;
  details: Record<string, unknown>;
  checked_at: IsoDateTime;
}

export interface RouterHealth {
  router: string;
  is_active: boolean;
  onboarding_state: OnboardingState;
  deployment_status: DeploymentStatus;
  last_seen_at: IsoDateTime | null;
  observed_at: IsoDateTime;
  checks: { check_type: CheckType; passed: boolean; checked_at: IsoDateTime }[];
  /** Always null in the current backend. */
  online: boolean | null;
  /** Always false in the current backend. */
  telemetry_available: boolean;
}

export interface RouterRadiusTestRequest {
  username: string;
  password: string;
}

export interface RouterRadiusTestResult {
  passed: boolean;
}

export type OperationAction = 'provision' | 'suspend';
export type OperationStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export interface RouterOperation {
  id: string;
  router: string;
  action: OperationAction;
  status: OperationStatus;
  attempts: number;
  error_code: string;
  created_at: IsoDateTime;
  completed_at: IsoDateTime | null;
}

export interface OperationListParams extends PageParams {
  router?: string;
  status?: OperationStatus;
  action?: OperationAction;
}

export interface ProvisionRequest {
  action: OperationAction;
}

export interface ReplaceSecretsRequest {
  current_password: string;
  nas_secret?: string;
  /** Empty string explicitly clears the stored RouterOS password. */
  routeros_password_encrypted?: string;
  expected_updated_at: IsoDateTime;
}
