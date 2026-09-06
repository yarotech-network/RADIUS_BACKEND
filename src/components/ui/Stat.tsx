import type { ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';
import { Skeleton } from './Skeleton';

export function Stat({
  label,
  value,
  hint,
  icon,
  loading,
  className,
  tone = 'default',
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  loading?: boolean;
  className?: string;
  tone?: 'default' | 'brand' | 'warning';
}) {
  return (
    <div
      className={cn(
        'rounded-card border p-4',
        tone === 'brand' ? 'border-brand-950 bg-brand-950 text-white' : 'border-border bg-surface',
        tone === 'warning' && 'border-warning-600/40 bg-warning-50',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p
          className={cn(
            'text-xs font-medium tracking-wide uppercase',
            tone === 'brand' ? 'text-brand-200' : 'text-ink-500',
          )}
        >
          {label}
        </p>
        {icon && (
          <span
            className={cn(
              'inline-flex [&>svg]:size-4',
              tone === 'brand' ? 'text-brand-300' : 'text-ink-400',
            )}
          >
            {icon}
          </span>
        )}
      </div>
      {loading ? (
        <Skeleton className={cn('mt-2 h-7 w-24', tone === 'brand' && 'bg-white/20')} />
      ) : (
        <p
          className={cn(
            'mt-1.5 text-2xl font-semibold tabular',
            tone === 'brand' ? 'text-white' : 'text-brand-950',
          )}
        >
          {value}
        </p>
      )}
      {hint && (
        <p className={cn('mt-1 text-xs', tone === 'brand' ? 'text-brand-200' : 'text-ink-500')}>
          {hint}
        </p>
      )}
    </div>
  );
}
