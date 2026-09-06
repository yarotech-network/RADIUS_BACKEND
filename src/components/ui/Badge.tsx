import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utilities/cn';

export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'brand' | 'outline';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  dot?: boolean;
  icon?: ReactNode;
  size?: 'sm' | 'md';
}

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-slate-100 text-ink-700',
  info: 'bg-info-100 text-info-700',
  success: 'bg-success-100 text-success-700',
  warning: 'bg-warning-100 text-warning-700',
  danger: 'bg-danger-100 text-danger-700',
  brand: 'bg-brand-950 text-white',
  outline: 'bg-transparent text-ink-600 border border-border',
};

const DOTS: Record<BadgeTone, string> = {
  neutral: 'bg-ink-400',
  info: 'bg-info-700',
  success: 'bg-success-600',
  warning: 'bg-warning-600',
  danger: 'bg-danger-600',
  brand: 'bg-brand-300',
  outline: 'bg-ink-400',
};

export function Badge({
  tone = 'neutral',
  dot,
  icon,
  size = 'md',
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-medium whitespace-nowrap',
        size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-0.5 text-xs',
        TONES[tone],
        className,
      )}
      {...rest}
    >
      {dot && <span aria-hidden className={cn('size-1.5 rounded-full', DOTS[tone])} />}
      {icon && <span className="inline-flex [&>svg]:size-3">{icon}</span>}
      {children}
    </span>
  );
}
