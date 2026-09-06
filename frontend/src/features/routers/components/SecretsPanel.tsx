import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { KeyRound, ShieldCheck } from 'lucide-react';
import {
  Button,
  Checkbox,
  DescriptionList,
  Dialog,
  FormField,
  PasswordInput,
} from '@/components/ui';
import { Alert, useToast } from '@/components/feedback';
import { formatDateTime } from '@/lib/formatting/dates';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { isApiError } from '@/services/api/errors';
import type { NasDevice, ReplaceSecretsRequest } from '@/types/api';
import { useReplaceSecrets } from '../queries';
import {
  replaceSecretsSchema,
  type ReplaceSecretsInput,
  type ReplaceSecretsOutput,
} from '../routerSchemas';

const FIELDS = [
  'current_password',
  'nas_secret',
  'routeros_password',
  'clear_routeros_password',
] as const;
const ALIASES = {
  routeros_password_encrypted: 'routeros_password',
  expected_updated_at: 'current_password',
};

export function SecretsPanel({
  router,
  canManage,
  onReload,
}: {
  router: NasDevice;
  canManage: boolean;
  onReload: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-5">
      <Alert tone="info" title="Secrets are write-only">
        The RADIUS shared secret and RouterOS password are stored encrypted and can never be viewed
        again. If you lose one, replace it here and update the router to match.
      </Alert>
      <DescriptionList
        columns={2}
        items={[
          {
            label: 'RADIUS shared secret',
            value: (
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4 text-success-600" aria-hidden /> Stored encrypted
              </span>
            ),
          },
          {
            label: 'RouterOS password',
            value: (
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4 text-success-600" aria-hidden /> Stored encrypted or
                empty
              </span>
            ),
          },
          { label: 'RouterOS username', value: router.routeros_username || null, mono: true },
          { label: 'Last changed', value: formatDateTime(router.updated_at) },
        ]}
      />
      {canManage ? (
        <div>
          <Button
            leadingIcon={<KeyRound className="h-4 w-4" aria-hidden />}
            onClick={() => setOpen(true)}
          >
            Replace secrets…
          </Button>
        </div>
      ) : (
        <p className="text-xs text-ink-500">Only managers can replace secrets.</p>
      )}
      {open && (
        <ReplaceSecretsDialog router={router} onClose={() => setOpen(false)} onReload={onReload} />
      )}
    </div>
  );
}

function ReplaceSecretsDialog({
  router,
  onClose,
  onReload,
}: {
  router: NasDevice;
  onClose: () => void;
  onReload: () => void;
}) {
  const toast = useToast();
  const replace = useReplaceSecrets();
  const [idempotencyKey] = useState(() => newIdempotencyKey('secrets'));
  const [stale, setStale] = useState(false);
  const form = useForm<ReplaceSecretsInput, unknown, ReplaceSecretsOutput>({
    resolver: zodResolver(replaceSecretsSchema),
    defaultValues: {
      current_password: '',
      nas_secret: '',
      routeros_password: '',
      clear_routeros_password: false,
    },
    mode: 'onTouched',
  });
  const {
    message,
    reset: resetErrors,
    captureError,
  } = useFormSubmit(form.setError, FIELDS, ALIASES);
  const clearRos = useWatch({ control: form.control, name: 'clear_routeros_password' });

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    setStale(false);
    const payload: ReplaceSecretsRequest = {
      current_password: values.current_password,
      expected_updated_at: router.updated_at,
    };
    if (values.nas_secret) payload.nas_secret = values.nas_secret;
    if (values.clear_routeros_password) payload.routeros_password_encrypted = '';
    else if (values.routeros_password)
      payload.routeros_password_encrypted = values.routeros_password;
    try {
      await replace.mutateAsync({ id: router.id, payload, idempotencyKey });
      toast.success('Secrets replaced', 'Update the router so it matches the new values.');
      onClose();
    } catch (error) {
      if (isApiError(error) && error.status === 409 && /reload/i.test(error.message))
        setStale(true);
      else captureError(error);
    }
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title="Replace secrets"
      description={`Confirm with your own password. Leave a field blank to keep the current value for ${router.name}.`}
      size="md"
    >
      <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
        {stale && (
          <Alert
            tone="warning"
            title="This router changed since you opened it"
            actions={
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  onReload();
                  onClose();
                }}
              >
                Reload router
              </Button>
            }
          >
            Reload to pick up the latest version, then try again.
          </Alert>
        )}
        {message && !stale && <Alert tone="danger">{message}</Alert>}
        <FormField
          label="New RADIUS shared secret"
          optionalLabel
          hint="At least 8 characters."
          error={form.formState.errors.nas_secret?.message}
        >
          <PasswordInput
            autoComplete="new-password"
            spellCheck={false}
            className="font-mono"
            {...form.register('nas_secret')}
          />
        </FormField>
        <FormField
          label="New RouterOS password"
          optionalLabel
          error={form.formState.errors.routeros_password?.message}
        >
          <PasswordInput
            autoComplete="new-password"
            disabled={clearRos}
            {...form.register('routeros_password')}
          />
        </FormField>
        <Checkbox
          label="Remove the stored RouterOS password"
          description="The provisioning agent will no longer be able to log in to RouterOS."
          {...form.register('clear_routeros_password')}
        />
        <hr className="border-border" />
        <FormField
          label="Your password"
          required
          hint="Re-authenticate to authorise the change."
          error={form.formState.errors.current_password?.message}
        >
          <PasswordInput autoComplete="current-password" {...form.register('current_password')} />
        </FormField>
        <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={form.formState.isSubmitting}
          >
            Cancel
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting} disabled={stale}>
            Replace secrets
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
