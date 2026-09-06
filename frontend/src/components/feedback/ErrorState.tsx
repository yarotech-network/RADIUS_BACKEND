import { AlertTriangle, Lock, RefreshCw, SearchX, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { errorMessage, isApiError } from '@/services/api/errors';
import { cn } from '@/lib/utilities/cn';

export function ErrorState({
  error,
  onRetry,
  title,
  className,
  compact,
}: {
  error: unknown;
  onRetry?: (() => void) | undefined;
  title?: string;
  className?: string;
  compact?: boolean;
}) {
  const kind = isApiError(error) ? error.kind : 'unknown';
  const Icon =
    kind === 'network'
      ? WifiOff
      : kind === 'forbidden' || kind === 'unauthorized'
        ? Lock
        : kind === 'not_found'
          ? SearchX
          : AlertTriangle;
  const heading =
    title ??
    (kind === 'network'
      ? 'Connection problem'
      : kind === 'forbidden'
        ? 'Access restricted'
        : kind === 'not_found'
          ? 'Not found'
          : kind === 'throttled'
            ? 'Slow down'
            : kind === 'unavailable'
              ? 'Service unavailable'
              : 'Something went wrong');
  const retryable = kind !== 'forbidden' && kind !== 'not_found' && kind !== 'validation';
  const retryAfter = isApiError(error) ? error.retryAfterSeconds : null;
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'px-4 py-8' : 'px-6 py-14',
        className,
      )}
    >
      <span className="mb-3 inline-flex size-11 items-center justify-center rounded-full bg-danger-50 text-danger-600">
        <Icon className="size-5" aria-hidden />
      </span>
      <h3 className="text-sm font-semibold text-brand-950">{heading}</h3>
      <p className="mt-1 max-w-sm text-sm text-ink-500">
        {errorMessage(error)}
        {retryAfter ? ` Try again in ${retryAfter}s.` : ''}
      </p>
      {onRetry && retryable && (
        <Button
          variant="secondary"
          size="sm"
          className="mt-4"
          onClick={onRetry}
          leadingIcon={<RefreshCw />}
        >
          Try again
        </Button>
      )}
    </div>
  );
}
