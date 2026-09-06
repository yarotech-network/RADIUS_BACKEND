import { http } from '@/services/api/http';
import type { NasDevice, Paginated, RouterListParams } from '@/types/api';

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
};
