import { cn } from '@/lib/utilities/cn';

export function Avatar({
  initials,
  className,
  size = 'md',
}: {
  initials: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-800',
        size === 'sm' && 'size-7 text-[11px]',
        size === 'md' && 'size-9 text-xs',
        size === 'lg' && 'size-12 text-sm',
        className,
      )}
    >
      {initials}
    </span>
  );
}
