import type { ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className,
  ariaLabel,
  size = 'md',
}: {
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  ariaLabel?: string;
  size?: 'sm' | 'md';
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn('inline-flex rounded-control bg-slate-100 p-0.5', className)}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'rounded-[calc(var(--radius-control)-2px)] font-medium whitespace-nowrap transition-colors',
              size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-sm',
              active
                ? 'bg-surface text-brand-800 shadow-subtle'
                : 'text-ink-500 hover:text-ink-900',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
