import { RefreshCw } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import { Card, Select, Skeleton } from '@/components/ui';
import { EmptyState, ErrorState } from '@/components/feedback';
import { FilterBar, Pagination, useListParams } from '@/components/data';
import type { OperationAction, OperationStatus } from '@/types/api';
import { useRouterOperations, useRouterOptions } from '../queries';
import { isOperationOpen } from '../routerRules';
import { OperationRow } from '../components/VpnPanel';

const FILTERS = ['router', 'status', 'action'] as const;
const STATUS_OPTIONS: { value: OperationStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
];
const ACTION_OPTIONS: { value: OperationAction | ''; label: string }[] = [
  { value: '', label: 'All actions' },
  { value: 'provision', label: 'Provision' },
  { value: 'suspend', label: 'Suspend' },
];

export default function RouterOperationsPage() {
  const list = useListParams(FILTERS);
  const routers = useRouterOptions();
  const routerName = new Map((routers.data ?? []).map((r) => [r.id, r.name]));
  const { page, page_size, filters } = list.state;
  const query = useRouterOperations({
    page,
    page_size,
    ...(filters.router ? { router: filters.router } : {}),
    ...(filters.status ? { status: filters.status as OperationStatus } : {}),
    ...(filters.action ? { action: filters.action as OperationAction } : {}),
  });
  const live = query.data?.results.some(isOperationOpen) ?? false;

  return (
    <>
      <PageHeader
        title="Provisioning operations"
        description="Every provision and suspend run across your routers. Open operations refresh automatically."
        backTo="/routers"
        crumbs={[{ label: 'Routers', to: '/routers' }, { label: 'Operations' }]}
        meta={
          live && (
            <span className="inline-flex items-center gap-1 text-xs text-brand-700">
              <RefreshCw className="h-3 w-3 animate-spin" aria-hidden /> Live
            </span>
          )
        }
      />
      <FilterBar
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
        filters={
          <>
            <Select
              aria-label="Router"
              size="sm"
              value={filters.router ?? ''}
              onChange={(e) => list.setFilter('router', e.target.value || undefined)}
              options={[
                { value: '', label: 'All routers' },
                ...(routers.data ?? []).map((r) => ({ value: r.id, label: r.name })),
              ]}
            />
            <Select
              aria-label="Status"
              size="sm"
              value={filters.status ?? ''}
              onChange={(e) => list.setFilter('status', e.target.value || undefined)}
              options={STATUS_OPTIONS}
            />
            <Select
              aria-label="Action"
              size="sm"
              value={filters.action ?? ''}
              onChange={(e) => list.setFilter('action', e.target.value || undefined)}
              options={ACTION_OPTIONS}
            />
          </>
        }
      />
      <Card className="mt-4 p-0">
        {query.isPending ? (
          <div className="flex flex-col gap-3 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        ) : query.isError ? (
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
            title="Operations could not be loaded"
          />
        ) : query.data.results.length === 0 ? (
          <EmptyState
            title="No operations"
            description={
              list.activeFilterCount > 0
                ? 'Nothing matches these filters.'
                : 'Provisioning runs will appear here once you provision a router.'
            }
          />
        ) : (
          <>
            <ul className="divide-y divide-border" aria-label="Operations">
              {query.data.results.map((op) => (
                <OperationRow
                  key={op.id}
                  op={op}
                  showRouter={routerName.get(op.router) ?? `Router ${op.router.slice(0, 8)}`}
                />
              ))}
            </ul>
            <div className="border-t border-border px-4 py-3">
              <Pagination
                count={query.data.count}
                page={query.data.current_page}
                totalPages={query.data.total_pages}
                pageSize={page_size}
                onPageChange={list.setPage}
                onPageSizeChange={list.setPageSize}
                itemLabel="operations"
              />
            </div>
          </>
        )}
      </Card>
    </>
  );
}
