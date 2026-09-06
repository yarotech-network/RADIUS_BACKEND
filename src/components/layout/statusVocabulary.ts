import type { BadgeTone } from '@/components/ui/Badge';
import { humanise } from '@/lib/formatting/units';

/**
 * Single status vocabulary for the whole app (analysis/04_DESIGN_SYSTEM.md §3).
 * Unknown values fall back to a neutral badge with a humanised label — never crash on a new enum.
 */
const TONES: Record<string, BadgeTone> = {
  // vouchers
  unused: 'info',
  active: 'success',
  expired: 'neutral',
  disabled: 'danger',
  // payments / funding / operations
  pending: 'warning',
  success: 'success',
  succeeded: 'success',
  failed: 'danger',
  abandoned: 'neutral',
  running: 'info',
  // recovery
  fulfilled: 'success',
  paid_unfulfilled: 'warning',
  unverified: 'neutral',
  // delivery
  not_requested: 'neutral',
  sending: 'info',
  accepted: 'success',
  unknown: 'neutral',
  // agents
  suspended: 'danger',
  // routers — onboarding
  reviewed: 'info',
  approved: 'info',
  waiting_for_vpn: 'warning',
  vpn_failed: 'danger',
  testing_radius: 'warning',
  radius_failed: 'danger',
  accounting_failed: 'danger',
  // routers — deployment
  not_deployed: 'neutral',
  deploying: 'info',
  deployed: 'success',
  // subscriptions
  trial: 'info',
  cancelled: 'neutral',
  // invitations
  revoked: 'danger',
  // generic booleans
  yes: 'success',
  no: 'neutral',
  inactive: 'neutral',
  never: 'neutral',
  passed: 'success',
};

const LABELS: Record<string, string> = {
  paid_unfulfilled: 'Paid, not delivered',
  unverified: 'Not verified',
  not_requested: 'Not requested',
  waiting_for_vpn: 'Waiting for VPN',
  testing_radius: 'Testing RADIUS',
  radius_failed: 'RADIUS failed',
  vpn_failed: 'VPN failed',
  accounting_failed: 'Accounting failed',
  not_deployed: 'Not deployed',
  unused: 'Unused',
  never: 'Never run',
};

export function statusTone(status: string | null | undefined): BadgeTone {
  return (status && TONES[status]) || 'neutral';
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return '—';
  return LABELS[status] ?? humanise(status);
}
