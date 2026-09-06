import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { ExternalLink, Pencil, Power, Trash2 } from 'lucide-react';
import { PageHeader, Section, StatusBadge } from '@/components/layout';
import {
  Button,
  ButtonLink,
  Card,
  CardHeader,
  ConfirmDialog,
  DescriptionList,
  Skeleton,
  Tabs,
} from '@/components/ui';
import { Alert, ErrorState, useToast } from '@/components/feedback';
import { NotFoundPage } from '@/app/shell/NotFoundPage';
import { isApiError } from '@/services/api/errors';
import { formatDateTime } from '@/lib/formatting/dates';
import type { Tenant } from '@/types/api';
import { useDeleteTenant, useTenant, useUpdateTenant } from '../queries';
import { TenantDialog } from '../components/TenantDialog';
import { TenantMembersPanel } from '../components/TenantMembersPanel';

type Tab = 'overview' | 'members';
const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: 'Overview' },
  { value: 'members', label: 'Members' },
];

/** `/platform/tenants/:id` — one operator: profile, activation, members and cross-links. */
export default function TenantDetailPage() {
  const { id: rawId } = useParams();
  const id = Number(rawId);
  const valid = Number.isInteger(id) && id > 0;
  const query = useTenant(valid ? id : null);
  const tenant = query.data;
  useEffect(() => {
    document.title = `${tenant?.name ?? 'Tenant'} · Platform · Yarotech RADIUS`;
  }, [tenant?.name]);

  if (!valid || (query.isError && isApiError(query.error) && query.error.status === 404)) {
    return (
      <NotFoundPage
        homePath="/platform/tenants"
        title="Tenant not found"
        description="It may have been deleted, or the link is wrong."
      />
    );
  }
  if (query.isError) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        title="Could not load this tenant"
      />
    );
  }
  if (!tenant) {
    return (
      <div className="flex flex-col gap-4" aria-busy>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }
  return <TenantDetail tenant={tenant} />;
}

