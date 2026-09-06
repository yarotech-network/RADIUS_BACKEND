import { useEffect, useMemo, useState } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Checkbox, FormField, Input, Select } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { formatHours } from '@/lib/formatting/units';
import type { InternetPlan } from '@/types/api';
import {
  DURATION_PRESETS,
  formToPlan,
  planFormSchema,
  planToForm,
  type PlanFormInput,
  type PlanFormOutput,
} from '../planSchema';
import { useCreatePlan, useUpdatePlan } from '../queries';

const FIELDS = [
  'name',
  'price',
  'duration_hours',
  'rate_limit',
  'data_limit_mb',
  'voucher_prefix',
  'is_active',
] as const;
const ALIASES = { data_limit: 'data_limit_mb' };

export function PlanForm({
  plan,
  onSaved,
  onCancel,
}: {
  plan?: InternetPlan;
  onSaved: (plan: InternetPlan) => void;
  onCancel: () => void;
}) {
  const create = useCreatePlan();
  const update = useUpdatePlan();
  const [idempotencyKey] = useState(() => newIdempotencyKey('plan'));
  const form = useForm<PlanFormInput, unknown, PlanFormOutput>({
    resolver: zodResolver(planFormSchema),
    defaultValues: planToForm(plan),
    mode: 'onTouched',
  });
  const {
    message,
    reset: resetErrors,
    captureError,
  } = useFormSubmit(form.setError, FIELDS, ALIASES);
  const duration = useWatch({ control: form.control, name: 'duration_hours' });
  const presetValue = useMemo(
    () =>
      DURATION_PRESETS.some((p) => p.hours === Number(duration)) ? String(duration) : 'custom',
    [duration],
  );
  const [customDuration, setCustomDuration] = useState(presetValue === 'custom');

  useEffect(() => {
    form.reset(planToForm(plan));
  }, [plan, form]);

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      const saved = plan
        ? await update.mutateAsync({ id: plan.id, payload: formToPlan(values) })
        : await create.mutateAsync({ payload: formToPlan(values), idempotencyKey });
      onSaved(saved);
    } catch (error) {
      captureError(error);
    }
  });

  const busy = form.formState.isSubmitting;

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-5">
      {message && <Alert tone="danger">{message}</Alert>}
      <FormField label="Plan name" required error={form.formState.errors.name?.message}>
        <Input
          autoFocus
          placeholder="e.g. 1 Day Unlimited"
          maxLength={100}
          {...form.register('name')}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Price"
          required
          hint="Customers and agents pay this amount."
          error={form.formState.errors.price?.message}
        >
          <Input inputMode="decimal" prefix="₦" placeholder="500" {...form.register('price')} />
        </FormField>
        <FormField label="Duration" required error={form.formState.errors.duration_hours?.message}>
          {customDuration ? (
            <Input
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              placeholder="Hours"
              trailingSlot={<span className="text-xs text-ink-500">hours</span>}
              {...form.register('duration_hours')}
            />
          ) : (
            <Select
              value={presetValue}
              onChange={(e) => {
                if (e.target.value === 'custom') {
                  setCustomDuration(true);
                  return;
                }
                form.setValue('duration_hours', Number(e.target.value), {
                  shouldDirty: true,
                  shouldValidate: true,
                });
              }}
              options={[
                ...DURATION_PRESETS.map((p) => ({ value: String(p.hours), label: p.label })),
                { value: 'custom', label: 'Custom…' },
              ]}
            />
          )}
        </FormField>
      </div>
      {customDuration && (
        <p className="-mt-3 text-xs text-ink-500">
          {Number(duration) > 0
            ? `= ${formatHours(Number(duration))}`
            : 'Enter the number of hours the plan lasts once activated.'}{' '}
          <button
            type="button"
            className="text-brand-600 hover:underline"
            onClick={() => setCustomDuration(false)}
          >
            Use a preset
          </button>
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Speed limit"
          required
          hint="Upload/download as MikroTik rate-limit, e.g. 5M/10M."
          error={form.formState.errors.rate_limit?.message}
        >
          <Input placeholder="5M/10M" className="font-mono" {...form.register('rate_limit')} />
        </FormField>
        <FormField
          label="Data cap"
          hint="0 = unlimited."
          error={form.formState.errors.data_limit_mb?.message}
        >
          <Input
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
            trailingSlot={<span className="text-xs text-ink-500">MB</span>}
            {...form.register('data_limit_mb')}
          />
        </FormField>
      </div>
      <FormField
        label="Voucher prefix"
        optionalLabel
        hint="Prepended to generated usernames (letters and digits, max 10)."
        error={form.formState.errors.voucher_prefix?.message}
      >
        <Input
          placeholder="e.g. DAY"
          maxLength={10}
          className="font-mono uppercase"
          {...form.register('voucher_prefix')}
        />
      </FormField>
      <Controller
        control={form.control}
        name="is_active"
        render={({ field }) => (
          <Checkbox
            checked={field.value}
            onChange={(e) => field.onChange(e.target.checked)}
            label="Active"
            description="Inactive plans cannot be sold or used to generate vouchers, but existing vouchers keep working."
          />
        )}
      />
      <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" loading={busy}>
          {plan ? 'Save changes' : 'Create plan'}
        </Button>
      </div>
    </form>
  );
}
