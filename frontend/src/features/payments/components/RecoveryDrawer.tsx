import { useState } from 'react';
import { Link } from 'react-router';
import { Mail, RefreshCw, RotateCcw } from 'lucide-react';
import { Button, Checkbox, DescriptionList, Dialog, Skeleton } from '@/components/ui';
import { Alert, EmptyState, ErrorState, QueryBoundary, useToast } from '@/components/feedback';
import { StatusBadge } from '@/components/layout';
import { usePrincipal } from '@/app/auth/useAuth';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { formatKobo } from '@/lib/formatting/money';
import { can } from '@/services/auth/principal';
import { errorMessage, isApiError } from '@/services/api/errors';
import type { PaymentDelivery, PaymentRecovery } from '@/types/api';
import { useDeliverCredentials, useDeliveries, useRecovery, useRetryFulfillment } from '../queries';
import {
  DELIVERY_LABELS,
  FULFILLMENT_LABELS,
  canDeliver,
  canRetry,
  deliveryNeedsAcknowledgement,
  isDeliveryLive,
} from '../paymentRules';

export function RecoveryDrawer({
  paymentId,
  onClose,
}: {
  paymentId: number | null;
  onClose: () => void;
}) {
  const query = useRecovery(paymentId ?? NaN);
  return (
    <Dialog
      open={paymentId !== null}
      onClose={onClose}
      variant="drawer"
      size="md"
      title="Recover payment"
      description={query.data?.reference}
    >
      {paymentId !== null && (
        <QueryBoundary
          query={query}
          compact
          errorTitle="Payment not found"
          skeleton={<Skeleton className="h-64 w-full" />}
        >
          {(row) => <RecoveryDetail row={row} />}
        </QueryBoundary>
      )}
    </Dialog>
  );
}

