import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Store, Wallet } from 'lucide-react';
import { Button, FormField, Input } from '@/components/ui';
import { Alert, EmptyState, ErrorState } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { formatKobo } from '@/lib/formatting/money';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { cn } from '@/lib/utilities/cn';
import { isApiError } from '@/services/api/errors';
import { usePublicPlans, usePublicTenant } from '@/features/storefront/queries';
import { PlanCard, PlanCardSkeleton } from '@/features/storefront/components/PlanCard';
import type { AgentVoucherAllocation, PublicPlan } from '@/types/api';
import { useAgentWallet, useGenerateVouchers } from '../queries';
import { useStoreSlug } from '../storeSlug';
import { sellCost, sellSchema, type SellInput, type SellOutput } from '../sellSchema';
import { StoreLinkForm } from '../components/StoreLink';
import { SaleResult } from '../components/SaleResult';

const FIELDS = ['plan_id', 'quantity'] as const;

export default function AgentSellPage() {
  const [slug, setSlug] = useStoreSlug();
  useEffect(() => {
    document.title = 'Sell vouchers · Agent portal';
  }, []);

  if (!slug) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold text-brand-950">Sell vouchers</h1>
        <StoreLinkForm />
      </div>
    );
  }
  return <SellForm slug={slug} onChangeStore={() => setSlug(null)} />;
}

function SellForm({ slug, onChangeStore }: { slug: string; onChangeStore: () => void }) {
  const tenant = usePublicTenant(slug);
  const plans = usePublicPlans(slug);
  const wallet = useAgentWallet();
  const generate = useGenerateVouchers();
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey('agent-gen'));
  const [sold, setSold] = useState<{ vouchers: AgentVoucherAllocation[]; planName: string } | null>(
    null,
  );

  const form = useForm<SellInput, unknown, SellOutput>({
    resolver: zodResolver(sellSchema),
    defaultValues: { plan_id: 0, quantity: 1 },
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);
  const errors = form.formState.errors;
  const planId = useWatch({ control: form.control, name: 'plan_id' });
  const quantityRaw = useWatch({ control: form.control, name: 'quantity' });
  const quantity = Number(quantityRaw);
  const plan = useMemo(
    () => plans.data?.results.find((p) => p.id === planId) ?? null,
    [plans.data, planId],
  );
  const cost = plan ? sellCost(plan.price, quantity) : 0;
  const balance = wallet.data?.balance ?? null;
  const short = balance !== null && cost > balance;

  // The storefront slug may point at a tenant the agent does not belong to; the backend rejects
  // the plan with a 400 we surface on the field. Reset the choice when the slug changes.
  useEffect(() => {
    form.setValue('plan_id', 0);
  }, [slug, form]);

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      const res = await generate.mutateAsync({
        payload: { plan_id: values.plan_id, quantity: values.quantity },
        idempotencyKey,
      });
      setSold({ vouchers: res.vouchers, planName: plan?.name ?? 'Voucher' });
      setIdempotencyKey(newIdempotencyKey('agent-gen'));
      form.reset({ plan_id: 0, quantity: 1 });
    } catch (error) {
      setIdempotencyKey(newIdempotencyKey('agent-gen'));
      if (isApiError(error) && /insufficient/i.test(error.message)) {
        form.setError('root', { message: 'insufficient' });
        return;
      }
      captureError(error);
    }
  });

  if (sold) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold text-brand-950">Sell vouchers</h1>
        <SaleResult
          vouchers={sold.vouchers}
          planName={sold.planName}
          onDone={() => setSold(null)}
        />
      </div>
    );
  }

  return (
    <form
      onSubmit={(e) => void submit(e)}
      noValidate
      className="space-y-5"
      aria-label="Sell vouchers"
    >
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-brand-950">Sell vouchers</h1>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-500">
            <Store className="size-4" aria-hidden />
            {tenant.data?.name ?? slug}
            <button
              type="button"
              onClick={onChangeStore}
              className="ml-1 text-brand-600 hover:underline"
            >
              Change
            </button>
          </p>
        </div>
        <p className="flex items-center gap-1.5 text-sm text-ink-700">
          <Wallet className="size-4 text-ink-400" aria-hidden />
          Balance{' '}
          <strong className="tabular-nums">
            {wallet.isPending ? '…' : balance !== null ? formatKobo(balance) : '—'}
          </strong>
        </p>
      </header>

      {message && <Alert tone="danger">{message}</Alert>}
      {errors.root?.message === 'insufficient' && (
        <Alert
          tone="warning"
          title="Not enough in your wallet"
          actions={
            <Link
              to="/agent/wallet?fund=1"
              className="text-sm font-medium text-brand-600 hover:underline"
            >
              Fund wallet
            </Link>
          }
        >
          This sale needs {formatKobo(cost)}; your balance is{' '}
          {balance !== null ? formatKobo(balance) : 'lower than that'}.
        </Alert>
      )}

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-ink-900">
          1. Choose a plan{' '}
          {errors.plan_id && (
            <span className="font-normal text-danger-600"> — {errors.plan_id.message}</span>
          )}
        </legend>
        {plans.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2" aria-busy>
            {[0, 1].map((i) => (
              <PlanCardSkeleton key={i} />
            ))}
          </div>
        ) : plans.isError ? (
          <ErrorState
            error={plans.error}
            onRetry={() => void plans.refetch()}
            title="Could not load plans"
          />
        ) : plans.data.results.length === 0 ? (
          <EmptyState
            title="No plans to sell"
            description="Your operator has not published any active plans."
          />
        ) : (
          <div role="radiogroup" aria-label="Plan" className="grid gap-3 sm:grid-cols-2">
            {plans.data.results.map((p) => (
              <PlanOption
                key={p.id}
                plan={p}
                checked={p.id === planId}
                onSelect={() =>
                  form.setValue('plan_id', p.id, { shouldValidate: true, shouldDirty: true })
                }
              />
            ))}
          </div>
        )}
      </fieldset>

      <FormField
        label="2. How many?"
        required
        error={errors.quantity?.message}
        hint="Up to 100 per sale."
        className="max-w-xs"
      >
        <Input
          type="number"
          inputMode="numeric"
          min={1}
          max={100}
          step={1}
          {...form.register('quantity')}
        />
      </FormField>

      <div className="flex flex-col gap-3 rounded-card border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-xs text-ink-500">Wallet will be charged</div>
          <div
            className={cn(
              'text-xl font-semibold tabular-nums',
              short ? 'text-danger-700' : 'text-ink-900',
            )}
          >
            {formatKobo(cost)}
          </div>
          {short && (
            <div className="text-xs text-danger-700">
              Exceeds your balance by {formatKobo(cost - (balance ?? 0))}.
            </div>
          )}
        </div>
        <Button
          type="submit"
          size="lg"
          loading={form.formState.isSubmitting}
          disabled={!plan || short}
        >
          {plan && quantity > 1 ? `Sell ${quantity} vouchers` : 'Sell voucher'}
        </Button>
      </div>
    </form>
  );
}

function PlanOption({
  plan,
  checked,
  onSelect,
}: {
  plan: PublicPlan;
  checked: boolean;
  onSelect: () => void;
}) {
  return (
    <div
      role="radio"
      aria-checked={checked}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer rounded-card outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2"
    >
      <PlanCard plan={plan} selected={checked} />
    </div>
  );
}
