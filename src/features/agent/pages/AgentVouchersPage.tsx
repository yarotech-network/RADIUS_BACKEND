import { useEffect, useMemo } from 'react';
import { Ticket } from 'lucide-react';
import { StatusBadge } from '@/components/layout';
import { Button, ButtonLink, CopyButton, Select } from '@/components/ui';
import { Alert, EmptyState } from '@/components/feedback';
import { DataTable, Pagination, useListParams, type Column } from '@/components/data';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { formatKobo } from '@/lib/formatting/money';
import type { AgentVoucherAllocation, AllocationListParams, VoucherStatus } from '@/types/api';
import { useAllocationHistory } from '../queries';

const FILTERS = ['status'] as const;
const STATUS_OPTIONS = [
  { value: '', label: 'Any voucher status' },
  { value: 'unused', label: 'Unused' },
  { value: 'active', label: 'Active' },
  { value: 'expired', label: 'Expired' },
  { value: 'disabled', label: 'Disabled' },
];

/** `/agent/vouchers` — every voucher this agent has sold (allocation history; usernames only, gap #2). */
export default function AgentVouchersPage() {
  const list = useListParams(FILTERS);
  useEffect(() => {
    document.title = 'My vouchers · Agent portal';
  }, []);
  const query = useAllocationHistory(
    useMemo(() => {
      const p: AllocationListParams = { page: list.state.page, page_size: list.state.page_size };
      if (list.state.filters.status) p.status = list.state.filters.status as VoucherStatus;
      return p;
    }, [list.state]),
  );

  const columns: Column<AgentVoucherAllocation>[] = [
    {
      key: 'username',
      header: 'Voucher',
      primary: true,
      cell: (a) => (
        <span className="inline-flex items-center gap-1">
          <code className="font-mono text-sm font-semibold text-ink-900">{a.voucher_username}</code>
          <CopyButton value={a.voucher_username} label={`Copy ${a.voucher_username}`} />
        </span>
      ),
    },
    {
      key: 'amount',
      header: 'Charged',
      align: 'right',
      cell: (a) => <span className="tabular-nums">{formatKobo(a.amount_charged)}</span>,
    },
    {
      key: 'type',
      header: 'Paid by',
      hideBelow: 'sm',
      cell: (a) => <StatusBadge status={a.allocation_type} size="sm" dot={false} />,
    },
    {
      key: 'created',
      header: 'Sold',
      cell: (a) => (
        <time dateTime={a.created_at} title={formatDateTime(a.created_at)} className="text-ink-600">
          {formatRelative(a.created_at)}
        </time>
      ),
    },
  ];

  const filtered = list.activeFilterCount > 0;

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-brand-950">My vouchers</h1>
          <p className="mt-1 text-sm text-ink-500">Everything you have sold, newest first.</p>
        </div>
        <ButtonLink to="/agent/sell" leadingIcon={<Ticket className="size-4" aria-hidden />}>
          Sell
        </ButtonLink>
      </header>
      <div className="flex items-center justify-between gap-2">
        <Select
          aria-label="Voucher status"
          size="sm"
          value={list.state.filters.status ?? ''}
          onChange={(e) => list.setFilter('status', e.target.value || undefined)}
          options={STATUS_OPTIONS}
        />
        {query.data && (
          <span className="text-xs text-ink-500">{query.data.count.toLocaleString()} total</span>
        )}
      </div>
      <DataTable
        caption="Vouchers sold"
        columns={columns}
        rows={query.data?.results}
        rowKey={(a) => a.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        dense
        empty={
          filtered ? (
            <EmptyState
              title="No vouchers with that status"
              action={
                <Button variant="secondary" size="sm" onClick={list.clearFilters}>
                  Clear filter
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<Ticket className="size-6" aria-hidden />}
              title="You have not sold any vouchers yet"
              action={
                <ButtonLink to="/agent/sell" size="sm">
                  Sell your first voucher
                </ButtonLink>
              }
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
          itemLabel="vouchers"
        />
      )}
      <Alert tone="info">
        Voucher passwords are issued by your operator, not shown here. If a customer needs theirs
        re-sent, contact the operator with the voucher username.
      </Alert>
    </div>
  );
}
