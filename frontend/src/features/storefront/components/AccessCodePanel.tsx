import { Mail, Wifi } from 'lucide-react';
import { CopyButton } from '@/components/ui';
import { formatDataLimit, formatHours } from '@/lib/formatting/units';
import type { PaymentCallbackPlan } from '@/types/api';

/**
 * The customer's single access code (username == password) with the steps to connect. Shown on
 * the payment result page only while the backend still reveals the code (voucher unused).
 */
export function AccessCodePanel({
  code,
  tenantName,
  plan,
  emailMasked,
}: {
  code: string;
  tenantName?: string | undefined;
  plan: PaymentCallbackPlan | null;
  emailMasked?: string | undefined;
}) {
  const network = tenantName ?? 'the business';
  return (
    <div className="mt-4">
      <p className="text-sm font-medium text-ink-700">Your access code</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <output
          aria-label="Access code"
          className="rounded border border-success-100 bg-white px-4 py-2 font-mono text-2xl font-semibold tracking-[0.2em] text-ink-900 select-all"
        >
          {code}
        </output>
        <CopyButton value={code} label="Copy access code" />
      </div>
      {plan && (
        <p className="mt-2 text-sm text-ink-700">
          {plan.name} · {formatHours(plan.duration_hours)} · {formatDataLimit(plan.data_limit)}
          {plan.data_limit === 0 ? ' data' : ''}
        </p>
      )}
      <div className="mt-4 rounded-card border border-success-100 bg-white p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink-900">
          <Wifi className="size-4 text-brand-700" aria-hidden />
          How to connect
        </h3>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink-700">
          <li>Join the {network} Wi-Fi network.</li>
          <li>
            On the login page, enter{' '}
            <code className="rounded bg-surface-muted px-1 font-mono text-ink-900">{code}</code> as
            both the username and the password.
          </li>
          <li>Your time starts the first time you log in.</li>
        </ol>
      </div>
      <p className="mt-3 flex items-start gap-2 text-sm text-ink-600">
        <Mail className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          {emailMasked
            ? `A copy is on its way to ${emailMasked}. `
            : 'A copy is being emailed to the address you entered. '}
          Save the code now — for your security it disappears from this page after you log in.
        </span>
      </p>
    </div>
  );
}
