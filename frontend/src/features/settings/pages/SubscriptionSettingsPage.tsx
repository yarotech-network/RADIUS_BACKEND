import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { Check, CreditCard, ExternalLink, RefreshCw } from 'lucide-react';
import { Badge, Button, DescriptionList, Skeleton } from '@/components/ui';
import { Alert, EmptyState, ErrorState, useToast } from '@/components/feedback';
import { StatusBadge } from '@/components/layout';
import { usePrincipal } from '@/app/auth/useAuth';
import { formatDate, formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { formatKobo } from '@/lib/formatting/money';
import { cn } from '@/lib/utilities/cn';
import { errorMessage, isApiError } from '@/services/api/errors';
import { can } from '@/services/auth/principal';
import type { SubscriptionPlan, TenantSubscription } from '@/types/api';
import { useCheckout, usePricing, useSubscription, useSubscriptionPayment } from '../queries';
import { SettingsCard } from '../components/SettingsCard';

export default function SubscriptionSettingsPage() {
  const principal = usePrincipal();
  const canCheckout = can(principal, 'subscription.checkout');
  const [params, setParams] = useSearchParams();
  const reference = params.get('reference');
  const subscription = useSubscription();
  const pricing = usePricing();
  const checkout = useCheckout();
  const toast = useToast();
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  function trackReference(ref: string | null) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (ref) next.set('reference', ref);
        else next.delete('reference');
        return next;
      },
      { replace: true },
    );
  }

  async function startCheckout(plan: SubscriptionPlan) {
    setCheckoutError(null);
    try {
      const result = await checkout.mutateAsync({ plan_id: plan.id });
      trackReference(result.reference);
      window.open(result.authorization_url, '_blank', 'noopener');
      toast.info(
        'Paystack opened in a new tab',
        'This page updates automatically once the payment completes.',
      );
    } catch (error) {
      if (isApiError(error) && error.status === 503) {
        const ref = (error.body as { reference?: string } | null)?.reference;
        if (ref) trackReference(ref);
        setCheckoutError(
          'The payment provider is unavailable right now. Nothing was charged — try again in a few minutes.',
        );
      } else setCheckoutError(errorMessage(error));
    }
  }

  return (
    <div>
      <SettingsCard
        id="current-plan"
        title="Current plan"
        description="Your platform subscription for this workspace. It is separate from the Paystack account your customers pay into."
      >
        {subscription.isPending ? (
          <Skeleton className="h-28 w-full" />
        ) : subscription.isError ? (
          <ErrorState
            error={subscription.error}
            onRetry={() => void subscription.refetch()}
            compact
            title="Subscription could not be loaded"
          />
        ) : subscription.data ? (
          <CurrentPlan subscription={subscription.data} />
        ) : (
          <EmptyState
            compact
            icon={<CreditCard className="h-6 w-6" aria-hidden />}
            title="No active subscription"
            description={
              canCheckout
                ? 'Choose a plan below to activate this workspace.'
                : 'Ask a workspace owner to choose a plan.'
            }
          />
        )}
      </SettingsCard>

      {reference && <PaymentTracker reference={reference} onDismiss={() => trackReference(null)} />}

      <SettingsCard
        id="plans"
        title="Plans"
        description={
          canCheckout
            ? 'Pay securely with Paystack. Your subscription is extended as soon as the payment is confirmed.'
            : 'Only workspace owners can change the plan.'
        }
      >
        {checkoutError && (
          <Alert tone="warning" className="mb-4" onDismiss={() => setCheckoutError(null)}>
            {checkoutError}
          </Alert>
        )}
        {pricing.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-44 w-full" />
            <Skeleton className="h-44 w-full" />
          </div>
        ) : pricing.isError ? (
          <ErrorState
            error={pricing.error}
            onRetry={() => void pricing.refetch()}
            compact
            title="Plans could not be loaded"
          />
        ) : pricing.data.length === 0 ? (
          <EmptyState
            compact
            title="No plans available"
            description="The platform has not published any subscription plans yet."
          />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {pricing.data.map((plan) => {
              const current = subscription.data?.plan === plan.id && !subscription.data.is_expired;
              return (
                <li
                  key={plan.id}
                  className={cn(
                    'flex flex-col rounded-card border p-4',
                    current ? 'border-brand-600 ring-1 ring-brand-600' : 'border-border',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-base font-semibold text-brand-950">{plan.name}</h3>
                    {current && (
                      <Badge tone="brand" size="sm">
                        Current
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 text-2xl font-semibold text-ink-900 tabular-nums">
                    {formatKobo(plan.price)}{' '}
                    <span className="text-sm font-normal text-ink-500">
                      / {plan.duration_days} days
                    </span>
                  </p>
                  {plan.features.length > 0 && (
                    <ul className="mt-3 space-y-1 text-sm text-ink-700">
                      {plan.features.map((f, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
                          <span>{typeof f === 'string' ? f : JSON.stringify(f)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {canCheckout && (
                    <Button
                      className="mt-4"
                      variant={current ? 'secondary' : 'primary'}
                      onClick={() => void startCheckout(plan)}
                      loading={checkout.isPending && checkout.variables?.plan_id === plan.id}
                      disabled={checkout.isPending}
                      trailingIcon={<ExternalLink className="h-4 w-4" aria-hidden />}
                    >
                      {current ? 'Renew' : subscription.data ? 'Switch to this plan' : 'Subscribe'}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </SettingsCard>
    </div>
  );
}

function CurrentPlan({ subscription }: { subscription: TenantSubscription }) {
  const tone = subscription.is_expired ? 'expired' : subscription.status;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xl font-semibold text-ink-900">{subscription.plan_name}</span>
        <StatusBadge status={tone} size="md" />
        {subscription.is_trial && (
          <Badge tone="info" size="sm">
            Trial
          </Badge>
        )}
      </div>
      <DescriptionList
        columns={2}
        items={[
          { label: 'Started', value: formatDate(subscription.started_at) },
          {
            label: subscription.is_expired ? 'Expired' : 'Renews / expires',
            value: (
              <span title={formatDateTime(subscription.expires_at)}>
                {formatDate(subscription.expires_at)} ({formatRelative(subscription.expires_at)})
              </span>
            ),
          },
        ]}
      />
      {subscription.is_expired && (
        <Alert tone="warning" title="Subscription expired">
          Choose a plan below to reactivate this workspace.
        </Alert>
      )}
    </div>
  );
}

function PaymentTracker({ reference, onDismiss }: { reference: string; onDismiss: () => void }) {
  const payment = useSubscriptionPayment(reference);
  if (payment.isPending) return <Alert tone="info" className="mb-6" title="Checking payment…" />;
  if (payment.isError)
    return (
      <Alert
        tone="danger"
        className="mb-6"
        title="Could not check the payment"
        onDismiss={onDismiss}
      >
        {errorMessage(payment.error)} Reference {reference}.
      </Alert>
    );
  const p = payment.data;
  if (p.status === 'success') {
    return (
      <Alert tone="success" className="mb-6" title="Payment confirmed" onDismiss={onDismiss}>
        {formatKobo(p.amount)} received {p.completed_at ? formatRelative(p.completed_at) : ''}. Your
        subscription has been updated.
      </Alert>
    );
  }
  if (p.status === 'failed') {
    return (
      <Alert tone="danger" className="mb-6" title="Payment failed" onDismiss={onDismiss}>
        Paystack reported reference {reference} as failed. No subscription change was made — you can
        try again below.
      </Alert>
    );
  }
  return (
    <Alert
      tone="info"
      className="mb-6"
      title="Waiting for Paystack"
      onDismiss={onDismiss}
      actions={
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void payment.refetch()}
          leadingIcon={
            <RefreshCw
              className={cn('h-4 w-4', payment.isFetching && 'animate-spin')}
              aria-hidden
            />
          }
        >
          Check now
        </Button>
      }
    >
      Payment of {formatKobo(p.amount)} (reference {reference}) is pending. Complete it in the
      Paystack tab; this page refreshes automatically.
    </Alert>
  );
}
