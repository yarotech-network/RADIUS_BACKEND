import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route } from 'react-router';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type { AgentProfile } from '@/types/api';
import AgentsPage from './AgentsPage';
import AgentDetailPage from './AgentDetailPage';
import {
  agentCreateSchema,
  createFormToPayload,
  editFormToPatch,
  agentEditSchema,
  formatCommission,
} from '../agentSchemas';

const agent = (extra: Partial<AgentProfile> = {}): AgentProfile => ({
  id: 1,
  user: 8,
  username: 'agent',
  tenant: 5,
  phone: '+2348040000001',
  shop_name: 'Chidi Phones',
  status: 'active',
  commission_rate: '10.00',
  wallet_balance: 250000,
  created_at: '2026-09-01T10:00:00Z',
  ...extra,
});

describe('agent schemas', () => {
  it('sends commission as a 2-decimal string and omits blanks', () => {
    const parsed = agentCreateSchema.parse({
      username: 'chidi',
      email: 'c@x.com',
      password: 'Passw0rd!2026',
      phone: '+2348040000009',
      shop_name: '',
      commission_rate: '12.5',
    });
    expect(createFormToPayload(parsed)).toEqual({
      username: 'chidi',
      email: 'c@x.com',
      password: 'Passw0rd!2026',
      phone: '+2348040000009',
      commission_rate: '12.50',
    });
  });
  it('patches only changed fields and formats commission for display', () => {
    const parsed = agentEditSchema.parse({
      phone: '+2348040000001',
      shop_name: 'Chidi Phones & More',
      commission_rate: '10',
    });
    expect(editFormToPatch(parsed, agent())).toEqual({ shop_name: 'Chidi Phones & More' });
    expect(formatCommission('12.50')).toBe('12.5');
    expect(formatCommission('10.00')).toBe('10');
  });
});

describe('AgentsPage', () => {
  it('lists agents, filters by status and creates a new agent idempotently', async () => {
    const seen: URL[] = [];
    const created: { key: string | null; body: Record<string, unknown> }[] = [];
    server.use(
      http.get(`${API}/tenant/agents/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(
          paginated([
            agent(),
            agent({
              id: 2,
              username: 'agent2',
              shop_name: 'Waiting Shop',
              status: 'pending',
              wallet_balance: null,
            }),
          ]),
        );
      }),
      http.post(`${API}/tenant/agents/`, async ({ request }) => {
        created.push({
          key: request.headers.get('Idempotency-Key'),
          body: (await request.json()) as Record<string, unknown>,
        });
        return HttpResponse.json(
          agent({ id: 3, username: 'newagent', status: 'pending', wallet_balance: 0 }),
          { status: 201 },
        );
      }),
    );
    renderPage(<AgentsPage />, {
      path: '/agents',
      extraRoutes: <Route path="/agents/:id" element={<div>agent detail</div>} />,
    });
    const table = await screen.findByRole('table', { name: 'Agents' });
    expect(await within(table).findByText('agent2')).toBeInTheDocument();
    expect(within(table).getByText('₦2,500.00')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'pending');
    await waitFor(() => expect(seen.at(-1)?.searchParams.get('status')).toBe('pending'));

    await userEvent.click(screen.getByRole('button', { name: 'Add agent' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add agent' });
    await userEvent.type(within(dialog).getByLabelText(/Username/), 'newagent');
    await userEvent.type(within(dialog).getByLabelText(/Email/), 'new@example.com');
    await userEvent.type(within(dialog).getByLabelText(/Temporary password/), 'Passw0rd!2026');
    await userEvent.type(within(dialog).getByLabelText(/Phone/), '+2348040000003');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add agent' }));
    expect(await screen.findByText('agent detail')).toBeInTheDocument();
    expect(created).toHaveLength(1);
    expect(created[0]?.key).toMatch(/^[A-Za-z0-9_.:-]{16,128}$/);
    expect(created[0]?.body).toEqual({
      username: 'newagent',
      email: 'new@example.com',
      password: 'Passw0rd!2026',
      phone: '+2348040000003',
    });
  });

  it('maps field errors from the API onto the form', async () => {
    server.use(
      http.get(`${API}/tenant/agents/`, () => HttpResponse.json(paginated([]))),
      http.post(`${API}/tenant/agents/`, () =>
        HttpResponse.json({ username: ['Username already taken.'] }, { status: 400 }),
      ),
    );
    renderPage(<AgentsPage />, { path: '/agents' });
    await userEvent.click((await screen.findAllByRole('button', { name: 'Add agent' }))[0]!);
    const dialog = await screen.findByRole('dialog', { name: 'Add agent' });
    await userEvent.type(within(dialog).getByLabelText(/Username/), 'agent');
    await userEvent.type(within(dialog).getByLabelText(/Email/), 'a@example.com');
    await userEvent.type(within(dialog).getByLabelText(/Temporary password/), 'Passw0rd!2026');
    await userEvent.type(within(dialog).getByLabelText(/Phone/), '+2348040000003');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add agent' }));
    expect(await within(dialog).findByText('Username already taken.')).toBeInTheDocument();
  });
});

describe('AgentDetailPage', () => {
  it('approves a pending agent after confirmation and lists their sales', async () => {
    let current = agent({ status: 'pending', wallet_balance: null });
    const approvals: string[] = [];
    server.use(
      http.get(`${API}/tenant/agents/:id/`, () => HttpResponse.json(current)),
      http.post(`${API}/tenant/agents/:id/approve/`, ({ request }) => {
        approvals.push(request.headers.get('Idempotency-Key') ?? '');
        current = { ...current, status: 'active' };
        return HttpResponse.json(current);
      }),
      http.get(`${API}/vouchers/`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('search')).toBe('agent');
        return HttpResponse.json(
          paginated([
            {
              id: 9,
              username: 'AG10009',
              plan: 1,
              plan_name: 'Daily 1GB',
              plan_duration: '24',
              price_display: '₦500',
              tenant: 5,
              tenant_name: 'Wuse Hotspot',
              agent: 1,
              agent_name: 'agent',
              status: 'unused',
              generation_source: 'agent',
              device_limit: 1,
              expires_at: null,
              activated_at: null,
              created_at: '2026-09-05T09:00:00Z',
            },
          ]),
        );
      }),
    );
    renderPage(<AgentDetailPage />, { path: '/agents/:id', route: '/agents/1' });
    await screen.findByRole('heading', { name: /agent/ });
    expect(screen.getByText('Awaiting approval')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Suspend' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Approve agent' }));
    await waitFor(() => expect(approvals).toHaveLength(1));
    expect(await screen.findByRole('button', { name: 'Suspend' })).toBeInTheDocument();
    expect(screen.queryByText('Awaiting approval')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Vouchers sold' }));
    const table = await screen.findByRole('table', { name: 'Vouchers sold' });
    expect(await within(table).findByText('AG10009')).toBeInTheDocument();
  });
});
