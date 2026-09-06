import type { StaffAssignment, User } from '@/types/api';

export const API = 'http://localhost:3000/api/v1';

export function makeUser(role: User['role'], extra: Partial<User> = {}): User {
  return {
    id: 42,
    username: 'ada',
    email: 'ada@example.com',
    first_name: 'Ada',
    last_name: 'Obi',
    phone: '+2348000000000',
    role,
    tenant_name:
      role === 'platform_admin' || role === 'platform_staff' || role === 'user'
        ? null
        : 'Wuse Hotspot',
    tenant_id: role === 'platform_admin' || role === 'platform_staff' || role === 'user' ? null : 5,
    ...extra,
  };
}

export function makeAssignment(
  tenant: number,
  services: StaffAssignment['services'],
): StaffAssignment {
  return {
    id: tenant * 10,
    user: 42,
    tenant,
    services,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  };
}

export function paginated<T>(results: T[]) {
  return { count: results.length, total_pages: 1, current_page: 1, results };
}
