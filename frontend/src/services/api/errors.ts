import type { ApiErrorBody } from '@/types/api';

export type ApiErrorKind =
  | 'network'
  | 'validation'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'throttled'
  | 'unavailable'
  | 'server'
  | 'unknown';

/**
 * Normalised API error. Built from the backend `problem` envelope first, then legacy fields
 * (`detail`, `error`, `<field>: [...]`, `non_field_errors`). Never contains stack traces.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  readonly code: string;
  readonly fields: Record<string, string[]>;
  readonly retryAfterSeconds: number | null;
  readonly commandId: string | null;
  readonly replayed: boolean;
  readonly body: ApiErrorBody | null;

  constructor(init: {
    status: number;
    message: string;
    code?: string;
    fields?: Record<string, string[]>;
    retryAfterSeconds?: number | null;
    commandId?: string | null;
    body?: ApiErrorBody | null;
    replayed?: boolean;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.kind = kindFromStatus(init.status);
    this.code = init.code ?? `http_${init.status}`;
    this.fields = init.fields ?? {};
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
    this.commandId = init.commandId ?? null;
    this.body = init.body ?? null;
    this.replayed = init.replayed ?? false;
  }

  get hasFieldErrors(): boolean {
    return Object.keys(this.fields).length > 0;
  }

  /** First message for a field, if any. */
  fieldMessage(field: string): string | undefined {
    return this.fields[field]?.[0];
  }
}

export function kindFromStatus(status: number): ApiErrorKind {
  if (status === 0) return 'network';
  if (status === 400) return 'validation';
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 429) return 'throttled';
  if (status === 503) return 'unavailable';
  if (status >= 500) return 'server';
  return 'unknown';
}

const GENERIC_MESSAGES: Record<ApiErrorKind, string> = {
  network: 'Cannot reach the server. Check your connection and try again.',
  validation: 'Check the highlighted fields.',
  unauthorized: 'Your session has expired. Please sign in again.',
  forbidden: 'You do not have permission to do this.',
  not_found: 'The requested record could not be found.',
  conflict: 'The request conflicts with the current state. Reload and try again.',
  throttled: 'Too many attempts. Please wait a moment and try again.',
  unavailable: 'A required service is temporarily unavailable. Try again shortly.',
  server: 'Something went wrong on the server. Please try again.',
  unknown: 'The request could not be completed.',
};

function toStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === 'string');
  if (typeof value === 'string') return [value];
  if (value && typeof value === 'object') {
    // Nested serializer errors: flatten one level.
    return Object.values(value as Record<string, unknown>).flatMap(toStringArray);
  }
  return [];
}

function extractFields(body: ApiErrorBody): Record<string, string[]> {
  const fields: Record<string, string[]> = {};
  const source =
    body.problem && body.problem.fields && Object.keys(body.problem.fields).length > 0
      ? body.problem.fields
      : body;
  for (const [key, value] of Object.entries(source)) {
    if (['problem', 'detail', 'error', 'message', 'command_id'].includes(key)) continue;
    const messages = toStringArray(value);
    if (messages.length > 0) fields[key] = messages;
  }
  return fields;
}

/** Backend fallbacks that carry no information; prefer a field/detail message when present. */
const GENERIC_PROBLEM_MESSAGES = new Set([
  'The request could not be completed.',
  'Check the submitted fields.',
  'Invalid input.',
]);

function extractMessage(
  status: number,
  body: ApiErrorBody | null,
  fields: Record<string, string[]>,
) {
  const kind = kindFromStatus(status);
  if (!body) return GENERIC_MESSAGES[kind];
  // DRF `ValidationError("text")` raised in a view arrives as `detail: ["text"]` with the generic
  // problem message; the specific text is the useful part.
  const detailList = Array.isArray(body.detail) ? toStringArray(body.detail) : [];
  const specific = detailList[0] ?? fields['non_field_errors']?.[0] ?? fields['detail']?.[0];
  const candidates = [body.problem?.message, body.detail, body.error, body.message];
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      if (GENERIC_PROBLEM_MESSAGES.has(candidate) && specific) return specific;
      return candidate;
    }
  }
  if (specific) return specific;
  return GENERIC_MESSAGES[kind];
}

export function parseRetryAfter(header: string | null): number | null {
  if (!header) return null;
  const seconds = Number.parseInt(header, 10);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds;
  const date = Date.parse(header);
  if (!Number.isNaN(date)) return Math.max(0, Math.round((date - Date.now()) / 1000));
  return null;
}

export function apiErrorFromResponse(status: number, body: unknown, headers: Headers): ApiError {
  const parsed: ApiErrorBody | null =
    body && typeof body === 'object' && !Array.isArray(body) ? (body as ApiErrorBody) : null;
  const fields = parsed ? extractFields(parsed) : {};
  const message = extractMessage(status, parsed, fields);
  return new ApiError({
    status,
    message,
    code: parsed?.problem?.code ?? `http_${status}`,
    fields,
    retryAfterSeconds: parseRetryAfter(headers.get('Retry-After')),
    commandId: typeof parsed?.command_id === 'string' ? parsed.command_id : null,
    body: parsed,
  });
}

export function networkError(cause?: unknown): ApiError {
  const error = new ApiError({ status: 0, message: GENERIC_MESSAGES.network, code: 'network' });
  if (cause instanceof Error) error.cause = cause;
  return error;
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Human message for any thrown value, without leaking internals. */
export function errorMessage(value: unknown, fallback = GENERIC_MESSAGES.unknown): string {
  if (isApiError(value)) return value.message;
  if (value instanceof Error && value.message && import.meta.env.DEV) return value.message;
  return fallback;
}
