import { CheckCircle2, CircleDashed, XCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui';
import { ErrorState } from '@/components/feedback';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { useRouterChecks } from '../queries';
import { checkRows } from '../routerRules';

/** The six onboarding checks; never-run ones are listed so nothing is silently missing. */
export function ChecksPanel({ routerId }: { routerId: string }) {
  const query = useRouterChecks(routerId);
  if (query.isPending) {
    return (
      <ul className="divide-y divide-border">
        {Array.from({ length: 6 }).map((_, i) => (
          <li key={i} className="flex items-center gap-3 py-3">
            <Skeleton className="h-5 w-5 rounded-full" />
            <Skeleton className="h-4 w-48" />
          </li>
        ))}
      </ul>
    );
  }
  if (query.isError)
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        compact
        title="Checks could not be loaded"
      />
    );
  const rows = checkRows(query.data);
  const passed = rows.filter((r) => r.status === 'passed').length;
  return (
    <div>
      <p className="mb-2 text-sm text-ink-600">
        {passed} of {rows.length} checks passing. Checks are recorded by the RADIUS test and the
        provisioning agent.
      </p>
      <ul className="divide-y divide-border rounded-card border border-border bg-surface">
        {rows.map((row) => {
          const Icon =
            row.status === 'passed'
              ? CheckCircle2
              : row.status === 'failed'
                ? XCircle
                : CircleDashed;
          const tone =
            row.status === 'passed'
              ? 'text-success-600'
              : row.status === 'failed'
                ? 'text-danger-600'
                : 'text-ink-300';
          const outcome = typeof row.details.outcome === 'string' ? row.details.outcome : null;
          return (
            <li key={row.type} className="flex items-start gap-3 px-4 py-3">
              <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${tone}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="text-sm font-medium text-ink-900">{row.label}</span>
                  <span className="text-xs text-ink-500">
                    {row.checkedAt ? (
                      <time dateTime={row.checkedAt} title={formatDateTime(row.checkedAt)}>
                        {formatRelative(row.checkedAt)}
                      </time>
                    ) : (
                      'Never run'
                    )}
                  </span>
                </div>
                <span className="sr-only">{row.status}</span>
                {outcome && <p className="text-xs text-ink-500">Outcome: {outcome}</p>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
