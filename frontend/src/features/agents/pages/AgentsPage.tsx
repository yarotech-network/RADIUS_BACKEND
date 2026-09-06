import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { Plus, Store } from 'lucide-react';
import { PageHeader, StatusBadge } from '@/components/layout';
import { Button, Select } from '@/components/ui';
import { EmptyState, useToast } from '@/components/feedback';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { formatKobo } from '@/lib/formatting/money';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import type { AgentListParams, AgentProfile, AgentStatus } from '@/types/api';
import { useAgents } from '../queries';
import { AGENT_STATUS_FILTERS } from '../agentRules';
import { formatCommission } from '../agentSchemas';
import { CreateAgentDialog } from '../components/AgentForms';

const FILTERS = ['status'] as const;

export default function AgentsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const list = useListParams(FILTERS);
  const debouncedSearch = useDebouncedValue(list.state.search);
  const [creating, setCreating] = useState(false);
  const params = useMemo(() => {
    const p: AgentListParams = { page: list.state.page, page_size: list.state.page_size };
    if (debouncedSearch) p.search = debouncedSearch;
    if (list.state.ordering) p.ordering = list.state.ordering;
    if (list.state.filters.status) p.status = list.state.filters.status as AgentStatus;
    return p;
  }, [list.state, debouncedSearch]);
  const query = useAgents(params);

  const columns: Column<AgentProfile>[] = [
    {
      key: 'agent',
      header: 'Agent',
      primary: true,
      cell: (a) => (
        <div className="min-w-0">
          <div className="font-medium text-ink-900">{a.username}</div>
          <div className="truncate text-xs text-ink-500">{a.shop_name || 'No shop name'}</div>
        </div>
      ),
    },
    {
      key: 'phone',
      header: 'Phone',
      hideBelow: 'md',
      cell: (a) => <span className="font-mono text-[13px] text-ink-700">{a.phone}</span>,
    },
    { key: 'status', header: 'Status', cell: (a) => <StatusBadge status={a.status} size="sm" /> },
    {
      key: 'commission',
      header: 'Commission',
      align: 'right',
      hideBelow: 'lg',
      cell: (a) => <span className="tabular-nums">{formatCommission(a.commission_rate)}%</span>,
    },
    {
      key: 'wallet',
      header: 'Wallet',
      align: 'right',
      cell: (a) => <span className="tabular-nums">{formatKobo(a.wallet_balance)}</span>,
    },
    {
      key: 'created',
      header: 'Joined',
      hideBelow: 'xl',
      sortField: 'created_at',
      cell: (a) => (
        <time dateTime={a.created_at} title={formatDateTime(a.created_at)} className="text-ink-600">
          {formatRelative(a.created_at)}
        </time>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Agents"
        description="Resellers who sell your vouchers from a prepaid wallet."
        actions={
          <Button
            leadingIcon={<Plus className="h-4 w-4" aria-hidden />}
            onClick={() => setCreating(true)}
          >
            Add agent
          </Button>
        }
      />
      <FilterBar
        search={
          <SearchInput
            value={list.state.search}
            onChange={list.setSearch}
            placeholder="Search username, shop or phone"
            ariaLabel="Search agents"
          />
        }
        filters={
          <Select
            aria-label="Status"
            size="sm"
            value={list.state.filters.status ?? ''}
            onChange={(e) => list.setFilter('status', e.target.value || undefined)}
            options={AGENT_STATUS_FILTERS}
          />
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Agents"
        columns={columns}
        rows={query.data?.results}
        rowKey={(a) => a.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        ordering={list.state.ordering}
        onOrderingChange={list.setOrdering}
        onRowClick={(a) => navigate(`/agents/${a.id}`)}
        empty={
          list.activeFilterCount > 0 ? (
            <EmptyState
              icon={<Store className="h-6 w-6" aria-hidden />}
              title="No agents match"
              description="Try another status or search term."
              action={
                <Button variant="secondary" onClick={list.clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<Store className="h-6 w-6" aria-hidden />}
              title="No agents yet"
              description="Add a reseller and approve them to let them sell vouchers."
              action={<Button onClick={() => setCreating(true)}>Add agent</Button>}
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
          itemLabel="agents"
        />
      )}
      <CreateAgentDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(agent) => {
          setCreating(false);
          toast.success('Agent added', `${agent.username} is pending approval.`);
          navigate(`/agents/${agent.id}`);
        }}
      />
    </>
  );
}
