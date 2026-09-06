/** Known audit action keys, grouped for the filter. Unknown keys fall back to a humanised form. */
export const AUDIT_ACTION_GROUPS: { label: string; actions: { value: string; label: string }[] }[] =
  [
    {
      label: 'Vouchers & payments',
      actions: [
        { value: 'vouchers.generated', label: 'Vouchers generated' },
        { value: 'voucher.updated', label: 'Voucher updated' },
        { value: 'voucher.disabled', label: 'Voucher disabled' },
        { value: 'voucher.deleted', label: 'Voucher deleted' },
        { value: 'payment.recovered', label: 'Payment recovery retried' },
        { value: 'payment.delivery_requested', label: 'Credentials email requested' },
      ],
    },
    {
      label: 'Plans',
      actions: [
        { value: 'internetplan.created', label: 'Plan created' },
        { value: 'internetplan.updated', label: 'Plan updated' },
        { value: 'internetplan.deleted', label: 'Plan deleted' },
      ],
    },
    {
      label: 'Routers',
      actions: [
        { value: 'nasdevice.created', label: 'Router added' },
        { value: 'nasdevice.updated', label: 'Router updated' },
        { value: 'nasdevice.deleted', label: 'Router deleted' },
        { value: 'router.provisioning_requested', label: 'Router provisioning requested' },
        { value: 'router.secrets_replaced', label: 'Router secrets replaced' },
        { value: 'command.executed', label: 'Router command executed' },
      ],
    },
    {
      label: 'Devices',
      actions: [
        { value: 'macdevice.created', label: 'Device registered' },
        { value: 'macdevice.updated', label: 'Device updated' },
        { value: 'macdevice.deleted', label: 'Device removed' },
      ],
    },
    {
      label: 'Agents',
      actions: [
        { value: 'agent.created', label: 'Agent created' },
        { value: 'agent.updated', label: 'Agent updated' },
        { value: 'agent.status_changed', label: 'Agent status changed' },
      ],
    },
    {
      label: 'Team',
      actions: [
        { value: 'staff.invited', label: 'Staff invited' },
        { value: 'staff.invitation_accepted', label: 'Invitation accepted' },
        { value: 'staff.invitation_revoked', label: 'Invitation revoked' },
        { value: 'staff.assignment_created', label: 'Assignment created' },
        { value: 'staff.assignment_updated', label: 'Assignment updated' },
        { value: 'staff.assignment_revoked', label: 'Assignment revoked' },
      ],
    },
    {
      label: 'Settings',
      actions: [
        { value: 'tenant.profile_updated', label: 'Business profile updated' },
        { value: 'tenant.settings_updated', label: 'Billing settings updated' },
      ],
    },
  ];

const LABELS = new Map(
  AUDIT_ACTION_GROUPS.flatMap((g) => g.actions.map((a) => [a.value, a.label] as const)),
);

/** "widget.deleted" → "Widget deleted"; known keys use their curated label. */
export function actionLabel(action: string): string {
  const known = LABELS.get(action);
  if (known) return known;
  const [subject = action, verb] = action.split('.');
  const words = [subject.replace(/_/g, ' '), verb?.replace(/_/g, ' ')].filter(Boolean).join(' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export type AuditTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export function actionTone(action: string): AuditTone {
  if (/\.(deleted|revoked|disabled|secrets_replaced)$/.test(action)) return 'danger';
  if (/\.(created|generated|invited|accepted|recovered)$/.test(action)) return 'success';
  if (/\.(status_changed|provisioning_requested|delivery_requested)$/.test(action))
    return 'warning';
  if (/updated$/.test(action)) return 'info';
  return 'neutral';
}

/** "vouchers.voucher:56" → { model: "voucher", pk: "56" } */
export function parseResource(resource: string): { app: string; model: string; pk: string } | null {
  const m = /^([\w-]+)\.([\w-]+):(.+)$/.exec(resource);
  return m ? { app: m[1] ?? '', model: m[2] ?? '', pk: m[3] ?? '' } : null;
}

/** Deep-link for resources that have a page in this app. */
export function resourceLink(resource: string): string | null {
  const parsed = parseResource(resource);
  if (!parsed) return null;
  const { model, pk } = parsed;
  if (model === 'voucher') return `/vouchers/${pk}`;
  if (model === 'nasdevice') return `/routers/${pk}`;
  if (model === 'agent') return `/agents/${pk}`;
  if (model === 'paymenttransaction') return `/payments?payment=${pk}`;
  return null;
}

/** Deep-link inside the platform console (no tenant-scoped pages there). */
export function platformResourceLink(resource: string): string | null {
  const parsed = parseResource(resource);
  if (!parsed) return null;
  const { model, pk } = parsed;
  if (model === 'tenant') return `/platform/tenants/${pk}`;
  if (model === 'staffassignment') return '/platform/staff';
  if (model === 'staffinvitation') return '/platform/staff?view=invitations';
  return null;
}
