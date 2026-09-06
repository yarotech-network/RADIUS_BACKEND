import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type { InternetPlan, MacDevice } from '@/types/api';
import DevicesPage from './DevicesPage';
import { deviceSchema, formToPatch, formToPayload, normaliseMac } from '../deviceSchemas';

const plan: InternetPlan = {
  id: 1,
  name: 'Daily 1GB',
  price: 50000,
  price_display: '₦500',
  duration_hours: 24,
  rate_limit: '5M/10M',
  data_limit: 1024,
  voucher_prefix: 'WH',
  is_active: true,
  created_at: '2026-09-01T10:00:00Z',
};
const device = (extra: Partial<MacDevice> = {}): MacDevice => ({
  id: 1,
  mac_address: 'AA:BB:CC:DD:EE:FF',
  device_name: 'Lobby TV',
  plan: 1,
  plan_name: 'Daily 1GB',
  tenant: 5,
  is_active: true,
  expires_at: '2027-09-01T10:00:00Z',
  created_at: '2026-09-01T10:00:00Z',
  ...extra,
});

describe('device schemas', () => {
  it('normalises MAC formats and converts the local expiry to ISO', () => {
    expect(normaliseMac('aabb.ccdd.eeff')).toBe('AA:BB:CC:DD:EE:FF');
    expect(normaliseMac('aa-bb-cc-dd-ee-ff')).toBe('AA:BB:CC:DD:EE:FF');
    const parsed = deviceSchema.parse({
      device_name: 'TV',
      mac_address: 'aa-bb-cc-dd-ee-01',
      plan: '1',
      expires_at: '2027-01-01T10:00',
      is_active: true,
    });
    const payload = formToPayload(parsed);
    expect(payload.mac_address).toBe('AA:BB:CC:DD:EE:01');
    expect(payload.plan).toBe(1);
    expect(new Date(payload.expires_at).getTime()).toBe(new Date('2027-01-01T10:00').getTime());
  });
  it('patches only what changed', () => {
    const d = device();
    const parsed = deviceSchema.parse({
      device_name: 'Lobby TV',
      mac_address: 'aa:bb:cc:dd:ee:ff',
      plan: '1',
      expires_at: '2027-09-01T11:00',
      is_active: false,
    });
    const patch = formToPatch(parsed, d);
    expect(patch).not.toHaveProperty('mac_address');
    expect(patch.is_active).toBe(false);
  });
});

describe('DevicesPage', () => {
  it('lists devices with expiry, registers a new one and removes one', async () => {
    const rows = [
      device(),
      device({
        id: 2,
        device_name: 'Old printer',
        mac_address: '00:11:22:33:44:55',
        is_active: false,
        expires_at: '2026-01-01T10:00:00Z',
      }),
    ];
    const created: Record<string, unknown>[] = [];
    const deleted: string[] = [];
    server.use(
      http.get(`${API}/plans/`, () => HttpResponse.json(paginated([plan]))),
      http.get(`${API}/iot-devices/`, () => HttpResponse.json(paginated(rows))),
      http.post(`${API}/iot-devices/`, async ({ request }) => {
        created.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(
          device({ id: 3, device_name: 'Kitchen tablet', mac_address: '11:22:33:44:55:66' }),
          { status: 201 },
        );
      }),
      http.delete(`${API}/iot-devices/:id/`, ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage(<DevicesPage />, { path: '/devices' });
    const table = await screen.findByRole('table', { name: 'Devices' });
    expect(await within(table).findByText('Lobby TV')).toBeInTheDocument();
    expect(within(table).getByText(/Expired/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Register device' }));
    const dialog = await screen.findByRole('dialog', { name: 'Register device' });
    await userEvent.type(within(dialog).getByLabelText(/Device name/), 'Kitchen tablet');
    await userEvent.type(within(dialog).getByLabelText(/MAC address/), '11-22-33-44-55-66');
    await userEvent.selectOptions(await within(dialog).findByLabelText(/Plan/), '1');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Register device' }));
    await waitFor(() => expect(created).toHaveLength(1));
    expect(created[0]).toMatchObject({
      device_name: 'Kitchen tablet',
      mac_address: '11:22:33:44:55:66',
      plan: 1,
      is_active: true,
    });
    expect(typeof created[0]?.expires_at).toBe('string');

    await userEvent.click(within(table).getByRole('button', { name: 'Actions for Old printer' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Remove' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Remove device' }));
    await waitFor(() => expect(deleted).toEqual(['2']));
  });

  it('is read-only for staff', async () => {
    server.use(
      http.get(`${API}/plans/`, () => HttpResponse.json(paginated([plan]))),
      http.get(`${API}/iot-devices/`, () => HttpResponse.json(paginated([device()]))),
    );
    renderPage(<DevicesPage />, { path: '/devices', role: 'staff' });
    const table = await screen.findByRole('table', { name: 'Devices' });
    expect(await within(table).findByText('Lobby TV')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Register device' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument();
  });
});
