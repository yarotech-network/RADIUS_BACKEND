import { useState } from 'react';
import { History } from 'lucide-react';
import { Skeleton } from '@/components/ui';
import { EmptyState, ErrorState } from '@/components/feedback';
import { Pagination } from '@/components/data';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { useRouterAudit } from '../queries';
import { ONBOARDING_LABELS, describeAuditAction } from '../routerRules';

const PAGE_SIZE = 20;

export function HistoryPanel({ routerId }: { routerId: string }) {
  const [page, setPage] = useState(1);
  const query = useRouterAudit(routerId, page);
  if (query.isPending) {
    return (
      <ol className="flex flex-col gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <li key={i} className="flex gap-3">
            <Skeleton className="h-3 w-3 rounded-full" />
            <Skeleton className="h-4 w-72" />
          </li>
        ))}
      </ol>
    );
  }
  if (query.isError)
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        compact
        title="History could not be loaded"
      />
    );
  if (query.data.results.length === 0)
    return (
      <EmptyState
        compact
        icon={<History />}
        title="No history yet"
        description="State changes, provisioning and secret rotations will appear here."
      />
    );
  return (
    <div className="flex flex-col gap-4">
      <ol className="relative flex flex-col gap-4 border-l border-border pl-5">
        {query.data.results.map((event) => (
          <li key={event.id} className="relative">
            <span
              className="absolute top-1.5 -left-[1.4rem] h-2.5 w-2.5 rounded-full border-2 border-brand-600 bg-surface"
              aria-hidden
            />
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <p className="text-sm text-ink-900">
                <span className="font-medium">{describeAuditAction(event.action)}</span>
                {event.from_state && event.to_state && (
                  <span className="text-ink-600">
                    {' '}
                    — {ONBOARDING_LABELS[event.from_state] ?? event.from_state} →{' '}
                    {ONBOARDING_LABELS[event.to_state] ?? event.to_state}
                  </span>
                )}
              </p>
              <time
                dateTime={event.created_at}
                title={formatDateTime(event.created_at)}
                className="text-xs text-ink-500"
              >
                {formatRelative(event.created_at)}
              </time>
            </div>
            {event.correlation_id && (
              <p className="font-mono text-[11px] text-ink-400">
                ref {event.correlation_id.slice(0, 8)}
              </p>
            )}
          </li>
        ))}
      </ol>
      <Pagination
        page={query.data.current_page}
        totalPages={query.data.total_pages}
        count={query.data.count}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        itemLabel="events"
      />
    </div>
  );
}
