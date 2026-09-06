import { cn } from '@/lib/utilities/cn';
import type { ButtonProps, ButtonSize, ButtonVariant } from './Button';

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 disabled:bg-brand-300 border border-transparent',
  secondary:
    'bg-surface text-ink-900 border border-border hover:bg-surface-muted hover:border-border-strong active:bg-slate-100 disabled:text-ink-400',
  ghost:
    'bg-transparent text-ink-700 hover:bg-slate-100 active:bg-slate-200 border border-transparent disabled:text-ink-400',
  danger:
    'bg-danger-600 text-white hover:bg-danger-700 border border-transparent disabled:bg-danger-600/50',
  link: 'bg-transparent text-brand-600 hover:text-brand-700 hover:underline underline-offset-4 border-0 px-0 h-auto',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-control',
  md: 'h-10 px-4 text-sm gap-2 rounded-control',
  lg: 'h-11 px-5 text-sm gap-2 rounded-control',
  icon: 'h-9 w-9 p-0 rounded-control',
};

export function buttonClasses({
  variant = 'primary',
  size = 'md',
  block = false,
  className,
}: Pick<ButtonProps, 'variant' | 'size' | 'block' | 'className'>) {
  return cn(
    'inline-flex items-center justify-center font-medium whitespace-nowrap transition-colors select-none',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600',
    VARIANTS[variant],
    SIZES[size],
    block && 'w-full',
    className,
  );
}
