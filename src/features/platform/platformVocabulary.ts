import type { StaffService } from '@/types/api';

/** Human names for the staff service grants (`SERVICES` in `apps/accounts/staff_api.py`). */
export const SERVICE_GROUPS: {
  label: string;
  services: { value: StaffService; label: string; hint: string }[];
}[] = [
  {
    label: 'Routers',
    services: [
      {
        value: 'routers.view',
        label: 'View routers',
        hint: 'Fleet list, detail, health and history',
      },
      {
        value: 'routers.test',
        label: 'Run RADIUS tests',
        hint: 'Trigger the test action on a router',
      },
    ],
  },
  {
    label: 'Live sessions',
    services: [
      { value: 'live_sessions.view', label: 'View live sessions', hint: 'Who is online right now' },
      {
        value: 'live_sessions.disconnect',
        label: 'Disconnect sessions',
        hint: 'Send CoA disconnects',
      },
    ],
  },
  {
    label: 'Payments',
    services: [
      {
        value: 'payments.view',
        label: 'View payments',
        hint: 'Transactions, recovery board, deliveries',
      },
      {
        value: 'payments.support',
        label: 'Payment support',
        hint: 'Re-verify and resend credentials',
      },
    ],
  },
  {
    label: 'Vouchers',
    services: [
      {
        value: 'vouchers.generate',
        label: 'Generate vouchers',
        hint: 'Also grants plan visibility',
      },
      {
        value: 'vouchers.print',
        label: 'View & print vouchers',
        hint: 'Voucher list, detail and print sheets',
      },
    ],
  },
];

const SERVICE_LABELS = new Map<string, string>(
  SERVICE_GROUPS.flatMap((g) => g.services.map((s) => [s.value, s.label] as const)),
);

export function serviceLabel(service: string): string {
  return SERVICE_LABELS.get(service) ?? service;
}

/** Slug rules shared with the backend `SlugField` (letters, digits, hyphen/underscore). */
export const SLUG_PATTERN = /^[a-zA-Z0-9_-]+$/;

export function slugify(input: string): string {
  return input
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50);
}
