import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Dialog, FormField, Input, PasswordInput } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type { AgentProfile } from '@/types/api';
import { useCreateAgent, useUpdateAgent } from '../queries';
import {
  AGENT_CREATE_DEFAULTS,
  agentCreateSchema,
  agentEditSchema,
  agentToEditForm,
  createFormToPayload,
  editFormToPatch,
  type AgentCreateInput,
  type AgentCreateOutput,
  type AgentEditInput,
  type AgentEditOutput,
} from '../agentSchemas';

const CREATE_FIELDS = [
  'username',
  'email',
  'password',
  'phone',
  'shop_name',
  'commission_rate',
] as const;
const EDIT_FIELDS = ['phone', 'shop_name', 'commission_rate'] as const;

function FormActions({
  submitting,
  submitLabel,
  onCancel,
}: {
  submitting: boolean;
  submitLabel: string;
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
      <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
        Cancel
      </Button>
      <Button type="submit" loading={submitting}>
        {submitLabel}
      </Button>
    </div>
  );
}

export function CreateAgentDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (agent: AgentProfile) => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      variant="drawer"
      size="md"
      title="Add agent"
      description="Agents resell vouchers from their own wallet. New agents start as pending until you approve them."
    >
      {open && <CreateAgentForm onCancel={onClose} onCreated={onCreated} />}
    </Dialog>
  );
}

function CreateAgentForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (agent: AgentProfile) => void;
}) {
  const create = useCreateAgent();
  const [idempotencyKey] = useState(() => newIdempotencyKey('agent'));
  const form = useForm<AgentCreateInput, unknown, AgentCreateOutput>({
    resolver: zodResolver(agentCreateSchema),
    defaultValues: AGENT_CREATE_DEFAULTS,
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, CREATE_FIELDS);
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      onCreated(await create.mutateAsync({ payload: createFormToPayload(values), idempotencyKey }));
    } catch (error) {
      captureError(error);
    }
  });

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      {message && <Alert tone="danger">{message}</Alert>}
      <FormField
        label="Username"
        required
        hint="The agent signs in with this."
        error={errors.username?.message}
      >
        <Input
          autoFocus
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          {...form.register('username')}
        />
      </FormField>
      <FormField label="Email" required error={errors.email?.message}>
        <Input type="email" autoComplete="off" inputMode="email" {...form.register('email')} />
      </FormField>
      <FormField
        label="Temporary password"
        required
        hint="At least 8 characters, not all digits. Share it with the agent securely."
        error={errors.password?.message}
      >
        <PasswordInput autoComplete="new-password" {...form.register('password')} />
      </FormField>
      <FormField label="Phone" required error={errors.phone?.message}>
        <Input
          type="tel"
          inputMode="tel"
          placeholder="+234 803 000 0000"
          {...form.register('phone')}
        />
      </FormField>
      <FormField label="Shop name" optionalLabel error={errors.shop_name?.message}>
        <Input placeholder="e.g. Chidi Phones" {...form.register('shop_name')} />
      </FormField>
      <FormField
        label="Commission rate"
        optionalLabel
        hint="Percent of each sale credited as commission. Defaults to 10%."
        error={errors.commission_rate?.message}
      >
        <Input
          inputMode="decimal"
          placeholder="10"
          className="max-w-32"
          trailingSlot={<span className="pr-2 text-sm text-ink-500">%</span>}
          {...form.register('commission_rate')}
        />
      </FormField>
      <FormActions
        submitting={form.formState.isSubmitting}
        submitLabel="Add agent"
        onCancel={onCancel}
      />
    </form>
  );
}

export function EditAgentDialog({
  agent,
  open,
  onClose,
  onSaved,
}: {
  agent: AgentProfile;
  open: boolean;
  onClose: () => void;
  onSaved: (agent: AgentProfile) => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      variant="drawer"
      size="md"
      title={`Edit ${agent.username}`}
      description="Username and email cannot be changed here."
    >
      {open && <EditAgentForm agent={agent} onCancel={onClose} onSaved={onSaved} />}
    </Dialog>
  );
}

function EditAgentForm({
  agent,
  onCancel,
  onSaved,
}: {
  agent: AgentProfile;
  onCancel: () => void;
  onSaved: (agent: AgentProfile) => void;
}) {
  const update = useUpdateAgent();
  const form = useForm<AgentEditInput, unknown, AgentEditOutput>({
    resolver: zodResolver(agentEditSchema),
    defaultValues: agentToEditForm(agent),
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, EDIT_FIELDS);
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    const patch = editFormToPatch(values, agent);
    if (Object.keys(patch).length === 0) {
      onCancel();
      return;
    }
    try {
      onSaved(await update.mutateAsync({ id: agent.id, payload: patch }));
    } catch (error) {
      captureError(error);
    }
  });

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      {message && <Alert tone="danger">{message}</Alert>}
      <FormField label="Phone" required error={errors.phone?.message}>
        <Input type="tel" inputMode="tel" autoFocus {...form.register('phone')} />
      </FormField>
      <FormField label="Shop name" optionalLabel error={errors.shop_name?.message}>
        <Input {...form.register('shop_name')} />
      </FormField>
      <FormField
        label="Commission rate"
        required
        hint="Applies to future sales only."
        error={errors.commission_rate?.message}
      >
        <Input
          inputMode="decimal"
          className="max-w-32"
          trailingSlot={<span className="pr-2 text-sm text-ink-500">%</span>}
          {...form.register('commission_rate')}
        />
      </FormField>
      <FormActions
        submitting={form.formState.isSubmitting}
        submitLabel="Save changes"
        onCancel={onCancel}
      />
    </form>
  );
}
