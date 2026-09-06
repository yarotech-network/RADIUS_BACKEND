import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { Ban, Mail, Pencil, ShieldOff, Trash2, UserPlus } from 'lucide-react';
import { PageHeader, StatusBadge } from '@/components/layout';
import { DataTable, FilterBar, Pagination, useListParams, type Column } from '@/components/data';
import { Button, ConfirmDialog, Select, Tabs } from '@/components/ui';
import { Alert, EmptyState, useToast } from '@/components/feedback';
import { formatDate, formatDateTime, formatRelative } from '@/lib/formatting/dates';
import type {
  StaffAssignment,
  StaffAssignmentListParams,
  StaffInvitation,
  StaffInvitationListParams,
  StaffInvitationStatus,
} from '@/types/api';
import {
  useAssignments,
  useInvitations,
  useRevokeAssignment,
  useRevokeInvitation,
  useTenantName,
} from '../queries';
import { invitationDisplayStatus } from '../platformRules';
import { InviteDialog } from '../components/InviteDialog';
import { EditGrantsDialog, NewAssignmentDialog } from '../components/AssignmentDialogs';
import { ServiceChips } from '../components/ServiceChips';
import { TenantSelect } from '../components/TenantSelect';

type View = 'assignments' | 'invitations';
const VIEWS: { value: View; label: string }[] = [
  { value: 'assignments', label: 'Assignments' },
  { value: 'invitations', label: 'Invitations' },
];
const FILTERS = ['tenant', 'status', 'is_active'] as const;
const INVITE_STATUSES: readonly string[] = ['pending', 'accepted', 'revoked'];

