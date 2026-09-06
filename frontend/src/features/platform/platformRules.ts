/** Human translations of backend validation strings that arrive as bare field/non-field errors. */

/** `tenant-memberships/` reports "already a member somewhere", "wrong account kind" and "no such user" all as `user` errors. */
export function friendlyMemberError(message: string | undefined): string | undefined {
  if (!message) return undefined;
  if (message.includes('already exists'))
    return 'That user already belongs to a workspace. Each account can be in one workspace at a time.';
  if (message.includes('does not exist')) return 'No account with that user ID.';
  if (message.includes('dedicated tenant account'))
    return 'Agents, platform staff and platform admins cannot be workspace members. Use a dedicated account.';
  return message;
}

/** `platform/staff-assignments/` reports account-kind and duplicate problems as `non_field_errors`. */
export function friendlyAssignmentError(message: string | undefined): string | undefined {
  if (!message) return undefined;
  if (message.includes('dedicated staff account'))
    return 'That user is a workspace member, agent or admin. Staff assignments need a dedicated platform-staff account (created via an invitation).';
  if (message.includes('unique set'))
    return 'That user already has an assignment for this tenant. Edit the existing grants instead.';
  if (message.includes('does not exist')) return 'No account with that user ID.';
  return message;
}

/** Pending invitations past `expires_at` are still reported as `pending` by the API. */
export function invitationDisplayStatus(
  invitation: { status: 'pending' | 'accepted' | 'revoked'; expires_at: string },
  now: number,
): 'pending' | 'accepted' | 'revoked' | 'expired' {
  return invitation.status === 'pending' && new Date(invitation.expires_at).getTime() < now
    ? 'expired'
    : invitation.status;
}
