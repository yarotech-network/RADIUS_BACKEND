import { useMemo, useState } from 'react';
import { Activity, Pause, Play, Unplug } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { Button, ConfirmDialog, Select } from '@/components/ui';
import { EmptyState, useToast } from '@/components/feedback';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import { formatBytes, formatDuration } from '@/lib/formatting/units';
import { formatRelative, formatTime } from '@/lib/formatting/dates';
import { can } from '@/services/auth/principal';
import { usePrincipal } from '@/app/auth/useAuth';
import { useDisconnectSession, useLiveUsers } from '@/features/dashboard/queries';
import { useRouterOptions } from '@/features/routers/queries';
import type { LiveUser, LiveUsersParams } from '@/types/api';

const FILTERS = ['router'] as const;

export default function SessionsPage() {
  const principal = usePrincipal();
  const toast = useToast();
  const canDisconnect = can(principal, 'sessions.disconnect');
  const list = useListParams(FILTERS);
  const debouncedSearch = useDebouncedValue(list.state.search);
  const [paused, setPaused] = useState(false);
  const params = useMemo<LiveUsersParams>(() => {
    const p: LiveUsersParams = { page: list.state.page, page_size: list.state.page_size };
    if (debouncedSearch) p.username = debouncedSearch;
    if (list.state.filters.router) p.router = list.state.filters.router;
    return p;
  }, [list.state, debouncedSearch]);
  const query = useLiveUsers(params, { live: !paused });
  const routers = useRouterOptions();
  const disconnect = useDisconnectSession();
  const [pending, setPending] = useState<LiveUser | null>(null);

  const columns: Column<LiveUser>[] = [
    {
      key: 'user',
      header: 'Voucher',
      primary: true,
      cell: (s) => (
        <div className="min-w-0">
          <code className="font-mono text-sm font-semibold text-ink-900">{s.username}</code>
          <div className="mt-0.5 text-xs text-ink-500">{s.router_name ?? s.ip_address}</div>
        </div>
      ),
    },
    {
      key: 'router',
      header: 'Router',
      hideBelow: 'lg',
      mobileHidden: true,
      cell: (s) => (
        <span className="text-ink-700">
          {s.router_name ?? <span className="text-ink-400">Unknown ({s.ip_address})</span>}
        </span>
      ),
    },
    {
      key: 'since',
      header: 'Connected',
      cell: (s) =>
        s.connected_at ? (
          <span title={formatTime(s.connected_at)}>{formatRelative(s.connected_at)}</span>
        ) : (
          '—'
        ),
    },
    {
      key: 'duration',
      header: 'Duration',
      hideBelow: 'md',
      cell: (s) => <span className="tabular-nums">{formatDuration(s.session_time)}</span>,
    },
    {
      key: 'down',
      header: 'Download',
      align: 'right',
      cell: (s) => <span className="tabular-nums">{formatBytes(s.bytes_out)}</span>,
    },
    {
      key: 'up',
      header: 'Upload',
      align: 'right',
      hideBelow: 'sm',
      cell: (s) => <span className="tabular-nums">{formatBytes(s.bytes_in)}</span>,
    },
  ];

  const observed = query.data?.observed_at;

  return (
    <>
      <PageHeader
        title="Live sessions"
        description="Devices currently online through your routers."
        meta={
          <span className="inline-flex items-center gap-2 text-xs text-ink-500" aria-live="polite">
            <span
              className={[
                'inline-block h-2 w-2 rounded-full',
                paused ? 'bg-ink-300' : 'animate-pulse bg-success-600',
              ].join(' ')}
              aria-hidden
            />
            {paused
              ? 'Paused'
              : query.isFetching
                ? 'Refreshing…'
                : observed
                  ? `Updated ${formatRelative(observed)}`
                  : 'Live'}
          </span>
        }
        actions={
          <Button
            variant="secondary"
            size="sm"
            leadingIcon={
              paused ? (
                <Play className="h-4 w-4" aria-hidden />
              ) : (
                <Pause className="h-4 w-4" aria-hidden />
              )
            }
            onClick={() => setPaused((p) => !p)}
            aria-pressed={paused}
          >
            {paused ? 'Resume updates' : 'Pause updates'}
          </Button>
        }
      />
      <FilterBar
        search={
          <SearchInput
            value={list.state.search}
            onChange={list.setSearch}
            placeholder="Search by voucher username"
            ariaLabel="Search sessions"
          />
        }
        filters={
          <Select
            aria-label="Router"
            size="sm"
            value={list.state.filters.router ?? ''}
            onChange={(e) => list.setFilter('router', e.target.value || undefined)}
            options={[
              { value: '', label: 'All routers' },
              ...(routers.data ?? []).map((r) => ({ value: r.id, label: r.name })),
            ]}
          />
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Live sessions"
        columns={columns}
        rows={query.data?.users}
        rowKey={(s) => s.session_id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        empty={
          <EmptyState
            icon={<Activity className="h-6 w-6" aria-hidden />}
            title={
              list.activeFilterCount > 0 ? 'No matching sessions' : 'Nobody is online right now'
            }
            description={
              list.activeFilterCount > 0
                ? 'Try clearing the filters.'
                : 'Sessions appear here as soon as a customer logs in with a voucher.'
            }
            action={
              list.activeFilterCount > 0 ? (
                <Button variant="secondary" onClick={list.clearFilters}>
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        }
        {...(canDisconnect
          ? {
              rowActions: (s: LiveUser) => (
                <Button
                  variant="ghost"
                  size="sm"
                  leadingIcon={<Unplug className="h-4 w-4" aria-hidden />}
                  onClick={() => setPending(s)}
                  aria-label={`Disconnect ${s.username}`}
                >
                  <span className="hidden sm:inline">Disconnect</span>
                </Button>
              ),
            }
          : {})}
      />
      {query.data && query.data.count > 0 && (
        <Pagination
          count={query.data.count}
          page={list.state.page}
          totalPages={query.data.total_pages}
          pageSize={list.state.page_size}
          onPageChange={list.setPage}
          onPageSizeChange={list.setPageSize}
          itemLabel="sessions"
        />
      )}
      <p className="mt-3 text-xs text-ink-500">
        Client IP and device addresses are not reported by the accounting feed; only router-side
        data is shown.
      </p>

      <ConfirmDialog
        open={pending !== null}
        onClose={() => setPending(null)}
        tone="danger"
        title={`Disconnect ${pending?.username ?? 'session'}?`}
        description="Sends a disconnect request to the router. The voucher stays valid and the customer can log in again."
        confirmLabel="Disconnect"
        onConfirm={async () => {
          if (!pending) return;
          const res = await disconnect.mutateAsync(pending.session_id);
          if (res.acknowledged)
            toast.success('Disconnect sent', `${pending.username} was disconnected by the router.`);
          else
            toast.info(
              'Request sent',
              'The router did not acknowledge the disconnect yet; the session may take a moment to drop.',
            );
        }}
      />
    </>
  );
}
