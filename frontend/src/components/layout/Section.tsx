import type { ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('space-y-3', className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            {title && <h2 className="text-base font-semibold text-brand-950">{title}</h2>}
            {description && <p className="text-sm text-ink-500">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
