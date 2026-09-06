import { z } from 'zod';
import { macAddressSchema } from '@/lib/validation/schemas';
import { fromDateTimeLocalInput, toDateTimeLocalInput } from '@/lib/formatting/dates';
import type { MacDevice, MacDeviceWrite } from '@/types/api';

export const deviceSchema = z.object({
  device_name: z.string().trim().min(1, 'Required').max(200, 'At most 200 characters'),
  mac_address: macAddressSchema,
  plan: z.string().min(1, 'Choose a plan'),
  expires_at: z
    .string()
    .min(1, 'Required')
    .refine((v) => fromDateTimeLocalInput(v) !== null, 'Enter a valid date and time'),
  is_active: z.boolean(),
});
export type DeviceInput = z.input<typeof deviceSchema>;
export type DeviceOutput = z.output<typeof deviceSchema>;

export function deviceDefaults(): DeviceInput {
  const inAYear = new Date();
  inAYear.setFullYear(inAYear.getFullYear() + 1);
  return {
    device_name: '',
    mac_address: '',
    plan: '',
    expires_at: toDateTimeLocalInput(inAYear.toISOString()),
    is_active: true,
  };
}

export function deviceToForm(device: MacDevice): DeviceInput {
  return {
    device_name: device.device_name,
    mac_address: device.mac_address,
    plan: String(device.plan),
    expires_at: toDateTimeLocalInput(device.expires_at),
    is_active: device.is_active,
  };
}

export function formToPayload(values: DeviceOutput): MacDeviceWrite {
  return {
    device_name: values.device_name,
    mac_address: normaliseMac(values.mac_address),
    plan: Number(values.plan),
    expires_at: fromDateTimeLocalInput(values.expires_at) ?? values.expires_at,
    is_active: values.is_active,
  };
}

export function formToPatch(values: DeviceOutput, device: MacDevice): Partial<MacDeviceWrite> {
  const next = formToPayload(values);
  const patch: Partial<MacDeviceWrite> = {};
  if (next.device_name !== device.device_name) patch.device_name = next.device_name;
  if (next.mac_address !== device.mac_address) patch.mac_address = next.mac_address;
  if (next.plan !== device.plan) patch.plan = next.plan;
  if (new Date(next.expires_at).getTime() !== new Date(device.expires_at).getTime())
    patch.expires_at = next.expires_at;
  if (next.is_active !== device.is_active) patch.is_active = values.is_active;
  return patch;
}

/** Same canonical form the server stores (AA:BB:CC:DD:EE:FF) so change detection is stable. */
export function normaliseMac(value: string): string {
  const hex = value.replace(/[^0-9a-fA-F]/g, '').toUpperCase();
  return hex.match(/.{2}/g)?.join(':') ?? value;
}