function TenantDetail({ tenant }: { tenant: Tenant }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get('tab') === 'members' ? 'members' : 'overview';
  const [editing, setEditing] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const update = useUpdateTenant();
  const remove = useDeleteTenant();

  function setTab(next: Tab) {
    const params = new URLSearchParams(searchParams);
    if (next === 'overview') params.delete('tab');
    else params.set('tab', next);
    setSearchParams(params, { replace: true });
  }

  const storefront = `/s/${tenant.slug}`;

  return (
    <>
      <PageHeader
        title={tenant.name}
        crumbs={[{ label: 'Tenants', to: '/platform/tenants' }, { label: tenant.name }]}
        description={
          <span className="inline-flex flex-wrap items-center gap-2">
            <StatusBadge status={tenant.is_active ? 'active' : 'inactive'} size="sm" dot />
            <code className="font-mono text-xs text-ink-500">{storefront}</code>
            {tenant.is_platform_admin && (
              <span className="text-xs text-ink-500">· platform tenant</span>
            )}
          </span>
        }
        actions={
          <>
            <ButtonLink
              to={storefront}
              target="_blank"
              rel="noreferrer"
              variant="secondary"
              trailingIcon={<ExternalLink className="h-4 w-4" aria-hidden />}
            >
              Storefront
            </ButtonLink>
            <Button
              variant="secondary"
              leadingIcon={<Pencil className="h-4 w-4" aria-hidden />}
              onClick={() => setEditing(true)}
            >
              Edit
            </Button>
          </>
        }
      />
      <Tabs
        items={TABS}
        value={tab}
        onChange={setTab}
        ariaLabel="Tenant sections"
        className="mb-5"
      />
      {tab === 'members' ? (
        <TenantMembersPanel tenantId={tenant.id} tenantName={tenant.name} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="flex flex-col gap-6 lg:col-span-2">
            <Card>
              <DescriptionList
                columns={2}
                items={[
                  { label: 'Business name', value: tenant.name },
                  { label: 'Slug', value: tenant.slug, mono: true },
                  { label: 'Contact email', value: tenant.email || '—' },
                  { label: 'Phone', value: tenant.phone || '—' },
                  { label: 'Address', value: tenant.address || '—', span: 2 },
                  { label: 'Created', value: formatDateTime(tenant.created_at) },
                  { label: 'Last updated', value: formatDateTime(tenant.updated_at) },
                ]}
              />
            </Card>
            <Section
              title="Activity"
              description="Tenant-scoped views across the platform console."
            >
              <ul className="grid gap-2 sm:grid-cols-2">
                <CrossLink
                  to={`/platform/routers?tenant=${tenant.id}`}
                  label="Routers"
                  hint="Fleet, onboarding state and health"
                />
                <CrossLink
                  to={`/platform/payments?tenant=${tenant.id}`}
                  label="Payments"
                  hint="Voucher sales, wallet top-ups, subscriptions"
                />
                <CrossLink
                  to={`/platform/staff?tenant=${tenant.id}`}
                  label="Staff access"
                  hint="Support staff assigned to this tenant"
                />
                <CrossLink
                  to={`/platform/audit?tenant=${tenant.id}`}
                  label="Audit log"
                  hint="Every recorded change in this workspace"
                />
              </ul>
            </Section>
          </div>
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader title="At a glance" className="mb-3" />
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-ink-500">Members</dt>
                  <dd className="text-xl font-semibold text-brand-950 tabular-nums">
                    {tenant.member_count}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-500">Vouchers</dt>
                  <dd className="text-xl font-semibold text-brand-950 tabular-nums">
                    {tenant.voucher_count.toLocaleString()}
                  </dd>
                </div>
              </dl>
              <Button variant="link" size="sm" className="mt-2" onClick={() => setTab('members')}>
                Manage members
              </Button>
            </Card>
            <Card>
              <CardHeader title={tenant.is_active ? 'Deactivate' : 'Reactivate'} className="mb-2" />
              <p className="text-sm text-ink-600">
                {tenant.is_active
                  ? 'Blocks sign-in, sales and payments for this operator. Data is kept and can be restored any time.'
                  : 'Restores sign-in, sales and the public storefront for this operator.'}
              </p>
              <Button
                className="mt-3"
                variant={tenant.is_active ? 'secondary' : 'primary'}
                leadingIcon={<Power className="h-4 w-4" aria-hidden />}
                onClick={() => setToggling(true)}
                disabled={tenant.is_platform_admin && tenant.is_active}
                title={
                  tenant.is_platform_admin && tenant.is_active
                    ? 'The platform tenant cannot be deactivated from here'
                    : undefined
                }
              >
                {tenant.is_active ? 'Deactivate tenant' : 'Reactivate tenant'}
              </Button>
            </Card>
            <Card className="border-danger-200">
              <CardHeader title="Danger zone" className="mb-2" />
              <p className="text-sm text-ink-600">
                Deleting removes the tenant and <strong>everything in it</strong> — members,
                routers, plans, vouchers, agents and payment history. This cannot be undone.
              </p>
              {tenant.is_platform_admin ? (
                <Alert tone="warning" className="mt-3">
                  The platform's own tenant cannot be deleted.
                </Alert>
              ) : (
                <Button
                  className="mt-3"
                  variant="danger"
                  leadingIcon={<Trash2 className="h-4 w-4" aria-hidden />}
                  onClick={() => setDeleting(true)}
                >
                  Delete tenant
                </Button>
              )}
            </Card>
          </div>
        </div>
      )}

      <TenantDialog open={editing} onClose={() => setEditing(false)} tenant={tenant} />
      <ConfirmDialog
        open={toggling}
        onClose={() => setToggling(false)}
        tone={tenant.is_active ? 'danger' : 'default'}
        title={tenant.is_active ? `Deactivate ${tenant.name}?` : `Reactivate ${tenant.name}?`}
        description={
          tenant.is_active
            ? 'Members will be signed out on their next request, agents cannot sell, and the storefront will return not found.'
            : 'Members, agents and the storefront will be available again immediately.'
        }
        confirmLabel={tenant.is_active ? 'Deactivate' : 'Reactivate'}
        onConfirm={async () => {
          const next = !tenant.is_active;
          await update.mutateAsync({ id: tenant.id, payload: { is_active: next } });
          toast.success(next ? 'Tenant reactivated' : 'Tenant deactivated');
        }}
      />
      <ConfirmDialog
        open={deleting}
        onClose={() => setDeleting(false)}
        tone="danger"
        title={`Delete ${tenant.name}?`}
        description={
          <>
            This permanently deletes the tenant, its {tenant.member_count} member
            {tenant.member_count === 1 ? '' : 's'} and {tenant.voucher_count.toLocaleString()}{' '}
            vouchers. Type <strong>{tenant.slug}</strong> to confirm.
          </>
        }
        typeToConfirm={tenant.slug}
        confirmLabel="Delete permanently"
        onConfirm={async () => {
          await remove.mutateAsync(tenant.id);
          toast.success(`${tenant.name} deleted`);
          void navigate('/platform/tenants', { replace: true });
        }}
      />
    </>
  );
}

function CrossLink({ to, label, hint }: { to: string; label: string; hint: string }) {
  return (
    <li>
      <Link
        to={to}
        className="flex flex-col rounded-control border border-border bg-surface px-4 py-3 hover:border-border-strong hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-brand-600"
      >
        <span className="text-sm font-medium text-brand-700">{label}</span>
        <span className="text-xs text-ink-500">{hint}</span>
      </Link>
    </li>
  );
}
