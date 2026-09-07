/**
 * Error reporting (phase 11 — production readiness).
 *
 * One funnel for unexpected errors: React error boundaries, `window.onerror`
 * and `unhandledrejection` all call `reportError`. The default sink logs in
 * development and, in production, POSTs a small JSON report to
 * `VITE_ERROR_REPORT_ENDPOINT` when that variable is configured (best effort,
 * `keepalive`, no retries — reporting must never amplify an incident).
 */
export interface ErrorContext {
  /** Where the error originated, e.g. 'error-boundary' or 'window.error'. */
  source: string;
  [key: string]: unknown;
}

type Sink = (error: unknown, context: ErrorContext) => void;

function serialize(error: unknown): Record<string, unknown> {
  if (error instanceof Error) {
    return { name: error.name, message: error.message, stack: error.stack };
  }
  return { message: String(error) };
}

function defaultSink(error: unknown, context: ErrorContext): void {
  if (import.meta.env.DEV) {
    console.error('[error-report]', context.source, error, context);
    return;
  }
  const endpoint = import.meta.env.VITE_ERROR_REPORT_ENDPOINT;
  if (!endpoint) return; // Not configured — no-op.
  try {
    void fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        detail: serialize(error),
        context,
        url: window.location.href,
        userAgent: navigator.userAgent,
        at: new Date().toISOString(),
      }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    /* Reporting must never throw. */
  }
}

let sink: Sink = defaultSink;

/** Report an unexpected error. Never throws. */
export function reportError(error: unknown, context: ErrorContext): void {
  try {
    sink(error, context);
  } catch {
    /* A broken sink must not break the app. */
  }
}

/** Replace the sink (tests, embedding apps). `null` restores the default. */
export function setErrorSink(next: Sink | null): void {
  sink = next ?? defaultSink;
}

let installed = false;

/** Install `window` -level handlers (idempotent). Called once from `main.tsx`. */
export function installGlobalErrorReporting(): void {
  if (installed) return;
  installed = true;
  window.addEventListener('error', (event) => {
    reportError(event.error ?? event.message, { source: 'window.error' });
  });
  window.addEventListener('unhandledrejection', (event) => {
    reportError(event.reason, { source: 'unhandledrejection' });
  });
}
