import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { ChevronDown, ChevronRight, ScrollText } from 'lucide-react';
import type { UseQueryResult } from '@tanstack/react-query';
import { Badge, Button, Input, Select } from '@/components/ui';
import { EmptyState } from '@/components/feedback';
import { DataTable, FilterBar, Pagination, SearchInput, type Column } from '@/components/data';
import type { useListParams } from '@/components/data';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import type { AuditEvent, Paginated } from '@/types/api';
import { AUDIT_ACTION_GROUPS, actionLabel, actionTone, parseResource } from '../auditVocabulary';

export interface AuditLogViewProps {
  query: UseQueryResult<Paginated<AuditEvent>>;
  list: ReturnType<typeof useListParams>;
  debouncedSearch: string;
  /** Highlights the signed-in user's rows as "You" and enables the "Mine" shortcut. */
  currentUserId?: number | undefined;
  /** Deep-link for a resource key, or null when there is no page for it in this surface. */
  linkFor: (resource: string) => string | null;
  /** Extra filter controls rendered before the action select (e.g. a tenant picker). */
  leadingFilters?: ReactNode;
  /** Extra columns inserted after the action column (e.g. tenant). */
  extraColumns?: Column<AuditEvent>[];
  emptyDescription: string;
}

/** Shared audit table: filters, expandable details, pagination. Pages own the query. */
export function AuditLogView({
  query,
  list,
  debouncedSearch,
  currentUserId,
  linkFor,
  leadingFilters,
  extraColumns = [],
  emptyDescription,
}: AuditLogViewProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

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
    ...extraColumns,
    {
      key: 'resource',
      header: 'Resource',
      hideBelow: 'md',
      cell: (e) => <ResourceCell resource={e.resource} to={linkFor(e.resource)} />,
    },
    {
      key: 'actor',
      header: 'By',
      hideBelow: 'lg',
      cell: (e) =>
        e.actor === null ? (
          <span className="text-ink-400">System</span>
        ) : e.actor === currentUserId ? (
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
            {leadingFilters}
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
            {currentUserId !== undefined && (
              <Button
                size="sm"
                variant={
                  list.state.filters.actor === String(currentUserId) ? 'primary' : 'secondary'
                }
                onClick={() =>
                  list.setFilter(
                    'actor',
                    list.state.filters.actor === String(currentUserId)
                      ? undefined
                      : String(currentUserId),
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
              description={emptyDescription}
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

function ResourceCell({ resource, to }: { resource: string; to: string | null }) {
  const parsed = parseResource(resource);
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
