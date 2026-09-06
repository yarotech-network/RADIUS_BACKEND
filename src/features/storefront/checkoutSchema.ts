import { z } from 'zod';
import { emailSchema, optionalPhoneSchema } from '@/lib/validation/schemas';

export const checkoutSchema = z.object({
  email: emailSchema,
  name: z.string().trim().max(200, 'At most 200 characters'),
  phone: optionalPhoneSchema,
});
export type CheckoutInput = z.input<typeof checkoutSchema>;
export type CheckoutOutput = z.output<typeof checkoutSchema>;
