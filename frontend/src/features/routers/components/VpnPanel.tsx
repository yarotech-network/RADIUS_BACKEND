import { useState } from 'react';
import { Link } from 'react-router';
import { Cable, PauseCircle, RefreshCw } from 'lucide-react';
import { Button, ConfirmDialog, DescriptionList, Skeleton } from '@/components/ui';
import { Alert, EmptyState, ErrorState, useToast } from '@/components/feedback';
import { StatusBadge } from '@/components/layout';
import { DeploymentBadge } from './RouterStateBadges';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { errorMessage, isApiError } from '@/services/api/errors';
import type { NasDevice, RouterOperation } from '@/types/api';
import { useProvisionRouter, useRouterOperations } from '../queries';
import { isRouterBusy, provisionBlocker, suspendBlocker } from '../routerRules';

export function VpnPanel({ router, canManage }: { router: NasDevice; canManage: boolean }) {
  const toast = useToast();
  const ops = useRouterOperations({ router: router.id, page_size: 10 }, canManage);
  const provision = useProvisionRouter();
  const [confirmSuspend, setConfirmSuspend] = useState(false);
  const [conflict, setConflict] = useState<string | null>(null);
  const operations = ops.data?.results;
  const busy = isRouterBusy(router, operations);
  const provisionWhy = provisionBlocker(router, operations);
  const suspendWhy = suspendBlocker(router, operations);

  async function run(action: 'provision' | 'suspend') {
    setConflict(null);
    try {
      const op = await provision.mutateAsync({ id: router.id, payload: { action } });
      toast.success(
        action === 'provision' ? 'Provisioning queued' : 'Suspension queued',
        `Operation ${op.id.slice(0, 8)} is ${op.status}.`,
      );
    } catch (error) {
      if (isApiError(error) && error.status === 409) setConflict(errorMessage(error));
      else
        toast.error(
          action === 'provision' ? 'Could not start provisioning' : 'Could not suspend',
          errorMessage(error),
        );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <DescriptionList
        columns={3}
        items={[
          { label: 'Deployment', value: <DeploymentBadge status={router.deployment_status} /> },
          {
            label: 'WireGuard IP',
            value: router.wireguard_ip ? (
              <span className="font-mono">{router.wireguard_ip}</span>
            ) : (
              <span className="text-ink-400">Not set</span>
            ),
          },
          {
            label: 'Listen port',
            value: <span className="font-mono">{router.wireguard_port}</span>,
          },
          {
            label: 'Router public key',
            value: router.wireguard_public_key ? (
              <span className="font-mono text-xs break-all">{router.wireguard_public_key}</span>
            ) : (
              <span className="text-ink-400">Not set</span>
            ),
            span: 3,
          },
        ]}
      />

      {conflict && (
        <Alert
          tone="warning"
          title="Another operation is in progress"
          onDismiss={() => setConflict(null)}
        >
          {conflict} This page refreshes automatically while an operation is open.
        </Alert>
      )}

      {canManage && (
        <div className="flex flex-col gap-3 rounded-card border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-ink-900">Provisioning agent</h3>
            <p className="text-xs text-ink-500">
              Provisioning pushes the VPN peer and RADIUS client config to the router; suspending
              removes the peer. Both run asynchronously.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              leadingIcon={<Cable className="h-4 w-4" aria-hidden />}
              onClick={() => void run('provision')}
              disabled={provisionWhy !== null || provision.isPending}
              loading={provision.isPending && provision.variables?.payload.action === 'provision'}
              title={provisionWhy ?? undefined}
            >
              {router.deployment_status === 'deployed' ? 'Re-provision' : 'Provision'}
            </Button>
            <Button
              variant="secondary"
              leadingIcon={<PauseCircle className="h-4 w-4" aria-hidden />}
              onClick={() => setConfirmSuspend(true)}
              disabled={suspendWhy !== null || provision.isPending}
              title={suspendWhy ?? undefined}
            >
              Suspend VPN
            </Button>
          </div>
        </div>
      )}
      {canManage && provisionWhy && !busy && (
        <p className="-mt-3 text-xs text-ink-500">{provisionWhy}</p>
      )}

      {canManage && (
        <section aria-labelledby="ops-heading">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 id="ops-heading" className="text-sm font-semibold text-ink-900">
              Recent operations
            </h3>
            <div className="flex items-center gap-2">
              {busy && (
                <span className="inline-flex items-center gap-1 text-xs text-brand-700">
                  <RefreshCw className="h-3 w-3 animate-spin" aria-hidden /> Live
                </span>
              )}
              <Link
                to={`/routers/operations?router=${router.id}`}
                className="text-xs font-medium text-brand-700 hover:underline"
              >
                View all
              </Link>
            </div>
          </div>
          <OperationsList query={ops} />
        </section>
      )}
      <ConfirmDialog
        open={confirmSuspend}
        onClose={() => setConfirmSuspend(false)}
        tone="danger"
        title={`Suspend VPN for ${router.name}?`}
        description="The agent removes the router's WireGuard peer. Customers stay connected to the hotspot but RADIUS traffic over the VPN stops."
        confirmLabel="Suspend VPN"
        onConfirm={() => run('suspend')}
      />
    </div>
  );
}

function OperationsList({ query }: { query: ReturnType<typeof useRouterOperations> }) {
  if (query.isPending) return <Skeleton className="h-24 w-full" />;
  if (query.isError)
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        compact
        title="Operations could not be loaded"
      />
    );
  if (query.data.results.length === 0)
    return (
      <EmptyState
        compact
        title="No operations yet"
        description="Provisioning and suspension runs will be listed here."
      />
    );
  return (
    <ul className="divide-y divide-border rounded-card border border-border bg-surface">
      {query.data.results.map((op) => (
        <OperationRow key={op.id} op={op} />
      ))}
    </ul>
  );
}

export function OperationRow({
  op,
  showRouter,
}: {
  op: RouterOperation;
  showRouter?: string | undefined;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
      <StatusBadge status={op.status} />
      <span className="font-medium text-ink-900 capitalize">{op.action}</span>
      {showRouter && <span className="text-ink-600">{showRouter}</span>}
      <span className="text-ink-500">
        {op.attempts} {op.attempts === 1 ? 'attempt' : 'attempts'}
      </span>
      {op.error_code && (
        <code className="rounded bg-danger-50 px-1.5 py-0.5 text-xs text-danger-700">
          {op.error_code}
        </code>
      )}
      <span className="ml-auto text-xs text-ink-500">
        <time dateTime={op.created_at} title={formatDateTime(op.created_at)}>
          {formatRelative(op.created_at)}
        </time>
        {op.completed_at && <> · finished {formatRelative(op.completed_at)}</>}
      </span>
    </li>
  );
}
