import type { ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

/** Two-column settings block: explanation on the left, form/content on the right (stacks on mobile). */
export function SettingsCard({
  id,
  title,
  description,
  children,
  footer,
  className,
}: {
  id?: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={cn(
        'grid gap-4 border-b border-border py-6 first:pt-0 last:border-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-10',
        className,
      )}
    >
      <div>
        <h2 id={headingId} className="text-base font-semibold text-brand-950">
          {title}
        </h2>
        {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
      </div>
      <div className="rounded-card border border-border bg-surface">
        <div className="p-5">{children}</div>
        {footer && (
          <div className="flex flex-col-reverse gap-2 border-t border-border bg-surface-muted px-5 py-3 sm:flex-row sm:justify-end">
            {footer}
          </div>
        )}
      </div>
    </section>
  );
}
