import type { Key, ReactNode } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/utilities/cn';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/feedback/EmptyState';
import { ErrorState } from '@/components/feedback/ErrorState';

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Backend `ordering` field name — only set for fields the API actually supports. */
  sortField?: string;
  align?: 'left' | 'right' | 'center';
  width?: string;
  /** Hide below this breakpoint (the mobile card layout shows it anyway). */
  hideBelow?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  /** Show this column as the title line in the mobile card layout. */
  primary?: boolean;
  /** Omit from the mobile card layout (e.g. the actions column, rendered separately). */
  mobileHidden?: boolean;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => Key;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: ReactNode;
  ordering?: string | undefined;
  onOrderingChange?: (ordering: string | undefined) => void;
  onRowClick?: (row: T) => void;
  rowActions?: (row: T) => ReactNode;
  skeletonRows?: number;
  /** Below `md` render each row as a card instead of a horizontally scrolling table. */
  mobileCards?: boolean;
  caption?: string;
  className?: string;
  dense?: boolean;
  /** Whether this is a background refresh (keeps rows visible, dims them). */
  refreshing?: boolean;
}

const HIDE: Record<NonNullable<Column<unknown>['hideBelow']>, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
  xl: 'hidden xl:table-cell',
};

function nextOrdering(current: string | undefined, field: string): string | undefined {
  if (current === field) return `-${field}`;
  if (current === `-${field}`) return undefined;
  return field;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  empty,
  ordering,
  onOrderingChange,
  onRowClick,
  rowActions,
  skeletonRows = 6,
  mobileCards = true,
  caption,
  className,
  dense,
  refreshing,
}: DataTableProps<T>) {
  const showSkeleton = loading && !rows;
  const showError = Boolean(error) && !rows;
  const showEmpty = !loading && !error && rows && rows.length === 0;
  const alignClass = (a: Column<T>['align']) =>
    a === 'right' ? 'text-right' : a === 'center' ? 'text-center' : 'text-left';
  const cellPad = dense ? 'px-3 py-2' : 'px-4 py-3';

  const table = (
    <table className="w-full border-collapse text-sm">
      {caption && <caption className="sr-only">{caption}</caption>}
      <thead>
        <tr className="border-b border-border bg-surface-muted">
          {columns.map((col) => {
            const sortable = Boolean(col.sortField && onOrderingChange);
            const active =
              col.sortField && (ordering === col.sortField || ordering === `-${col.sortField}`);
            const desc = ordering === `-${col.sortField}`;
            return (
              <th
                key={col.key}
                scope="col"
                style={col.width ? { width: col.width } : undefined}
                aria-sort={active ? (desc ? 'descending' : 'ascending') : undefined}
                className={cn(
                  'text-xs font-semibold tracking-wide whitespace-nowrap text-ink-500 uppercase',
                  cellPad,
                  alignClass(col.align),
                  col.hideBelow && HIDE[col.hideBelow],
                  col.className,
                )}
              >
                {sortable ? (
                  <button
                    type="button"
                    onClick={() => onOrderingChange?.(nextOrdering(ordering, col.sortField!))}
                    className={cn(
                      'inline-flex items-center gap-1 rounded hover:text-ink-900 focus-visible:outline-brand-600',
                      active && 'text-brand-700',
                    )}
                  >
                    {col.header}
                    {active ? (
                      desc ? (
                        <ArrowDown className="size-3.5" aria-hidden />
                      ) : (
                        <ArrowUp className="size-3.5" aria-hidden />
                      )
                    ) : (
                      <ArrowUpDown className="size-3.5 opacity-50" aria-hidden />
                    )}
                  </button>
                ) : (
                  col.header
                )}
              </th>
            );
          })}
          {rowActions && (
            <th scope="col" className={cn(cellPad, 'w-12')}>
              <span className="sr-only">Actions</span>
            </th>
          )}
        </tr>
      </thead>
      <tbody className={cn(refreshing && 'opacity-60 transition-opacity')}>
        {showSkeleton &&
          Array.from({ length: skeletonRows }).map((_, r) => (
            <tr key={r} className="border-b border-border last:border-0">
              {columns.map((col) => (
                <td key={col.key} className={cn(cellPad, col.hideBelow && HIDE[col.hideBelow])}>
                  <Skeleton className="h-3.5 w-full max-w-40" />
                </td>
              ))}
              {rowActions && (
                <td className={cellPad}>
                  <Skeleton className="h-3.5 w-6" />
                </td>
              )}
            </tr>
          ))}
        {!showSkeleton &&
          rows?.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn(
                'border-b border-border last:border-0',
                onRowClick && 'cursor-pointer transition-colors hover:bg-brand-50/60',
              )}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn(
                    cellPad,
                    'align-middle text-ink-900',
                    alignClass(col.align),
                    col.hideBelow && HIDE[col.hideBelow],
                    col.className,
                  )}
                >
                  {col.cell(row)}
                </td>
              ))}
              {rowActions && (
                <td
                  className={cn(cellPad, 'text-right align-middle')}
                  onClick={(e) => e.stopPropagation()}
                >
                  {rowActions(row)}
                </td>
              )}
            </tr>
          ))}
      </tbody>
    </table>
  );

  const cards = (
    <ul className="divide-y divide-border">
      {showSkeleton &&
        Array.from({ length: 4 }).map((_, i) => (
          <li key={i} className="space-y-2 p-4">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
          </li>
        ))}
      {!showSkeleton &&
        rows?.map((row) => {
          const primary = columns.find((c) => c.primary) ?? columns[0];
          const rest = columns.filter((c) => c !== primary && !c.mobileHidden);
          return (
            <li
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn('p-4', onRowClick && 'cursor-pointer active:bg-brand-50/60')}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1 text-sm font-medium text-ink-900">
                  {primary?.cell(row)}
                </div>
                {rowActions && (
                  <div onClick={(e) => e.stopPropagation()} className="-mt-1 -mr-2 shrink-0">
                    {rowActions(row)}
                  </div>
                )}
              </div>
              {rest.length > 0 && (
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                  {rest.map((col) => (
                    <div key={col.key} className="min-w-0">
                      <dt className="truncate text-ink-400">{col.header}</dt>
                      <dd className="truncate text-ink-700">{col.cell(row)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          );
        })}
    </ul>
  );

  return (
    <div className={cn('overflow-hidden rounded-card border border-border bg-surface', className)}>
      {showError ? (
        <ErrorState error={error} onRetry={onRetry} compact />
      ) : showEmpty ? (
        (empty ?? <EmptyState title="Nothing here yet" compact />)
      ) : (
        <>
          <div className={cn('overflow-x-auto', mobileCards && 'hidden md:block')}>{table}</div>
          {mobileCards && <div className="md:hidden">{cards}</div>}
        </>
      )}
    </div>
  );
}
