import { z } from 'zod';
import { ipv4Schema, wireguardPublicKeySchema } from '@/lib/validation/schemas';
import type { NasDevice, NasDeviceCreate, NasDeviceUpdate, OnboardingState } from '@/types/api';

const optional = <T extends z.ZodTypeAny>(schema: T) => z.union([z.literal(''), schema]);

const secretSchema = z
  .string()
  .min(8, 'At least 8 characters')
  .max(255, 'At most 255 characters')
  .refine((v) => !v.startsWith('enc:v1:'), 'Enter the plain secret, not stored ciphertext');

const baseShape = {
  name: z.string().trim().min(1, 'Give the router a name').max(100, 'At most 100 characters'),
  ip_address: ipv4Schema,
  location: z.string().trim().max(200, 'At most 200 characters'),
  wireguard_ip: optional(ipv4Schema),
  wireguard_public_key: optional(wireguardPublicKeySchema),
  wireguard_port: z.coerce.number().int('Whole number').min(1, '1–65535').max(65535, '1–65535'),
  routeros_username: z.string().trim().max(150, 'At most 150 characters'),
  is_active: z.boolean(),
};

export const routerCreateSchema = z.object({
  ...baseShape,
  nas_secret: secretSchema,
  routeros_password: z.string().max(255, 'At most 255 characters'),
});
export type RouterCreateInput = z.input<typeof routerCreateSchema>;
export type RouterCreateOutput = z.output<typeof routerCreateSchema>;

export const routerEditSchema = z.object(baseShape);
export type RouterEditInput = z.input<typeof routerEditSchema>;
export type RouterEditOutput = z.output<typeof routerEditSchema>;

export const CREATE_DEFAULTS: RouterCreateInput = {
  name: '',
  ip_address: '',
  location: '',
  wireguard_ip: '',
  wireguard_public_key: '',
  wireguard_port: 51820,
  routeros_username: '',
  is_active: true,
  nas_secret: '',
  routeros_password: '',
};

export function routerToEditForm(router: NasDevice): RouterEditInput {
  return {
    name: router.name,
    ip_address: router.ip_address,
    location: router.location,
    wireguard_ip: router.wireguard_ip ?? '',
    wireguard_public_key: router.wireguard_public_key,
    wireguard_port: router.wireguard_port,
    routeros_username: router.routeros_username,
    is_active: router.is_active,
  };
}

export function createFormToPayload(v: RouterCreateOutput): NasDeviceCreate {
  return {
    name: v.name,
    ip_address: v.ip_address,
    nas_secret: v.nas_secret,
    location: v.location,
    wireguard_ip: v.wireguard_ip || null,
    wireguard_public_key: v.wireguard_public_key,
    wireguard_port: v.wireguard_port,
    routeros_username: v.routeros_username,
    ...(v.routeros_password ? { routeros_password_encrypted: v.routeros_password } : {}),
    is_active: v.is_active,
  };
}

/** Only send fields that changed (PATCH); the API rejects secrets on this endpoint anyway. */
export function editFormToPatch(v: RouterEditOutput, router: NasDevice): NasDeviceUpdate {
  const patch: NasDeviceUpdate = {};
  if (v.name !== router.name) patch.name = v.name;
  if (v.ip_address !== router.ip_address) patch.ip_address = v.ip_address;
  if (v.location !== router.location) patch.location = v.location;
  if ((v.wireguard_ip || null) !== router.wireguard_ip) patch.wireguard_ip = v.wireguard_ip || null;
  if (v.wireguard_public_key !== router.wireguard_public_key)
    patch.wireguard_public_key = v.wireguard_public_key;
  if (v.wireguard_port !== router.wireguard_port) patch.wireguard_port = v.wireguard_port;
  if (v.routeros_username !== router.routeros_username)
    patch.routeros_username = v.routeros_username;
  if (v.is_active !== router.is_active) patch.is_active = v.is_active;
  return patch;
}

export const replaceSecretsSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your password to confirm'),
    nas_secret: optional(secretSchema),
    routeros_password: z.string().max(255),
    clear_routeros_password: z.boolean(),
  })
  .refine(
    (v) => Boolean(v.nas_secret) || Boolean(v.routeros_password) || v.clear_routeros_password,
    {
      message: 'Choose at least one secret to replace',
      path: ['nas_secret'],
    },
  );
export type ReplaceSecretsInput = z.input<typeof replaceSecretsSchema>;
export type ReplaceSecretsOutput = z.output<typeof replaceSecretsSchema>;

export const radiusTestSchema = z.object({
  username: z.string().trim().min(1, 'Enter a voucher username'),
  password: z.string().min(1, 'Enter the voucher password'),
});
export type RadiusTestInput = z.infer<typeof radiusTestSchema>;

export const ONBOARDING_FILTER_OPTIONS: { value: '' | OnboardingState; label: string }[] = [
  { value: '', label: 'All states' },
  { value: 'pending', label: 'Pending review' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'approved', label: 'Approved' },
  { value: 'waiting_for_vpn', label: 'Waiting for VPN' },
  { value: 'vpn_failed', label: 'VPN failed' },
  { value: 'testing_radius', label: 'Testing RADIUS' },
  { value: 'radius_failed', label: 'RADIUS failed' },
  { value: 'accounting_failed', label: 'Accounting failed' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
];
