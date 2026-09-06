import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  leadingIcon?: ReactNode;
  trailingSlot?: ReactNode;
  prefix?: string;
}

export const inputClasses =
  'h-10 w-full rounded-control border border-border bg-surface px-3 text-sm text-ink-900 placeholder:text-ink-400 transition-colors hover:border-border-strong focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/20 disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-500 read-only:bg-surface-muted aria-[invalid=true]:border-danger-600 aria-[invalid=true]:focus:ring-danger-600/20';

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, leadingIcon, trailingSlot, prefix, ...rest },
  ref,
) {
  if (!leadingIcon && !trailingSlot && !prefix) {
    return (
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(inputClasses, className)}
        {...rest}
      />
    );
  }
  return (
    <div className="relative flex w-full items-stretch">
      {prefix && (
        <span className="inline-flex items-center rounded-l-[var(--radius-control)] border border-r-0 border-border bg-surface-muted px-3 text-sm text-ink-500">
          {prefix}
        </span>
      )}
      {leadingIcon && (
        <span className="pointer-events-none absolute inset-y-0 left-3 inline-flex items-center text-ink-400 [&>svg]:size-4">
          {leadingIcon}
        </span>
      )}
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          inputClasses,
          leadingIcon && 'pl-9',
          trailingSlot && 'pr-10',
          prefix && 'rounded-l-none',
          className,
        )}
        {...rest}
      />
      {trailingSlot && (
        <span className="absolute inset-y-0 right-1 inline-flex items-center">{trailingSlot}</span>
      )}
    </div>
  );
});
