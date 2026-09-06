import type { HTMLAttributes, ReactNode } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { cn } from '@/lib/utilities/cn';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';

export interface AlertProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  tone?: AlertTone;
  title?: ReactNode;
  actions?: ReactNode;
  /** Renders a close button; the parent owns visibility. */
  onDismiss?: (() => void) | undefined;
}

const STYLES: Record<AlertTone, { box: string; icon: typeof Info }> = {
  info: { box: 'bg-info-50 border-info-100 text-info-700', icon: Info },
  success: { box: 'bg-success-50 border-success-100 text-success-700', icon: CheckCircle2 },
  warning: { box: 'bg-warning-50 border-warning-100 text-warning-700', icon: AlertTriangle },
  danger: { box: 'bg-danger-50 border-danger-100 text-danger-700', icon: AlertCircle },
};

export function Alert({
  tone = 'info',
  title,
  actions,
  onDismiss,
  className,
  children,
  ...rest
}: AlertProps) {
  const { box, icon: Icon } = STYLES[tone];
  return (
    <div
      role={tone === 'danger' || tone === 'warning' ? 'alert' : 'status'}
      className={cn('flex gap-3 rounded-control border px-3.5 py-3 text-sm', box, className)}
      {...rest}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && (
          <div className={cn(title && 'mt-0.5', 'text-[13px] leading-relaxed')}>{children}</div>
        )}
        {actions && <div className="mt-2 flex flex-wrap gap-2">{actions}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-m-1 h-fit rounded p-1 opacity-70 hover:opacity-100"
        >
          <X className="size-4" aria-hidden />
        </button>
      )}
    </div>
  );
}
