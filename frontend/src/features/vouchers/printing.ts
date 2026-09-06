import { vouchersApi } from './api';

export interface PrintedCredential {
  id: number;
  username: string;
  password: string;
  plan: string;
  duration: string;
}

/**
 * The backend returns a tiny HTML page per voucher; extract the credential fields so the UI can
 * render its own print sheet (many cards per page) instead of one browser tab per voucher.
 */
export function parsePrintHtml(id: number, html: string): PrintedCredential | null {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const fields: Record<string, string> = {};
  for (const p of Array.from(doc.querySelectorAll('p'))) {
    const label = p.querySelector('strong')?.textContent?.replace(':', '').trim().toLowerCase();
    if (!label) continue;
    const value = (p.textContent ?? '')
      .replace(p.querySelector('strong')?.textContent ?? '', '')
      .trim();
    fields[label] = value;
  }
  if (!fields.username || !fields.password) return null;
  return {
    id,
    username: fields.username,
    password: fields.password,
    plan: fields.plan ?? '',
    duration: fields.duration ?? '',
  };
}

export interface BulkPrintProgress {
  done: number;
  total: number;
}

/**
 * Sequentially fetch credentials for a batch (keeps the server load predictable and lets the UI
 * show progress). Failures are collected instead of aborting the whole batch.
 */
export async function fetchCredentials(
  ids: readonly number[],
  onProgress?: (p: BulkPrintProgress) => void,
  signal?: AbortSignal,
) {
  const ok: PrintedCredential[] = [];
  const failed: number[] = [];
  let done = 0;
  for (const id of ids) {
    if (signal?.aborted) break;
    try {
      const html = await vouchersApi.printHtml(id);
      const parsed = parsePrintHtml(id, html);
      if (parsed) ok.push(parsed);
      else failed.push(id);
    } catch {
      failed.push(id);
    }
    done += 1;
    onProgress?.({ done, total: ids.length });
  }
  return { ok, failed };
}

function escapeHtml(value: string) {
  return value.replace(
    /[&<>"']/g,
    (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch] ?? ch,
  );
}

/** Print sheet: 2 columns of credential cards sized for A4/Letter, plain black on white. */
export function buildPrintSheet(
  credentials: readonly PrintedCredential[],
  options: { tenantName: string; footnote?: string },
) {
  const cards = credentials
    .map(
      (c) => `
      <article class="card">
        <header>${escapeHtml(options.tenantName)}</header>
        <div class="row"><span>Plan</span><strong>${escapeHtml(c.plan)}${c.duration ? ` · ${escapeHtml(c.duration)}` : ''}</strong></div>
        <div class="row"><span>Username</span><code>${escapeHtml(c.username)}</code></div>
        <div class="row"><span>Password</span><code>${escapeHtml(c.password)}</code></div>
        ${options.footnote ? `<footer>${escapeHtml(options.footnote)}</footer>` : ''}
      </article>`,
    )
    .join('');
  return `<!doctype html><html><head><meta charset="utf-8"><title>Vouchers — ${escapeHtml(options.tenantName)}</title>
<style>
  @page { margin: 12mm; }
  * { box-sizing: border-box; }
  body { font: 11pt/1.35 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #000; margin: 0; }
  .sheet { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6mm; }
  .card { border: 1px dashed #000; padding: 5mm; break-inside: avoid; }
  header { font-weight: 700; font-size: 12pt; margin-bottom: 3mm; }
  .row { display: flex; justify-content: space-between; gap: 4mm; padding: 1mm 0; }
  .row span { color: #444; }
  code { font: 700 13pt/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.04em; }
  footer { margin-top: 3mm; font-size: 8.5pt; color: #444; }
</style></head><body><main class="sheet">${cards}</main></body></html>`;
}
