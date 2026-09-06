import type { ReactNode } from 'react';
import { FilterX } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utilities/cn';

/** Layout wrapper: search on the left, filters wrap, actions on the right, "Clear" when active. */
export function FilterBar({
  search,
  filters,
  actions,
  activeCount = 0,
  onClear,
  className,
}: {
  search?: ReactNode;
  filters?: ReactNode;
  actions?: ReactNode;
  activeCount?: number;
  onClear?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between',
        className,
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        {search && <div className="w-full sm:max-w-xs">{search}</div>}
        {filters && <div className="flex flex-wrap items-center gap-2">{filters}</div>}
        {activeCount > 0 && onClear && (
          <Button variant="link" size="sm" onClick={onClear} leadingIcon={<FilterX />}>
            Clear {activeCount > 1 ? `${activeCount} filters` : 'filter'}
          </Button>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
