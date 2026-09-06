import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, useToast } from '@/components/feedback';
import { Button, Dialog, FormField, Input, Switch } from '@/components/ui';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type { StaffAssignment } from '@/types/api';
import { useCreateAssignment, useTenantName, useUpdateAssignment } from '../queries';
import {
  assignmentSchema,
  grantsSchema,
  type AssignmentInput,
  type AssignmentOutput,
  type GrantsInput,
  type GrantsOutput,
} from '../platformSchemas';
import { friendlyAssignmentError } from '../platformRules';
import { ServicesField } from './ServicesField';
import { TenantSelect } from './TenantSelect';

const CREATE_FIELDS = ['user', 'tenant', 'services'] as const;

/** Grant an existing platform-staff account access to a tenant. */
export function NewAssignmentDialog({
  open,
  onClose,
  defaultTenant,
}: {
  open: boolean;
  onClose: () => void;
  defaultTenant?: number | undefined;
}) {
  const toast = useToast();
  const create = useCreateAssignment();
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey('assign'));
  const defaults = (): AssignmentInput => ({
    user: '' as unknown as number,
    tenant: (defaultTenant ? String(defaultTenant) : '') as unknown as number,
    services: [],
  });
  const form = useForm<AssignmentInput, unknown, AssignmentOutput>({
    resolver: zodResolver(assignmentSchema),
    defaultValues: defaults(),
    mode: 'onTouched',
  });
  const { message, reset, captureError } = useFormSubmit(form.setError, CREATE_FIELDS);
  const errors = form.formState.errors;

  function close() {
    form.reset(defaults());
    reset();
    onClose();
  }

  const submit = form.handleSubmit(async (values) => {
    reset();
    try {
      await create.mutateAsync({ payload: values, idempotencyKey });
      setIdempotencyKey(newIdempotencyKey('assign'));
      toast.success('Assignment created');
      close();
    } catch (error) {
      setIdempotencyKey(newIdempotencyKey('assign'));
      captureError(error);
    }
  });

  return (
    <Dialog
      open={open}
      onClose={close}
      title="New assignment"
      description="For staff accounts that already exist. To onboard someone new, send an invitation instead."
      size="lg"
    >
      <form
        onSubmit={(e) => void submit(e)}
        noValidate
        className="flex flex-col gap-4"
        aria-label="New assignment"
      >
        {message && <Alert tone="danger">{friendlyAssignmentError(message)}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="User ID"
            required
            error={friendlyAssignmentError(errors.user?.message)}
            hint="Numeric ID of the platform-staff account."
          >
            <Input
              autoFocus
              type="number"
              inputMode="numeric"
              min={1}
              placeholder="e.g. 6"
              {...form.register('user')}
            />
          </FormField>
          <FormField label="Tenant" required error={errors.tenant?.message}>
            <Controller
              control={form.control}
              name="tenant"
              render={({ field }) => (
                <TenantSelect
                  id={field.name}
                  required
                  size="md"
                  value={field.value ? String(field.value) : ''}
                  onChange={(v) => field.onChange(v)}
                  invalid={Boolean(errors.tenant)}
                />
              )}
            />
          </FormField>
        </div>
        <Controller
          control={form.control}
          name="services"
          render={({ field }) => (
            <ServicesField
              value={field.value ?? []}
              onChange={field.onChange}
              error={errors.services?.message}
            />
          )}
        />
        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Create assignment
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

const GRANT_FIELDS = ['services', 'is_active'] as const;

/** Edit the services + active flag of one assignment (user and tenant are immutable by design). */
export function EditGrantsDialog({
  assignment,
  onClose,
}: {
  assignment: StaffAssignment | null;
  onClose: () => void;
}) {
  const tenantName = useTenantName();
  return (
    <Dialog
      open={assignment !== null}
      onClose={onClose}
      title="Edit grants"
      description={
        assignment ? `User #${assignment.user} · ${tenantName(assignment.tenant)}` : undefined
      }
      size="lg"
    >
      {/* Mounted per assignment so the form always starts from that row's current grants. */}
      {assignment && <GrantsForm key={assignment.id} assignment={assignment} onClose={onClose} />}
    </Dialog>
  );
}

function GrantsForm({ assignment, onClose }: { assignment: StaffAssignment; onClose: () => void }) {
  const toast = useToast();
  const update = useUpdateAssignment();
  const form = useForm<GrantsInput, unknown, GrantsOutput>({
    resolver: zodResolver(grantsSchema),
    defaultValues: { services: assignment.services, is_active: assignment.is_active },
  });
  const { message, reset, captureError } = useFormSubmit(form.setError, GRANT_FIELDS);
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    reset();
    const payload: Partial<GrantsOutput> = {};
    const sameServices =
      values.services.length === assignment.services.length &&
      values.services.every((s) => assignment.services.includes(s));
    if (!sameServices) payload.services = values.services;
    if (values.is_active !== assignment.is_active) payload.is_active = values.is_active;
    if (Object.keys(payload).length === 0) {
      toast.info('Nothing to save');
      onClose();
      return;
    }
    try {
      await update.mutateAsync({ id: assignment.id, payload });
      toast.success('Grants updated');
      onClose();
    } catch (error) {
      captureError(error);
    }
  });

  return (
    <form
      onSubmit={(e) => void submit(e)}
      noValidate
      className="flex flex-col gap-4"
      aria-label="Edit grants"
    >
      {message && <Alert tone="danger">{friendlyAssignmentError(message)}</Alert>}
      <Controller
        control={form.control}
        name="services"
        render={({ field }) => (
          <ServicesField
            value={field.value ?? []}
            onChange={field.onChange}
            error={errors.services?.message}
          />
        )}
      />
      <Controller
        control={form.control}
        name="is_active"
        render={({ field }) => (
          <div className="flex items-start justify-between gap-4 rounded-control border border-border px-3 py-2.5">
            <div>
              <p className="text-sm font-medium text-ink-900">Active</p>
              <p className="text-xs text-ink-500">
                Pause access without deleting the assignment; grants are kept for later.
              </p>
            </div>
            <Switch
              checked={Boolean(field.value)}
              onCheckedChange={field.onChange}
              label="Active"
            />
          </div>
        )}
      />
      <div className="flex justify-end gap-2 border-t border-border pt-4">
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Save grants
        </Button>
      </div>
    </form>
  );
}
