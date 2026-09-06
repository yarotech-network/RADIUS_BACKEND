import { http, request } from '@/services/api/http';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type {
  Paginated,
  SimpleMessage,
  Voucher,
  VoucherGenerateRequest,
  VoucherListParams,
  VoucherManualWrite,
} from '@/types/api';

export const vouchersApi = {
  list(params: VoucherListParams) {
    return http.get<Paginated<Voucher>>('/vouchers/', { ...params });
  },
  get(id: number) {
    return http.get<Voucher>(`/vouchers/${id}/`);
  },
  /** Returns the created batch (passwords are NOT included — see API gap #2). */
  async generate(payload: VoucherGenerateRequest, idempotencyKey = newIdempotencyKey('gen')) {
    const res = await request<Voucher[]>({
      method: 'POST',
      path: '/vouchers/generate/',
      body: payload,
      idempotencyKey,
    });
    return { vouchers: res.data, replayed: res.replayed };
  },
  createManual(payload: VoucherManualWrite, idempotencyKey = newIdempotencyKey('voucher')) {
    return http.post<Voucher>('/vouchers/', payload, { idempotencyKey });
  },
  update(id: number, payload: Partial<VoucherManualWrite>) {
    return http.patch<Voucher>(`/vouchers/${id}/`, payload);
  },
  remove(id: number) {
    return http.delete(`/vouchers/${id}/`);
  },
  disable(id: number, idempotencyKey = newIdempotencyKey('disable')) {
    return http.post<SimpleMessage>(`/vouchers/${id}/disable/`, undefined, { idempotencyKey });
  },
  /** Server-rendered credential card (HTML). The only place the password is readable. */
  printHtml(id: number) {
    return http.text(`/vouchers/${id}/print/`);
  },
  /** May answer 503 when the PDF renderer is not installed on the server. */
  pdf(id: number) {
    return http.blob(`/vouchers/${id}/pdf/`);
  },
};
