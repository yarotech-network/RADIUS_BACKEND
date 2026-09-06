import { StatusBadge } from '@/components/layout';
import { Tooltip } from '@/components/ui';
import type { NasDevice } from '@/types/api';
import { DEPLOYMENT_LABELS } from '../routerRules';

/** Onboarding state + deployment status side by side (deployment only when informative). */
export function RouterStateBadges({
  router,
  size = 'sm',
}: {
  router: Pick<NasDevice, 'onboarding_state' | 'deployment_status' | 'is_active'>;
  size?: 'sm' | 'md';
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <StatusBadge status={router.onboarding_state} size={size} dot />
      {router.deployment_status !== 'not_deployed' && (
        <Tooltip content="WireGuard peer deployment">
          <span>
            <StatusBadge status={router.deployment_status} size={size} />
          </span>
        </Tooltip>
      )}
      {!router.is_active && <StatusBadge status="inactive" size={size} />}
      <span className="sr-only">{DEPLOYMENT_LABELS[router.deployment_status]}</span>
    </span>
  );
}

/** Deployment status with the human label from the router vocabulary (e.g. "Not deployed"). */
export function DeploymentBadge({
  status,
  size = 'sm',
}: {
  status: NasDevice['deployment_status'];
  size?: 'sm' | 'md';
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <StatusBadge status={status} size={size} />
      <span className="sr-only">{DEPLOYMENT_LABELS[status]}</span>
    </span>
  );
}
