import { useMemo, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Trash2, UserPlus, Users } from 'lucide-react';
import {
  Avatar,
  Badge,
  Button,
  ConfirmDialog,
  Dialog,
  FormField,
  Input,
  Select,
} from '@/components/ui';
import { Alert, EmptyState, useToast } from '@/components/feedback';
import { DataTable, FilterBar, Pagination, useListParams, type Column } from '@/components/data';
import { usePrincipal } from '@/app/auth/useAuth';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { formatDate } from '@/lib/formatting/dates';
import { errorMessage } from '@/services/api/errors';
import { can } from '@/services/auth/principal';
import type { MembershipRole, TenantMembership } from '@/types/api';
import type { MembershipListParams } from '../api';
import { useAddMember, useChangeRole, useMemberships, useRemoveMember } from '../queries';
import {
  ROLE_OPTIONS,
  addMemberSchema,
  addMemberToPayload,
  type AddMemberInput,
  type AddMemberOutput,
} from '../settingsSchemas';

const FILTERS = ['role'] as const;

function initialsOf(display: string): string {
  const parts = display
    .replace(/[<>()]/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  return (
    (
      (parts[0]?.[0] ?? '') + (parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : '')
    ).toUpperCase() || '?'
  );
}
const ROLE_TONE: Record<MembershipRole, 'brand' | 'info' | 'neutral'> = {
  owner: 'brand',
  manager: 'info',
  staff: 'neutral',
};

export default function TeamSettingsPage() {
  const principal = usePrincipal();
  const canManage = can(principal, 'team.manage');
  const toast = useToast();
  const list = useListParams(FILTERS);
  const params = useMemo<MembershipListParams>(() => {
    const p: MembershipListParams = { page: list.state.page, page_size: list.state.page_size };
    if (list.state.filters.role) p.role = list.state.filters.role as MembershipRole;
    return p;
  }, [list.state]);
  const query = useMemberships(params);
  const changeRole = useChangeRole();
  const remove = useRemoveMember();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<TenantMembership | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const owners = query.data?.results.filter((m) => m.role === 'owner').length ?? 0;

  async function onRoleChange(member: TenantMembership, role: MembershipRole) {
    setActionError(null);
    try {
      await changeRole.mutateAsync({ id: member.id, role });
      toast.success(`${member.user_display} is now ${role}`);
    } catch (error) {
      setActionError(errorMessage(error));
    }
  }

  async function onRemove() {
    if (!removing) return;
    // ConfirmDialog surfaces thrown errors inline (e.g. "The final tenant owner cannot be removed.").
    await remove.mutateAsync(removing.id);
    toast.success(`${removing.user_display} removed from the team`);
  }

  const columns: Column<TenantMembership>[] = [
    {
      key: 'user',
      header: 'Member',
      primary: true,
      cell: (m) => (
        <div className="flex items-center gap-3">
          <Avatar initials={initialsOf(m.user_display)} size="sm" />
          <div className="min-w-0">
            <div className="truncate font-medium text-ink-900">
              {m.user_display}
              {m.user === principal?.user.id && (
                <span className="ml-2 text-xs font-normal text-ink-500">(you)</span>
              )}
            </div>
            <div className="text-xs text-ink-500">User #{m.user}</div>
          </div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      cell: (m) =>
        canManage ? (
          <Select
            aria-label={`Role for ${m.user_display}`}
            size="sm"
            className="max-w-36"
            value={m.role}
            disabled={changeRole.isPending || (m.role === 'owner' && owners <= 1)}
            title={
              m.role === 'owner' && owners <= 1 ? 'A workspace needs at least one owner' : undefined
            }
            onChange={(e) => void onRoleChange(m, e.target.value as MembershipRole)}
            options={ROLE_OPTIONS.map((r) => ({ value: r.value, label: r.label }))}
          />
        ) : (
          <Badge tone={ROLE_TONE[m.role]} size="sm" className="capitalize">
            {m.role}
          </Badge>
        ),
    },
    {
      key: 'since',
      header: 'Member since',
      hideBelow: 'md',
      cell: (m) => <span className="text-ink-600">{formatDate(m.created_at)}</span>,
    },
  ];

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-brand-950">Team members</h2>
          <p className="text-sm text-ink-500">
            {canManage
              ? 'Owners manage the team; managers run day-to-day operations; staff sell and print vouchers.'
              : 'People with access to this workspace. Ask an owner to change roles.'}
          </p>
        </div>
        {canManage && (
          <Button
            leadingIcon={<UserPlus className="h-4 w-4" aria-hidden />}
            onClick={() => setAdding(true)}
          >
            Add member
          </Button>
        )}
      </div>
      {actionError && (
        <Alert tone="danger" className="mb-4" onDismiss={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}
      <FilterBar
        filters={
          <Select
            aria-label="Role"
            size="sm"
            value={list.state.filters.role ?? ''}
            onChange={(e) => list.setFilter('role', e.target.value || undefined)}
            options={[
              { value: '', label: 'All roles' },
              ...ROLE_OPTIONS.map((r) => ({ value: r.value, label: r.label })),
            ]}
          />
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Team members"
        columns={columns}
        rows={query.data?.results}
        rowKey={(m) => m.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        {...(canManage
          ? {
              rowActions: (m: TenantMembership) => (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Remove ${m.user_display}`}
                  title={
                    m.role === 'owner' && owners <= 1
                      ? 'The last owner cannot be removed'
                      : 'Remove from team'
                  }
                  disabled={m.role === 'owner' && owners <= 1}
                  onClick={() => setRemoving(m)}
                  leadingIcon={<Trash2 className="h-4 w-4" aria-hidden />}
                />
              ),
            }
          : {})}
        empty={
          list.activeFilterCount > 0 ? (
            <EmptyState
              icon={<Users className="h-6 w-6" aria-hidden />}
              title="No members with this role"
              action={
                <Button variant="secondary" onClick={list.clearFilters}>
                  Show everyone
                </Button>
              }
            />
          ) : (
            <EmptyState icon={<Users className="h-6 w-6" aria-hidden />} title="No team members" />
          )
        }
      />
      {query.data && query.data.count > 0 && (
        <Pagination
          count={query.data.count}
          page={list.state.page}
          totalPages={query.data.total_pages}
          pageSize={list.state.page_size}
          onPageChange={list.setPage}
          onPageSizeChange={list.setPageSize}
          itemLabel="members"
        />
      )}
      {canManage && principal?.kind === 'member' && (
        <AddMemberDialog
          open={adding}
          onClose={() => setAdding(false)}
          tenantId={principal.tenantId}
        />
      )}
      <ConfirmDialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        onConfirm={onRemove}
        tone="danger"
        title={`Remove ${removing?.user_display ?? 'member'}?`}
        description="They lose access to this workspace immediately. Their account is not deleted and they can be added again later."
        confirmLabel="Remove"
      />
    </>
  );
}

const ADD_FIELDS = ['user', 'role'] as const;

/** The API reports both "already a member somewhere" and "no such user" as `user` field errors. */
function friendlyMemberError(message: string | undefined): string | undefined {
  if (!message) return undefined;
  if (message.includes('already exists'))
    return 'That user already belongs to a workspace. Each account can be in one workspace at a time.';
  if (message.includes('does not exist')) return 'No account with that user ID.';
  return message;
}

function AddMemberDialog({
  open,
  onClose,
  tenantId,
}: {
  open: boolean;
  onClose: () => void;
  tenantId: number;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add team member"
      description="Ask the person for the user ID shown under Settings → General → Your account. They need an existing account that is not already in a workspace."
    >
      {open && <AddMemberForm onClose={onClose} tenantId={tenantId} />}
    </Dialog>
  );
}

function AddMemberForm({ onClose, tenantId }: { onClose: () => void; tenantId: number }) {
  const toast = useToast();
  const add = useAddMember();
  const form = useForm<AddMemberInput, unknown, AddMemberOutput>({
    resolver: zodResolver(addMemberSchema),
    defaultValues: { user: '' as unknown as number, role: 'staff' },
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, ADD_FIELDS);
  const errors = form.formState.errors;
  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      const member = await add.mutateAsync(addMemberToPayload(values, tenantId));
      toast.success(`${member.user_display} added as ${member.role}`);
      onClose();
    } catch (error) {
      captureError(error);
    }
  });
  const role = useWatch({ control: form.control, name: 'role' });
  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      {message && <Alert tone="danger">{friendlyMemberError(message)}</Alert>}
      <FormField label="User ID" required error={friendlyMemberError(errors.user?.message)}>
        <Input
          autoFocus
          type="number"
          inputMode="numeric"
          min={1}
          placeholder="e.g. 42"
          {...form.register('user')}
        />
      </FormField>
      <FormField
        label="Role"
        required
        error={errors.role?.message}
        hint={ROLE_OPTIONS.find((r) => r.value === role)?.description}
      >
        <Select
          {...form.register('role')}
          options={ROLE_OPTIONS.map((r) => ({ value: r.value, label: r.label }))}
        />
      </FormField>
      <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" onClick={onClose} disabled={add.isPending}>
          Cancel
        </Button>
        <Button type="submit" loading={add.isPending}>
          Add member
        </Button>
      </div>
    </form>
  );
}
