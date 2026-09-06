import { Clock, Database, Gauge } from 'lucide-react';
import { describeRateLimit, formatDataLimit, formatHours } from '@/lib/formatting/units';
import type { InternetPlan } from '@/types/api';

/** Compact spec line used in tables, pickers and the voucher detail. */
export function PlanSummary({
  plan,
  className,
}: {
  plan: Pick<InternetPlan, 'duration_hours' | 'rate_limit' | 'data_limit'>;
  className?: string;
}) {
  return (
    <span
      className={[
        'inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-600',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="inline-flex items-center gap-1">
        <Clock className="h-3.5 w-3.5 text-ink-400" aria-hidden />
        {formatHours(plan.duration_hours)}
      </span>
      <span className="inline-flex items-center gap-1">
        <Gauge className="h-3.5 w-3.5 text-ink-400" aria-hidden />
        {describeRateLimit(plan.rate_limit)}
      </span>
      <span className="inline-flex items-center gap-1">
        <Database className="h-3.5 w-3.5 text-ink-400" aria-hidden />
        {formatDataLimit(plan.data_limit)}
      </span>
    </span>
  );
}
