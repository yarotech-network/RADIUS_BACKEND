import { z } from 'zod';
import { LIMITS } from '@/app/config/constants';
import { idempotentPrefixSchema, positiveIntSchema } from '@/lib/validation/schemas';

export const generateSchema = z.object({
  plan_id: z.coerce.number().int().positive('Choose a plan'),
  quantity: z.coerce
    .number()
    .int('Quantity must be a whole number')
    .min(1, 'Generate at least 1 voucher')
    .max(LIMITS.voucherBatchMax, `At most ${LIMITS.voucherBatchMax} per batch`),
  prefix: idempotentPrefixSchema,
});
export type GenerateInput = z.input<typeof generateSchema>;
export type GenerateOutput = z.output<typeof generateSchema>;

const credentialSchema = z
  .string()
  .trim()
  .min(4, 'At least 4 characters')
  .max(50, 'At most 50 characters')
  .regex(/^[A-Za-z0-9._-]+$/, 'Letters, digits, dot, dash and underscore only');

export const manualVoucherSchema = z.object({
  username: credentialSchema,
  password: credentialSchema,
  plan: z.coerce.number().int().positive('Choose a plan'),
  device_limit: positiveIntSchema('Device limit'),
});
export type ManualVoucherInput = z.input<typeof manualVoucherSchema>;
export type ManualVoucherOutput = z.output<typeof manualVoucherSchema>;

export const QUANTITY_PRESETS = [10, 20, 50, 100] as const;
