import { z } from 'zod';
import { phoneSchema } from '@/lib/validation/schemas';
import type { AgentProfile, AgentSelfEditRequest } from '@/types/api';

export const agentProfileSchema = z.object({
  shop_name: z.string().trim().max(150, 'At most 150 characters'),
  phone: phoneSchema,
});
export type AgentProfileInput = z.input<typeof agentProfileSchema>;
export type AgentProfileOutput = z.output<typeof agentProfileSchema>;

export function agentProfileToForm(profile: AgentProfile): AgentProfileInput {
  return { shop_name: profile.shop_name, phone: profile.phone };
}

/** Only the fields that actually changed (the API accepts phone/shop_name only). */
export function agentProfileToPatch(
  profile: AgentProfile,
  values: AgentProfileOutput,
): AgentSelfEditRequest {
  const patch: AgentSelfEditRequest = {};
  if (values.shop_name !== profile.shop_name) patch.shop_name = values.shop_name;
  if (values.phone !== profile.phone) patch.phone = values.phone;
  return patch;
}