function RecoveryDetail({ row }: { row: PaymentRecovery }) {
  const principal = usePrincipal();
  const canAct = can(principal, 'payments.recovery.act');
  const toast = useToast();
  const retry = useRetryFulfillment();
  const deliver = useDeliverCredentials();
  const deliveries = useDeliveries(row.id);
  const [notice, setNotice] = useState<{
    tone: 'danger' | 'warning' | 'info';
    title: string;
    body?: string;
  } | null>(null);
  const [ackOpen, setAckOpen] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const live = deliveries.data?.results.some(isDeliveryLive) ?? false;

  async function runRetry() {
    setNotice(null);
    try {
      const updated = await retry.mutateAsync(row.id);
      if (updated.fulfillment_status === 'fulfilled')
        toast.success('Voucher issued', 'Fulfilment succeeded. You can now email the credentials.');
      else
        toast.info(
          'Verification complete',
          `Status is now “${FULFILLMENT_LABELS[updated.fulfillment_status]}”.`,
        );
    } catch (error) {
      if (isApiError(error) && error.status === 503)
        setNotice({
          tone: 'warning',
          title: 'Could not reach the payment provider',
          body: `${errorMessage(error)} Nothing changed — try again in a moment.`,
        });
      else if (isApiError(error) && error.status === 409)
        setNotice({
          tone: 'danger',
          title: 'Payment did not verify',
          body: `${errorMessage(error)} Check the reference in the Paystack dashboard before retrying.`,
        });
      else setNotice({ tone: 'danger', title: 'Retry failed', body: errorMessage(error) });
    }
  }

  async function runDeliver(ack: boolean) {
    setNotice(null);
    try {
      const delivery = await deliver.mutateAsync({
        id: row.id,
        payload: ack ? { acknowledge_duplicate_risk: true } : {},
      });
      setAckOpen(false);
      setAcknowledged(false);
      toast.success(
        isDeliveryLive(delivery) ? 'Email queued' : 'Delivery recorded',
        `Delivery is ${DELIVERY_LABELS[delivery.status].toLowerCase()}.`,
      );
    } catch (error) {
      if (isApiError(error) && error.status === 409 && /acknowledge/i.test(error.message))
        setAckOpen(true);
      else if (isApiError(error) && error.status === 409)
        setNotice({ tone: 'warning', title: 'Cannot send yet', body: errorMessage(error) });
      else
        setNotice({
          tone: 'danger',
          title: 'Could not queue the email',
          body: errorMessage(error),
        });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface-muted px-4 py-3">
        <span className="text-2xl font-semibold text-ink-900 tabular-nums">
          {formatKobo(row.amount)}
        </span>
        <StatusBadge status={row.status} size="md" />
      </div>
      <DescriptionList
        columns={2}
        items={[
          {
            label: 'Voucher',
            value: row.voucher ? (
              <Link
                to={`/vouchers/${row.voucher}`}
                className="font-mono text-brand-700 hover:underline"
              >
                #{row.voucher}
              </Link>
            ) : (
              <span className="inline-flex items-center gap-1.5">
                <StatusBadge status={row.fulfillment_status} size="sm" />
                <span className="sr-only">{FULFILLMENT_LABELS[row.fulfillment_status]}</span>
              </span>
            ),
          },
          {
            label: 'Credentials email',
            value: (
              <span className="inline-flex items-center gap-1.5">
                <StatusBadge status={row.delivery_status} size="sm" />
                {live && (
                  <RefreshCw
                    className="h-3 w-3 animate-spin text-brand-700"
                    aria-label="Updating"
                  />
                )}
              </span>
            ),
          },
          {
            label: 'Verified with Paystack',
            value: row.verified_at ? (
              formatDateTime(row.verified_at)
            ) : (
              <span className="text-ink-400">Not yet</span>
            ),
            span: 2,
          },
        ]}
      />

      {notice && (
        <Alert tone={notice.tone} title={notice.title} onDismiss={() => setNotice(null)}>
          {notice.body}
        </Alert>
      )}

      {canAct ? (
        <div className="flex flex-col gap-3 rounded-card border border-border p-4">
          <h3 className="text-sm font-semibold text-ink-900">Actions</h3>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              variant={row.fulfillment_status === 'paid_unfulfilled' ? 'primary' : 'secondary'}
              leadingIcon={<RotateCcw className="h-4 w-4" aria-hidden />}
              onClick={() => void runRetry()}
              loading={retry.isPending}
              disabled={!canRetry(row) || deliver.isPending}
              title={canRetry(row) ? undefined : 'Already fulfilled'}
            >
              Re-verify & issue voucher
            </Button>
            <Button
              variant={
                row.fulfillment_status === 'fulfilled' && row.delivery_status !== 'accepted'
                  ? 'primary'
                  : 'secondary'
              }
              leadingIcon={<Mail className="h-4 w-4" aria-hidden />}
              onClick={() =>
                deliveryNeedsAcknowledgement(row) ? setAckOpen(true) : void runDeliver(false)
              }
              loading={deliver.isPending}
              disabled={!canDeliver(row) || live || retry.isPending}
              title={
                !canDeliver(row)
                  ? 'Only paid payments with a voucher can be emailed'
                  : live
                    ? 'An email is already in progress'
                    : undefined
              }
            >
              {row.delivery_status === 'not_requested' ? 'Email credentials' : 'Resend credentials'}
            </Button>
          </div>
          <p className="text-xs text-ink-500">
            Re-verify asks Paystack for the payment's current state and issues the voucher if it was
            paid. Emailing sends the voucher to the customer's address on the payment.
          </p>
          {ackOpen && (
            <div className="rounded-card border border-warning-100 bg-warning-50 p-3">
              <p className="text-sm font-medium text-warning-700">
                The customer may already have received this email.
              </p>
              <p className="mt-1 text-xs text-ink-600">
                Resending gives them the same voucher again. Confirm only if they say it never
                arrived.
              </p>
              <Checkbox
                className="mt-2"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                label="I understand this may be a duplicate"
              />
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  onClick={() => void runDeliver(true)}
                  disabled={!acknowledged}
                  loading={deliver.isPending}
                >
                  Resend anyway
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setAckOpen(false);
                    setAcknowledged(false);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-ink-500">
          You can view recovery status; retrying and resending need the payments-support role.
        </p>
      )}

      <section aria-labelledby="deliveries-heading">
        <h3 id="deliveries-heading" className="mb-2 text-sm font-semibold text-ink-900">
          Email history
        </h3>
        {deliveries.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : deliveries.isError ? (
          <ErrorState
            error={deliveries.error}
            onRetry={() => void deliveries.refetch()}
            compact
            title="History could not be loaded"
          />
        ) : deliveries.data.results.length === 0 ? (
          <EmptyState compact title="No emails sent yet" />
        ) : (
          <ul className="divide-y divide-border rounded-card border border-border">
            {deliveries.data.results.map((d) => (
              <DeliveryRow key={d.id} delivery={d} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function DeliveryRow({ delivery }: { delivery: PaymentDelivery }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
      <StatusBadge status={delivery.status} size="sm" />
      <span className="text-ink-700">{DELIVERY_LABELS[delivery.status]}</span>
      {delivery.error_code && (
        <code className="rounded bg-danger-50 px-1.5 py-0.5 text-xs text-danger-700">
          {delivery.error_code}
        </code>
      )}
      <time
        dateTime={delivery.created_at}
        title={formatDateTime(delivery.created_at)}
        className="ml-auto text-xs text-ink-500"
      >
        {formatRelative(delivery.completed_at ?? delivery.created_at)}
      </time>
    </li>
  );
}
