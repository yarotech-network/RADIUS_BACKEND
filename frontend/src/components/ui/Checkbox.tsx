import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: ReactNode;
  description?: ReactNode;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { className, label, description, id, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <label
      htmlFor={inputId}
      className={cn('flex cursor-pointer items-start gap-3 text-sm', className)}
    >
      <input
        ref={ref}
        id={inputId}
        type="checkbox"
        className="mt-0.5 size-4 shrink-0 rounded border-border accent-brand-600"
        {...rest}
      />
      {(label || description) && (
        <span className="flex flex-col">
          {label && <span className="font-medium text-ink-900">{label}</span>}
          {description && <span className="text-xs text-ink-500">{description}</span>}
        </span>
      )}
    </label>
  );
});
