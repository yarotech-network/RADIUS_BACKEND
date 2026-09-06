import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { Building2, Plus } from 'lucide-react';
import { PageHeader, StatusBadge } from '@/components/layout';
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
import { formatDate } from '@/lib/formatting/dates';
import type { Tenant, TenantListParams } from '@/types/api';
import { useTenants } from '../queries';
import { TenantDialog } from '../components/TenantDialog';

const FILTERS = ['is_active', 'kind'] as const;

/** `/platform/tenants` — every operator on the platform; create + open detail. */
export default function TenantsPage() {
  const navigate = useNavigate();
  const list = useListParams(FILTERS);
  const debouncedSearch = useDebouncedValue(list.state.search);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    document.title = 'Tenants · Platform · Yarotech RADIUS';
  }, []);

  const params = useMemo<TenantListParams>(() => {
    const p: TenantListParams = { page: list.state.page, page_size: list.state.page_size };
    if (debouncedSearch) p.search = debouncedSearch;
    if (list.state.filters.is_active) p.is_active = list.state.filters.is_active === 'true';
    // Default view hides the platform's own tenant; "platform" shows only it.
    const kind = list.state.filters.kind;
    if (kind === 'platform') p.is_platform_admin = true;
    else if (kind !== 'all') p.is_platform_admin = false;
    return p;
  }, [list.state, debouncedSearch]);
  const query = useTenants(params);

  const columns: Column<Tenant>[] = [
    {
      key: 'name',
      header: 'Tenant',
      primary: true,
      cell: (t) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-medium text-ink-900">
            <span className="truncate">{t.name}</span>
            {t.is_platform_admin && (
              <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700">
                platform
              </span>
            )}
          </div>
          <div className="mt-0.5 truncate text-xs text-ink-500">
            <code className="font-mono">/s/{t.slug}</code>
            {t.email ? ` · ${t.email}` : ''}
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      cell: (t) => <StatusBadge status={t.is_active ? 'active' : 'inactive'} size="sm" dot />,
    },
    {
      key: 'members',
      header: 'Members',
      align: 'right',
      hideBelow: 'sm',
      cell: (t) => <span className="tabular-nums">{t.member_count}</span>,
    },
    {
      key: 'vouchers',
      header: 'Vouchers',
      align: 'right',
      hideBelow: 'md',
      cell: (t) => <span className="tabular-nums">{t.voucher_count.toLocaleString()}</span>,
    },
    {
      key: 'created',
      header: 'Created',
      hideBelow: 'lg',
      cell: (t) => <span className="text-ink-600">{formatDate(t.created_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title="Tenants"
        description="Operators running hotspots on the platform. Open a tenant to manage its members, status and links."
        actions={
          <Button
            leadingIcon={<Plus className="h-4 w-4" aria-hidden />}
            onClick={() => setCreating(true)}
          >
            New tenant
          </Button>
        }
      />
      <FilterBar
        search={
          <SearchInput
            value={list.state.search}
            onChange={list.setSearch}
            placeholder="Search name or slug"
            ariaLabel="Search tenants"
          />
        }
        filters={
          <>
            <Select
              aria-label="Status"
              size="sm"
              value={list.state.filters.is_active ?? ''}
              onChange={(e) => list.setFilter('is_active', e.target.value || undefined)}
              options={[
                { value: '', label: 'Any status' },
                { value: 'true', label: 'Active' },
                { value: 'false', label: 'Inactive' },
              ]}
            />
            <Select
              aria-label="Kind"
              size="sm"
              value={list.state.filters.kind ?? ''}
              onChange={(e) => list.setFilter('kind', e.target.value || undefined)}
              options={[
                { value: '', label: 'Operators' },
                { value: 'platform', label: 'Platform tenant' },
                { value: 'all', label: 'All tenants' },
              ]}
            />
          </>
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Tenants"
        columns={columns}
        rows={query.data?.results}
        rowKey={(t) => t.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        onRowClick={(t) => void navigate(`/platform/tenants/${t.id}`)}
        rowActions={(t) => (
          <ButtonLink to={`/platform/tenants/${t.id}`} size="sm" variant="ghost">
            Open
          </ButtonLink>
        )}
        empty={
          list.activeFilterCount > 0 || debouncedSearch ? (
            <EmptyState
              icon={<Building2 className="h-6 w-6" aria-hidden />}
              title="No tenants match"
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    list.clearFilters();
                    list.setSearch('');
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<Building2 className="h-6 w-6" aria-hidden />}
              title="No tenants yet"
              description="Create the first operator workspace to get started."
              action={<Button onClick={() => setCreating(true)}>New tenant</Button>}
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
          itemLabel="tenants"
        />
      )}
      <TenantDialog
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(t) => void navigate(`/platform/tenants/${t.id}`)}
      />
    </>
  );
}
