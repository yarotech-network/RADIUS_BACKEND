import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export interface FormFieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: string | undefined;
  required?: boolean;
  optionalLabel?: boolean;
  className?: string;
  children: ReactElement<{
    id?: string;
    'aria-describedby'?: string;
    invalid?: boolean;
    'aria-invalid'?: boolean;
  }>;
  /** Render the control inline with the label (checkbox / switch layouts). */
  inline?: boolean;
}

/**
 * Wires label, hint and error to a single control via aria attributes.
 */
export function FormField({
  label,
  hint,
  error,
  required,
  optionalLabel,
  className,
  children,
  inline,
}: FormFieldProps) {
  const id = useId();
  const controlId = children.props.id ?? `${id}-control`;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;

  const control = isValidElement(children)
    ? cloneElement(children, {
        id: controlId,
        ...(describedBy ? { 'aria-describedby': describedBy } : {}),
        ...(error ? { invalid: true } : {}),
      })
    : children;

  return (
    <div
      className={cn(
        'flex flex-col gap-1.5',
        inline && 'flex-row items-center justify-between gap-4',
        className,
      )}
    >
      {label && (
        <label htmlFor={controlId} className="text-sm font-medium text-ink-700">
          {label}
          {required && (
            <span className="ml-0.5 text-danger-600" aria-hidden>
              *
            </span>
          )}
          {optionalLabel && !required && (
            <span className="ml-1 text-xs font-normal text-ink-400">(optional)</span>
          )}
        </label>
      )}
      {control}
      {hint && !error && (
        <p id={hintId} className="text-xs text-ink-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs font-medium text-danger-600">
          {error}
        </p>
      )}
    </div>
  );
}
