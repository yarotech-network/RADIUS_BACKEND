import { z } from 'zod';
import { LIMITS } from '@/app/config/constants';
import { emailSchema, optionalPhoneSchema, positiveIntSchema } from '@/lib/validation/schemas';
import { STAFF_SERVICES, type StaffService, type Tenant, type TenantWrite } from '@/types/api';
import { SLUG_PATTERN } from './platformVocabulary';

/* ---------- tenants ---------- */

export const tenantSchema = z.object({
  name: z
    .string()
    .trim()
    .min(LIMITS.tenantNameMin, `At least ${LIMITS.tenantNameMin} characters`)
    .max(LIMITS.tenantNameMax, `At most ${LIMITS.tenantNameMax} characters`),
  slug: z
    .string()
    .trim()
    .min(2, 'At least 2 characters')
    .max(50, 'At most 50 characters')
    .regex(SLUG_PATTERN, 'Letters, digits, hyphens and underscores only'),
  email: z.union([z.literal(''), emailSchema]),
  phone: optionalPhoneSchema,
  address: z.string().trim().max(500, 'At most 500 characters'),
  is_active: z.boolean(),
});
export type TenantInput = z.input<typeof tenantSchema>;
export type TenantOutput = z.output<typeof tenantSchema>;

export function tenantToForm(tenant?: Tenant): TenantInput {
  return {
    name: tenant?.name ?? '',
    slug: tenant?.slug ?? '',
    email: tenant?.email ?? '',
    phone: tenant?.phone ?? '',
    address: tenant?.address ?? '',
    is_active: tenant?.is_active ?? true,
  };
}

export function tenantFormToCreate(values: TenantOutput): TenantWrite {
  return {
    name: values.name,
    slug: values.slug,
    email: values.email,
    phone: values.phone,
    address: values.address,
    is_active: values.is_active,
  };
}

/** Only fields that changed (PATCH). */
export function tenantFormToPatch(tenant: Tenant, values: TenantOutput): Partial<TenantWrite> {
  const patch: Partial<TenantWrite> = {};
  for (const key of ['name', 'slug', 'email', 'phone', 'address', 'is_active'] as const) {
    if (values[key] !== tenant[key]) (patch as Record<string, unknown>)[key] = values[key];
  }
  return patch;
}

/* ---------- memberships (admin side needs a tenant + user id) ---------- */

export const adminMembershipSchema = z.object({
  user: positiveIntSchema('User ID'),
  role: z.enum(['owner', 'manager', 'staff']),
});
export type AdminMembershipInput = z.input<typeof adminMembershipSchema>;
export type AdminMembershipOutput = z.output<typeof adminMembershipSchema>;

/* ---------- staff ---------- */

const servicesSchema = z
  .array(z.enum(STAFF_SERVICES as unknown as [StaffService, ...StaffService[]]))
  .min(1, 'Pick at least one service');

export const inviteSchema = z.object({
  email: emailSchema,
  tenant: positiveIntSchema('Tenant'),
  services: servicesSchema,
});
export type InviteInput = z.input<typeof inviteSchema>;
export type InviteOutput = z.output<typeof inviteSchema>;

export const assignmentSchema = z.object({
  user: positiveIntSchema('User ID'),
  tenant: positiveIntSchema('Tenant'),
  services: servicesSchema,
});
export type AssignmentInput = z.input<typeof assignmentSchema>;
export type AssignmentOutput = z.output<typeof assignmentSchema>;

export const grantsSchema = z.object({ services: servicesSchema, is_active: z.boolean() });
export type GrantsInput = z.input<typeof grantsSchema>;
export type GrantsOutput = z.output<typeof grantsSchema>;
