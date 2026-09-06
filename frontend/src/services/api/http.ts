import { env } from '@/app/config/env';
import type { RefreshResponse } from '@/types/api';
import { ApiError, apiErrorFromResponse, networkError } from './errors';
import { toQueryString, type QueryParams } from './queryString';
import { tokenStore } from '@/services/auth/tokenStore';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type ResponseType = 'json' | 'blob' | 'text' | 'void';

export interface RequestOptions {
  method?: HttpMethod;
  path: string;
  query?: QueryParams;
  body?: unknown;
  /** Send `Idempotency-Key`. The caller owns the key so it is reused across retries. */
  idempotencyKey?: string;
  /** Skip auth header + refresh logic (login, register, public endpoints). */
  anonymous?: boolean;
  responseType?: ResponseType;
  signal?: AbortSignal;
  /** Explicit tenant override; defaults to the active tenant context. */
  tenantId?: number | null;
}

export interface HttpResponse<T> {
  data: T;
  status: number;
  headers: Headers;
  /** True when the backend replayed a previously completed idempotent command. */
  replayed: boolean;
}

type SessionExpiredHandler = (reason: 'expired' | 'revoked') => void;

let activeTenantId: number | null = null;
let onSessionExpired: SessionExpiredHandler | null = null;
let refreshInFlight: Promise<string | null> | null = null;

/** Platform staff must send `X-Tenant-ID`; members must not (the server ignores it, but we keep requests clean). */
export function setActiveTenantHeader(tenantId: number | null) {
  activeTenantId = tenantId;
}
export function getActiveTenantHeader(): number | null {
  return activeTenantId;
}
export function setSessionExpiredHandler(handler: SessionExpiredHandler | null) {
  onSessionExpired = handler;
}

function buildUrl(path: string, query?: QueryParams): string {
  const normalised = path.startsWith('/') ? path : `/${path}`;
  return `${env.apiBaseUrl}${normalised}${toQueryString(query)}`;
}

async function parseBody(response: Response, responseType: ResponseType): Promise<unknown> {
  if (response.status === 204 || responseType === 'void') return undefined;
  if (responseType === 'blob') return response.blob();
  if (responseType === 'text') return response.text();
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function parseErrorBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('Content-Type') ?? '';
  try {
    if (contentType.includes('application/json')) return await response.json();
    const text = await response.text();
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text ? { detail: text.slice(0, 200) } : null;
    }
  } catch {
    return null;
  }
}

/**
 * Single-flight refresh. Concurrent 401s share one refresh request. The rotated refresh token is
 * persisted immediately because the previous one is blacklisted server-side.
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  const refresh = tokenStore.getRefresh();
  if (!refresh) return null;
  refreshInFlight = (async () => {
    try {
      const response = await fetch(buildUrl('/auth/token/refresh/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ refresh }),
      });
      if (!response.ok) {
        // 401 = expired/blacklisted refresh; anything else is treated as a failed session too.
        tokenStore.clear();
        return null;
      }
      const data = (await response.json()) as RefreshResponse;
      tokenStore.set({ access: data.access, refresh: data.refresh ?? refresh });
      return data.access;
    } catch {
      // Network failure: keep tokens so the user can retry when back online.
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function execute<T>(options: RequestOptions, attempt: number): Promise<HttpResponse<T>> {
  const {
    method = 'GET',
    path,
    query,
    body,
    idempotencyKey,
    anonymous = false,
    responseType = 'json',
    signal,
  } = options;

  const headers = new Headers({ Accept: responseType === 'json' ? 'application/json' : '*/*' });
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && !isFormData) headers.set('Content-Type', 'application/json');
  if (idempotencyKey) headers.set('Idempotency-Key', idempotencyKey);
  const tenantId = options.tenantId === undefined ? activeTenantId : options.tenantId;
  if (tenantId !== null && tenantId !== undefined) headers.set('X-Tenant-ID', String(tenantId));
  if (!anonymous) {
    const access = tokenStore.getAccess();
    if (access) headers.set('Authorization', `Bearer ${access}`);
  }

  let response: Response;
  try {
    const init: RequestInit = { method, headers };
    if (body !== undefined) init.body = isFormData ? (body as FormData) : JSON.stringify(body);
    if (signal) init.signal = signal;
    response = await fetch(buildUrl(path, query), init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw networkError(cause);
  }

  if (response.status === 401 && !anonymous && attempt === 0) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return execute<T>(options, attempt + 1);
    if (!tokenStore.getRefresh()) {
      onSessionExpired?.('expired');
    }
  }

  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    throw apiErrorFromResponse(response.status, errorBody, response.headers);
  }

  const data = (await parseBody(response, responseType)) as T;
  return {
    data,
    status: response.status,
    headers: response.headers,
    replayed: response.headers.get('Idempotency-Replayed') === 'true',
  };
}

export async function request<T>(options: RequestOptions): Promise<HttpResponse<T>> {
  return execute<T>(options, 0);
}

/** Convenience helpers returning only the parsed body. */
export const http = {
  get<T>(path: string, query?: QueryParams, extra?: Partial<RequestOptions>): Promise<T> {
    return request<T>({ ...extra, method: 'GET', path, ...(query ? { query } : {}) }).then(
      (r) => r.data,
    );
  },
  post<T>(path: string, body?: unknown, extra?: Partial<RequestOptions>): Promise<T> {
    return request<T>({ ...extra, method: 'POST', path, body }).then((r) => r.data);
  },
  put<T>(path: string, body?: unknown, extra?: Partial<RequestOptions>): Promise<T> {
    return request<T>({ ...extra, method: 'PUT', path, body }).then((r) => r.data);
  },
  patch<T>(path: string, body?: unknown, extra?: Partial<RequestOptions>): Promise<T> {
    return request<T>({ ...extra, method: 'PATCH', path, body }).then((r) => r.data);
  },
  delete(path: string, extra?: Partial<RequestOptions>): Promise<void> {
    return request<void>({ ...extra, method: 'DELETE', path, responseType: 'void' }).then(
      () => undefined,
    );
  },
  blob(path: string, query?: QueryParams, extra?: Partial<RequestOptions>): Promise<Blob> {
    return request<Blob>({
      ...extra,
      method: 'GET',
      path,
      ...(query ? { query } : {}),
      responseType: 'blob',
    }).then((r) => r.data);
  },
  text(path: string, query?: QueryParams, extra?: Partial<RequestOptions>): Promise<string> {
    return request<string>({
      ...extra,
      method: 'GET',
      path,
      ...(query ? { query } : {}),
      responseType: 'text',
    }).then((r) => r.data);
  },
};

export { ApiError };
