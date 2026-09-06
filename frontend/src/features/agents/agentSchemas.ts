import { z } from 'zod';
import { emailSchema, passwordSchema, phoneSchema, usernameSchema } from '@/lib/validation/schemas';
import type { AgentCreateRequest, AgentEditRequest, AgentProfile } from '@/types/api';

/** Percentage 0–100 with at most 2 decimals; sent as a decimal string ("10.00"). */
const commissionSchema = z
  .string()
  .trim()
  .regex(/^\d{1,3}(\.\d{1,2})?$/, 'Use a number like 10 or 12.5')
  .refine((v) => Number(v) <= 100, 'At most 100%');

export const agentCreateSchema = z.object({
  username: usernameSchema,
  email: emailSchema,
  password: passwordSchema,
  phone: phoneSchema,
  shop_name: z.string().trim().max(200, 'At most 200 characters'),
  commission_rate: z.union([z.literal(''), commissionSchema]),
});
export type AgentCreateInput = z.input<typeof agentCreateSchema>;
export type AgentCreateOutput = z.output<typeof agentCreateSchema>;

export const agentEditSchema = z.object({
  phone: phoneSchema,
  shop_name: z.string().trim().max(200, 'At most 200 characters'),
  commission_rate: commissionSchema,
});
export type AgentEditInput = z.input<typeof agentEditSchema>;
export type AgentEditOutput = z.output<typeof agentEditSchema>;

export const AGENT_CREATE_DEFAULTS: AgentCreateInput = {
  username: '',
  email: '',
  password: '',
  phone: '',
  shop_name: '',
  commission_rate: '',
};

export function agentToEditForm(agent: AgentProfile): AgentEditInput {
  return {
    phone: agent.phone,
    shop_name: agent.shop_name,
    commission_rate: formatCommission(agent.commission_rate),
  };
}

export function createFormToPayload(values: AgentCreateOutput): AgentCreateRequest {
  const payload: AgentCreateRequest = {
    username: values.username,
    email: values.email,
    password: values.password,
    phone: values.phone,
  };
  if (values.shop_name) payload.shop_name = values.shop_name;
  if (values.commission_rate !== '')
    payload.commission_rate = normaliseCommission(values.commission_rate);
  return payload;
}

/** Only changed fields are sent. */
export function editFormToPatch(values: AgentEditOutput, agent: AgentProfile): AgentEditRequest {
  const patch: AgentEditRequest = {};
  if (values.phone !== agent.phone) patch.phone = values.phone;
  if (values.shop_name !== agent.shop_name) patch.shop_name = values.shop_name;
  if (normaliseCommission(values.commission_rate) !== normaliseCommission(agent.commission_rate))
    patch.commission_rate = normaliseCommission(values.commission_rate);
  return patch;
}

/** "12.5" → "12.50" (matches the server's 2-decimal representation). */
export function normaliseCommission(value: string): string {
  return Number(value).toFixed(2);
}

/** "10.00" → "10", "12.50" → "12.5" for display / editing. */
export function formatCommission(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? String(Number(n.toFixed(2))) : value;
}
