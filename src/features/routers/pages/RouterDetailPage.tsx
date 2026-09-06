import { useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { PageHeader, StatusBadge } from '@/components/layout';
import {
  Button,
  Card,
  ConfirmDialog,
  DescriptionList,
  Dialog,
  Menu,
  Skeleton,
  Tabs,
} from '@/components/ui';
import { Alert, QueryBoundary, useToast } from '@/components/feedback';
import { usePrincipal } from '@/app/auth/useAuth';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { can, type Capability } from '@/services/auth/principal';
import { errorMessage, isApiError } from '@/services/api/errors';
import type { NasDevice } from '@/types/api';
import { useDeleteRouter, useRouter, useRouterHealth, useRouterOperations } from '../queries';
import { ONBOARDING_LABELS, canDeleteRouter, isRouterBusy } from '../routerRules';
import { RouterStateBadges } from '../components/RouterStateBadges';
import { RouterEditForm } from '../components/RouterEditForm';
import { OnboardingPanel } from '../components/OnboardingPanel';
import { ChecksPanel } from '../components/ChecksPanel';
import { VpnPanel } from '../components/VpnPanel';
import { SecretsPanel } from '../components/SecretsPanel';
import { RadiusTestPanel } from '../components/RadiusTestPanel';
import { HistoryPanel } from '../components/HistoryPanel';

type Tab = 'onboarding' | 'vpn' | 'secrets' | 'test' | 'history';
const TAB_ITEMS: { value: Tab; label: string; capability: Capability | null }[] = [
  { value: 'onboarding', label: 'Onboarding', capability: null },
  { value: 'vpn', label: 'VPN & provisioning', capability: null },
  { value: 'secrets', label: 'Secrets', capability: 'routers.manage' },
  { value: 'test', label: 'RADIUS test', capability: 'routers.test' },
  { value: 'history', label: 'History', capability: 'routers.diagnostics' },
];

export default function RouterDetailPage() {
  const { id = '' } = useParams();
  const query = useRouter(id);
  return (
    <QueryBoundary
      query={query}
      errorTitle="Router not found"
      skeleton={
        <>
          <PageHeader title={<Skeleton className="h-7 w-56" />} backTo="/routers" />
          <Card>
            <Skeleton className="h-24 w-full" />
          </Card>
          <Skeleton className="mt-4 h-64 w-full" />
        </>
      }
    >
      {(router) => <RouterDetail router={router} onReload={() => void query.refetch()} />}
    </QueryBoundary>
  );
}

function RouterDetail({ router, onReload }: { router: NasDevice; onReload: () => void }) {
  const principal = usePrincipal();
  const canManage = can(principal, 'routers.manage');
  const canDiagnose = can(principal, 'routers.diagnostics');
  const tabs = TAB_ITEMS.filter((t) => t.capability === null || can(principal, t.capability)).map(
    ({ value, label }) => ({ value, label }),
  );
  const navigate = useNavigate();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab');
  const tab: Tab = tabs.some((t) => t.value === tabParam) ? (tabParam as Tab) : 'onboarding';
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [busyNotice, setBusyNotice] = useState<string | null>(null);
  const health = useRouterHealth(router.id, canDiagnose);
  const ops = useRouterOperations({ router: router.id, page_size: 5 }, canManage);
  const remove = useDeleteRouter();
  const busy = isRouterBusy(router, ops.data?.results);
  const deletable = canDeleteRouter(router, ops.data?.results);

  function selectTab(next: Tab) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next === 'onboarding') p.delete('tab');
        else p.set('tab', next);
        return p;
      },
      { replace: true },
    );
  }

  return (
    <>
      <PageHeader
        backTo="/routers"
        crumbs={[{ label: 'Routers', to: '/routers' }, { label: router.name }]}
        title={
          <span className="inline-flex flex-wrap items-center gap-3">
            {router.name}
            <RouterStateBadges router={router} size="md" />
          </span>
        }
        description={[router.location, router.ip_address].filter(Boolean).join(' · ')}
        actions={
          canManage && (
            <div className="flex gap-2">
              <Button
                variant="secondary"
                leadingIcon={<Pencil className="h-4 w-4" aria-hidden />}
                onClick={() =>
                  busy
                    ? setBusyNotice(
                        'Wait for the current provisioning operation to finish before editing.',
                      )
                    : setEditing(true)
                }
              >
                Edit
              </Button>
              <Menu
                trigger={(props) => (
                  <Button variant="ghost" size="md" aria-label="More actions" {...props}>
                    <MoreHorizontal className="h-4 w-4" aria-hidden />
                  </Button>
                )}
                items={[
                  {
                    key: 'delete',
                    label: deletable ? 'Delete router' : 'Delete (suspend VPN first)',
                    icon: <Trash2 className="h-4 w-4" aria-hidden />,
                    tone: 'danger',
                    disabled: !deletable,
                    onSelect: () => setDeleting(true),
                  },
                ]}
              />
            </div>
          )
        }
      />

      {busyNotice && (
        <Alert tone="warning" className="mb-4" onDismiss={() => setBusyNotice(null)}>
          {busyNotice}
        </Alert>
      )}

      <Card className="mb-4">
        <DescriptionList
          columns={3}
          items={[
            { label: 'NAS IP', value: router.ip_address, mono: true },
            { label: 'Onboarding', value: ONBOARDING_LABELS[router.onboarding_state] },
            {
              label: 'Reachability',
              value: !canDiagnose ? (
                <span className="text-ink-400">—</span>
              ) : health.isPending ? (
                <Skeleton className="h-4 w-32" />
              ) : health.isError ? (
                <span className="text-ink-400">Unknown</span>
              ) : health.data.telemetry_available && health.data.online !== null ? (
                <StatusBadge status={health.data.online ? 'online' : 'offline'} />
              ) : (
                <span className="text-ink-500">Telemetry not available</span>
              ),
            },
            {
              label: 'Last seen',
              value: router.last_seen_at ? (
                <time dateTime={router.last_seen_at} title={formatDateTime(router.last_seen_at)}>
                  {formatRelative(router.last_seen_at)}
                </time>
              ) : (
                <span className="text-ink-400">Never</span>
              ),
            },
            { label: 'Registered', value: formatDateTime(router.created_at) },
            { label: 'Updated', value: formatDateTime(router.updated_at) },
          ]}
        />
      </Card>

      <Tabs
        items={tabs}
        value={tab}
        onChange={selectTab}
        ariaLabel="Router sections"
        className="mb-4"
      />
      <Card>
        {tab === 'onboarding' && (
          <div className="flex flex-col gap-8">
            <OnboardingPanel router={router} canManage={canManage} />
            {canDiagnose && (
              <section aria-labelledby="checks-heading">
                <h3 id="checks-heading" className="mb-2 text-sm font-semibold text-ink-900">
                  Checks
                </h3>
                <ChecksPanel routerId={router.id} />
              </section>
            )}
          </div>
        )}
        {tab === 'vpn' && <VpnPanel router={router} canManage={canManage} />}
        {tab === 'secrets' && (
          <SecretsPanel router={router} canManage={canManage} onReload={onReload} />
        )}
        {tab === 'test' && <RadiusTestPanel router={router} canManage={canManage} />}
        {tab === 'history' && <HistoryPanel routerId={router.id} />}
      </Card>

      {editing && (
        <Dialog open onClose={() => setEditing(false)} title={`Edit ${router.name}`} size="lg">
          <RouterEditForm
            router={router}
            onCancel={() => setEditing(false)}
            onSaved={(saved) => {
              setEditing(false);
              toast.success('Router updated', `${saved.name} saved.`);
            }}
          />
        </Dialog>
      )}
      <ConfirmDialog
        open={deleting}
        onClose={() => setDeleting(false)}
        tone="danger"
        title={`Delete ${router.name}?`}
        description="The router is removed as a RADIUS client and its history is deleted. Sessions already recorded are kept. This cannot be undone."
        confirmLabel="Delete router"
        onConfirm={async () => {
          try {
            await remove.mutateAsync(router.id);
            toast.success('Router deleted', `${router.name} was removed.`);
            navigate('/routers', { replace: true });
          } catch (error) {
            if (isApiError(error) && error.status === 409) {
              setDeleting(false);
              setBusyNotice(errorMessage(error));
              return;
            }
            throw error;
          }
        }}
      />
    </>
  );
}
