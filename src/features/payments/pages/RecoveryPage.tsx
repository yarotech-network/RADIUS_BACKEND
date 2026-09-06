import { useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { LifeBuoy } from 'lucide-react';
import { PageHeader, StatusBadge } from '@/components/layout';
import { Button, Select, Tooltip } from '@/components/ui';
import { Alert, EmptyState } from '@/components/feedback';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { formatKobo } from '@/lib/formatting/money';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import { usePlanOptions } from '@/features/plans/queries';
import type { PaymentRecovery, PaymentStatus, RecoveryListParams } from '@/types/api';
import { useRecoveryList } from '../queries';
import {
  DELIVERY_LABELS,
  FULFILLMENT_LABELS,
  PAYMENT_STATUS_FILTERS,
  needsAttention,
} from '../paymentRules';
import { RecoveryDrawer } from '../components/RecoveryDrawer';

const FILTERS = ['status', 'plan', 'attention'] as const;

export default function RecoveryPage() {
  const [params, setParams] = useSearchParams();
  const list = useListParams(FILTERS);
  const plans = usePlanOptions(false);
  const debouncedSearch = useDebouncedValue(list.state.search);
  const attentionOnly = list.state.filters.attention === '1';
  const selectedId = Number(params.get('payment')) || null;
  const query = useRecoveryList(
    useMemo(() => {
      const p: RecoveryListParams = { page: list.state.page, page_size: list.state.page_size };
      if (debouncedSearch) p.search = debouncedSearch;
      if (list.state.filters.status) p.status = list.state.filters.status as PaymentStatus;
      if (list.state.filters.plan) p.plan = Number(list.state.filters.plan);
      return p;
    }, [list.state, debouncedSearch]),
  );
  // Fulfilment/delivery are computed per row by the server and not filterable there; narrow the current page client-side.
  const rows = attentionOnly ? query.data?.results.filter(needsAttention) : query.data?.results;
  const attentionCount = query.data?.results.filter(needsAttention).length ?? 0;

  function select(id: number | null) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id) next.set('payment', String(id));
        else next.delete('payment');
        return next;
      },
      { replace: true },
    );
  }

  const columns: Column<PaymentRecovery>[] = [
    {
      key: 'reference',
      header: 'Reference',
      primary: true,
      cell: (r) => (
        <div className="min-w-0">
          <code className="font-mono text-sm font-semibold text-ink-900">{r.reference}</code>
          <div className="text-xs text-ink-500">
            {r.verified_at ? (
              <span title={formatDateTime(r.verified_at)}>
                Verified {formatRelative(r.verified_at)}
              </span>
            ) : (
              'Not verified with Paystack'
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      cell: (r) => <span className="tabular-nums">{formatKobo(r.amount)}</span>,
    },
    { key: 'status', header: 'Payment', cell: (r) => <StatusBadge status={r.status} size="sm" /> },
    {
      key: 'fulfillment',
      header: 'Voucher',
      cell: (r) => (
        <span className="inline-flex items-center gap-1.5">
          <StatusBadge status={r.fulfillment_status} size="sm" />
          <span className="sr-only">{FULFILLMENT_LABELS[r.fulfillment_status]}</span>
        </span>
      ),
    },
    {
      key: 'delivery',
      header: 'Email',
      hideBelow: 'md',
      cell: (r) => (
        <Tooltip content={DELIVERY_LABELS[r.delivery_status]}>
          <span>
            <StatusBadge status={r.delivery_status} size="sm" />
          </span>
        </Tooltip>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Payment recovery"
        description="Find customers who paid but did not get their voucher, re-run fulfilment, and resend credentials."
        backTo="/payments"
        crumbs={[{ label: 'Payments', to: '/payments' }, { label: 'Recovery' }]}
      />
      {attentionCount > 0 && !attentionOnly && (
        <Alert
          tone="warning"
          className="mb-4"
          title={`${attentionCount} ${attentionCount === 1 ? 'payment needs' : 'payments need'} attention on this page`}
          actions={
            <Button size="sm" variant="secondary" onClick={() => list.setFilter('attention', '1')}>
              Show only those
            </Button>
          }
        >
          Paid without a voucher, or the credentials email failed.
        </Alert>
      )}
      <FilterBar
        search={
          <SearchInput
            value={list.state.search}
            onChange={list.setSearch}
            placeholder="Search by reference"
            ariaLabel="Search payments by reference"
          />
        }
        filters={
          <>
            <Select
              aria-label="Needs attention"
              size="sm"
              value={attentionOnly ? '1' : ''}
              onChange={(e) => list.setFilter('attention', e.target.value || undefined)}
              options={[
                { value: '', label: 'All payments' },
                { value: '1', label: 'Needs attention' },
              ]}
            />
            <Select
              aria-label="Payment status"
              size="sm"
              value={list.state.filters.status ?? ''}
              onChange={(e) => list.setFilter('status', e.target.value || undefined)}
              options={PAYMENT_STATUS_FILTERS}
            />
            <Select
              aria-label="Plan"
              size="sm"
              value={list.state.filters.plan ?? ''}
              onChange={(e) => list.setFilter('plan', e.target.value || undefined)}
              options={[
                { value: '', label: 'All plans' },
                ...(plans.data ?? []).map((p) => ({ value: String(p.id), label: p.name })),
              ]}
            />
          </>
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Payment recovery"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        onRowClick={(r) => select(r.id)}
        empty={
          attentionOnly && (query.data?.results.length ?? 0) > 0 ? (
            <EmptyState
              icon={<LifeBuoy className="h-6 w-6" aria-hidden />}
              title="Nothing needs attention on this page"
              description="Every payment here either has its voucher and email delivered, or never completed."
              action={
                <Button variant="secondary" onClick={() => list.setFilter('attention', undefined)}>
                  Show all payments
                </Button>
              }
            />
          ) : list.activeFilterCount > 0 ? (
            <EmptyState
              icon={<LifeBuoy className="h-6 w-6" aria-hidden />}
              title="No payments match"
              action={
                <Button variant="secondary" onClick={list.clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<LifeBuoy className="h-6 w-6" aria-hidden />}
              title="No payments yet"
              description="Storefront purchases will show up here once customers start buying."
            />
          )
        }
      />
      {query.data && query.data.count > 0 && (
        <Pagination
          count={query.data.count}
          page={list.state.page}
          totalPages={query.data.total_pages}
          pageSize={list.state.page_size}
          onPageChange={list.setPage}
          onPageSizeChange={list.setPageSize}
          itemLabel="payments"
        />
      )}
      <RecoveryDrawer paymentId={selectedId} onClose={() => select(null)} />
    </>
  );
}
