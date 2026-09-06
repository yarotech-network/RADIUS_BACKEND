import type {
  DeliveryStatus,
  FulfillmentStatus,
  PaymentDelivery,
  PaymentRecovery,
  PaymentStatus,
  PaymentTransaction,
} from '@/types/api';

export const PAYMENT_STATUS_FILTERS: { value: PaymentStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'success', label: 'Successful' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
  { value: 'abandoned', label: 'Abandoned' },
];

export const FULFILLMENT_LABELS: Record<FulfillmentStatus, string> = {
  fulfilled: 'Voucher issued',
  paid_unfulfilled: 'Paid, no voucher',
  unverified: 'Not verified',
};

export const DELIVERY_LABELS: Record<DeliveryStatus, string> = {
  not_requested: 'Not sent',
  pending: 'Queued',
  sending: 'Sending',
  accepted: 'Sent',
  failed: 'Failed',
  unknown: 'Unknown',
};

export function isDeliveryLive(delivery: Pick<PaymentDelivery, 'status'>): boolean {
  return delivery.status === 'pending' || delivery.status === 'sending';
}

/** A payment the customer paid for but never received a voucher — the case the recovery board exists for. */
export function needsAttention(row: PaymentRecovery): boolean {
  return (
    row.fulfillment_status === 'paid_unfulfilled' ||
    (row.fulfillment_status === 'fulfilled' && row.delivery_status === 'failed')
  );
}

/** Retry re-verifies with Paystack; useful for anything that has not produced a voucher yet. */
export function canRetry(row: PaymentRecovery): boolean {
  return row.fulfillment_status !== 'fulfilled' && row.status !== 'abandoned';
}

/** Server rule: only `success` payments with a voucher can be delivered. */
export function canDeliver(row: PaymentRecovery): boolean {
  return row.status === 'success' && row.voucher !== null;
}

/** Server asks for explicit acknowledgement when a previous delivery may have reached the customer. */
export function deliveryNeedsAcknowledgement(row: PaymentRecovery): boolean {
  return row.delivery_status === 'accepted' || row.delivery_status === 'unknown';
}

export function customerLabel(
  payment: Pick<PaymentTransaction, 'customer_name' | 'customer_email'>,
): string {
  return payment.customer_name || payment.customer_email;
}
