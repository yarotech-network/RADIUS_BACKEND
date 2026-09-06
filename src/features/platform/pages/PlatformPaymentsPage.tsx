import { useEffect, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router';
import { CreditCard } from 'lucide-react';
import { PageHeader, StatusBadge } from '@/components/layout';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { Button, Select, Tabs } from '@/components/ui';
import { EmptyState } from '@/components/feedback';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import { formatKobo } from '@/lib/formatting/money';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import type {
  PaymentListParams,
  PaymentStatus,
  PaymentTransaction,
  PlatformSubscriptionPayment,
  PlatformWalletPayment,
  PlatformWalletPaymentListParams,
  SubscriptionPaymentListParams,
} from '@/types/api';
import { usePricing } from '@/features/settings/queries';
import {
  usePlatformPayments,
  usePlatformSubscriptionPayments,
  usePlatformWalletPayments,
  useTenantName,
} from '../queries';
import { TenantSelect } from '../components/TenantSelect';

type Source = 'vouchers' | 'wallet' | 'subscriptions';
const SOURCES: { value: Source; label: string }[] = [
  { value: 'vouchers', label: 'Voucher sales' },
  { value: 'wallet', label: 'Agent wallet top-ups' },
  { value: 'subscriptions', label: 'Subscriptions' },
];
const FILTERS = ['tenant', 'status'] as const;
const STATUSES: readonly string[] = ['pending', 'success', 'failed', 'abandoned'];

function sourceFrom(raw: string | null): Source {
  return raw === 'wallet' || raw === 'subscriptions' ? raw : 'vouchers';
}

/** `/platform/payments` — money across all tenants, split by source (three read-only endpoints). */
export default function PlatformPaymentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const source = sourceFrom(searchParams.get('source'));
  const list = useListParams(FILTERS);
  const debouncedSearch = useDebouncedValue(list.state.search);
  const tenantName = useTenantName();
  const pricing = usePricing();
  useEffect(() => {
    document.title = 'Payments · Platform · Yarotech RADIUS';
  }, []);

  function setSource(next: Source) {
    const params = new URLSearchParams(searchParams);
    if (next === 'vouchers') params.delete('source');
    else params.set('source', next);
    params.delete('page');
    params.delete('search');
    // "abandoned" only exists for voucher sales.
    if (next !== 'vouchers' && params.get('status') === 'abandoned') params.delete('status');
    setSearchParams(params, { replace: true });
  }

  const { page, page_size: pageSize } = list.state;
  const tenant = Number(list.state.filters.tenant);
  const tenantId = Number.isInteger(tenant) && tenant > 0 ? tenant : undefined;
  const status = STATUSES.includes(list.state.filters.status ?? '')
    ? (list.state.filters.status as PaymentStatus)
    : undefined;

  const voucherParams = useMemo<PaymentListParams>(() => {
    const p: PaymentListParams = { page, page_size: pageSize };
    if (debouncedSearch) p.search = debouncedSearch;
    if (tenantId) p.tenant = tenantId;
    if (status) p.status = status;
    return p;
  }, [page, pageSize, debouncedSearch, tenantId, status]);
  const walletParams = useMemo<PlatformWalletPaymentListParams>(() => {
    const p: PlatformWalletPaymentListParams = { page, page_size: pageSize };
    if (debouncedSearch) p.search = debouncedSearch;
    if (tenantId) p.wallet__agent__tenant = tenantId;
    if (status && status !== 'abandoned') p.status = status;
    return p;
  }, [page, pageSize, debouncedSearch, tenantId, status]);
  const subscriptionParams = useMemo<SubscriptionPaymentListParams>(() => {
    const p: SubscriptionPaymentListParams = { page, page_size: pageSize };
    if (tenantId) p.tenant = tenantId;
    if (status && status !== 'abandoned') p.status = status;
    return p;
  }, [page, pageSize, tenantId, status]);

  const vouchers = usePlatformPayments(voucherParams, source === 'vouchers');
  const wallet = usePlatformWalletPayments(walletParams, source === 'wallet');
  const subscriptions = usePlatformSubscriptionPayments(
    subscriptionParams,
    source === 'subscriptions',
  );
  const active = source === 'vouchers' ? vouchers : source === 'wallet' ? wallet : subscriptions;
  const planName = (id: number) => pricing.data?.find((p) => p.id === id)?.name ?? `Plan #${id}`;

  const tenantCell = (id: number) => (
    <Link to={`/platform/tenants/${id}`} className="text-brand-700 hover:underline">
      {tenantName(id)}
    </Link>
  );
  const when = (iso: string) => (
    <time dateTime={iso} title={formatDateTime(iso)} className="text-ink-600">
      {formatRelative(iso)}
    </time>
  );
  const completed = (iso: string | null) =>
    iso ? (
      <span title={formatDateTime(iso)}>{formatRelative(iso)}</span>
    ) : (
      <span className="text-ink-400">—</span>
    );

  const voucherColumns: Column<PaymentTransaction>[] = [
    {
      key: 'reference',
      header: 'Reference',
      primary: true,
      cell: (p) => (
        <div className="min-w-0">
          <code className="font-mono text-sm font-semibold text-ink-900">{p.reference}</code>
          <div className="truncate text-xs text-ink-500">
            {p.customer_email || p.customer_phone || 'Anonymous customer'}
          </div>
        </div>
      ),
    },
    { key: 'tenant', header: 'Tenant', cell: (p) => tenantCell(p.tenant) },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      cell: (p) => <span className="tabular-nums">{formatKobo(p.amount)}</span>,
    },
    { key: 'status', header: 'Status', cell: (p) => <StatusBadge status={p.status} size="sm" /> },
    {
      key: 'voucher',
      header: 'Voucher',
      hideBelow: 'lg',
      cell: (p) =>
        p.voucher_username ? (
          <code className="font-mono text-[13px]">{p.voucher_username}</code>
        ) : (
          <span className="text-ink-400">—</span>
        ),
    },
    { key: 'created', header: 'Created', hideBelow: 'md', cell: (p) => when(p.created_at) },
  ];
  const walletColumns: Column<PlatformWalletPayment>[] = [
    {
      key: 'reference',
      header: 'Reference',
      primary: true,
      cell: (p) => (
        <div className="min-w-0">
          <code className="font-mono text-sm font-semibold text-ink-900">{p.reference}</code>
          <div className="text-xs text-ink-500">Agent #{p.agent_id}</div>
        </div>
      ),
    },
    { key: 'tenant', header: 'Tenant', cell: (p) => tenantCell(p.tenant_id) },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      cell: (p) => <span className="tabular-nums">{formatKobo(p.amount)}</span>,
    },
    { key: 'status', header: 'Status', cell: (p) => <StatusBadge status={p.status} size="sm" /> },
    { key: 'created', header: 'Created', hideBelow: 'md', cell: (p) => when(p.created_at) },
    {
      key: 'completed',
      header: 'Completed',
      hideBelow: 'lg',
      cell: (p) => completed(p.completed_at),
    },
  ];
  const subscriptionColumns: Column<PlatformSubscriptionPayment>[] = [
    {
      key: 'reference',
      header: 'Reference',
      primary: true,
      cell: (p) => (
        <div className="min-w-0">
          <code className="font-mono text-sm font-semibold text-ink-900">{p.reference}</code>
          <div className="text-xs text-ink-500">{planName(p.plan)}</div>
        </div>
      ),
    },
    { key: 'tenant', header: 'Tenant', cell: (p) => tenantCell(p.tenant) },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      cell: (p) => <span className="tabular-nums">{formatKobo(p.amount)}</span>,
    },
    { key: 'status', header: 'Status', cell: (p) => <StatusBadge status={p.status} size="sm" /> },
    { key: 'created', header: 'Created', hideBelow: 'md', cell: (p) => when(p.created_at) },
    {
      key: 'completed',
      header: 'Completed',
      hideBelow: 'lg',
      cell: (p) => completed(p.completed_at),
    },
  ];

  const statusOptions = [
    { value: '', label: 'All statuses' },
    { value: 'success', label: 'Successful' },
    { value: 'pending', label: 'Pending' },
    { value: 'failed', label: 'Failed' },
    ...(source === 'vouchers' ? [{ value: 'abandoned', label: 'Abandoned' }] : []),
  ];

  const emptyState = (
    <EmptyState
      icon={<CreditCard className="h-6 w-6" aria-hidden />}
      title={
        list.activeFilterCount > 0 || debouncedSearch ? 'No payments match' : 'No payments yet'
      }
      action={
        list.activeFilterCount > 0 ? (
          <Button variant="secondary" onClick={list.clearFilters}>
            Clear filters
          </Button>
        ) : undefined
      }
    />
  );
  const pagination = active.data && active.data.count > 0 && (
    <Pagination
      count={active.data.count}
      page={list.state.page}
      totalPages={active.data.total_pages}
      pageSize={list.state.page_size}
      onPageChange={list.setPage}
      onPageSizeChange={list.setPageSize}
      itemLabel="payments"
    />
  );

  return (
    <>
      <PageHeader
        title="Payments"
        description="Every Paystack transaction across the platform, by source. Amounts are in naira."
      />
      <Tabs
        items={SOURCES}
        value={source}
        onChange={setSource}
        ariaLabel="Payment source"
        className="mb-4"
      />
      <FilterBar
        search={
          source === 'subscriptions' ? undefined : (
            <SearchInput
              value={list.state.search}
              onChange={list.setSearch}
              placeholder="Search reference"
              ariaLabel="Search payments"
            />
          )
        }
        filters={
          <>
            <TenantSelect
              value={list.state.filters.tenant ?? ''}
              onChange={(v) => list.setFilter('tenant', v || undefined)}
            />
            <Select
              aria-label="Status"
              size="sm"
              value={list.state.filters.status ?? ''}
              onChange={(e) => list.setFilter('status', e.target.value || undefined)}
              options={statusOptions}
            />
          </>
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      {source === 'vouchers' && (
        <DataTable
          caption="Voucher sales"
          columns={voucherColumns}
          rows={vouchers.data?.results}
          rowKey={(p) => p.id}
          loading={vouchers.isPending}
          refreshing={vouchers.isFetching && !vouchers.isPending}
          error={vouchers.error}
          onRetry={() => void vouchers.refetch()}
          empty={emptyState}
        />
      )}
      {source === 'wallet' && (
        <DataTable
          caption="Agent wallet top-ups"
          columns={walletColumns}
          rows={wallet.data?.results}
          rowKey={(p) => p.id}
          loading={wallet.isPending}
          refreshing={wallet.isFetching && !wallet.isPending}
          error={wallet.error}
          onRetry={() => void wallet.refetch()}
          empty={emptyState}
        />
      )}
      {source === 'subscriptions' && (
        <DataTable
          caption="Subscription payments"
          columns={subscriptionColumns}
          rows={subscriptions.data?.results}
          rowKey={(p) => p.id}
          loading={subscriptions.isPending}
          refreshing={subscriptions.isFetching && !subscriptions.isPending}
          error={subscriptions.error}
          onRetry={() => void subscriptions.refetch()}
          empty={emptyState}
        />
      )}
      {pagination}
    </>
  );
}
