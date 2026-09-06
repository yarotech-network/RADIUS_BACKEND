import { z } from 'zod';

export const MAX_QUANTITY = 100;

export const sellSchema = z.object({
  plan_id: z.number().int().positive('Choose a plan'),
  quantity: z.coerce
    .number({ message: 'Enter how many vouchers' })
    .int('Whole numbers only')
    .min(1, 'At least 1')
    .max(MAX_QUANTITY, `At most ${MAX_QUANTITY} at a time`),
});
export type SellInput = z.input<typeof sellSchema>;
export type SellOutput = z.output<typeof sellSchema>;

/** Wallet debit the backend will make: plan price × quantity (both kobo integers). */
export function sellCost(price: number, quantity: number): number {
  if (!Number.isFinite(quantity) || quantity < 1) return 0;
  return price * Math.floor(quantity);
}