/** `/platform/staff` — platform support staff: who can reach which tenant, and pending invitations. */
export default function StaffPage() {
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const view: View = searchParams.get('view') === 'invitations' ? 'invitations' : 'assignments';
  const list = useListParams(FILTERS);
  const tenantName = useTenantName();
  const [inviting, setInviting] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [editing, setEditing] = useState<StaffAssignment | null>(null);
  const [revokingAssignment, setRevokingAssignment] = useState<StaffAssignment | null>(null);
  const [revokingInvite, setRevokingInvite] = useState<StaffInvitation | null>(null);
  const [now] = useState(() => Date.now());
  const revokeAssignment = useRevokeAssignment();
  const revokeInvitation = useRevokeInvitation();
  useEffect(() => {
    document.title = 'Staff access · Platform · Yarotech RADIUS';
  }, []);

  function setView(next: View) {
    const params = new URLSearchParams(searchParams);
    if (next === 'assignments') params.delete('view');
    else params.set('view', next);
    params.delete('page');
    params.delete('status');
    params.delete('is_active');
    setSearchParams(params, { replace: true });
  }

  const tenantRaw = Number(list.state.filters.tenant);
  const tenantId = Number.isInteger(tenantRaw) && tenantRaw > 0 ? tenantRaw : undefined;
  const { page, page_size: pageSize } = list.state;
  const isActive = list.state.filters.is_active;
  const status = list.state.filters.status;

  const assignmentParams = useMemo<StaffAssignmentListParams>(() => {
    const p: StaffAssignmentListParams = { page, page_size: pageSize };
    if (tenantId) p.tenant = tenantId;
    if (isActive) p.is_active = isActive === 'true';
    return p;
  }, [page, pageSize, tenantId, isActive]);
  const invitationParams = useMemo<StaffInvitationListParams>(() => {
    const p: StaffInvitationListParams = { page, page_size: pageSize };
    if (tenantId) p.tenant = tenantId;
    if (status && INVITE_STATUSES.includes(status)) p.status = status as StaffInvitationStatus;
    return p;
  }, [page, pageSize, tenantId, status]);

  const assignments = useAssignments(assignmentParams);
  const invitations = useInvitations(invitationParams);
  const active = view === 'assignments' ? assignments : invitations;

  const tenantCell = (id: number) => (
    <Link to={`/platform/tenants/${id}`} className="text-brand-700 hover:underline">
      {tenantName(id)}
    </Link>
  );

  const assignmentColumns: Column<StaffAssignment>[] = [
    {
      key: 'user',
      header: 'Staff account',
      primary: true,
      cell: (a) => (
        <div className="min-w-0">
          <div className="font-medium text-ink-900">User #{a.user}</div>
          <div className="text-xs text-ink-500">since {formatDate(a.created_at)}</div>
        </div>
      ),
    },
    { key: 'tenant', header: 'Tenant', cell: (a) => tenantCell(a.tenant) },
    { key: 'services', header: 'Services', cell: (a) => <ServiceChips services={a.services} /> },
    {
      key: 'status',
      header: 'Status',
      cell: (a) => <StatusBadge status={a.is_active ? 'active' : 'inactive'} size="sm" dot />,
    },
  ];
  const invitationColumns: Column<StaffInvitation>[] = [
    {
      key: 'email',
      header: 'Invitee',
      primary: true,
      cell: (i) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-ink-900">{i.email}</div>
          <div className="text-xs text-ink-500">sent {formatRelative(i.created_at)}</div>
        </div>
      ),
    },
    { key: 'tenant', header: 'Tenant', cell: (i) => tenantCell(i.tenant) },
    {
      key: 'services',
      header: 'Services',
      hideBelow: 'lg',
      cell: (i) => <ServiceChips services={i.services} max={3} />,
    },
    {
      key: 'status',
      header: 'Status',
      cell: (i) => (
        <span className="inline-flex items-center gap-1.5">
          <StatusBadge status={invitationDisplayStatus(i, now)} size="sm" dot />
        </span>
      ),
    },
    {
      key: 'expires',
      header: 'Expires',
      hideBelow: 'md',
      cell: (i) => (
        <time
          dateTime={i.expires_at}
          title={formatDateTime(i.expires_at)}
          className={i.status === 'pending' ? 'text-ink-600' : 'text-ink-400'}
        >
          {formatRelative(i.expires_at)}
        </time>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Staff access"
        description="Platform support staff see only the tenants and services granted here. Invitations create the account; assignments grant access."
        actions={
          <>
            <Button
              variant="secondary"
              leadingIcon={<UserPlus className="h-4 w-4" aria-hidden />}
              onClick={() => setAssigning(true)}
            >
              New assignment
            </Button>
            <Button
              leadingIcon={<Mail className="h-4 w-4" aria-hidden />}
              onClick={() => setInviting(true)}
            >
              Invite staff
            </Button>
          </>
        }
      />
      <Alert tone="info" className="mb-4">
        Invitation links are shown once and are not e-mailed by the system — copy and send them
        yourself.
      </Alert>
      <Tabs
        items={VIEWS}
        value={view}
        onChange={setView}
        ariaLabel="Staff views"
        className="mb-4"
      />
      <FilterBar
        filters={
          <>
            <TenantSelect
              value={list.state.filters.tenant ?? ''}
              onChange={(v) => list.setFilter('tenant', v || undefined)}
            />
            {view === 'assignments' ? (
              <Select
                aria-label="Active"
                size="sm"
                value={list.state.filters.is_active ?? ''}
                onChange={(e) => list.setFilter('is_active', e.target.value || undefined)}
                options={[
                  { value: '', label: 'Active or paused' },
                  { value: 'true', label: 'Active only' },
                  { value: 'false', label: 'Paused only' },
                ]}
              />
            ) : (
              <Select
                aria-label="Status"
                size="sm"
                value={list.state.filters.status ?? ''}
                onChange={(e) => list.setFilter('status', e.target.value || undefined)}
                options={[
                  { value: '', label: 'All statuses' },
                  { value: 'pending', label: 'Pending' },
                  { value: 'accepted', label: 'Accepted' },
                  { value: 'revoked', label: 'Revoked' },
                ]}
              />
            )}
          </>
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      {view === 'assignments' ? (
        <DataTable
          caption="Staff assignments"
          columns={assignmentColumns}
          rows={assignments.data?.results}
          rowKey={(a) => a.id}
          loading={assignments.isPending}
          refreshing={assignments.isFetching && !assignments.isPending}
          error={assignments.error}
          onRetry={() => void assignments.refetch()}
          rowActions={(a) => (
            <span className="inline-flex gap-1">
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Edit grants for user ${a.user}`}
                title="Edit grants"
                onClick={() => setEditing(a)}
                leadingIcon={<Pencil className="h-4 w-4" aria-hidden />}
              />
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Revoke assignment for user ${a.user}`}
                title="Revoke assignment"
                onClick={() => setRevokingAssignment(a)}
                leadingIcon={<Trash2 className="h-4 w-4" aria-hidden />}
              />
            </span>
          )}
          empty={
            <EmptyState
              icon={<ShieldOff className="h-6 w-6" aria-hidden />}
              title={
                list.activeFilterCount > 0 ? 'No assignments match' : 'No staff assignments yet'
              }
              description={
                list.activeFilterCount > 0
                  ? undefined
                  : 'Invite a staff member, or grant an existing staff account access to a tenant.'
              }
              action={
                list.activeFilterCount > 0 ? (
                  <Button variant="secondary" onClick={list.clearFilters}>
                    Clear filters
                  </Button>
                ) : (
                  <Button onClick={() => setInviting(true)}>Invite staff</Button>
                )
              }
            />
          }
        />
      ) : (
        <DataTable
          caption="Staff invitations"
          columns={invitationColumns}
          rows={invitations.data?.results}
          rowKey={(i) => i.id}
          loading={invitations.isPending}
          refreshing={invitations.isFetching && !invitations.isPending}
          error={invitations.error}
          onRetry={() => void invitations.refetch()}
          rowActions={(i) =>
            i.status === 'pending' ? (
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Revoke invitation for ${i.email}`}
                title="Revoke invitation"
                onClick={() => setRevokingInvite(i)}
                leadingIcon={<Ban className="h-4 w-4" aria-hidden />}
              />
            ) : null
          }
          empty={
            <EmptyState
              icon={<Mail className="h-6 w-6" aria-hidden />}
              title={list.activeFilterCount > 0 ? 'No invitations match' : 'No invitations yet'}
              action={
                list.activeFilterCount > 0 ? (
                  <Button variant="secondary" onClick={list.clearFilters}>
                    Clear filters
                  </Button>
                ) : (
                  <Button onClick={() => setInviting(true)}>Invite staff</Button>
                )
              }
            />
          }
        />
      )}
      {active.data && active.data.count > 0 && (
        <Pagination
          count={active.data.count}
          page={list.state.page}
          totalPages={active.data.total_pages}
          pageSize={list.state.page_size}
          onPageChange={list.setPage}
          onPageSizeChange={list.setPageSize}
          itemLabel={view}
        />
      )}

      <InviteDialog open={inviting} onClose={() => setInviting(false)} defaultTenant={tenantId} />
      <NewAssignmentDialog
        open={assigning}
        onClose={() => setAssigning(false)}
        defaultTenant={tenantId}
      />
      <EditGrantsDialog assignment={editing} onClose={() => setEditing(null)} />
      <ConfirmDialog
        open={revokingAssignment !== null}
        onClose={() => setRevokingAssignment(null)}
        tone="danger"
        title={`Revoke access for user #${revokingAssignment?.user ?? ''}?`}
        description={`They immediately lose access to ${revokingAssignment ? tenantName(revokingAssignment.tenant) : 'this tenant'}. To pause instead, edit the grants and switch it off.`}
        confirmLabel="Revoke"
        onConfirm={async () => {
          if (!revokingAssignment) return;
          await revokeAssignment.mutateAsync(revokingAssignment.id);
          toast.success('Assignment revoked');
        }}
      />
      <ConfirmDialog
        open={revokingInvite !== null}
        onClose={() => setRevokingInvite(null)}
        tone="danger"
        title={`Revoke invitation for ${revokingInvite?.email ?? ''}?`}
        description="The link stops working immediately. Create a new invitation if they still need access."
        confirmLabel="Revoke invitation"
        onConfirm={async () => {
          if (!revokingInvite) return;
          await revokeInvitation.mutateAsync(revokingInvite.id);
          toast.success('Invitation revoked');
        }}
      />
    </>
  );
}
