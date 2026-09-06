import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ChevronLeft, ExternalLink, Lock } from 'lucide-react';
import { Button, ButtonLink, FormField, Input } from '@/components/ui';
import { Alert, ErrorState } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { formatKobo } from '@/lib/formatting/money';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { isApiError } from '@/services/api/errors';
import type { PublicPlan } from '@/types/api';
import { storefrontApi } from '../api';
import { usePublicPlans } from '../queries';
import { pendingCheckout } from '../pendingCheckout';
import { checkoutSchema, type CheckoutInput, type CheckoutOutput } from '../checkoutSchema';
import { PlanCard, PlanCardSkeleton } from '../components/PlanCard';

const FIELDS = ['email', 'name', 'phone'] as const;

export default function CheckoutPage({
  slug,
  tenantName,
}: {
  slug: string;
  tenantName: string | null;
}) {
  const { planId = '' } = useParams();
  const plans = usePublicPlans(slug);
  const plan = plans.data?.results.find((p) => String(p.id) === planId) ?? null;

  useEffect(() => {
    if (plan) document.title = `${plan.name} · ${tenantName ?? 'Checkout'}`;
  }, [plan, tenantName]);

  return (
    <div>
      <Link
        to={`/s/${slug}`}
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink-500 hover:text-ink-900"
      >
        <ChevronLeft className="size-4" aria-hidden /> All plans
      </Link>
      <h1 className="text-2xl font-semibold text-brand-950">Checkout</h1>
      <p className="mt-1 text-sm text-ink-500">
        {tenantName ? `Buying from ${tenantName}.` : ''} You will be taken to Paystack to pay.
      </p>
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="order-2 lg:order-1">
          {plans.isPending ? (
            <div
              className="h-64 animate-pulse rounded-card border border-border bg-surface"
              aria-busy
            />
          ) : plans.isError ? (
            <ErrorState
              error={plans.error}
              onRetry={() => void plans.refetch()}
              title="Could not load this plan"
            />
          ) : !plan ? (
            <Alert
              tone="warning"
              title="This plan is no longer available"
              actions={
                <ButtonLink to={`/s/${slug}`} size="sm" variant="secondary">
                  See current plans
                </ButtonLink>
              }
            />
          ) : (
            <CheckoutForm plan={plan} slug={slug} />
          )}
        </div>
        <aside className="order-1 lg:order-2" aria-label="Order summary">
          {plan ? <PlanCard plan={plan} selected /> : <PlanCardSkeleton />}
        </aside>
      </div>
    </div>
  );
}

function CheckoutForm({ plan, slug }: { plan: PublicPlan; slug: string }) {
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey('buy'));
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const form = useForm<CheckoutInput, unknown, CheckoutOutput>({
    resolver: zodResolver(checkoutSchema),
    defaultValues: { email: '', name: '', phone: '' },
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    setUnavailable(null);
    try {
      const result = await storefrontApi.buy(
        {
          plan_id: plan.id,
          email: values.email,
          ...(values.name ? { name: values.name } : {}),
          ...(values.phone ? { phone: values.phone } : {}),
        },
        idempotencyKey,
      );
      pendingCheckout.save({
        kind: 'voucher',
        reference: result.reference,
        slug,
        planName: plan.name,
        amount: plan.price,
      });
      window.location.assign(result.authorization_url);
    } catch (error) {
      if (isApiError(error) && error.status === 503) {
        const reference = (error.body as { reference?: string } | null)?.reference;
        if (reference)
          pendingCheckout.save({
            kind: 'voucher',
            reference,
            slug,
            planName: plan.name,
            amount: plan.price,
          });
        setUnavailable(reference ?? '');
        // The pending order behind this key is dead; a retry must create a fresh one.
        setIdempotencyKey(newIdempotencyKey('buy'));
        return;
      }
      captureError(error);
    }
  });

  return (
    <form
      onSubmit={(e) => void submit(e)}
      noValidate
      className="flex flex-col gap-4 rounded-card border border-border bg-surface p-5"
      aria-label="Your details"
    >
      {message && <Alert tone="danger">{message}</Alert>}
      {unavailable !== null && (
        <Alert tone="warning" title="Payments are temporarily unavailable">
          We could not reach the payment provider. You have not been charged — please try again in a
          few minutes.
          {unavailable && (
            <span className="mt-1 block text-xs">
              Order reference: <code className="font-mono">{unavailable}</code>
            </span>
          )}
        </Alert>
      )}
      <FormField
        label="Email address"
        required
        hint="Your access code is shown after payment and also emailed here."
        error={errors.email?.message}
      >
        <Input
          type="email"
          inputMode="email"
          autoComplete="email"
          autoFocus
          {...form.register('email')}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Name" optionalLabel error={errors.name?.message}>
          <Input autoComplete="name" {...form.register('name')} />
        </FormField>
        <FormField label="Phone" optionalLabel error={errors.phone?.message}>
          <Input
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="+234 803 000 0000"
            {...form.register('phone')}
          />
        </FormField>
      </div>
      <div className="flex items-center justify-between gap-4 border-t border-border pt-4">
        <div>
          <div className="text-xs text-ink-500">Total</div>
          <div className="text-xl font-semibold text-ink-900 tabular-nums">
            {formatKobo(plan.price)}
          </div>
        </div>
        <Button
          type="submit"
          size="lg"
          loading={form.formState.isSubmitting}
          trailingIcon={<ExternalLink className="size-4" aria-hidden />}
        >
          Pay with Paystack
        </Button>
      </div>
      <p className="flex items-center gap-1.5 text-xs text-ink-400">
        <Lock className="size-3.5" aria-hidden /> Card details are entered on Paystack's secure
        page, never here.
      </p>
    </form>
  );
}
