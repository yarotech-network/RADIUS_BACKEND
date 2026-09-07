import { type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

/**
 * Radiogroup-styled segmented control with the WAI-ARIA radio keyboard pattern
 * (phase 10): arrows move focus and select; only the checked option is a tab
 * stop.
 */
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
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const radios = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]:not([disabled])'),
    );
    if (radios.length === 0) return;
    const current = radios.findIndex((radio) => radio === document.activeElement);
    let next: number;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown')
      next = (current + 1) % radios.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp')
      next = (current - 1 + radios.length) % radios.length;
    else return;
    event.preventDefault();
    radios[next]?.focus();
    radios[next]?.click();
  }

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
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
            tabIndex={active ? 0 : -1}
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
