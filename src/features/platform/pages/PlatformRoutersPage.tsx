import { useEffect, useMemo } from 'react';
import { Link } from 'react-router';
import { Radio } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { Button, Select } from '@/components/ui';
import { EmptyState } from '@/components/feedback';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import type { DeploymentStatus, NasDevice, OnboardingState, RouterListParams } from '@/types/api';
import { RouterStateBadges } from '@/features/routers/components/RouterStateBadges';
import { ONBOARDING_FILTER_OPTIONS } from '@/features/routers/routerSchemas';
import { usePlatformRouters, useTenantName } from '../queries';
import { TenantSelect } from '../components/TenantSelect';

const FILTERS = ['tenant', 'onboarding_state', 'deployment_status', 'is_active'] as const;
const STATES = ONBOARDING_FILTER_OPTIONS.map((o) => o.value).filter(Boolean) as readonly string[];
const DEPLOYMENTS: readonly string[] = ['not_deployed', 'deploying', 'deployed', 'failed'];

/** `/platform/routers` — read-only fleet view across tenants (`platform/routers/`). */
export default function PlatformRoutersPage() {
  const list = useListParams(FILTERS);
  const debouncedSearch = useDebouncedValue(list.state.search);
  const tenantName = useTenantName();
  useEffect(() => {
    document.title = 'Router fleet · Platform · Yarotech RADIUS';
  }, []);

  const params = useMemo<RouterListParams>(() => {
    const p: RouterListParams = { page: list.state.page, page_size: list.state.page_size };
    if (debouncedSearch) p.search = debouncedSearch;
    const tenant = Number(list.state.filters.tenant);
    if (Number.isInteger(tenant) && tenant > 0) p.tenant = tenant;
    const state = list.state.filters.onboarding_state;
    if (state && STATES.includes(state)) p.onboarding_state = state as OnboardingState;
    const dep = list.state.filters.deployment_status;
    if (dep && DEPLOYMENTS.includes(dep)) p.deployment_status = dep as DeploymentStatus;
    if (list.state.filters.is_active) p.is_active = list.state.filters.is_active === 'true';
    return p;
  }, [list.state, debouncedSearch]);
  const query = usePlatformRouters(params);

  const columns: Column<NasDevice>[] = [
    {
      key: 'name',
      header: 'Router',
      primary: true,
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
    {
      key: 'tenant',
      header: 'Tenant',
      cell: (r) => (
        <Link to={`/platform/tenants/${r.tenant}`} className="text-brand-700 hover:underline">
          {r.tenant_name || tenantName(r.tenant)}
        </Link>
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
        title="Router fleet"
        description="Every MikroTik router registered on the platform. Onboarding actions happen inside each operator's workspace."
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
            <TenantSelect
              value={list.state.filters.tenant ?? ''}
              onChange={(v) => list.setFilter('tenant', v || undefined)}
            />
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
                { value: '', label: 'Active or not' },
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
        caption="Router fleet"
        columns={columns}
        rows={query.data?.results}
        rowKey={(r) => r.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        empty={
          <EmptyState
            icon={<Radio className="h-6 w-6" aria-hidden />}
            title={
              list.activeFilterCount > 0 || debouncedSearch
                ? 'No routers match'
                : 'No routers registered yet'
            }
            description={
              list.activeFilterCount > 0 || debouncedSearch
                ? undefined
                : 'Routers appear here once operators add them in their workspace.'
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
