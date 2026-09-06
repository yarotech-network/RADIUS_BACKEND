import {
  CHECK_TYPES,
  ROUTER_TRANSITIONS,
  type CheckType,
  type DeploymentStatus,
  type NasDevice,
  type OnboardingState,
  type RouterOnboardingCheck,
  type RouterOperation,
} from '@/types/api';

/** Human labels for the onboarding state machine (apps/routers/state_machine.py). */
export const ONBOARDING_LABELS: Record<OnboardingState, string> = {
  pending: 'Pending review',
  reviewed: 'Reviewed',
  approved: 'Approved',
  waiting_for_vpn: 'Waiting for VPN',
  vpn_failed: 'VPN failed',
  testing_radius: 'Testing RADIUS',
  radius_failed: 'RADIUS failed',
  accounting_failed: 'Accounting failed',
  active: 'Active',
  suspended: 'Suspended',
};

/** The "happy path" through onboarding, used for the progress stepper. */
export const ONBOARDING_STEPS: readonly { state: OnboardingState; title: string; hint: string }[] =
  [
    { state: 'pending', title: 'Registered', hint: 'Router details submitted.' },
    { state: 'reviewed', title: 'Reviewed', hint: 'Details checked by a manager.' },
    { state: 'approved', title: 'Approved', hint: 'Cleared for connection.' },
    { state: 'waiting_for_vpn', title: 'VPN', hint: 'WireGuard peer provisioned and reachable.' },
    { state: 'testing_radius', title: 'RADIUS', hint: 'Authentication and accounting verified.' },
    { state: 'active', title: 'Active', hint: 'Serving customers.' },
  ];

const FAILURE_PARENT: Partial<Record<OnboardingState, OnboardingState>> = {
  vpn_failed: 'waiting_for_vpn',
  radius_failed: 'testing_radius',
  accounting_failed: 'testing_radius',
};

/** Index into ONBOARDING_STEPS the router is currently at (failures map to their step). */
export function onboardingStepIndex(state: OnboardingState): number {
  if (state === 'suspended') return -1;
  const effective = FAILURE_PARENT[state] ?? state;
  return ONBOARDING_STEPS.findIndex((s) => s.state === effective);
}

export function isFailureState(state: OnboardingState): boolean {
  return state in FAILURE_PARENT;
}

export function nextStates(state: OnboardingState): readonly OnboardingState[] {
  return ROUTER_TRANSITIONS[state] ?? [];
}

/** How to present a transition button: forward / retry / back / suspend. */
export function transitionIntent(
  from: OnboardingState,
  to: OnboardingState,
): 'forward' | 'retry' | 'back' | 'suspend' | 'fail' {
  if (to === 'suspended') return 'suspend';
  if (to === 'vpn_failed' || to === 'radius_failed' || to === 'accounting_failed') return 'fail';
  if (isFailureState(from) || from === 'suspended') return to === 'pending' ? 'back' : 'retry';
  const fi = onboardingStepIndex(from);
  const ti = onboardingStepIndex(to);
  return ti < fi ? 'back' : 'forward';
}

export const DEPLOYMENT_LABELS: Record<DeploymentStatus, string> = {
  not_deployed: 'Not deployed',
  deploying: 'Deploying…',
  deployed: 'Deployed',
  failed: 'Deployment failed',
};

export const CHECK_LABELS: Record<CheckType, string> = {
  ping: 'Reachability (ping)',
  routeros_api: 'RouterOS API',
  wireguard_peer: 'WireGuard peer',
  radius_auth: 'RADIUS authentication',
  radius_acct: 'RADIUS accounting',
  firewall: 'Firewall rules',
};

export interface CheckRow {
  type: CheckType;
  label: string;
  status: 'passed' | 'failed' | 'never';
  checkedAt: string | null;
  details: Record<string, unknown>;
}

/** Merge stored checks with the full catalogue so never-run checks are visible. */
export function checkRows(checks: readonly RouterOnboardingCheck[] | undefined): CheckRow[] {
  return CHECK_TYPES.map((type) => {
    const found = checks?.find((c) => c.check_type === type);
    return {
      type,
      label: CHECK_LABELS[type],
      status: found ? (found.passed ? 'passed' : 'failed') : 'never',
      checkedAt: found?.checked_at ?? null,
      details: found?.details ?? {},
    };
  });
}

export function isOperationOpen(op: RouterOperation): boolean {
  return op.status === 'pending' || op.status === 'running';
}

/** Mirrors the backend guards in perform_update / perform_destroy / provisioning. */
export function isRouterBusy(router: NasDevice, operations?: readonly RouterOperation[]): boolean {
  return router.deployment_status === 'deploying' || Boolean(operations?.some(isOperationOpen));
}

export function canDeleteRouter(
  router: NasDevice,
  operations?: readonly RouterOperation[],
): boolean {
  return (
    !['deploying', 'deployed'].includes(router.deployment_status) &&
    !isRouterBusy(router, operations)
  );
}

/** Why "Provision" is not available right now (null = allowed). */
export function provisionBlocker(
  router: NasDevice,
  operations?: readonly RouterOperation[],
): string | null {
  if (isRouterBusy(router, operations)) return 'A provisioning operation is already in progress.';
  if (!router.wireguard_public_key) return 'Add the WireGuard public key first.';
  if (!router.wireguard_ip) return 'Assign a WireGuard IP first.';
  if (!router.is_active) return 'The router is inactive.';
  return null;
}

export function suspendBlocker(
  router: NasDevice,
  operations?: readonly RouterOperation[],
): string | null {
  if (isRouterBusy(router, operations)) return 'A provisioning operation is already in progress.';
  if (!router.wireguard_public_key) return 'No WireGuard peer is configured.';
  return null;
}

export function describeAuditAction(action: string): string {
  const known: Record<string, string> = {
    manual_transition: 'State changed',
    state_change: 'State changed',
    radius_auth_test: 'RADIUS test run',
    radius_disconnect_request: 'Session disconnect requested',
    provisioning_requested: 'Provisioning requested',
    provision: 'Peer provisioned',
    suspend: 'Peer suspended',
    secrets_replaced: 'Secrets replaced',
  };
  return known[action] ?? action.replaceAll('_', ' ');
}
