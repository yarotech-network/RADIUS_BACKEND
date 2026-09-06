import { STORAGE_KEYS } from '@/app/config/constants';

export type CheckoutKind = 'voucher' | 'wallet' | 'subscription';

export interface PendingCheckout {
  kind: CheckoutKind;
  reference: string;
  /** Storefront slug for voucher purchases (so the result page can link back). */
  slug?: string;
  planName?: string;
  amount?: number;
  startedAt: string;
}

/**
 * The backend does not pass a callback URL to Paystack (gap #9), so the browser may come back
 * with only `?reference=` — or with nothing at all. Remember the last checkout locally so the
 * result pages can recover it.
 */
export const pendingCheckout = {
  save(entry: Omit<PendingCheckout, 'startedAt'>) {
    try {
      localStorage.setItem(
        STORAGE_KEYS.pendingCheckout,
        JSON.stringify({ ...entry, startedAt: new Date().toISOString() }),
      );
    } catch {
      /* private mode: the reference is still in the URL */
    }
  },
  load(): PendingCheckout | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEYS.pendingCheckout);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as PendingCheckout;
      return typeof parsed.reference === 'string' && typeof parsed.kind === 'string'
        ? parsed
        : null;
    } catch {
      return null;
    }
  },
  clear() {
    try {
      localStorage.removeItem(STORAGE_KEYS.pendingCheckout);
    } catch {
      /* ignore */
    }
  },
};
