import { describe, expect, it } from 'vitest';
import { formToPlan, planFormSchema, planToForm } from './planSchema';

describe('plan form schema', () => {
  it('converts naira input to kobo and MB to data_limit', () => {
    const parsed = planFormSchema.parse({
      name: ' Daily ',
      price: '1,500.50',
      duration_hours: '24',
      rate_limit: '5M/10M',
      data_limit_mb: '1024',
      voucher_prefix: 'DAY',
      is_active: true,
    });
    expect(formToPlan(parsed)).toEqual({
      name: 'Daily',
      price: 150050,
      duration_hours: 24,
      rate_limit: '5M/10M',
      data_limit: 1024,
      voucher_prefix: 'DAY',
      is_active: true,
    });
  });
  it('rejects bad rate limits, negative data caps and long prefixes', () => {
    const res = planFormSchema.safeParse({
      name: 'x',
      price: '10',
      duration_hours: 1,
      rate_limit: 'fast',
      data_limit_mb: -1,
      voucher_prefix: 'TOOLONGPREFIX',
      is_active: true,
    });
    expect(res.success).toBe(false);
    const paths = res.success ? [] : res.error.issues.map((i) => i.path[0]);
    expect(paths).toEqual(
      expect.arrayContaining(['rate_limit', 'data_limit_mb', 'voucher_prefix']),
    );
  });
  it('round-trips an existing plan into form values', () => {
    const form = planToForm({
      id: 1,
      name: 'Weekly',
      price: 250000,
      price_display: '₦2,500',
      duration_hours: 168,
      rate_limit: '10M/20M',
      data_limit: 0,
      voucher_prefix: 'WK',
      is_active: false,
      created_at: '2026-01-01T00:00:00Z',
    });
    expect(form).toMatchObject({
      name: 'Weekly',
      price: '2500',
      duration_hours: 168,
      is_active: false,
    });
  });
});
