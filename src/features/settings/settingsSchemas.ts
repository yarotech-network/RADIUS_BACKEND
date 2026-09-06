import { z } from 'zod';
import { LIMITS } from '@/app/config/constants';
import {
  emailSchema,
  idempotentPrefixSchema,
  nairaAmountSchema,
  optionalPhoneSchema,
  passwordSchema,
  positiveIntSchema,
} from '@/lib/validation/schemas';
import { koboToNairaInput } from '@/lib/formatting/money';
import type {
  MembershipRole,
  TenantMembershipWrite,
  TenantProfile,
  TenantProfileWrite,
  TenantSetting,
  TenantSettingWrite,
} from '@/types/api';

/* ---------- business profile ---------- */

export const tenantProfileSchema = z.object({
  name: z
    .string()
    .trim()
    .min(LIMITS.tenantNameMin, `At least ${LIMITS.tenantNameMin} characters`)
    .max(LIMITS.tenantNameMax),
  email: z.union([z.literal(''), emailSchema]),
  phone: optionalPhoneSchema,
  address: z.string().trim().max(500, 'At most 500 characters'),
});
export type TenantProfileInput = z.input<typeof tenantProfileSchema>;
export type TenantProfileOutput = z.output<typeof tenantProfileSchema>;

export function profileToForm(profile: TenantProfile): TenantProfileInput {
  return {
    name: profile.name,
    email: profile.email,
    phone: profile.phone,
    address: profile.address,
  };
}

/** Only changed fields are sent, so an untouched form is a no-op PATCH. */
export function profileFormToPatch(
  values: TenantProfileOutput,
  current: TenantProfile,
): TenantProfileWrite {
  const patch: TenantProfileWrite = {};
  if (values.name !== current.name) patch.name = values.name;
  if (values.email !== current.email) patch.email = values.email;
  if (values.phone !== current.phone) patch.phone = values.phone;
  if (values.address !== current.address) patch.address = values.address;
  return patch;
}

/* ---------- billing & payouts ---------- */

const percentSchema = z
  .string()
  .trim()
  .min(1, 'Required')
  .regex(/^\d{1,3}(?:\.\d{1,2})?$/, 'Use a number like 10 or 12.5')
  .refine((v) => Number(v) <= 100, 'At most 100%');

export const billingSettingsSchema = z.object({
  agent_commission_percent: percentSchema,
  voucher_prefix: idempotentPrefixSchema,
  max_funding_amount: nairaAmountSchema({ minKobo: 1 }),
  /** Blank = keep the stored key. */
  paystack_public_key: z.string().trim().max(200),
  paystack_secret_key: z.string().trim().max(200),
});
export type BillingSettingsInput = z.input<typeof billingSettingsSchema>;
export type BillingSettingsOutput = z.output<typeof billingSettingsSchema>;

export function settingsToForm(s: TenantSetting): BillingSettingsInput {
  return {
    agent_commission_percent: String(Number(s.agent_commission_percent)),
    voucher_prefix: s.voucher_prefix,
    max_funding_amount: koboToNairaInput(s.max_funding_amount),
    paystack_public_key: '',
    paystack_secret_key: '',
  };
}

export function settingsFormToPatch(
  values: BillingSettingsOutput,
  current: TenantSetting,
): TenantSettingWrite {
  const patch: TenantSettingWrite = {};
  if (Number(values.agent_commission_percent) !== Number(current.agent_commission_percent))
    patch.agent_commission_percent = values.agent_commission_percent;
  if (values.voucher_prefix !== current.voucher_prefix)
    patch.voucher_prefix = values.voucher_prefix;
  if (values.max_funding_amount !== current.max_funding_amount)
    patch.max_funding_amount = values.max_funding_amount;
  if (values.paystack_public_key) patch.paystack_public_key = values.paystack_public_key;
  if (values.paystack_secret_key) patch.paystack_secret_key = values.paystack_secret_key;
  return patch;
}

/* ---------- team ---------- */

export const ROLE_OPTIONS: { value: MembershipRole; label: string; description: string }[] = [
  {
    value: 'staff',
    label: 'Staff',
    description: 'Sell and print vouchers, see sessions and payments.',
  },
  {
    value: 'manager',
    label: 'Manager',
    description:
      'Everything staff can, plus plans, routers, agents, recovery, settings and the audit log.',
  },
  {
    value: 'owner',
    label: 'Owner',
    description: 'Full control including team membership and the subscription.',
  },
];

export const addMemberSchema = z.object({
  user: positiveIntSchema('User ID'),
  role: z.enum(['owner', 'manager', 'staff']),
});
export type AddMemberInput = z.input<typeof addMemberSchema>;
export type AddMemberOutput = z.output<typeof addMemberSchema>;

export function addMemberToPayload(
  values: AddMemberOutput,
  tenantId: number,
): TenantMembershipWrite {
  return { user: values.user, role: values.role, tenant: tenantId };
}

/* ---------- account ---------- */

export const changePasswordSchema = z
  .object({
    old_password: z.string().min(1, 'Enter your current password'),
    new_password: passwordSchema,
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    message: 'Passwords do not match',
    path: ['confirm'],
  })
  .refine((v) => v.new_password !== v.old_password, {
    message: 'Choose a different password',
    path: ['new_password'],
  });
export type ChangePasswordInput = z.input<typeof changePasswordSchema>;
export type ChangePasswordOutput = z.output<typeof changePasswordSchema>;
