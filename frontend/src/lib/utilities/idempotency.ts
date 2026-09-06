/**
 * Idempotency keys for backend commands. Accepted syntax: 16–128 chars of [A-Za-z0-9_.:-].
 * A key must be generated ONCE per logical user action and reused on transport retries.
 */
export function newIdempotencyKey(prefix = 'ui'): string {
  const random =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  const key = `${prefix}-${random}`.replace(/[^A-Za-z0-9_.:-]/g, '');
  return key.slice(0, 128).padEnd(16, '0');
}

export const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9_.:-]{16,128}$/;
