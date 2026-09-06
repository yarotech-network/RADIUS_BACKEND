import { http as mswHttp, HttpResponse, delay } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '@/test/server';
import { tokenStore } from '@/services/auth/tokenStore';
import { http, request, setActiveTenantHeader, setSessionExpiredHandler } from './http';
import { ApiError } from './errors';

const BASE = 'http://localhost:3000/api/v1';

beforeEach(() => {
  tokenStore.clear();
  setActiveTenantHeader(null);
  setSessionExpiredHandler(null);
});
afterEach(() => vi.restoreAllMocks());

describe('http client', () => {
  it('sends Bearer, X-Tenant-ID and Idempotency-Key headers and reports replay', async () => {
    tokenStore.set({ access: 'A1', refresh: 'R1' });
    setActiveTenantHeader(7);
    let seen: Headers | null = null;
    server.use(
      mswHttp.post(`${BASE}/vouchers/generate/`, async ({ request: req }) => {
        seen = req.headers;
        return HttpResponse.json([{ id: 1 }], {
          status: 201,
          headers: { 'Idempotency-Replayed': 'true' },
        });
      }),
    );
    const res = await request<{ id: number }[]>({
      method: 'POST',
      path: '/vouchers/generate/',
      body: { plan_id: 1, quantity: 1 },
      idempotencyKey: 'ui-0123456789abcdef',
    });
    expect(res.status).toBe(201);
    expect(res.replayed).toBe(true);
    expect(res.data).toEqual([{ id: 1 }]);
    expect(seen!.get('Authorization')).toBe('Bearer A1');
    expect(seen!.get('X-Tenant-ID')).toBe('7');
    expect(seen!.get('Idempotency-Key')).toBe('ui-0123456789abcdef');
    expect(seen!.get('Content-Type')).toBe('application/json');
  });

  it('serialises query params and drops empty values', async () => {
    let url = '';
    server.use(
      mswHttp.get(`${BASE}/vouchers/`, ({ request: req }) => {
        url = req.url;
        return HttpResponse.json({ count: 0, results: [] });
      }),
    );
    await http.get(
      '/vouchers/',
      { page: 2, status: 'active', search: '', plan: undefined, is_active: true },
      { anonymous: true },
    );
    const params = new URL(url).searchParams;
    expect(params.get('page')).toBe('2');
    expect(params.get('status')).toBe('active');
    expect(params.get('is_active')).toBe('true');
    expect(params.has('search')).toBe(false);
    expect(params.has('plan')).toBe(false);
  });

  it('throws a normalised ApiError for non-2xx responses', async () => {
    server.use(
      mswHttp.get(`${BASE}/plans/`, () =>
        HttpResponse.json(
          { problem: { code: 'http_403', message: 'Forbidden for agents', fields: {} } },
          { status: 403 },
        ),
      ),
    );
    const error = await http
      .get('/plans/', undefined, { anonymous: true })
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 403,
      kind: 'forbidden',
      message: 'Forbidden for agents',
    });
  });

  it('converts fetch failures into a network ApiError', async () => {
    server.use(mswHttp.get(`${BASE}/health/`, () => HttpResponse.error()));
    await expect(http.get('/health/', undefined, { anonymous: true })).rejects.toMatchObject({
      status: 0,
      kind: 'network',
    });
  });

  it('refreshes once for concurrent 401s, stores the rotated refresh token and retries', async () => {
    tokenStore.set({ access: 'expired', refresh: 'R1' });
    let refreshCalls = 0;
    let dataCalls = 0;
    server.use(
      mswHttp.post(`${BASE}/auth/token/refresh/`, async ({ request: req }) => {
        refreshCalls += 1;
        const body = (await req.json()) as { refresh: string };
        expect(body.refresh).toBe('R1');
        await delay(20);
        return HttpResponse.json({ access: 'A2', refresh: 'R2' });
      }),
      mswHttp.get(`${BASE}/dashboard/stats/`, ({ request: req }) => {
        dataCalls += 1;
        if (req.headers.get('Authorization') !== 'Bearer A2')
          return HttpResponse.json({ detail: 'expired' }, { status: 401 });
        return HttpResponse.json({ total_vouchers: 1 });
      }),
    );
    const [a, b, c] = await Promise.all([
      http.get('/dashboard/stats/'),
      http.get('/dashboard/stats/'),
      http.get('/dashboard/stats/'),
    ]);
    expect(a).toEqual({ total_vouchers: 1 });
    expect(b).toEqual(a);
    expect(c).toEqual(a);
    expect(refreshCalls).toBe(1);
    expect(dataCalls).toBe(6); // 3 rejected + 3 retried
    expect(tokenStore.getAccess()).toBe('A2');
    expect(tokenStore.getRefresh()).toBe('R2');
  });

  it('clears the session and notifies when the refresh token is rejected', async () => {
    tokenStore.set({ access: 'expired', refresh: 'dead' });
    const onExpired = vi.fn();
    setSessionExpiredHandler(onExpired);
    server.use(
      mswHttp.post(`${BASE}/auth/token/refresh/`, () =>
        HttpResponse.json(
          { detail: 'Token is blacklisted', code: 'token_not_valid' },
          { status: 401 },
        ),
      ),
      mswHttp.get(`${BASE}/auth/user/`, () =>
        HttpResponse.json({ detail: 'expired' }, { status: 401 }),
      ),
    );
    await expect(http.get('/auth/user/')).rejects.toMatchObject({
      status: 401,
      kind: 'unauthorized',
    });
    expect(onExpired).toHaveBeenCalledWith('expired');
    expect(tokenStore.hasSession()).toBe(false);
  });

  it('does not attempt a refresh for anonymous requests', async () => {
    tokenStore.set({ access: 'x', refresh: 'y' });
    let refreshCalls = 0;
    server.use(
      mswHttp.post(`${BASE}/auth/token/refresh/`, () => {
        refreshCalls += 1;
        return HttpResponse.json({ access: 'n', refresh: 'm' });
      }),
      mswHttp.post(`${BASE}/auth/login/`, () =>
        HttpResponse.json({ detail: 'No active account' }, { status: 401 }),
      ),
    );
    await expect(
      http.post('/auth/login/', { username: 'a', password: 'b' }, { anonymous: true }),
    ).rejects.toMatchObject({ status: 401 });
    expect(refreshCalls).toBe(0);
  });

  it('returns blobs and text for non-JSON endpoints', async () => {
    server.use(
      mswHttp.get(
        `${BASE}/vouchers/pdf/`,
        () =>
          new HttpResponse(new Uint8Array([37, 80, 68, 70]), {
            headers: { 'Content-Type': 'application/pdf' },
          }),
      ),
      mswHttp.get(
        `${BASE}/vouchers/print/`,
        () => new HttpResponse('<html>print</html>', { headers: { 'Content-Type': 'text/html' } }),
      ),
    );
    const blob = await http.blob('/vouchers/pdf/', undefined, { anonymous: true });
    expect(blob.size).toBe(4);
    const html = await http.text('/vouchers/print/', undefined, { anonymous: true });
    expect(html).toContain('print');
  });

  it('treats 204 as void', async () => {
    server.use(mswHttp.delete(`${BASE}/plans/3/`, () => new HttpResponse(null, { status: 204 })));
    await expect(http.delete('/plans/3/', { anonymous: true })).resolves.toBeUndefined();
  });
});
