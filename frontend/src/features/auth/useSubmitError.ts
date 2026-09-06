import { useCallback, useState } from 'react';
import { isApiError } from '@/services/api/errors';

/**
 * Shared error state for auth forms: a form-level message plus a throttle countdown for 429s.
 */
export function useSubmitError() {
  const [message, setMessage] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState<number | null>(null);
  const reset = useCallback(() => {
    setMessage(null);
    setRetryAfter(null);
  }, []);
  const capture = useCallback(
    (error: unknown, fallback = 'Something went wrong. Please try again.') => {
      if (isApiError(error)) {
        if (error.kind === 'throttled') {
          setRetryAfter(error.retryAfterSeconds ?? 60);
          setMessage(null);
          return;
        }
        setMessage(error.message);
        return;
      }
      setMessage(fallback);
    },
    [],
  );
  return {
    message,
    retryAfter,
    setMessage,
    reset,
    capture,
    clearThrottle: () => setRetryAfter(null),
  };
}
