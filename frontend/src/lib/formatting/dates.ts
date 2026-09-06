const dateTime = new Intl.DateTimeFormat(undefined, {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});
const dateOnly = new Intl.DateTimeFormat(undefined, {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});
const timeOnly = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value);
  return date ? dateTime.format(date) : '—';
}

export function formatDate(value: string | null | undefined): string {
  const date = parseDate(value);
  return date ? dateOnly.format(date) : '—';
}

export function formatTime(value: string | null | undefined): string {
  const date = parseDate(value);
  return date ? timeOnly.format(date) : '—';
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 1000 * 60 * 60 * 24 * 365],
  ['month', 1000 * 60 * 60 * 24 * 30],
  ['week', 1000 * 60 * 60 * 24 * 7],
  ['day', 1000 * 60 * 60 * 24],
  ['hour', 1000 * 60 * 60],
  ['minute', 1000 * 60],
];

/** "3 hours ago" / "in 2 days" / "now". */
export function formatRelative(value: string | Date | null | undefined, now = Date.now()): string {
  const date = value instanceof Date ? value : parseDate(value);
  if (!date) return '—';
  const diff = date.getTime() - now;
  for (const [unit, ms] of UNITS) {
    if (Math.abs(diff) >= ms) return relative.format(Math.round(diff / ms), unit);
  }
  return Math.abs(diff) < 30_000 ? 'just now' : relative.format(Math.round(diff / 1000), 'second');
}

export function isPast(value: string | null | undefined): boolean {
  const date = parseDate(value);
  return date ? date.getTime() < Date.now() : false;
}

/** For `<input type="datetime-local">`: local wall-clock string without seconds. */
export function toDateTimeLocalInput(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Convert a datetime-local input value to an ISO string with offset. */
export function fromDateTimeLocalInput(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}
