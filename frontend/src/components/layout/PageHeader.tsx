import type { ReactNode } from 'react';
import { ChevronLeft } from 'lucide-react';
import { Link } from 'react-router';
import { cn } from '@/lib/utilities/cn';

export interface Crumb {
  label: ReactNode;
  to?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  crumbs,
  backTo,
  meta,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  crumbs?: Crumb[];
  backTo?: string;
  /** Badges / status shown next to the title. */
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn('mb-5 flex flex-col gap-3', className)}>
      {(crumbs || backTo) && (
        <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-ink-500">
          {backTo && (
            <Link
              to={backTo}
              className="-ml-1 inline-flex items-center gap-0.5 rounded px-1 py-0.5 hover:text-ink-900"
            >
              <ChevronLeft className="size-3.5" aria-hidden /> Back
            </Link>
          )}
          {crumbs?.map((crumb, index) => (
            <span key={index} className="inline-flex items-center gap-1">
              {index > 0 && <span aria-hidden>/</span>}
              {crumb.to ? (
                <Link to={crumb.to} className="rounded hover:text-ink-900">
                  {crumb.label}
                </Link>
              ) : (
                <span className="text-ink-700" aria-current="page">
                  {crumb.label}
                </span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-xl font-semibold text-brand-950 sm:text-2xl">{title}</h1>
            {meta}
          </div>
          {description && <p className="mt-1 max-w-2xl text-sm text-ink-500">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
