import { Link } from 'react-router';
import { LifeBuoy } from 'lucide-react';
import { Button, CopyButton, DescriptionList, Dialog, Skeleton } from '@/components/ui';
import { QueryBoundary } from '@/components/feedback';
import { StatusBadge } from '@/components/layout';
import { usePrincipal } from '@/app/auth/useAuth';
import { formatDateTime } from '@/lib/formatting/dates';
import { formatKobo } from '@/lib/formatting/money';
import { can } from '@/services/auth/principal';
import { usePayment } from '../queries';

export function PaymentDrawer({
  paymentId,
  onClose,
  onOpenRecovery,
}: {
  paymentId: number | null;
  onClose: () => void;
  onOpenRecovery: (id: number) => void;
}) {
  const principal = usePrincipal();
  const canRecover = can(principal, 'payments.recovery.view');
  const query = usePayment(paymentId ?? NaN);
  return (
    <Dialog
      open={paymentId !== null}
      onClose={onClose}
      variant="drawer"
      size="md"
      title="Payment"
      description={query.data ? query.data.reference : undefined}
    >
      {paymentId !== null && (
        <QueryBoundary
          query={query}
          compact
          errorTitle="Payment not found"
          skeleton={<Skeleton className="h-64 w-full" />}
        >
          {(p) => (
            <div className="flex flex-col gap-6">
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface-muted px-4 py-3">
                <span className="text-2xl font-semibold text-ink-900 tabular-nums">
                  {formatKobo(p.amount)}
                </span>
                <StatusBadge status={p.status} size="md" />
              </div>
              <DescriptionList
                columns={2}
                items={[
                  {
                    label: 'Reference',
                    value: (
                      <span className="inline-flex items-center gap-1 font-mono text-[13px]">
                        {p.reference}
                        <CopyButton value={p.reference} label="Copy reference" />
                      </span>
                    ),
                    span: 2,
                  },
                  { label: 'Customer', value: p.customer_name || null },
                  {
                    label: 'Email',
                    value: (
                      <a
                        href={`mailto:${p.customer_email}`}
                        className="text-brand-700 hover:underline"
                      >
                        {p.customer_email}
                      </a>
                    ),
                  },
                  { label: 'Phone', value: p.customer_phone || null, mono: true },
                  { label: 'Paystack reference', value: p.paystack_reference || null, mono: true },
                  {
                    label: 'Voucher',
                    value: p.voucher ? (
                      <Link
                        to={`/vouchers/${p.voucher}`}
                        className="font-mono text-brand-700 hover:underline"
                      >
                        {p.voucher_username}
                      </Link>
                    ) : (
                      <span className="text-ink-400">Not issued</span>
                    ),
                  },
                  { label: 'Plan', value: p.plan ? `#${p.plan}` : null },
                  { label: 'Created', value: formatDateTime(p.created_at) },
                  { label: 'Paid', value: p.paid_at ? formatDateTime(p.paid_at) : null },
                ]}
              />
              {canRecover && p.status === 'success' && (
                <div className="border-t border-border pt-4">
                  <Button
                    variant="secondary"
                    leadingIcon={<LifeBuoy className="h-4 w-4" aria-hidden />}
                    onClick={() => onOpenRecovery(p.id)}
                  >
                    {p.voucher ? 'Resend credentials…' : 'Recover this payment…'}
                  </Button>
                  <p className="mt-2 text-xs text-ink-500">
                    {p.voucher
                      ? 'Email the voucher to the customer again from the recovery board.'
                      : 'The customer paid but no voucher was issued — retry fulfilment from the recovery board.'}
                  </p>
                </div>
              )}
            </div>
          )}
        </QueryBoundary>
      )}
    </Dialog>
  );
}
