import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { ChevronDown, ChevronRight, ScrollText } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import { Badge, Button, Input, Select } from '@/components/ui';
import { EmptyState } from '@/components/feedback';
import {
  DataTable,
  FilterBar,
  Pagination,
  SearchInput,
  useListParams,
  type Column,
} from '@/components/data';
import { usePrincipal } from '@/app/auth/useAuth';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import type { AuditEvent, AuditListParams } from '@/types/api';
import { useAuditEvents } from '../queries';
import {
  AUDIT_ACTION_GROUPS,
  actionLabel,
  actionTone,
  parseResource,
  resourceLink,
} from '../auditVocabulary';

const FILTERS = ['action', 'actor'] as const;

export default function AuditPage() {
  const principal = usePrincipal();
  const list = useListParams(FILTERS, { ordering: '-created_at' });
  const debouncedSearch = useDebouncedValue(list.state.search);
  const debouncedActor = useDebouncedValue(list.state.filters.actor ?? '');
  const [expanded, setExpanded] = useState<string | null>(null);
  const query = useAuditEvents(
    useMemo(() => {
      const p: AuditListParams = { page: list.state.page, page_size: list.state.page_size };
      if (debouncedSearch) p.search = debouncedSearch;
      if (list.state.ordering) p.ordering = list.state.ordering;
      if (list.state.filters.action) p.action = list.state.filters.action;
      const actor = Number(debouncedActor);
      if (debouncedActor && Number.isInteger(actor) && actor > 0) p.actor = actor;
      return p;
    }, [list.state, debouncedSearch, debouncedActor]),
  );

  const columns: Column<AuditEvent>[] = [
    {
      key: 'when',
      header: 'When',
      sortField: 'created_at',
      cell: (e) => (
        <time
          dateTime={e.created_at}
          title={formatDateTime(e.created_at)}
          className="whitespace-nowrap text-ink-600"
        >
          {formatRelative(e.created_at)}
        </time>
      ),
    },
    {
      key: 'action',
      header: 'Action',
      primary: true,
      cell: (e) => (
        <div className="min-w-0">
          <Badge tone={actionTone(e.action)} size="sm">
            {actionLabel(e.action)}
          </Badge>
          <div className="mt-1 truncate font-mono text-xs text-ink-500">{e.action}</div>
        </div>
      ),
    },
    {
      key: 'resource',
      header: 'Resource',
      hideBelow: 'md',
      cell: (e) => <ResourceCell resource={e.resource} />,
    },
    {
      key: 'actor',
      header: 'By',
      hideBelow: 'lg',
      cell: (e) =>
        e.actor === null ? (
          <span className="text-ink-400">System</span>
        ) : e.actor === principal?.user.id ? (
          <span className="font-medium text-ink-900">You</span>
        ) : (
          <span className="text-ink-700">User #{e.actor}</span>
        ),
    },
    {
      key: 'details',
      header: <span className="sr-only">Details</span>,
      align: 'right',
      cell: (e) => {
        const has = Object.keys(e.details ?? {}).length > 0;
        const open = expanded === e.id;
        return has ? (
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={open}
            aria-controls={`audit-${e.id}`}
            onClick={(ev) => {
              ev.stopPropagation();
              setExpanded(open ? null : e.id);
            }}
            leadingIcon={
              open ? (
                <ChevronDown className="h-4 w-4" aria-hidden />
              ) : (
                <ChevronRight className="h-4 w-4" aria-hidden />
              )
            }
          >
            Details
          </Button>
        ) : null;
      },
    },
  ];

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Who did what in your workspace — voucher batches, router changes, team updates and payment recovery."
      />
      <FilterBar
        search={
          <SearchInput
            value={list.state.search}
            onChange={list.setSearch}
            placeholder="Search resource, e.g. voucher:56"
            ariaLabel="Search audit resources"
          />
        }
        filters={
          <>
            <Select
              aria-label="Action"
              size="sm"
              value={list.state.filters.action ?? ''}
              onChange={(e) => list.setFilter('action', e.target.value || undefined)}
            >
              <option value="">All actions</option>
              {AUDIT_ACTION_GROUPS.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.actions.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
            <Input
              aria-label="Actor user ID"
              type="number"
              min={1}
              inputMode="numeric"
              className="h-8 w-32 text-xs"
              placeholder="Actor user ID"
              value={list.state.filters.actor ?? ''}
              onChange={(e) => list.setFilter('actor', e.target.value || undefined)}
            />
            {principal && (
              <Button
                size="sm"
                variant={
                  list.state.filters.actor === String(principal.user.id) ? 'primary' : 'secondary'
                }
                onClick={() =>
                  list.setFilter(
                    'actor',
                    list.state.filters.actor === String(principal.user.id)
                      ? undefined
                      : String(principal.user.id),
                  )
                }
              >
                Mine
              </Button>
            )}
          </>
        }
        activeCount={list.activeFilterCount}
        onClear={list.clearFilters}
      />
      <DataTable
        caption="Audit events"
        columns={columns}
        rows={query.data?.results}
        rowKey={(e) => e.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        ordering={list.state.ordering}
        onOrderingChange={list.setOrdering}
        onRowClick={(e) => setExpanded(expanded === e.id ? null : e.id)}
        renderExpanded={(e) => (expanded === e.id ? <DetailsPanel event={e} /> : null)}
        empty={
          list.activeFilterCount > 0 || debouncedSearch ? (
            <EmptyState
              icon={<ScrollText className="h-6 w-6" aria-hidden />}
              title="No matching events"
              description="Try a different action, actor or resource."
              action={
                <Button variant="secondary" onClick={list.clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<ScrollText className="h-6 w-6" aria-hidden />}
              title="Nothing recorded yet"
              description="Actions taken by your team will appear here."
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
          itemLabel="events"
        />
      )}
    </>
  );
}

function ResourceCell({ resource }: { resource: string }) {
  const parsed = parseResource(resource);
  const to = resourceLink(resource);
  const label = parsed ? `${parsed.model} #${parsed.pk}` : resource;
  return to ? (
    <Link
      to={to}
      onClick={(e) => e.stopPropagation()}
      className="font-mono text-[13px] text-brand-700 hover:underline"
    >
      {label}
    </Link>
  ) : (
    <code className="font-mono text-[13px] text-ink-700">{label}</code>
  );
}

function DetailsPanel({ event }: { event: AuditEvent }) {
  const entries = Object.entries(event.details ?? {});
  return (
    <div
      id={`audit-${event.id}`}
      className="grid gap-3 border-t border-border bg-surface-muted px-4 py-3 text-sm sm:grid-cols-[auto_1fr]"
    >
      <span className="text-ink-500">Resource</span>
      <code className="text-ink-800 font-mono text-[13px]">{event.resource}</code>
      <span className="text-ink-500">Event ID</span>
      <code className="text-ink-800 font-mono text-[13px]">{event.id}</code>
      {entries.length > 0 && (
        <>
          <span className="text-ink-500">Details</span>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            {entries.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="font-mono text-xs text-ink-500">{k}</dt>
                <dd className="text-ink-800 font-mono text-xs break-all">
                  {typeof v === 'string' ? v : JSON.stringify(v)}
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </div>
  );
}
