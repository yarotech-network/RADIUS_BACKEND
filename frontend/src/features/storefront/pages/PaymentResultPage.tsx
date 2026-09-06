import { useEffect, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router';
import { CheckCircle2, Clock, RefreshCw, XCircle } from 'lucide-react';
import { Button, ButtonLink, CopyButton } from '@/components/ui';
import { Alert, EmptyState, ErrorState } from '@/components/feedback';
import { cn } from '@/lib/utilities/cn';
import { isApiError } from '@/services/api/errors';
import { usePaymentResult } from '../queries';
import { pendingCheckout } from '../pendingCheckout';
import { AccessCodePanel } from '../components/AccessCodePanel';

/**
 * `/pay/result?reference=` — where Paystack sends the customer back (configured in the Paystack
 * dashboard, gap #9). Falls back to the locally remembered checkout when the reference is missing.
 *
 * On success the backend returns the voucher's access code only while the voucher is unused; once
 * the customer has logged in, the page shows the username alone and points at the email copy.
 */
export default function PaymentResultPage() {
  const [params] = useSearchParams();
  const remembered = useMemo(() => pendingCheckout.load(), []);
  const reference =
    params.get('reference') ??
    params.get('trxref') ??
    (remembered?.kind === 'voucher' ? remembered.reference : null);
  const slug = remembered?.reference === reference ? remembered.slug : undefined;
  const result = usePaymentResult(reference);

  useEffect(() => {
    document.title = 'Payment result · Yarotech RADIUS';
  }, []);
  useEffect(() => {
    if (result.data && result.data.status !== 'pending') pendingCheckout.clear();
  }, [result.data]);

  if (!reference) {
    return (
      <div className="mx-auto w-full max-w-lg py-10">
        <EmptyState
          icon={<Clock className="size-6" aria-hidden />}
          title="No payment to check"
          description="Open the link from your Paystack receipt, or start a new purchase from the storefront link you were given."
        />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-lg py-6">
      <h1 className="text-2xl font-semibold text-brand-950">Payment result</h1>
      <p className="mt-1 text-sm text-ink-500">
        Reference <code className="font-mono text-ink-700">{reference}</code>
      </p>
      <div className="mt-6">
        {result.isPending ? (
          <div
            className="h-48 animate-pulse rounded-card border border-border bg-surface"
            aria-busy
          />
        ) : result.isError ? (
          isApiError(result.error) && result.error.status === 404 ? (
            <Alert tone="danger" title="We could not find this payment">
              Check the reference on your Paystack receipt. If you were charged, contact the
              business with that reference.
            </Alert>
          ) : (
            <ErrorState
              error={result.error}
              onRetry={() => void result.refetch()}
              title="Could not check the payment"
            />
          )
        ) : result.data.status === 'success' ? (
          <section
            aria-live="polite"
            className="rounded-card border border-success-100 bg-success-50 p-5"
          >
            <div className="flex items-center gap-2 text-success-700">
              <CheckCircle2 className="size-6" aria-hidden />
              <h2 className="text-lg font-semibold">Payment successful</h2>
            </div>
            {result.data.access_code ? (
              <AccessCodePanel
                code={result.data.access_code}
                tenantName={result.data.tenant_name}
                plan={result.data.plan ?? null}
                emailMasked={result.data.customer_email_masked}
              />
            ) : result.data.voucher ? (
              <>
                <p className="mt-3 text-sm text-ink-700">
                  This access code has already been used to log in, so it is no longer shown here.
                  Your Wi-Fi username:
                </p>
                <p className="mt-1 flex items-center gap-2">
                  <code className="rounded bg-white px-3 py-2 font-mono text-xl font-semibold tracking-wide text-ink-900">
                    {result.data.voucher}
                  </code>
                  <CopyButton value={result.data.voucher} label="Copy username" />
                </p>
                <p className="mt-3 text-sm text-ink-600">
                  {result.data.customer_email_masked
                    ? `The full access code was emailed to ${result.data.customer_email_masked}. `
                    : ''}
                  If you did not log in yourself, contact{' '}
                  {result.data.tenant_name ?? 'the business'} with this reference.
                </p>
              </>
            ) : (
              <p className="mt-3 text-sm text-ink-700">
                Your payment went through. Your access code is being prepared — this page will keep
                checking
                {result.data.customer_email_masked
                  ? `, and a copy will be emailed to ${result.data.customer_email_masked}`
                  : ''}
                .
              </p>
            )}
          </section>
        ) : result.data.status === 'pending' ? (
          <section aria-live="polite" className="rounded-card border border-border bg-surface p-5">
            <div className="flex items-center gap-2 text-brand-700">
              <RefreshCw
                className={cn('size-5', result.isFetching && 'animate-spin')}
                aria-hidden
              />
              <h2 className="text-lg font-semibold">Waiting for confirmation</h2>
            </div>
            <p className="mt-2 text-sm text-ink-600">
              Paystack has not confirmed this payment yet. If you completed the payment, this
              usually takes a few seconds; if you closed the Paystack page, you can go back and pay
              again.
            </p>
            <Button
              className="mt-4"
              variant="secondary"
              size="sm"
              onClick={() => void result.refetch()}
              loading={result.isFetching}
            >
              Check again
            </Button>
          </section>
        ) : (
          <section
            aria-live="polite"
            className="rounded-card border border-danger-100 bg-danger-50 p-5"
          >
            <div className="flex items-center gap-2 text-danger-700">
              <XCircle className="size-6" aria-hidden />
              <h2 className="text-lg font-semibold">
                {result.data.status === 'abandoned' ? 'Payment not completed' : 'Payment failed'}
              </h2>
            </div>
            <p className="mt-2 text-sm text-ink-700">
              You have not been charged for this order. You can start again from the plan list.
            </p>
          </section>
        )}
      </div>
      <div className="mt-6 flex flex-wrap gap-3">
        {slug && (
          <ButtonLink to={`/s/${slug}`} variant="secondary">
            Back to plans
          </ButtonLink>
        )}
        <Link to="/" className="inline-flex items-center text-sm text-ink-500 hover:text-ink-900">
          Home
        </Link>
      </div>
    </div>
  );
}
