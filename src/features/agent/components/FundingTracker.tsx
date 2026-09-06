import { CheckCircle2, RefreshCw, X, XCircle } from 'lucide-react';
import { Button } from '@/components/ui';
import { formatKobo } from '@/lib/formatting/money';
import { cn } from '@/lib/utilities/cn';
import { useFundingByReference } from '../queries';

/** Live status of one top-up (polls the agent's funding list by reference until it settles). */
export function FundingTracker({
  reference,
  onDismiss,
}: {
  reference: string;
  onDismiss: () => void;
}) {
  const funding = useFundingByReference(reference);
  const status = funding.data?.status ?? (funding.data === null ? 'missing' : 'loading');
  const settled = status === 'success' || status === 'failed';
  return (
    <section
      aria-live="polite"
      className={cn(
        'flex items-start gap-3 rounded-card border p-4',
        status === 'success' && 'border-success-100 bg-success-50',
        status === 'failed' && 'border-danger-100 bg-danger-50',
        !settled && 'border-border bg-surface',
      )}
    >
      {status === 'success' ? (
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success-700" aria-hidden />
      ) : status === 'failed' ? (
        <XCircle className="mt-0.5 size-5 shrink-0 text-danger-700" aria-hidden />
      ) : (
        <RefreshCw
          className={cn(
            'mt-0.5 size-5 shrink-0 text-brand-700',
            funding.isFetching && 'animate-spin',
          )}
          aria-hidden
        />
      )}
      <div className="min-w-0 flex-1">
        <h2 className="text-sm font-semibold text-ink-900">
          {status === 'success'
            ? `Top-up of ${formatKobo(funding.data?.amount)} received`
            : status === 'failed'
              ? 'Top-up failed — nothing was added'
              : status === 'missing'
                ? 'We could not find this top-up'
                : 'Waiting for Paystack to confirm your top-up'}
        </h2>
        <p className="mt-0.5 text-xs text-ink-500">
          Reference <code className="font-mono">{reference}</code>
          {!settled && status !== 'missing' && ' · checking every few seconds'}
        </p>
        {!settled && status !== 'missing' && (
          <Button
            size="sm"
            variant="secondary"
            className="mt-2"
            onClick={() => void funding.refetch()}
            loading={funding.isFetching}
          >
            Check now
          </Button>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="rounded p-1 text-ink-400 hover:text-ink-700"
      >
        <X className="size-4" aria-hidden />
      </button>
    </section>
  );
}
