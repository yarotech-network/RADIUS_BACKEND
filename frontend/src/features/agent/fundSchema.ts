import { z } from 'zod';
import { parseNairaToKobo } from '@/lib/formatting/money';

/** Backend floor: 50 000 kobo (₦500). The ceiling is the tenant's `max_funding_amount`, echoed by the API on 400. */
export const MIN_FUNDING_KOBO = 50_000;
export const QUICK_AMOUNTS_KOBO = [100_000, 200_000, 500_000, 1_000_000] as const;

export const fundSchema = z.object({
  amount: z
    .string()
    .trim()
    .min(1, 'Enter an amount')
    .transform((raw, ctx) => {
      const kobo = parseNairaToKobo(raw);
      if (kobo === null) {
        ctx.addIssue({ code: 'custom', message: 'Enter an amount in naira, e.g. 2000' });
        return z.NEVER;
      }
      if (kobo < MIN_FUNDING_KOBO) {
        ctx.addIssue({ code: 'custom', message: 'Minimum top-up is ₦500' });
        return z.NEVER;
      }
      return kobo;
    }),
});
export type FundInput = z.input<typeof fundSchema>;
export type FundOutput = z.output<typeof fundSchema>;
