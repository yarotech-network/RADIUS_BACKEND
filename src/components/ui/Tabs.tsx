import { type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  count?: number;
  disabled?: boolean;
}

/**
 * Tabs with the WAI-ARIA tabs keyboard pattern (phase 10): ArrowLeft/ArrowRight
 * (and Home/End) move focus and activate the tab; only the selected tab is a
 * tab stop.
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className,
  ariaLabel,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  ariaLabel?: string;
}) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const tabs = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])'),
    );
    if (tabs.length === 0) return;
    const current = tabs.findIndex((tab) => tab === document.activeElement);
    let next: number;
    if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    const target = tabs[next];
    target?.focus();
    target?.click();
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={cn('no-scrollbar flex gap-1 overflow-x-auto border-b border-border', className)}
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onChange(item.value)}
            className={cn(
              '-mb-px inline-flex h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-medium whitespace-nowrap transition-colors',
              active
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-ink-500 hover:text-ink-900',
              item.disabled && 'cursor-not-allowed opacity-50',
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[11px] tabular',
                  active ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-ink-500',
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
