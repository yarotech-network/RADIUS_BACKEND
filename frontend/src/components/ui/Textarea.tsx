import { forwardRef, type TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/utilities/cn';
import { inputClasses } from './Input';

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, rows = 3, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(inputClasses, 'h-auto min-h-20 resize-y py-2', className)}
      {...rest}
    />
  );
});
