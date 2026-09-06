import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ShieldCheck } from 'lucide-react';
import { Alert, useToast } from '@/components/feedback';
import { Button, CopyButton, Dialog, FormField, Input } from '@/components/ui';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { formatDateTime } from '@/lib/formatting/dates';
import type { CreatedStaffInvitation } from '@/types/api';
import { useInvite, useTenantName } from '../queries';
import { inviteSchema, type InviteInput, type InviteOutput } from '../platformSchemas';
import { ServicesField } from './ServicesField';
import { TenantSelect } from './TenantSelect';

const FIELDS = ['email', 'tenant', 'services'] as const;

/**
 * Invite a support-staff account to one tenant. The API returns the plaintext token exactly
 * once (Cache-Control: no-store) and never e-mails it, so the resulting link is shown here
 * until the dialog is closed.
 */
export function InviteDialog({
  open,
  onClose,
  defaultTenant,
}: {
  open: boolean;
  onClose: () => void;
  defaultTenant?: number | undefined;
}) {
  const toast = useToast();
  const invite = useInvite();
  const tenantName = useTenantName();
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey('invite'));
  const [created, setCreated] = useState<CreatedStaffInvitation | null>(null);
  const defaults = (): InviteInput => ({
    email: '',
    tenant: (defaultTenant ? String(defaultTenant) : '') as unknown as number,
    services: [],
  });
  const form = useForm<InviteInput, unknown, InviteOutput>({
    resolver: zodResolver(inviteSchema),
    defaultValues: defaults(),
    mode: 'onTouched',
  });
  const { message, reset, captureError } = useFormSubmit(form.setError, FIELDS);
  const errors = form.formState.errors;

  function close() {
    form.reset(defaults());
    reset();
    setCreated(null);
    onClose();
  }

  const submit = form.handleSubmit(async (values) => {
    reset();
    try {
      const result = await invite.mutateAsync({ payload: values, idempotencyKey });
      setIdempotencyKey(newIdempotencyKey('invite'));
      setCreated(result);
      toast.success('Invitation created', `Share the link with ${result.email}.`);
    } catch (error) {
      setIdempotencyKey(newIdempotencyKey('invite'));
      captureError(error);
    }
  });

  const link = created
    ? `${window.location.origin}/accept-invitation?token=${encodeURIComponent(created.token)}`
    : '';

  return (
    <Dialog
      open={open}
      onClose={close}
      title={created ? 'Invitation ready' : 'Invite staff'}
      description={
        created
          ? undefined
          : 'Staff sign in with their own account and only see the services you grant, for this tenant only.'
      }
      size="lg"
    >
      {created ? (
        <div className="flex flex-col gap-4">
          <Alert tone="warning" title="This link is shown once">
            The system does not e-mail invitations. Copy the link now and send it to {created.email}{' '}
            yourself — it cannot be retrieved again. If it is lost, revoke this invitation and
            create a new one.
          </Alert>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="invitation-link" className="text-sm font-medium text-ink-700">
              Invitation link
            </label>
            <div className="flex items-stretch gap-2">
              <Input
                id="invitation-link"
                readOnly
                value={link}
                onFocus={(e) => e.currentTarget.select()}
                className="font-mono text-xs"
                aria-describedby="invitation-link-hint"
              />
              <CopyButton value={link} label="Copy link" variant="secondary" size="md" />
            </div>
            <p id="invitation-link-hint" className="text-xs text-ink-500">
              Expires {formatDateTime(created.expires_at)}.
            </p>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-ink-500">Tenant</dt>
            <dd className="text-ink-800">{tenantName(created.tenant)}</dd>
            <dt className="text-ink-500">Services</dt>
            <dd className="text-ink-800">{created.services.length}</dd>
          </dl>
          <div className="flex justify-end border-t border-border pt-4">
            <Button onClick={close} leadingIcon={<ShieldCheck className="h-4 w-4" aria-hidden />}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => void submit(e)}
          noValidate
          className="flex flex-col gap-4"
          aria-label="Invite staff"
        >
          {message && <Alert tone="danger">{message}</Alert>}
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              label="Email"
              required
              error={errors.email?.message}
              hint="Used to match the account when the invitation is accepted."
            >
              <Input
                autoFocus
                type="email"
                inputMode="email"
                autoComplete="off"
                {...form.register('email')}
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
              Create invitation
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
