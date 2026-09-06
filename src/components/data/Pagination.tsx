import { ChevronLeft, ChevronRight } from 'lucide-react';
import { PAGE_SIZE_OPTIONS } from '@/app/config/constants';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { cn } from '@/lib/utilities/cn';

export interface PaginationProps {
  count: number;
  page: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  className?: string;
  itemLabel?: string;
}

export function Pagination({
  count,
  page,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  className,
  itemLabel = 'records',
}: PaginationProps) {
  if (count === 0) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, count);
  return (
    <nav
      aria-label="Pagination"
      className={cn('flex flex-wrap items-center justify-between gap-3 text-sm', className)}
    >
      <p className="text-ink-500 tabular">
        <span className="font-medium text-ink-900">
          {start.toLocaleString()}–{end.toLocaleString()}
        </span>{' '}
        of {count.toLocaleString()} {itemLabel}
      </p>
      <div className="flex items-center gap-2">
        {onPageSizeChange && (
          <label className="hidden items-center gap-2 text-xs text-ink-500 sm:flex">
            Rows
            <Select
              size="sm"
              className="w-20"
              aria-label="Rows per page"
              value={String(pageSize)}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              options={PAGE_SIZE_OPTIONS.map((n) => ({ value: String(n), label: String(n) }))}
            />
          </label>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
          leadingIcon={<ChevronLeft />}
        >
          <span className="hidden sm:inline">Prev</span>
        </Button>
        <span className="px-1 text-xs text-ink-600 tabular">
          Page {page} / {Math.max(totalPages, 1)}
        </span>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Next page"
          trailingIcon={<ChevronRight />}
        >
          <span className="hidden sm:inline">Next</span>
        </Button>
      </div>
    </nav>
  );
}
