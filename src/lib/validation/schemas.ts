import { z } from 'zod';
import { LIMITS } from '@/app/config/constants';
import { parseNairaToKobo } from '@/lib/formatting/money';

/* ---------- primitives shared across features ---------- */

export const usernameSchema = z
  .string()
  .trim()
  .min(LIMITS.usernameMin, `At least ${LIMITS.usernameMin} characters`)
  .max(LIMITS.usernameMax, `At most ${LIMITS.usernameMax} characters`)
  .regex(/^[\w.@+-]+$/, 'Letters, digits and @ . + - _ only');

export const emailSchema = z.string().trim().email('Enter a valid email address');

/** Passwords are NOT trimmed (backend uses trim_whitespace=False). */
export const passwordSchema = z
  .string()
  .min(LIMITS.passwordMin, `At least ${LIMITS.passwordMin} characters`)
  .refine((v) => !/^\d+$/.test(v), 'Password cannot be entirely numeric');

export const phoneSchema = z
  .string()
  .trim()
  .min(LIMITS.phoneMin, `At least ${LIMITS.phoneMin} digits`)
  .max(LIMITS.phoneMax, `At most ${LIMITS.phoneMax} characters`)
  .regex(/^[+\d][\d\s-]*$/, 'Digits only (may start with +)');

export const optionalPhoneSchema = z.union([z.literal(''), phoneSchema]);

export const slugSchema = z
  .string()
  .trim()
  .min(1, 'Required')
  .max(50)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, 'Lower-case letters, digits and single hyphens');

/** Naira text input → integer kobo. */
export const nairaAmountSchema = (opts?: { minKobo?: number; maxKobo?: number; label?: string }) =>
  z
    .string()
    .trim()
    .min(1, 'Required')
    .transform((raw, ctx) => {
      const kobo = parseNairaToKobo(raw);
      if (kobo === null) {
        ctx.addIssue({ code: 'custom', message: 'Enter an amount like 1500 or 1500.50' });
        return z.NEVER;
      }
      if (opts?.minKobo !== undefined && kobo < opts.minKobo) {
        ctx.addIssue({
          code: 'custom',
          message: `Minimum is ₦${(opts.minKobo / 100).toLocaleString()}`,
        });
        return z.NEVER;
      }
      if (opts?.maxKobo !== undefined && kobo > opts.maxKobo) {
        ctx.addIssue({
          code: 'custom',
          message: `Maximum is ₦${(opts.maxKobo / 100).toLocaleString()}`,
        });
        return z.NEVER;
      }
      return kobo;
    });

export const positiveIntSchema = (label = 'Value') =>
  z.coerce
    .number()
    .int(`${label} must be a whole number`)
    .positive(`${label} must be greater than 0`);

export const nonNegativeIntSchema = (label = 'Value') =>
  z.coerce.number().int(`${label} must be a whole number`).min(0, `${label} cannot be negative`);

export const ipv4Schema = z
  .string()
  .trim()
  .regex(
    /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/,
    'Enter a valid IPv4 address',
  );

export const ipAddressSchema = z.union([ipv4Schema, z.ipv6('Enter a valid IP address')]);

export const macAddressSchema = z
  .string()
  .trim()
  .regex(/^([0-9A-Fa-f]{2}[:-]?){5}[0-9A-Fa-f]{2}$/, 'Enter a MAC like AA:BB:CC:DD:EE:FF');

/** RouterOS rate limit syntax used by the backend, e.g. 5M/10M or 512k/1M. */
export const rateLimitSchema = z
  .string()
  .trim()
  .min(1, 'Required')
  .max(LIMITS.rateLimitMax)
  .regex(
    /^\d+(?:\.\d+)?[kKmMgG]?\/\d+(?:\.\d+)?[kKmMgG]?$/,
    'Use the form upload/download, e.g. 5M/10M',
  );

export const wireguardPublicKeySchema = z
  .string()
  .trim()
  .regex(/^[A-Za-z0-9+/]{43}=$/, 'WireGuard public keys are 44 base64 characters ending in =');

export const idempotentPrefixSchema = z
  .string()
  .trim()
  .max(LIMITS.voucherPrefixMax, `At most ${LIMITS.voucherPrefixMax} characters`)
  .regex(/^[A-Za-z0-9]*$/, 'Letters and digits only');

/** Password + confirmation pair used by register / reset / invitation acceptance. */
export const passwordPairRefinement = {
  check: (v: { password: string; password_confirm: string }) => v.password === v.password_confirm,
  options: { message: 'Passwords do not match', path: ['password_confirm'] as const },
};

export const passwordPairShape = { password: passwordSchema, password_confirm: z.string() };

export type Infer<T extends z.ZodTypeAny> = z.infer<T>;
