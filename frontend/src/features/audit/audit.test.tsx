import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server } from '@/test/server';
import { API, paginated } from '@/test/fixtures';
import { renderPage } from '@/test/renderPage';
import type { AuditEvent } from '@/types/api';
import AuditPage from './pages/AuditPage';
import { actionLabel, actionTone, parseResource, resourceLink } from './auditVocabulary';

const event = (extra: Partial<AuditEvent> = {}): AuditEvent => ({
  id: 'evt-1',
  tenant: 5,
  actor: 42,
  action: 'vouchers.generated',
  resource: 'vouchers.voucher:56',
  details: { count: 10, plan: 1 },
  created_at: '2026-09-01T10:00:00Z',
  ...extra,
});

describe('audit vocabulary', () => {
  it('labels known and unknown actions and picks a tone', () => {
    expect(actionLabel('vouchers.generated')).toBe('Vouchers generated');
    expect(actionLabel('macdevice.deleted')).toBe('Macdevice deleted');
    expect(actionLabel('weird')).toBe('Weird');
    expect(actionTone('router.secrets_replaced')).toBe('danger');
    expect(actionTone('agent.created')).toBe('success');
    expect(actionTone('tenant.profile_updated')).toBe('info');
  });
  it('parses resource keys and deep-links the ones with pages', () => {
    expect(parseResource('vouchers.voucher:56')).toEqual({
      app: 'vouchers',
      model: 'voucher',
      pk: '56',
    });
    expect(resourceLink('vouchers.voucher:56')).toBe('/vouchers/56');
    expect(resourceLink('routers.nasdevice:d856aee7')).toBe('/routers/d856aee7');
    expect(resourceLink('tenants.tenant:2')).toBeNull();
    expect(parseResource('garbage')).toBeNull();
  });
});

describe('AuditPage', () => {
  it('lists events, labels the current user, filters by action/actor and expands details', async () => {
    const seen: URL[] = [];
    server.use(
      http.get(`${API}/audit-events/`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json(
          paginated([
            event(),
            event({
              id: 'evt-2',
              actor: 7,
              action: 'router.secrets_replaced',
              resource: 'routers.nasdevice:abc',
              details: {},
            }),
            event({
              id: 'evt-3',
              actor: null,
              action: 'macdevice.deleted',
              resource: 'iot_devices.macdevice:9',
              details: {},
            }),
          ]),
        );
      }),
    );
    renderPage(<AuditPage />, { path: '/audit', role: 'manager' });
    const table = await screen.findByRole('table', { name: 'Audit events' });
    expect(await within(table).findByText('Vouchers generated')).toBeInTheDocument();
    expect(within(table).getByText('You')).toBeInTheDocument();
    expect(within(table).getByText('User #7')).toBeInTheDocument();
    expect(within(table).getByText('System')).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'voucher #56' })).toHaveAttribute(
      'href',
      '/vouchers/56',
    );
    expect(seen[0]?.searchParams.get('ordering')).toBe('-created_at');

    await userEvent.click(within(table).getByRole('button', { name: 'Details' }));
    expect(await within(table).findByText('count')).toBeInTheDocument();
    expect(within(table).getByText('10')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Action'), 'router.secrets_replaced');
    await waitFor(() =>
      expect(seen.at(-1)?.searchParams.get('action')).toBe('router.secrets_replaced'),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Mine' }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.get('actor')).toBe('42'));
  });

  it('shows the empty state', async () => {
    server.use(http.get(`${API}/audit-events/`, () => HttpResponse.json(paginated([]))));
    renderPage(<AuditPage />, { path: '/audit', role: 'owner' });
    expect(await screen.findByText('Nothing recorded yet')).toBeInTheDocument();
  });
});
