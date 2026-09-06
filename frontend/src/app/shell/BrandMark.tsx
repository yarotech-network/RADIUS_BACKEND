import { env } from '@/app/config/env';
import { cn } from '@/lib/utilities/cn';

export function BrandMark({
  size = 'md',
  inverse = false,
  hideText = false,
  className,
}: {
  size?: 'sm' | 'md' | 'lg';
  inverse?: boolean;
  hideText?: boolean;
  className?: string;
}) {
  const box =
    size === 'lg'
      ? 'size-11 rounded-xl'
      : size === 'sm'
        ? 'size-7 rounded-md'
        : 'size-8 rounded-lg';
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center',
          box,
          inverse ? 'bg-white/10' : 'bg-brand-950',
        )}
        aria-hidden
      >
        <svg
          viewBox="0 0 32 32"
          className={size === 'lg' ? 'size-8' : size === 'sm' ? 'size-5' : 'size-6'}
        >
          <path
            d="M8 20a8 8 0 0 1 16 0"
            fill="none"
            stroke="#60A5FA"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d="M11.5 21.5a4.5 4.5 0 0 1 9 0"
            fill="none"
            stroke="#fff"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <circle cx="16" cy="23.5" r="1.8" fill="#fff" />
        </svg>
      </span>
      {!hideText && (
        <span
          className={cn(
            'font-semibold tracking-tight',
            size === 'lg' ? 'text-xl' : 'text-[15px]',
            inverse ? 'text-white' : 'text-brand-950',
          )}
        >
          {env.appName}
        </span>
      )}
    </span>
  );
}
