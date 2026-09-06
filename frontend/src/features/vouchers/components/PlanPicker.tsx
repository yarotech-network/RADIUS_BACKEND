import { Check } from 'lucide-react';
import { cn } from '@/lib/utilities/cn';
import { formatKobo } from '@/lib/formatting/money';
import { Skeleton } from '@/components/ui';
import { ErrorState } from '@/components/feedback';
import type { InternetPlan } from '@/types/api';
import { PlanSummary } from '@/features/plans/components/PlanSummary';

/** Radio-group of plan cards; keyboard accessible, wraps 1→2→3 columns. */
export function PlanPicker({
  plans,
  loading,
  error,
  onRetry,
  value,
  onChange,
  invalid,
  describedBy,
}: {
  plans: InternetPlan[] | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  value: number | null;
  onChange: (id: number) => void;
  invalid?: boolean;
  describedBy?: string;
}) {
  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy>
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-card" />
        ))}
      </div>
    );
  }
  if (error)
    return <ErrorState error={error} onRetry={onRetry} compact title="Plans could not be loaded" />;
  if (!plans || plans.length === 0) {
    return (
      <p className="rounded-card border border-dashed border-border-strong p-4 text-sm text-ink-600">
        No active plans. A manager needs to create (or activate) a plan before vouchers can be
        generated.
      </p>
    );
  }
  return (
    <div
      role="radiogroup"
      aria-invalid={invalid || undefined}
      aria-describedby={describedBy}
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
    >
      {plans.map((plan) => {
        const checked = plan.id === value;
        return (
          <button
            key={plan.id}
            type="button"
            role="radio"
            aria-checked={checked}
            onClick={() => onChange(plan.id)}
            className={cn(
              'flex min-h-24 flex-col items-start gap-1 rounded-card border p-4 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600',
              checked
                ? 'border-brand-600 bg-brand-50 ring-1 ring-brand-600'
                : 'border-border bg-surface hover:border-border-strong',
              invalid && !checked && 'border-danger-600/50',
            )}
          >
            <span className="flex w-full items-start justify-between gap-2">
              <span className="font-medium text-ink-900">{plan.name}</span>
              <span
                className={cn(
                  'grid h-5 w-5 shrink-0 place-items-center rounded-full border',
                  checked ? 'border-brand-600 bg-brand-600 text-white' : 'border-border-strong',
                )}
                aria-hidden
              >
                {checked && <Check className="h-3.5 w-3.5" />}
              </span>
            </span>
            <span className="text-lg font-semibold text-ink-900 tabular-nums">
              {formatKobo(plan.price)}
            </span>
            <PlanSummary plan={plan} />
          </button>
        );
      })}
    </div>
  );
}
