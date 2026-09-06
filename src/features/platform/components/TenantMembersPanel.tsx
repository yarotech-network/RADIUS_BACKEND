import { useMemo, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Trash2, UserPlus, Users } from 'lucide-react';
import { Button, ConfirmDialog, Dialog, FormField, Input, Select } from '@/components/ui';
import { Alert, EmptyState, useToast } from '@/components/feedback';
import { DataTable, Pagination, useListParams, type Column } from '@/components/data';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { formatDate } from '@/lib/formatting/dates';
import { errorMessage } from '@/services/api/errors';
import type { MembershipListParams, MembershipRole, TenantMembership } from '@/types/api';
import { ROLE_OPTIONS } from '@/features/settings/settingsSchemas';
import {
  useAddMembership,
  useChangeMembershipRole,
  useMemberships,
  useRemoveMembership,
} from '../queries';
import { friendlyMemberError } from '../platformRules';
import {
  adminMembershipSchema,
  type AdminMembershipInput,
  type AdminMembershipOutput,
} from '../platformSchemas';

/** Members of one tenant, administered from the platform console (`tenant-memberships/?tenant=`). */
export function TenantMembersPanel({
  tenantId,
  tenantName,
}: {
  tenantId: number;
  tenantName: string;
}) {
  const toast = useToast();
  const list = useListParams([], { page_size: 20 });
  const params = useMemo<MembershipListParams>(
    () => ({ tenant: tenantId, page: list.state.page, page_size: list.state.page_size }),
    [tenantId, list.state],
  );
  const query = useMemberships(params);
  const changeRole = useChangeMembershipRole();
  const remove = useRemoveMembership();
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

  const columns: Column<TenantMembership>[] = [
    {
      key: 'user',
      header: 'Member',
      primary: true,
      cell: (m) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-ink-900">{m.user_display}</div>
          <div className="text-xs text-ink-500">User #{m.user}</div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      cell: (m) => (
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
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-500">
          People who sign in to the <span className="text-ink-800 font-medium">{tenantName}</span>{' '}
          workspace. A tenant always keeps at least one owner.
        </p>
        <Button
          size="sm"
          leadingIcon={<UserPlus className="h-4 w-4" aria-hidden />}
          onClick={() => setAdding(true)}
        >
          Add member
        </Button>
      </div>
      {actionError && (
        <Alert tone="danger" onDismiss={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}
      <DataTable
        caption={`Members of ${tenantName}`}
        columns={columns}
        rows={query.data?.results}
        rowKey={(m) => m.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        dense
        rowActions={(m) => (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Remove ${m.user_display}`}
            title={
              m.role === 'owner' && owners <= 1
                ? 'The last owner cannot be removed'
                : 'Remove from workspace'
            }
            disabled={m.role === 'owner' && owners <= 1}
            onClick={() => setRemoving(m)}
            leadingIcon={<Trash2 className="h-4 w-4" aria-hidden />}
          />
        )}
        empty={
          <EmptyState
            icon={<Users className="h-6 w-6" aria-hidden />}
            title="No members yet"
            description="Add the operator's owner account so they can sign in and finish setup."
            action={<Button onClick={() => setAdding(true)}>Add member</Button>}
          />
        }
      />
      {query.data && query.data.count > list.state.page_size && (
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
      <AddMemberDialog open={adding} onClose={() => setAdding(false)} tenantId={tenantId} />
      <ConfirmDialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        onConfirm={async () => {
          if (!removing) return;
          await remove.mutateAsync(removing.id);
          toast.success(`${removing.user_display} removed from ${tenantName}`);
        }}
        tone="danger"
        title={`Remove ${removing?.user_display ?? 'member'}?`}
        description="They lose access to this workspace immediately. Their account is not deleted."
        confirmLabel="Remove"
      />
    </div>
  );
}

const ADD_FIELDS = ['user', 'role'] as const;

function AddMemberDialog({
  open,
  onClose,
  tenantId,
}: {
  open: boolean;
  onClose: () => void;
  tenantId: number;
}) {
  const toast = useToast();
  const add = useAddMembership();
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey('member'));
  const form = useForm<AdminMembershipInput, unknown, AdminMembershipOutput>({
    resolver: zodResolver(adminMembershipSchema),
    defaultValues: { user: '' as unknown as number, role: 'staff' },
    mode: 'onTouched',
  });
  const { message, reset, captureError } = useFormSubmit(form.setError, ADD_FIELDS);
  const errors = form.formState.errors;
  const role = useWatch({ control: form.control, name: 'role' });

  function close() {
    form.reset({ user: '' as unknown as number, role: 'staff' });
    reset();
    onClose();
  }

  const submit = form.handleSubmit(async (values) => {
    reset();
    try {
      const member = await add.mutateAsync({
        payload: { user: values.user, tenant: tenantId, role: values.role },
        idempotencyKey,
      });
      setIdempotencyKey(newIdempotencyKey('member'));
      toast.success(`${member.user_display} added as ${member.role}`);
      close();
    } catch (error) {
      setIdempotencyKey(newIdempotencyKey('member'));
      captureError(error);
    }
  });

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Add member"
      description="The account must already exist and not belong to another workspace."
      size="sm"
    >
      <form
        onSubmit={(e) => void submit(e)}
        noValidate
        className="flex flex-col gap-4"
        aria-label="Add member"
      >
        {message && <Alert tone="danger">{friendlyMemberError(message)}</Alert>}
        <FormField
          label="User ID"
          required
          error={friendlyMemberError(errors.user?.message)}
          hint="Numeric account ID (there is no user search yet)."
        >
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
        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Add member
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
