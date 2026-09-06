import { z } from 'zod';
import { LIMITS } from '@/app/config/constants';
import {
  idempotentPrefixSchema,
  nairaAmountSchema,
  nonNegativeIntSchema,
  positiveIntSchema,
  rateLimitSchema,
} from '@/lib/validation/schemas';
import type { InternetPlan, InternetPlanWrite } from '@/types/api';
import { koboToNairaInput } from '@/lib/formatting/money';

export const DURATION_PRESETS = [
  { label: '1 hour', hours: 1 },
  { label: '3 hours', hours: 3 },
  { label: '12 hours', hours: 12 },
  { label: '1 day', hours: 24 },
  { label: '3 days', hours: 72 },
  { label: '1 week', hours: 168 },
  { label: '2 weeks', hours: 336 },
  { label: '30 days', hours: 720 },
] as const;

export const planFormSchema = z.object({
  name: z.string().trim().min(1, 'Give the plan a name').max(LIMITS.planNameMax),
  price: nairaAmountSchema({ minKobo: 0 }),
  duration_hours: positiveIntSchema('Duration'),
  rate_limit: rateLimitSchema,
  data_limit_mb: nonNegativeIntSchema('Data limit'),
  voucher_prefix: idempotentPrefixSchema,
  is_active: z.boolean(),
});

export type PlanFormInput = z.input<typeof planFormSchema>;
export type PlanFormOutput = z.output<typeof planFormSchema>;

export function planToForm(plan?: InternetPlan): PlanFormInput {
  return {
    name: plan?.name ?? '',
    price: plan ? koboToNairaInput(plan.price) : '',
    duration_hours: plan?.duration_hours ?? 24,
    rate_limit: plan?.rate_limit ?? '5M/10M',
    data_limit_mb: plan?.data_limit ?? 0,
    voucher_prefix: plan?.voucher_prefix ?? '',
    is_active: plan?.is_active ?? true,
  };
}

export function formToPlan(values: PlanFormOutput): InternetPlanWrite {
  return {
    name: values.name,
    price: values.price,
    duration_hours: values.duration_hours,
    rate_limit: values.rate_limit,
    data_limit: values.data_limit_mb,
    voucher_prefix: values.voucher_prefix,
    is_active: values.is_active,
  };
}
