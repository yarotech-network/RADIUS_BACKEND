import { CheckCircle2, Printer } from 'lucide-react';
import { Button, CopyButton } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { formatKobo } from '@/lib/formatting/money';
import type { AgentVoucherAllocation } from '@/types/api';

/**
 * Post-sale sheet. The agent API returns usernames only (gap #2) — passwords are printed/delivered
 * by the operator — so the UI is honest about what the agent can hand to the customer.
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
  const usernames = vouchers.map((v) => v.voucher_username).join('\n');
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
      <ul className="mt-4 divide-y divide-success-100 rounded-card border border-success-100 bg-white">
        {vouchers.map((v) => (
          <li key={v.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
            <code className="font-mono text-base font-semibold tracking-wide text-ink-900">
              {v.voucher_username}
            </code>
            <CopyButton value={v.voucher_username} label={`Copy ${v.voucher_username}`} />
          </li>
        ))}
      </ul>
      <Alert tone="info" className="mt-4">
        These are the voucher usernames. The password for each voucher is issued by the operator
        (printed slip or their delivery channel) — it is not shown to agents.
      </Alert>
      <div className="mt-4 flex flex-wrap gap-2">
        {vouchers.length > 1 && (
          <CopyButton value={usernames} label="Copy all usernames" variant="secondary" />
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
