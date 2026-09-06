import { http } from '@/services/api/http';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import type { InternetPlan, InternetPlanWrite, Paginated, PlanListParams } from '@/types/api';

export const plansApi = {
  list(params: PlanListParams) {
    return http.get<Paginated<InternetPlan>>('/plans/', { ...params });
  },
  /** All active plans for pickers (≤100 per page; tenants rarely exceed this). */
  async listAll(options: { activeOnly?: boolean } = {}) {
    const first = await http.get<Paginated<InternetPlan>>('/plans/', {
      page_size: 100,
      ...(options.activeOnly ? { is_active: true } : {}),
    });
    if (first.total_pages <= 1) return first.results;
    const rest = await Promise.all(
      Array.from({ length: first.total_pages - 1 }, (_, i) =>
        http.get<Paginated<InternetPlan>>('/plans/', {
          page_size: 100,
          page: i + 2,
          ...(options.activeOnly ? { is_active: true } : {}),
        }),
      ),
    );
    return [...first.results, ...rest.flatMap((p) => p.results)];
  },
  get(id: number) {
    return http.get<InternetPlan>(`/plans/${id}/`);
  },
  create(payload: InternetPlanWrite, idempotencyKey = newIdempotencyKey('plan')) {
    return http.post<InternetPlan>('/plans/', payload, { idempotencyKey });
  },
  update(id: number, payload: Partial<InternetPlanWrite>) {
    return http.patch<InternetPlan>(`/plans/${id}/`, payload);
  },
  remove(id: number) {
    return http.delete(`/plans/${id}/`);
  },
};
