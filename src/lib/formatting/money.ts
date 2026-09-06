import type { Kobo } from '@/types/api';

const NGN = new Intl.NumberFormat('en-NG', {
  style: 'currency',
  currency: 'NGN',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const NGN_WHOLE = new Intl.NumberFormat('en-NG', {
  style: 'currency',
  currency: 'NGN',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/** Format an integer kobo amount as ₦. `compact` drops the decimals when they are zero. */
export function formatKobo(
  amount: Kobo | null | undefined,
  options?: { compact?: boolean },
): string {
  if (amount === null || amount === undefined || !Number.isFinite(amount)) return '—';
  const naira = amount / 100;
  if (options?.compact && Number.isInteger(naira)) return NGN_WHOLE.format(naira);
  return NGN.format(naira);
}

/** Parse a user-typed naira string ("1,250.50") into integer kobo. Returns null when invalid. */
export function parseNairaToKobo(input: string): Kobo | null {
  const cleaned = input.replace(/[₦,\s]/g, '');
  if (cleaned === '' || !/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const [whole = '0', fraction = ''] = cleaned.split('.');
  const kobo = Number(whole) * 100 + Number((fraction + '00').slice(0, 2));
  return Number.isSafeInteger(kobo) ? kobo : null;
}

export function koboToNairaInput(amount: Kobo | null | undefined): string {
  if (amount === null || amount === undefined) return '';
  return (amount / 100).toFixed(Number.isInteger(amount / 100) ? 0 : 2);
}
