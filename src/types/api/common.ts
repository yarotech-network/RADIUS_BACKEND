/**
 * Cross-cutting API contracts (see analysis/01_BACKEND_AUDIT.md §6).
 */

/** Standard DRF pagination envelope produced by `apps.core.pagination.StandardResultsPagination`. */
export interface Paginated<T> {
  count: number;
  total_pages: number;
  current_page: number;
  results: T[];
}

/** Common list query parameters. */
export interface PageParams {
  page?: number;
  /** Server default 20, max 100. */
  page_size?: number;
  ordering?: string;
  search?: string;
}

/** `problem` envelope added to every /api/ error response by ApiErrorEnvelopeMiddleware. */
export interface ApiProblem {
  code: string;
  message: string;
  fields: Record<string, unknown>;
}

export interface ApiErrorBody {
  problem?: ApiProblem;
  detail?: string;
  error?: string;
  /** Machine-readable error code (e.g. `email_not_verified` on login 403). */
  code?: string;
  message?: string;
  command_id?: string;
  non_field_errors?: string[];
  [field: string]: unknown;
}

/** ISO-8601 datetime string with offset (server TZ Africa/Lagos, USE_TZ=True). */
export type IsoDateTime = string;

/** Integer amount in kobo (NGN). Divide by 100 for naira. */
export type Kobo = number;

export interface SimpleMessage {
  message: string;
}

export interface CheckoutInitResponse {
  authorization_url: string;
  reference: string;
}
