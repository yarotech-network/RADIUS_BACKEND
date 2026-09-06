import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { KeyRound } from 'lucide-react';
import { Button, FormField, Input, PasswordInput, Skeleton } from '@/components/ui';
import { Alert, QueryBoundary, useToast } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { formatDateTime } from '@/lib/formatting/dates';
import type { TenantSetting } from '@/types/api';
import { useTenantSettings, useUpdateTenantSettings } from '../queries';
import { SettingsCard } from '../components/SettingsCard';
import {
  billingSettingsSchema,
  settingsFormToPatch,
  settingsToForm,
  type BillingSettingsInput,
  type BillingSettingsOutput,
} from '../settingsSchemas';

export default function BillingSettingsPage() {
  const settings = useTenantSettings();
  return (
    <QueryBoundary
      query={settings}
      errorTitle="Settings could not be loaded"
      skeleton={<Skeleton className="h-96 w-full" />}
    >
      {(data) => <BillingForm settings={data} />}
    </QueryBoundary>
  );
}

const FIELDS = [
  'agent_commission_percent',
  'voucher_prefix',
  'max_funding_amount',
  'paystack_public_key',
  'paystack_secret_key',
] as const;

function BillingForm({ settings }: { settings: TenantSetting }) {
  const toast = useToast();
  const update = useUpdateTenantSettings();
  const form = useForm<BillingSettingsInput, unknown, BillingSettingsOutput>({
    resolver: zodResolver(billingSettingsSchema),
    defaultValues: settingsToForm(settings),
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);
  const errors = form.formState.errors;

  useEffect(() => {
    if (!form.formState.isDirty) form.reset(settingsToForm(settings));
  }, [settings, form]);

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    const patch = settingsFormToPatch(values, settings);
    if (Object.keys(patch).length === 0) {
      toast.info('Nothing to save');
      return;
    }
    try {
      const saved = await update.mutateAsync(patch);
      form.reset(settingsToForm(saved));
      toast.success(
        'Billing settings saved',
        patch.paystack_secret_key || patch.paystack_public_key
          ? 'Paystack keys updated. They are stored securely and never shown again.'
          : undefined,
      );
    } catch (error) {
      captureError(error);
    }
  });

  return (
    <form onSubmit={(e) => void submit(e)} noValidate aria-label="Billing and payouts">
      {message && (
        <Alert tone="danger" className="mb-4">
          {message}
        </Alert>
      )}
      <SettingsCard
        id="paystack"
        title="Paystack"
        description="Keys from your Paystack dashboard. Customers pay into your own Paystack account; the platform never sees your balance."
      >
        <div className="mb-4 flex items-start gap-2 rounded-card border border-border bg-surface-muted p-3 text-xs text-ink-600">
          <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
          <span>
            For security the stored keys are never displayed. Leave a field blank to keep the
            current key; type a new one to replace it.
          </span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Public key"
            hint="Starts with pk_test_ or pk_live_"
            error={errors.paystack_public_key?.message}
          >
            <Input
              autoComplete="off"
              spellCheck={false}
              placeholder="Unchanged"
              {...form.register('paystack_public_key')}
            />
          </FormField>
          <FormField
            label="Secret key"
            hint="Starts with sk_test_ or sk_live_"
            error={errors.paystack_secret_key?.message}
          >
            <PasswordInput
              autoComplete="new-password"
              placeholder="Unchanged"
              {...form.register('paystack_secret_key')}
            />
          </FormField>
        </div>
      </SettingsCard>
      <SettingsCard
        id="vouchers"
        title="Vouchers & agents"
        description="Defaults applied when vouchers are generated and when agents sell on your behalf."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField
            label="Voucher prefix"
            hint="Up to 10 letters/digits, e.g. WH"
            error={errors.voucher_prefix?.message}
          >
            <Input
              autoCapitalize="characters"
              maxLength={10}
              {...form.register('voucher_prefix')}
            />
          </FormField>
          <FormField
            label="Agent commission"
            hint="Recorded for reporting; not applied to wallets automatically"
            error={errors.agent_commission_percent?.message}
          >
            <div className="relative">
              <Input
                inputMode="decimal"
                className="pr-8"
                {...form.register('agent_commission_percent')}
              />
              <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-ink-400">
                %
              </span>
            </div>
          </FormField>
          <FormField
            label="Max wallet top-up"
            hint="Per agent funding request"
            error={errors.max_funding_amount?.message}
          >
            <div className="relative">
              <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-ink-400">
                ₦
              </span>
              <Input
                inputMode="decimal"
                className="pl-7"
                {...form.register('max_funding_amount')}
              />
            </div>
          </FormField>
        </div>
        <div className="mt-6 flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs text-ink-500">
            Last updated {formatDateTime(settings.updated_at)}
          </span>
          <div className="flex gap-2 sm:justify-end">
            <Button
              type="button"
              variant="secondary"
              onClick={() => form.reset(settingsToForm(settings))}
              disabled={!form.formState.isDirty || update.isPending}
            >
              Discard
            </Button>
            <Button type="submit" loading={update.isPending} disabled={!form.formState.isDirty}>
              Save changes
            </Button>
          </div>
        </div>
      </SettingsCard>
    </form>
  );
}
