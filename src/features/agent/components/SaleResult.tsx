import { CheckCircle2, Printer } from 'lucide-react';
import { Button, CopyButton } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { formatKobo } from '@/lib/formatting/money';
import type { AgentVoucherAllocation } from '@/types/api';

/**
 * Post-sale sheet. New vouchers carry one access code that is both username and password, so the
 * agent can read it out or copy it for the customer. Legacy vouchers (no `access_code`) still
 * need the operator's printed slip for the password.
 */
export function SaleResult({
  vouchers,
  planName,
  onDone,
}: {
  vouchers: AgentVoucherAllocation[];
  planName: string;
  onDone: () => void;
}) {
  const total = vouchers.reduce((sum, v) => sum + v.amount_charged, 0);
  const allSingleCode = vouchers.every((v) => Boolean(v.access_code));
  const usernames = vouchers.map((v) => v.access_code ?? v.voucher_username).join('\n');
  return (
    <section
      aria-live="polite"
      aria-label="Sale complete"
      className="rounded-card border border-success-100 bg-success-50 p-5"
    >
      <div className="flex items-center gap-2 text-success-700">
        <CheckCircle2 className="size-6" aria-hidden />
        <h2 className="text-lg font-semibold">
          {vouchers.length === 1 ? '1 voucher' : `${vouchers.length} vouchers`} sold
        </h2>
      </div>
      <p className="mt-1 text-sm text-ink-700">
        {planName} · {formatKobo(total)} taken from your wallet.
      </p>
      <ul
        aria-label={allSingleCode ? 'Access codes' : 'Voucher usernames'}
        className="mt-4 divide-y divide-success-100 rounded-card border border-success-100 bg-white"
      >
        {vouchers.map((v) => (
          <li key={v.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
            <code className="font-mono text-base font-semibold tracking-wide text-ink-900">
              {v.access_code ?? v.voucher_username}
            </code>
            <CopyButton
              value={v.access_code ?? v.voucher_username}
              label={`Copy ${v.access_code ?? v.voucher_username}`}
            />
          </li>
        ))}
      </ul>
      <Alert tone="info" className="mt-4">
        {allSingleCode
          ? 'Give the customer their access code — they enter it as both username and password on the Wi-Fi login page.'
          : 'Some of these vouchers use a separate password issued by the operator (printed slip) — it is not shown to agents.'}
      </Alert>
      <div className="mt-4 flex flex-wrap gap-2">
        {vouchers.length > 1 && (
          <CopyButton
            value={usernames}
            label={allSingleCode ? 'Copy all codes' : 'Copy all usernames'}
            variant="secondary"
          />
        )}
        <Button
          variant="secondary"
          leadingIcon={<Printer className="size-4" aria-hidden />}
          onClick={() => window.print()}
        >
          Print this page
        </Button>
        <Button onClick={onDone}>Sell another</Button>
      </div>
    </section>
  );
}
