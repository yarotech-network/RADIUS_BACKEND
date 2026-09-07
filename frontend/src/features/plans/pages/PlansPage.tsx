import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Layers, MoreHorizontal, Pencil, Plus, Ticket, Trash2 } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import { BooleanBadge } from '@/components/layout/StatusBadge';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { Button, ConfirmDialog, Menu, Select } from '@/components/ui';
import { EmptyState, useToast } from '@/components/feedback';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import { formatKobo } from '@/lib/formatting/money';
import { formatDate } from '@/lib/formatting/dates';
import { errorMessage } from '@/services/api/errors';
import { can } from '@/services/auth/principal';
import { usePrincipal } from '@/app/auth/useAuth';
import type { InternetPlan, PlanListParams } from '@/types/api';
import { PlanDialog } from '../components/PlanDialog';
import { PlanSummary } from '../components/PlanSummary';
import { PLANS_DEFAULT_ORDERING, useDeletePlan, usePlans, useUpdatePlan } from '../queries';

const FILTERS = ['is_active'] as const;

export default function PlansPage() {
  const principal = usePrincipal();
  const canManage = can(principal, 'plans.manage');
  const canGenerate = can(principal, 'vouchers.generate');
  const toast = useToast();
  const list = useListParams(FILTERS, { ordering: PLANS_DEFAULT_ORDERING });
  const debouncedSearch = useDebouncedValue(list.state.search);
  const params = useMemo<PlanListParams>(() => {
    const p: PlanListParams = { page: list.state.page, page_size: list.state.page_size };
    if (debouncedSearch) p.search = debouncedSearch;
    if (list.state.ordering) p.ordering = list.state.ordering;
    if (list.state.filters.is_active) p.is_active = list.state.filters.is_active === 'true';
    return p;
  }, [list.state, debouncedSearch]);
  const query = usePlans(params);
  const update = useUpdatePlan();
  const remove = useDeletePlan();
  const [editor, setEditor] = useState<{ open: boolean; plan?: InternetPlan }>({ open: false });
  const [pendingDelete, setPendingDelete] = useState<InternetPlan | null>(null);

  async function toggleActive(plan: InternetPlan) {
    try {
      await update.mutateAsync({ id: plan.id, payload: { is_active: !plan.is_active } });
      toast.success(plan.is_active ? `${plan.name} deactivated` : `${plan.name} activated`);
    } catch (error) {
      toast.error('Could not update plan', errorMessage(error));
    }
  }

  const columns: Column<InternetPlan>[] = [
    {
      key: 'name',
      header: 'Plan',
      primary: true,
      cell: (plan) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink-900">{plan.name}</span>
            {!plan.is_active && <BooleanBadge value={false} falseLabel="Inactive" size="sm" />}
          </div>
          <PlanSummary plan={plan} className="mt-1" />
        </div>
      ),
    },
    {
      key: 'price',
      header: 'Price',
      sortField: 'price',
      align: 'right',
      cell: (plan) => (
        <span className="font-medium text-ink-900 tabular-nums">{formatKobo(plan.price)}</span>
      ),
    },
    {
      key: 'prefix',
      header: 'Prefix',
      hideBelow: 'lg',
      cell: (plan) =>
        plan.voucher_prefix ? (
          <code className="rounded bg-surface-muted px-1.5 py-0.5 text-xs">
            {plan.voucher_prefix}
          </code>
        ) : (
          <span className="text-ink-400">—</span>
        ),
    },
    {
      key: 'created',
      header: 'Created',
      hideBelow: 'xl',
      sortField: 'created_at',
      cell: (plan) => <span className="text-ink-600">{formatDate(plan.created_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title="Plans"
        description="Internet packages your customers buy. Every voucher is generated from a plan."
        actions={
          canManage ? (
            <Button
              leadingIcon={<Plus className="h-4 w-4" aria-hidden />}
              onClick={() => setEditor({ open: true })}
            >
              New plan
            </Button>
          ) : undefined
        }
      />
      <FilterBar
        search={
          <SearchInput
            value={list.state.search}
            onChange={list.setSearch}
            placeholder="Search plans"
            ariaLabel="Search plans"
          />
        }
        filters={
          <Select
            aria-label="Status"
            size="sm"
            value={list.state.filters.is_active ?? ''}
            onChange={(e) => list.setFilter('is_active', e.target.value || undefined)}
            options={[
              { value: '', label: 'All plans' },
              { value: 'true', label: 'Active only' },
              { value: 'false', label: 'Inactive only' },
            ]}
          />
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Internet plans"
        columns={columns}
        rows={query.data?.results}
        rowKey={(plan) => plan.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        ordering={list.state.ordering}
        onOrderingChange={list.setOrdering}
        empty={
          list.activeFilterCount > 0 ? (
            <EmptyState
              icon={<Layers className="h-6 w-6" aria-hidden />}
              title="No plans match"
              description="Try a different search or clear the filters."
              action={
                <Button variant="secondary" onClick={list.clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<Layers className="h-6 w-6" aria-hidden />}
              title="No plans yet"
              description={
                canManage
                  ? 'Create your first plan to start generating vouchers.'
                  : 'Plans will appear here once a manager creates them.'
              }
              action={
                canManage ? (
                  <Button onClick={() => setEditor({ open: true })}>Create a plan</Button>
                ) : undefined
              }
            />
          )
        }
        rowActions={(plan) => {
          const items = [
            ...(canGenerate
              ? [
                  {
                    key: 'gen',
                    label: 'Generate vouchers',
                    icon: <Ticket className="h-4 w-4" aria-hidden />,
                    href: `/vouchers/generate?plan=${plan.id}`,
                  },
                ]
              : []),
            ...(canManage
              ? [
                  {
                    key: 'edit',
                    label: 'Edit',
                    icon: <Pencil className="h-4 w-4" aria-hidden />,
                    onSelect: () => setEditor({ open: true, plan }),
                  },
                  {
                    key: 'toggle',
                    label: plan.is_active ? 'Deactivate' : 'Activate',
                    onSelect: () => void toggleActive(plan),
                  },
                  'separator' as const,
                  {
                    key: 'delete',
                    label: 'Delete',
                    icon: <Trash2 className="h-4 w-4" aria-hidden />,
                    tone: 'danger' as const,
                    onSelect: () => setPendingDelete(plan),
                  },
                ]
              : []),
          ];
          if (items.length === 0) return null;
          return (
            <Menu
              trigger={(props) => (
                <Button
                  {...props}
                  variant="ghost"
                  size="icon"
                  aria-label={`Actions for ${plan.name}`}
                >
                  <MoreHorizontal className="h-4 w-4" aria-hidden />
                </Button>
              )}
              items={items}
            />
          );
        }}
      />
      {query.data && query.data.count > 0 && (
        <Pagination
          count={query.data.count}
          page={list.state.page}
          totalPages={query.data.total_pages}
          pageSize={list.state.page_size}
          onPageChange={list.setPage}
          onPageSizeChange={list.setPageSize}
          itemLabel="plans"
        />
      )}

      <PlanDialog
        open={editor.open}
        {...(editor.plan ? { plan: editor.plan } : {})}
        onClose={() => setEditor({ open: false })}
        onSaved={(saved) => {
          setEditor({ open: false });
          toast.success(
            editor.plan ? 'Plan updated' : 'Plan created',
            editor.plan ? undefined : `${saved.name} is ready.`,
          );
        }}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        tone="danger"
        title={`Delete ${pendingDelete?.name ?? 'plan'}?`}
        description="Deletion fails if vouchers reference this plan — deactivate it instead to stop new sales while keeping history."
        confirmLabel="Delete plan"
        onConfirm={async () => {
          if (!pendingDelete) return;
          await remove.mutateAsync(pendingDelete.id);
          toast.success('Plan deleted');
        }}
      />
      {!canManage && canGenerate && (
        <p className="mt-4 text-xs text-ink-500">
          Need a new plan? Ask a manager — you can still{' '}
          <Link to="/vouchers/generate" className="text-brand-600 hover:underline">
            generate vouchers
          </Link>{' '}
          from active plans.
        </p>
      )}
    </>
  );
}
