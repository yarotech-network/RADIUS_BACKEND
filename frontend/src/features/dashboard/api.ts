import { http } from '@/services/api/http';
import type {
  DashboardStats,
  DisconnectResult,
  LiveUsersParams,
  LiveUsersResponse,
} from '@/types/api';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';

export const dashboardApi = {
  stats() {
    return http.get<DashboardStats>('/dashboard/stats/');
  },
  liveUsers(params: LiveUsersParams) {
    return http.get<LiveUsersResponse>('/dashboard/live-users/', { ...params });
  },
  disconnect(sessionId: number, idempotencyKey = newIdempotencyKey('kick')) {
    return http.post<DisconnectResult>(
      `/dashboard/live-users/${sessionId}/disconnect/`,
      undefined,
      { idempotencyKey },
    );
  },
};
