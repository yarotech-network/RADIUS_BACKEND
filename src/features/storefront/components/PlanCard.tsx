import type { ReactNode } from 'react';
import { Clock, Database, Gauge } from 'lucide-react';
import { formatKobo } from '@/lib/formatting/money';
import { describeRateLimit, formatDataLimit, formatHours } from '@/lib/formatting/units';
import { cn } from '@/lib/utilities/cn';
import type { PublicPlan } from '@/types/api';

/** Customer-facing plan card shared by the storefront and the agent "Sell" screen. */
export function PlanCard({
  plan,
  action,
  selected,
  className,
}: {
  plan: PublicPlan;
  action?: ReactNode;
  selected?: boolean;
  className?: string;
}) {
  return (
    <article
      aria-label={plan.name}
      className={cn(
        'flex h-full flex-col rounded-card border bg-surface p-4',
        selected ? 'border-brand-600 ring-1 ring-brand-600' : 'border-border',
        className,
      )}
    >
      <h3 className="text-base font-semibold text-brand-950">{plan.name}</h3>
      <p className="mt-1 text-2xl font-semibold text-ink-900 tabular-nums">
        {formatKobo(plan.price)}
      </p>
      <dl className="mt-3 space-y-1.5 text-sm text-ink-700">
        <div className="flex items-center gap-2">
          <Clock className="size-4 shrink-0 text-ink-400" aria-hidden />
          <dt className="sr-only">Valid for</dt>
          <dd>{formatHours(plan.duration_hours)}</dd>
        </div>
        <div className="flex items-center gap-2">
          <Database className="size-4 shrink-0 text-ink-400" aria-hidden />
          <dt className="sr-only">Data</dt>
          <dd>
            {plan.data_limit === 0 ? 'Unlimited data' : `${formatDataLimit(plan.data_limit)} data`}
          </dd>
        </div>
        <div className="flex items-center gap-2">
          <Gauge className="size-4 shrink-0 text-ink-400" aria-hidden />
          <dt className="sr-only">Speed</dt>
          <dd>{describeRateLimit(plan.rate_limit)}</dd>
        </div>
      </dl>
      {action && <div className="mt-4 pt-1">{action}</div>}
    </article>
  );
}

export function PlanCardSkeleton() {
  return (
    <div className="h-52 animate-pulse rounded-card border border-border bg-surface p-4">
      <div className="h-4 w-1/2 rounded bg-slate-200" />
      <div className="mt-3 h-7 w-1/3 rounded bg-slate-200" />
      <div className="mt-4 space-y-2">
        <div className="h-3 w-2/3 rounded bg-slate-100" />
        <div className="h-3 w-1/2 rounded bg-slate-100" />
        <div className="h-3 w-3/4 rounded bg-slate-100" />
      </div>
    </div>
  );
}
