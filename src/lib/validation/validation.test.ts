import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/services/api/errors';
import { applyApiErrors } from './applyApiErrors';
import {
  idempotentPrefixSchema,
  macAddressSchema,
  nairaAmountSchema,
  passwordSchema,
  rateLimitSchema,
  usernameSchema,
  ipAddressSchema,
} from './schemas';
import { IDEMPOTENCY_KEY_PATTERN, newIdempotencyKey } from '@/lib/utilities/idempotency';

describe('schemas', () => {
  it('mirror backend constraints', () => {
    expect(usernameSchema.safeParse('ab').success).toBe(false);
    expect(usernameSchema.safeParse('shop.lagos_01').success).toBe(true);
    expect(passwordSchema.safeParse('12345678').success).toBe(false);
    expect(passwordSchema.safeParse('correct horse').success).toBe(true);
    expect(rateLimitSchema.safeParse('5M/10M').success).toBe(true);
    expect(rateLimitSchema.safeParse('fast').success).toBe(false);
    expect(macAddressSchema.safeParse('aa:bb:cc:dd:ee:ff').success).toBe(true);
    expect(macAddressSchema.safeParse('zz:bb:cc:dd:ee:ff').success).toBe(false);
    expect(ipAddressSchema.safeParse('10.100.100.12').success).toBe(true);
    expect(ipAddressSchema.safeParse('999.1.1.1').success).toBe(false);
    expect(idempotentPrefixSchema.safeParse('ABCDEFGHIJK').success).toBe(false);
  });

  it('converts naira text to kobo with bounds', () => {
    const schema = nairaAmountSchema({ minKobo: 50_000 });
    expect(schema.safeParse('500').data).toBe(50_000);
    expect(schema.safeParse('499.99').success).toBe(false);
    expect(schema.safeParse('1,000.5').data).toBe(100_050);
  });

  it('generates valid idempotency keys', () => {
    const key = newIdempotencyKey('vouchers');
    expect(key).toMatch(IDEMPOTENCY_KEY_PATTERN);
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });
});

describe('applyApiErrors', () => {
  it('maps field errors, honours aliases, and returns leftovers as a form-level message', () => {
    const setError = vi.fn();
    const error = new ApiError({
      status: 400,
      message: 'Check the submitted fields.',
      fields: { plan_id: ['Plan is inactive.'], quantity: ['Too many.'], secret: ['Nope'] },
    });
    const leftover = applyApiErrors(error, setError, ['plan', 'quantity'], { plan_id: 'plan' });
    expect(setError).toHaveBeenCalledWith('plan', { type: 'server', message: 'Plan is inactive.' });
    expect(setError).toHaveBeenCalledWith('quantity', { type: 'server', message: 'Too many.' });
    expect(leftover).toBe('Nope');
  });

  it('returns null when every error was attached to a field', () => {
    const setError = vi.fn();
    const error = new ApiError({
      status: 400,
      message: 'Check the submitted fields.',
      fields: { name: ['Required'] },
    });
    expect(applyApiErrors(error, setError, ['name'])).toBeNull();
  });

  it('returns the message for non-validation errors', () => {
    const setError = vi.fn();
    expect(
      applyApiErrors(new ApiError({ status: 409, message: 'Stale record.' }), setError, ['name']),
    ).toBe('Stale record.');
    expect(setError).not.toHaveBeenCalled();
  });
});
