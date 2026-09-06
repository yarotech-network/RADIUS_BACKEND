import type { ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export interface DescriptionItem {
  label: ReactNode;
  value: ReactNode;
  mono?: boolean;
  span?: 1 | 2;
}

export function DescriptionList({
  items,
  columns = 2,
  className,
}: {
  items: DescriptionItem[];
  columns?: 1 | 2 | 3;
  className?: string;
}) {
  return (
    <dl
      className={cn(
        'grid gap-x-6 gap-y-4',
        columns === 1 && 'grid-cols-1',
        columns === 2 && 'grid-cols-1 sm:grid-cols-2',
        columns === 3 && 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
        className,
      )}
    >
      {items.map((item, index) => (
        <div key={index} className={cn('min-w-0', item.span === 2 && 'sm:col-span-2')}>
          <dt className="text-xs font-medium tracking-wide text-ink-500 uppercase">{item.label}</dt>
          <dd
            className={cn(
              'mt-1 text-sm break-words text-ink-900',
              item.mono && 'font-mono text-[13px]',
            )}
          >
            {item.value === null || item.value === undefined || item.value === '' ? (
              <span className="text-ink-400">—</span>
            ) : (
              item.value
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
