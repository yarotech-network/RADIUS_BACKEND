import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, FormField, Input, Select } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { usePlanOptions } from '@/features/plans/queries';
import type { Voucher } from '@/types/api';
import { useCreateManualVoucher, useUpdateVoucher } from '../queries';
import {
  manualVoucherSchema,
  type ManualVoucherInput,
  type ManualVoucherOutput,
} from '../voucherSchemas';

const FIELDS = ['username', 'password', 'plan', 'device_limit'] as const;

/**
 * Manual voucher: create a specific username/password (e.g. for a known customer) or edit a
 * pristine one. Editing re-writes the RADIUS credentials, so the password is required again.
 */
export function ManualVoucherForm({
  voucher,
  onSaved,
  onCancel,
}: {
  voucher?: Voucher;
  onSaved: (voucher: Voucher) => void;
  onCancel: () => void;
}) {
  const plans = usePlanOptions(true);
  const create = useCreateManualVoucher();
  const update = useUpdateVoucher();
  const [idempotencyKey] = useState(() => newIdempotencyKey('voucher'));
  const form = useForm<ManualVoucherInput, unknown, ManualVoucherOutput>({
    resolver: zodResolver(manualVoucherSchema),
    defaultValues: {
      username: voucher?.username ?? '',
      password: '',
      plan: voucher?.plan ?? 0,
      device_limit: voucher?.device_limit ?? 1,
    },
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);

  useEffect(() => {
    form.reset({
      username: voucher?.username ?? '',
      password: '',
      plan: voucher?.plan ?? 0,
      device_limit: voucher?.device_limit ?? 1,
    });
  }, [voucher, form]);

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      const saved = voucher
        ? await update.mutateAsync({ id: voucher.id, payload: values })
        : await create.mutateAsync({ payload: values, idempotencyKey });
      onSaved(saved);
    } catch (error) {
      captureError(error);
    }
  });

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-5">
      {message && <Alert tone="danger">{message}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Username" required error={form.formState.errors.username?.message}>
          <Input
            autoFocus
            autoComplete="off"
            spellCheck={false}
            className="font-mono"
            {...form.register('username')}
          />
        </FormField>
        <FormField
          label="Password"
          required
          hint={voucher ? 'Enter a new password — the current one cannot be shown.' : undefined}
          error={form.formState.errors.password?.message}
        >
          <Input
            autoComplete="off"
            spellCheck={false}
            className="font-mono"
            {...form.register('password')}
          />
        </FormField>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Plan" required error={form.formState.errors.plan?.message}>
          <Select
            placeholder={plans.isPending ? 'Loading plans…' : 'Choose a plan'}
            disabled={plans.isPending}
            options={(plans.data ?? []).map((p) => ({
              value: String(p.id),
              label: `${p.name} · ${p.price_display}`,
            }))}
            {...form.register('plan')}
          />
        </FormField>
        <FormField
          label="Device limit"
          required
          hint="Simultaneous devices allowed."
          error={form.formState.errors.device_limit?.message}
        >
          <Input
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            {...form.register('device_limit')}
          />
        </FormField>
      </div>
      <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={form.formState.isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" loading={form.formState.isSubmitting}>
          {voucher ? 'Save changes' : 'Create voucher'}
        </Button>
      </div>
    </form>
  );
}
