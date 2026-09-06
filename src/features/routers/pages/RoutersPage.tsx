import { useMemo } from 'react';
import { useNavigate } from 'react-router';
import { Plus, Radio } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { Button, ButtonLink, Select } from '@/components/ui';
import { EmptyState } from '@/components/feedback';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { can } from '@/services/auth/principal';
import { usePrincipal } from '@/app/auth/useAuth';
import type { DeploymentStatus, NasDevice, OnboardingState, RouterListParams } from '@/types/api';
import { RouterStateBadges } from '../components/RouterStateBadges';
import { useRouters } from '../queries';
import { ONBOARDING_FILTER_OPTIONS } from '../routerSchemas';

const FILTERS = ['onboarding_state', 'deployment_status', 'is_active'] as const;
const STATES = ONBOARDING_FILTER_OPTIONS.map((o) => o.value).filter(Boolean) as readonly string[];
const DEPLOYMENTS: readonly string[] = ['not_deployed', 'deploying', 'deployed', 'failed'];

export default function RoutersPage() {
  const principal = usePrincipal();
  const navigate = useNavigate();
  const canManage = can(principal, 'routers.manage');
  const list = useListParams(FILTERS, { ordering: 'name' });
  const debouncedSearch = useDebouncedValue(list.state.search);
  const params = useMemo<RouterListParams>(() => {
    const p: RouterListParams = { page: list.state.page, page_size: list.state.page_size };
    if (debouncedSearch) p.search = debouncedSearch;
    if (list.state.ordering) p.ordering = list.state.ordering;
    const state = list.state.filters.onboarding_state;
    if (state && STATES.includes(state)) p.onboarding_state = state as OnboardingState;
    const dep = list.state.filters.deployment_status;
    if (dep && DEPLOYMENTS.includes(dep)) p.deployment_status = dep as DeploymentStatus;
    if (list.state.filters.is_active) p.is_active = list.state.filters.is_active === 'true';
    return p;
  }, [list.state, debouncedSearch]);
  const query = useRouters(params);

  const columns: Column<NasDevice>[] = [
    {
      key: 'name',
      header: 'Router',
      primary: true,
      sortField: 'name',
      cell: (r) => (
        <div className="min-w-0">
          <div className="font-medium text-ink-900">{r.name}</div>
          <div className="mt-0.5 text-xs text-ink-500">
            <code className="font-mono">{r.ip_address}</code>
            {r.location ? ` · ${r.location}` : ''}
          </div>
        </div>
      ),
    },
    { key: 'state', header: 'Status', cell: (r) => <RouterStateBadges router={r} /> },
    {
      key: 'vpn',
      header: 'VPN',
      hideBelow: 'lg',
      cell: (r) =>
        r.wireguard_ip ? (
          <code className="font-mono text-xs">{r.wireguard_ip}</code>
        ) : (
          <span className="text-ink-400">Not configured</span>
        ),
    },
    {
      key: 'seen',
      header: 'Last seen',
      hideBelow: 'md',
      sortField: 'last_seen_at',
      cell: (r) =>
        r.last_seen_at ? (
          <span title={formatDateTime(r.last_seen_at)}>{formatRelative(r.last_seen_at)}</span>
        ) : (
          <span className="text-ink-400">Never</span>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Routers"
        description="MikroTik hotspots registered as RADIUS clients, with their onboarding and VPN status."
        actions={
          canManage ? (
            <ButtonLink to="/routers/new" leadingIcon={<Plus className="h-4 w-4" aria-hidden />}>
              Add router
            </ButtonLink>
          ) : undefined
        }
      />
      <FilterBar
        search={
          <SearchInput
            value={list.state.search}
            onChange={list.setSearch}
            placeholder="Search name, IP or location"
            ariaLabel="Search routers"
          />
        }
        filters={
          <>
            <Select
              aria-label="Onboarding state"
              size="sm"
              value={list.state.filters.onboarding_state ?? ''}
              onChange={(e) => list.setFilter('onboarding_state', e.target.value || undefined)}
              options={ONBOARDING_FILTER_OPTIONS}
            />
            <Select
              aria-label="Deployment"
              size="sm"
              value={list.state.filters.deployment_status ?? ''}
              onChange={(e) => list.setFilter('deployment_status', e.target.value || undefined)}
              options={[
                { value: '', label: 'Any deployment' },
                { value: 'not_deployed', label: 'Not deployed' },
                { value: 'deploying', label: 'Deploying' },
                { value: 'deployed', label: 'Deployed' },
                { value: 'failed', label: 'Failed' },
              ]}
            />
            <Select
              aria-label="Active"
              size="sm"
              value={list.state.filters.is_active ?? ''}
              onChange={(e) => list.setFilter('is_active', e.target.value || undefined)}
              options={[
                { value: '', label: 'Active and inactive' },
                { value: 'true', label: 'Active only' },
                { value: 'false', label: 'Inactive only' },
              ]}
            />
          </>
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Routers"
        columns={columns}
        rows={query.data?.results}
        rowKey={(r) => r.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        ordering={list.state.ordering}
        onOrderingChange={list.setOrdering}
        onRowClick={(r) => navigate(`/routers/${r.id}`)}
        empty={
          list.activeFilterCount > 0 ? (
            <EmptyState
              icon={<Radio className="h-6 w-6" aria-hidden />}
              title="No routers match"
              description="Try another state or search term."
              action={
                <Button variant="secondary" onClick={list.clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<Radio className="h-6 w-6" aria-hidden />}
              title="No routers yet"
              description={
                canManage
                  ? 'Register your first MikroTik to start onboarding it.'
                  : 'Routers will appear here once a manager registers them.'
              }
              action={canManage ? <ButtonLink to="/routers/new">Add router</ButtonLink> : undefined}
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
          itemLabel="routers"
        />
      )}
    </>
  );
}
