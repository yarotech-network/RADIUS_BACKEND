import { useId, type ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

/** CSS-only tooltip (hover + focus). Fine for short hints; do not put interactive content inside. */
export function Tooltip({
  content,
  children,
  side = 'top',
  className,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: 'top' | 'bottom';
  className?: string;
}) {
  const id = useId();
  return (
    <span className={cn('group/tip relative inline-flex', className)} aria-describedby={id}>
      {children}
      <span
        role="tooltip"
        id={id}
        className={cn(
          'pointer-events-none absolute left-1/2 z-40 w-max max-w-56 -translate-x-1/2 rounded-md bg-brand-950 px-2 py-1 text-xs text-white opacity-0 transition-opacity',
          'group-focus-within/tip:opacity-100 group-hover/tip:opacity-100',
          side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5',
        )}
      >
        {content}
      </span>
    </span>
  );
}
