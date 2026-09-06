import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { CheckCircle2, Printer, RotateCcw } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import { Button, Card, FormField, Input, SegmentedControl } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { formatKobo } from '@/lib/formatting/money';
import { can } from '@/services/auth/principal';
import { usePrincipal } from '@/app/auth/useAuth';
import { usePlanOptions } from '@/features/plans/queries';
import type { Voucher } from '@/types/api';
import { PlanPicker } from '../components/PlanPicker';
import { usePrintVouchers } from '../hooks/usePrintVouchers';
import { useGenerateVouchers } from '../queries';
import {
  generateSchema,
  QUANTITY_PRESETS,
  type GenerateInput,
  type GenerateOutput,
} from '../voucherSchemas';

const FIELDS = ['plan_id', 'quantity', 'prefix'] as const;

interface BatchResult {
  vouchers: Voucher[];
  replayed: boolean;
}

export default function GenerateVouchersPage() {
  const principal = usePrincipal();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const plans = usePlanOptions(true);
  const generate = useGenerateVouchers();
  const printer = usePrintVouchers();
  const canPrint = can(principal, 'vouchers.print');
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey('gen'));
  const [result, setResult] = useState<BatchResult | null>(null);

  const initialPlan = Number(searchParams.get('plan'));
  const form = useForm<GenerateInput, unknown, GenerateOutput>({
    resolver: zodResolver(generateSchema),
    defaultValues: {
      plan_id: Number.isFinite(initialPlan) && initialPlan > 0 ? initialPlan : 0,
      quantity: 20,
      prefix: '',
    },
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);
  const [planIdRaw, quantityRaw] = useWatch({
    control: form.control,
    name: ['plan_id', 'quantity'],
  });
  const planId = Number(planIdRaw);
  const quantity = Number(quantityRaw);
  const selectedPlan = useMemo(
    () => plans.data?.find((p) => p.id === planId),
    [plans.data, planId],
  );
  const prefixPlaceholder = selectedPlan?.voucher_prefix
    ? `Defaults to ${selectedPlan.voucher_prefix}`
    : 'Optional';

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      const payload = {
        plan_id: values.plan_id,
        quantity: values.quantity,
        ...(values.prefix ? { prefix: values.prefix } : {}),
      };
      const res = await generate.mutateAsync({ payload, idempotencyKey });
      setResult(res);
    } catch (error) {
      captureError(error);
    }
  });

  function startAnother() {
    setResult(null);
    setIdempotencyKey(newIdempotencyKey('gen'));
    form.reset({ plan_id: planId, quantity, prefix: '' });
  }

  if (result) {
    const ids = result.vouchers.map((v) => v.id);
    const first = result.vouchers[0];
    return (
      <>
        <PageHeader
          title="Vouchers generated"
          backTo="/vouchers"
          crumbs={[{ label: 'Vouchers', to: '/vouchers' }, { label: 'Generate' }]}
        />
        <Card className="max-w-3xl">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-success-600" aria-hidden />
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-semibold text-ink-900">
                {result.vouchers.length} {result.vouchers.length === 1 ? 'voucher' : 'vouchers'}{' '}
                ready
              </h2>
              <p className="mt-1 text-sm text-ink-600">
                {first ? `${first.plan_name} · ${first.price_display}` : ''}
                {result.replayed &&
                  ' · This batch had already been created (your earlier request was replayed, nothing was duplicated).'}
              </p>
            </div>
          </div>
          <Alert tone="info" className="mt-4">
            Passwords are not shown on screen.{' '}
            {canPrint
              ? 'Print the batch now, or later from the voucher list — each print pulls the credentials fresh from the server.'
              : 'Ask a manager to print the credentials for you.'}
          </Alert>
          <ul
            className="mt-4 grid max-h-64 grid-cols-2 gap-1 overflow-y-auto rounded-card border border-border bg-surface-muted p-3 font-mono text-sm sm:grid-cols-3 md:grid-cols-4"
            aria-label="Generated usernames"
          >
            {result.vouchers.map((v) => (
              <li key={v.id}>
                <Link
                  to={`/vouchers/${v.id}`}
                  className="text-ink-700 hover:text-brand-700 hover:underline"
                >
                  {v.username}
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="secondary"
              leadingIcon={<RotateCcw className="h-4 w-4" aria-hidden />}
              onClick={startAnother}
            >
              Generate another batch
            </Button>
            <Button variant="secondary" onClick={() => navigate('/vouchers?status=unused')}>
              View in list
            </Button>
            {canPrint && (
              <Button
                leadingIcon={<Printer className="h-4 w-4" aria-hidden />}
                loading={printer.printing}
                onClick={() => void printer.print(ids)}
              >
                {printer.progress
                  ? `Preparing ${printer.progress.done}/${printer.progress.total}`
                  : 'Print all'}
              </Button>
            )}
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Generate vouchers"
        description="Create a batch of access codes from a plan. Each batch is protected against accidental double submission."
        backTo="/vouchers"
        crumbs={[{ label: 'Vouchers', to: '/vouchers' }, { label: 'Generate' }]}
      />
      <form
        onSubmit={(e) => void submit(e)}
        noValidate
        className="grid gap-6 lg:grid-cols-[1fr_20rem]"
      >
        <div className="flex flex-col gap-6">
          <Card>
            <h2 className="text-sm font-semibold text-ink-900">1. Choose a plan</h2>
            <p className="mb-4 text-sm text-ink-600">Only active plans are listed.</p>
            <Controller
              control={form.control}
              name="plan_id"
              render={({ field, fieldState }) => (
                <>
                  <PlanPicker
                    plans={plans.data}
                    loading={plans.isPending}
                    error={plans.error}
                    onRetry={() => void plans.refetch()}
                    value={Number(field.value) || null}
                    onChange={(id) => field.onChange(id)}
                    invalid={Boolean(fieldState.error)}
                    describedBy="plan-error"
                  />
                  {fieldState.error && (
                    <p id="plan-error" className="mt-2 text-sm text-danger-700" role="alert">
                      {fieldState.error.message}
                    </p>
                  )}
                </>
              )}
            />
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-ink-900">2. How many?</h2>
            <p className="mb-4 text-sm text-ink-600">Up to 100 per batch.</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Controller
                control={form.control}
                name="quantity"
                render={({ field, fieldState }) => (
                  <FormField label="Quantity" required error={fieldState.error?.message}>
                    <div className="flex flex-col gap-2">
                      <SegmentedControl
                        ariaLabel="Quantity presets"
                        size="sm"
                        options={QUANTITY_PRESETS.map((n) => ({
                          value: String(n),
                          label: String(n),
                        }))}
                        value={
                          QUANTITY_PRESETS.includes(
                            Number(field.value) as (typeof QUANTITY_PRESETS)[number],
                          )
                            ? String(field.value)
                            : ''
                        }
                        onChange={(v) => field.onChange(Number(v))}
                      />
                      <Input
                        type="number"
                        min={1}
                        max={100}
                        step={1}
                        inputMode="numeric"
                        value={field.value as number}
                        onChange={(e) => field.onChange(e.target.value)}
                        onBlur={field.onBlur}
                        invalid={Boolean(fieldState.error)}
                        aria-label="Custom quantity"
                      />
                    </div>
                  </FormField>
                )}
              />
              <FormField
                label="Username prefix"
                optionalLabel
                hint={prefixPlaceholder}
                error={form.formState.errors.prefix?.message}
              >
                <Input
                  maxLength={10}
                  className="font-mono uppercase"
                  placeholder="e.g. WK"
                  {...form.register('prefix')}
                />
              </FormField>
            </div>
          </Card>
          {message && <Alert tone="danger">{message}</Alert>}
        </div>
        <aside className="lg:sticky lg:top-20 lg:self-start">
          <Card>
            <h2 className="text-sm font-semibold text-ink-900">Summary</h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500">Plan</dt>
                <dd className="text-right font-medium text-ink-900">{selectedPlan?.name ?? '—'}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500">Quantity</dt>
                <dd className="font-medium text-ink-900 tabular-nums">
                  {Number.isFinite(quantity) && quantity > 0 ? quantity : '—'}
                </dd>
              </div>
              <div className="flex justify-between gap-3 border-t border-border pt-2">
                <dt className="text-ink-500">Face value</dt>
                <dd className="font-semibold text-ink-900 tabular-nums">
                  {selectedPlan && quantity > 0 ? formatKobo(selectedPlan.price * quantity) : '—'}
                </dd>
              </div>
            </dl>
            <Button
              type="submit"
              block
              className="mt-4"
              loading={form.formState.isSubmitting}
              disabled={plans.isPending || (plans.data?.length ?? 0) === 0}
            >
              Generate {Number.isFinite(quantity) && quantity > 0 ? quantity : ''} vouchers
            </Button>
            <p className="mt-2 text-xs text-ink-500">
              Credentials are written to the hotspot immediately; codes work as soon as they are
              printed.
            </p>
          </Card>
        </aside>
      </form>
    </>
  );
}
