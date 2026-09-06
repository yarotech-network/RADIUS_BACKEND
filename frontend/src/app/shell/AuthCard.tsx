import type { ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export function AuthCard({
  title,
  description,
  children,
  footer,
  className,
  wide,
}: {
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  wide?: boolean;
}) {
  return (
    <div
      className={cn(
        'mx-auto flex w-full flex-1 flex-col justify-center py-6',
        wide ? 'max-w-lg' : 'max-w-sm',
        className,
      )}
    >
      <div className="rounded-card border border-border bg-surface p-6 sm:p-8">
        <h1 className="text-xl font-semibold text-brand-950">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
        <div className="mt-6">{children}</div>
      </div>
      {footer && <div className="mt-4 text-center text-sm text-ink-500">{footer}</div>}
    </div>
  );
}
