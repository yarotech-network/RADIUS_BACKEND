import { http } from '@/services/api/http';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type {
  NasDevice,
  NasDeviceCreate,
  NasDeviceUpdate,
  OperationListParams,
  Paginated,
  ProvisionRequest,
  ReplaceSecretsRequest,
  RouterAuditEvent,
  RouterHealth,
  RouterListParams,
  RouterOnboardingCheck,
  RouterOperation,
  RouterRadiusTestRequest,
  RouterRadiusTestResult,
  RouterTransitionRequest,
  RouterTransitionResult,
} from '@/types/api';

export const routersApi = {
  list(params: RouterListParams) {
    return http.get<Paginated<NasDevice>>('/routers/', { ...params });
  },
  async listAll() {
    const first = await http.get<Paginated<NasDevice>>('/routers/', { page_size: 100 });
    if (first.total_pages <= 1) return first.results;
    const rest = await Promise.all(
      Array.from({ length: first.total_pages - 1 }, (_, i) =>
        http.get<Paginated<NasDevice>>('/routers/', { page_size: 100, page: i + 2 }),
      ),
    );
    return [...first.results, ...rest.flatMap((p) => p.results)];
  },
  get(id: string) {
    return http.get<NasDevice>(`/routers/${id}/`);
  },
  create(payload: NasDeviceCreate, idempotencyKey = newIdempotencyKey('router')) {
    return http.post<NasDevice>('/routers/', payload, { idempotencyKey });
  },
  /** Secrets are rejected here (400) — use replaceSecrets. 409 = router busy. */
  update(id: string, payload: NasDeviceUpdate) {
    return http.patch<NasDevice>(`/routers/${id}/`, payload);
  },
  /** 409 when deployed/deploying or an operation is pending. */
  remove(id: string) {
    return http.delete(`/routers/${id}/`);
  },
  transition(
    id: string,
    payload: RouterTransitionRequest,
    idempotencyKey = newIdempotencyKey('transition'),
  ) {
    return http.post<RouterTransitionResult>(`/routers/${id}/transition/`, payload, {
      idempotencyKey,
    });
  },
  /** 202 with the queued operation; 409 already pending; 400 missing WireGuard prerequisites. */
  provisioning(
    id: string,
    payload: ProvisionRequest,
    idempotencyKey = newIdempotencyKey('provision'),
  ) {
    return http.post<RouterOperation>(`/routers/${id}/provisioning/`, payload, { idempotencyKey });
  },
  /** 400 wrong password / nothing to replace; 409 stale (`expected_updated_at`) or busy. */
  replaceSecrets(
    id: string,
    payload: ReplaceSecretsRequest,
    idempotencyKey = newIdempotencyKey('secrets'),
  ) {
    return http.post<NasDevice>(`/routers/${id}/replace-secrets/`, payload, { idempotencyKey });
  },
  /** Throttled 10/min per user; 503 when the RADIUS server is unreachable. */
  test(id: string, payload: RouterRadiusTestRequest) {
    return http.post<RouterRadiusTestResult>(`/routers/${id}/test/`, payload);
  },
  /** Not paginated. */
  checks(id: string) {
    return http.get<RouterOnboardingCheck[]>(`/routers/${id}/checks/`);
  },
  health(id: string) {
    return http.get<RouterHealth>(`/routers/${id}/health/`);
  },
  audit(id: string, params: { page?: number; page_size?: number }) {
    return http.get<Paginated<RouterAuditEvent>>(`/routers/${id}/audit/`, { ...params });
  },
  operations(params: OperationListParams) {
    return http.get<Paginated<RouterOperation>>('/router-operations/', { ...params });
  },
  operation(id: string) {
    return http.get<RouterOperation>(`/router-operations/${id}/`);
  },
};
