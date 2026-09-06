import { useEffect, useMemo } from 'react';
import { Route, Routes, useSearchParams } from 'react-router';
import { Plus, Wallet } from 'lucide-react';
import { StatusBadge } from '@/components/layout';
import { Button, Select, Stat } from '@/components/ui';
import { EmptyState } from '@/components/feedback';
import { DataTable, Pagination, useListParams, type Column } from '@/components/data';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { formatKobo } from '@/lib/formatting/money';
import { pendingCheckout } from '@/features/storefront/pendingCheckout';
import type { AgentFundingPayment, FundingListParams, FundingStatus } from '@/types/api';
import { useAgentWallet, useFundings } from '../queries';
import { FundWalletDialog } from '../components/FundWalletDialog';
import { FundingTracker } from '../components/FundingTracker';

const FILTERS = ['status'] as const;
const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'success', label: 'Successful' },
  { value: 'failed', label: 'Failed' },
];

/** `/agent/wallet` (+ `/agent/wallet/return?reference=` where Paystack may send the agent back). */
export default function AgentWalletPage() {
  return (
    <Routes>
      <Route index element={<WalletScreen />} />
      <Route path="return" element={<WalletScreen returning />} />
      <Route path="*" element={<WalletScreen />} />
    </Routes>
  );
}

function WalletScreen({ returning = false }: { returning?: boolean }) {
  const [params, setParams] = useSearchParams();
  const wallet = useAgentWallet();
  const list = useListParams(FILTERS);
  const remembered = useMemo(() => pendingCheckout.load(), []);
  const reference =
    params.get('reference') ??
    params.get('trxref') ??
    (returning && remembered?.kind === 'wallet' ? remembered.reference : null);
  const fundOpen = params.get('fund') === '1';

  useEffect(() => {
    document.title = 'Wallet · Agent portal';
  }, []);

  const query = useFundings(
    useMemo(() => {
      const p: FundingListParams = { page: list.state.page, page_size: list.state.page_size };
      if (list.state.filters.status) p.status = list.state.filters.status as FundingStatus;
      return p;
    }, [list.state]),
  );

  function patch(entries: Record<string, string | null>) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(entries)) {
          if (v === null) next.delete(k);
          else next.set(k, v);
        }
        return next;
      },
      { replace: true },
    );
  }

  const columns: Column<AgentFundingPayment>[] = [
    {
      key: 'reference',
      header: 'Reference',
      primary: true,
      cell: (f) => (
        <div className="min-w-0">
          <code className="font-mono text-sm font-semibold text-ink-900">{f.reference}</code>
          <div className="text-xs text-ink-500">
            <time dateTime={f.created_at} title={formatDateTime(f.created_at)}>
              {formatRelative(f.created_at)}
            </time>
          </div>
        </div>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      cell: (f) => <span className="tabular-nums">{formatKobo(f.amount)}</span>,
    },
    { key: 'status', header: 'Status', cell: (f) => <StatusBadge status={f.status} size="sm" /> },
    {
      key: 'completed',
      header: 'Completed',
      hideBelow: 'md',
      cell: (f) =>
        f.completed_at ? (
          <span title={formatDateTime(f.completed_at)}>{formatRelative(f.completed_at)}</span>
        ) : (
          <span className="text-ink-400">—</span>
        ),
    },
  ];

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-brand-950">Wallet</h1>
          <p className="mt-1 text-sm text-ink-500">
            Vouchers you sell are paid for from this balance.
          </p>
        </div>
        <Button
          onClick={() => patch({ fund: '1' })}
          leadingIcon={<Plus className="size-4" aria-hidden />}
        >
          Fund wallet
        </Button>
      </header>

      <Stat
        tone="brand"
        label="Available balance"
        value={wallet.data ? formatKobo(wallet.data.balance) : wallet.isError ? 'Unavailable' : '—'}
        loading={wallet.isPending}
        icon={<Wallet className="size-4" aria-hidden />}
        hint={wallet.data ? `Updated ${formatRelative(wallet.data.updated_at)}` : undefined}
      />

      {reference && (
        <FundingTracker
          reference={reference}
          onDismiss={() => {
            pendingCheckout.clear();
            patch({ reference: null, trxref: null });
          }}
        />
      )}

      <section aria-labelledby="topups-heading" className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 id="topups-heading" className="text-base font-semibold text-brand-950">
            Top-up history
          </h2>
          <Select
            aria-label="Status"
            size="sm"
            value={list.state.filters.status ?? ''}
            onChange={(e) => list.setFilter('status', e.target.value || undefined)}
            options={STATUS_OPTIONS}
          />
        </div>
        <DataTable
          caption="Top-ups"
          columns={columns}
          rows={query.data?.results}
          rowKey={(f) => f.id}
          loading={query.isPending}
          refreshing={query.isFetching && !query.isPending}
          error={query.error}
          onRetry={() => void query.refetch()}
          dense
          empty={
            list.activeFilterCount > 0 ? (
              <EmptyState
                title="No top-ups match"
                action={
                  <Button variant="secondary" size="sm" onClick={list.clearFilters}>
                    Clear filter
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon={<Wallet className="size-6" aria-hidden />}
                title="No top-ups yet"
                description="Fund your wallet to start selling vouchers."
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
            itemLabel="top-ups"
          />
        )}
      </section>

      <FundWalletDialog
        open={fundOpen}
        onClose={() => patch({ fund: null })}
        onStarted={(ref) => patch({ fund: null, reference: ref })}
      />
    </div>
  );
}
