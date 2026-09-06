import { useCallback, useState } from 'react';
import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';
import { applyApiErrors } from '@/lib/validation/applyApiErrors';
import { isApiError } from '@/services/api/errors';

/**
 * Shared submit plumbing for feature forms: maps API field errors onto react-hook-form fields,
 * keeps the non-field message in local state, and reports throttling separately.
 */
export function useFormSubmit<T extends FieldValues>(
  setError: UseFormSetError<T>,
  knownFields: readonly Path<T>[],
  aliases: Record<string, string> = {},
) {
  const [message, setMessage] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState<number | null>(null);

  const reset = useCallback(() => {
    setMessage(null);
    setRetryAfter(null);
  }, []);

  const captureError = useCallback(
    (error: unknown) => {
      if (isApiError(error) && error.kind === 'throttled') {
        setRetryAfter(error.retryAfterSeconds ?? 60);
        return;
      }
      setMessage(
        applyApiErrors(error, setError, knownFields as readonly string[], aliases) ??
          'Something went wrong. Please try again.',
      );
    },
    [setError, knownFields, aliases],
  );

  return { message, retryAfter, reset, captureError, clearThrottle: () => setRetryAfter(null) };
}
