/** Bytes → "1.2 GB" (base 1024, as network gear reports). */
export function formatBytes(bytes: number | null | undefined, decimals = 1): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB', 'PB'];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(decimals)} ${units[index]}`;
}

/** Megabytes cap → label; 0 = unlimited (backend convention). */
export function formatDataLimit(mb: number | null | undefined): string {
  if (mb === null || mb === undefined) return '—';
  if (mb === 0) return 'Unlimited';
  if (mb >= 1024) {
    const gb = mb / 1024;
    return `${Number.isInteger(gb) ? gb : gb.toFixed(1)} GB`;
  }
  return `${mb} MB`;
}

/** Seconds → "2h 15m", "45s", "3d 4h". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0)
    return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/** Plan duration in hours → "24 hours", "7 days", "30 days", "1 hour". */
export function formatHours(hours: number | string | null | undefined): string {
  const n = typeof hours === 'string' ? Number(hours) : hours;
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  if (n % 24 === 0 && n >= 24) {
    const days = n / 24;
    return `${days} day${days === 1 ? '' : 's'}`;
  }
  return `${n} hour${n === 1 ? '' : 's'}`;
}

/** "5M/10M" → "5 Mbps up · 10 Mbps down" (falls back to raw). */
export function describeRateLimit(rate: string | null | undefined): string {
  if (!rate) return '—';
  const match = rate.trim().match(/^(\d+(?:\.\d+)?)([kKmMgG])?\/(\d+(?:\.\d+)?)([kKmMgG])?$/);
  if (!match) return rate;
  const unit = (u: string | undefined) =>
    ({ k: 'Kbps', m: 'Mbps', g: 'Gbps' })[(u ?? 'm').toLowerCase()] ?? 'Mbps';
  return `${match[1]} ${unit(match[2])} up · ${match[3]} ${unit(match[4])} down`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat().format(value);
}

/** Normalise a MAC address the same way the backend does (upper-case, colon separated). */
export function normaliseMac(input: string): string {
  const compact = input.replace(/[^0-9a-fA-F]/g, '').toUpperCase();
  if (compact.length !== 12) return input.toUpperCase();
  return compact.match(/.{2}/g)?.join(':') ?? input;
}

/** Human-readable label from snake_case / dotted identifiers ("vpn_failed" → "VPN failed"). */
export function humanise(value: string | null | undefined): string {
  if (!value) return '—';
  const words = value.replace(/[._]/g, ' ').trim().split(/\s+/);
  const acronyms = new Set(['vpn', 'radius', 'api', 'ip', 'mac', 'pdf', 'nas', 'id', 'url']);
  return words
    .map((w, i) => {
      const lower = w.toLowerCase();
      if (acronyms.has(lower)) return lower.toUpperCase();
      return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(' ');
}
