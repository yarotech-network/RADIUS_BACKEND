import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';
import { isApiError } from '@/services/api/errors';

/**
 * Map a backend validation error onto react-hook-form fields. Returns the message that could not
 * be attached to any field (to show as a form-level alert), or null when everything was mapped.
 *
 * `aliases` lets a form rename backend fields (e.g. backend `plan_id` → form `plan`).
 */
export function applyApiErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  knownFields: readonly string[],
  aliases: Record<string, string> = {},
): string | null {
  if (!isApiError(error))
    return error instanceof Error ? 'Something went wrong. Please try again.' : null;
  const unmatched: string[] = [];
  for (const [field, messages] of Object.entries(error.fields)) {
    const target = aliases[field] ?? field;
    const message = messages.join(' ');
    if (field !== 'non_field_errors' && knownFields.includes(target)) {
      setError(target as Path<T>, { type: 'server', message });
    } else {
      unmatched.push(message);
    }
  }
  if (unmatched.length > 0) return unmatched.join(' ');
  if (error.hasFieldErrors && error.message === 'Check the highlighted fields.') return null;
  if (error.hasFieldErrors && error.message === 'Check the submitted fields.') return null;
  return error.message;
}
