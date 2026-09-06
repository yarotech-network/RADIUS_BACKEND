import type { AgentStatus } from '@/types/api';

export const AGENT_STATUS_LABELS: Record<AgentStatus, string> = {
  pending: 'Pending approval',
  active: 'Active',
  suspended: 'Suspended',
};

export const AGENT_STATUS_FILTERS: { value: AgentStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending approval' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
];

/** approve → active, suspend → suspended; both are no-ops when already in the target state. */
export function canApprove(status: AgentStatus): boolean {
  return status !== 'active';
}
export function canSuspend(status: AgentStatus): boolean {
  return status === 'active';
}
