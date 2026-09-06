import { http } from '@/services/api/http';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type {
  DeliverRequest,
  DeliveryListParams,
  Paginated,
  PaymentDelivery,
  PaymentListParams,
  PaymentRecovery,
  PaymentTransaction,
  RecoveryListParams,
} from '@/types/api';

/** Customer purchases (`payments/transactions/`, read-only for every member) and the manager-only recovery board. */
export const paymentsApi = {
  list(params: PaymentListParams) {
    return http.get<Paginated<PaymentTransaction>>('/payments/transactions/', { ...params });
  },
  get(id: number) {
    return http.get<PaymentTransaction>(`/payments/transactions/${id}/`);
  },
  recoveryList(params: RecoveryListParams) {
    return http.get<Paginated<PaymentRecovery>>('/payment-recovery/', { ...params });
  },
  recovery(id: number) {
    return http.get<PaymentRecovery>(`/payment-recovery/${id}/`);
  },
  /** Re-verifies with Paystack and fulfils. 409 = verification/plan mismatch, 503 = provider or fulfilment unavailable. */
  retry(id: number, idempotencyKey = newIdempotencyKey('retry')) {
    return http.post<PaymentRecovery>(`/payment-recovery/${id}/retry/`, {}, { idempotencyKey });
  },
  /** 202 with the (possibly already live) delivery; 409 when not fulfilled or when a resend needs acknowledgement. */
  deliver(id: number, payload: DeliverRequest, idempotencyKey = newIdempotencyKey('deliver')) {
    return http.post<PaymentDelivery>(`/payment-recovery/${id}/deliver/`, payload, {
      idempotencyKey,
    });
  },
  deliveries(params: DeliveryListParams) {
    return http.get<Paginated<PaymentDelivery>>('/payment-deliveries/', { ...params });
  },
};
