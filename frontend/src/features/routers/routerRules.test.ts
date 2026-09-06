import { describe, expect, it } from 'vitest';
import type { NasDevice, RouterOnboardingCheck, RouterOperation } from '@/types/api';
import { ROUTER_TRANSITIONS } from '@/types/api';
import {
  canDeleteRouter,
  checkRows,
  nextStates,
  onboardingStepIndex,
  provisionBlocker,
  transitionIntent,
} from './routerRules';
import {
  createFormToPayload,
  editFormToPatch,
  routerCreateSchema,
  routerEditSchema,
} from './routerSchemas';

const router = (extra: Partial<NasDevice> = {}): NasDevice => ({
  id: 'r1',
  name: 'mikrotik-wuse-01',
  ip_address: '10.100.100.12',
  wireguard_ip: '10.100.100.12',
  wireguard_public_key: 'a'.repeat(43) + '=',
  wireguard_port: 51820,
  routeros_username: 'admin',
  location: 'Wuse',
  tenant: 5,
  tenant_name: 'Wuse Hotspot',
  onboarding_state: 'active',
  deployment_status: 'deployed',
  is_active: true,
  last_seen_at: null,
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
  ...extra,
});
const op = (status: RouterOperation['status']): RouterOperation => ({
  id: 'op',
  router: 'r1',
  action: 'provision',
  status,
  attempts: 1,
  error_code: '',
  created_at: '2026-09-01T10:00:00Z',
  completed_at: null,
});

describe('onboarding rules', () => {
  it('mirrors the backend transition table', () => {
    expect(nextStates('pending')).toEqual(['reviewed']);
    expect(nextStates('testing_radius')).toEqual(ROUTER_TRANSITIONS.testing_radius);
    expect(nextStates('active')).toEqual(['suspended']);
  });
  it('classifies transitions so the UI can pick a button style', () => {
    expect(transitionIntent('reviewed', 'approved')).toBe('forward');
    expect(transitionIntent('reviewed', 'pending')).toBe('back');
    expect(transitionIntent('vpn_failed', 'waiting_for_vpn')).toBe('retry');
    expect(transitionIntent('active', 'suspended')).toBe('suspend');
    expect(transitionIntent('testing_radius', 'radius_failed')).toBe('fail');
  });
  it('places failure states on the step they failed', () => {
    expect(onboardingStepIndex('radius_failed')).toBe(onboardingStepIndex('testing_radius'));
    expect(onboardingStepIndex('vpn_failed')).toBe(onboardingStepIndex('waiting_for_vpn'));
  });
});

describe('busy / delete / provision guards', () => {
  it('refuses delete while deployed or an operation is open', () => {
    expect(canDeleteRouter(router({ deployment_status: 'not_deployed' }))).toBe(true);
    expect(canDeleteRouter(router({ deployment_status: 'deployed' }))).toBe(false);
    expect(canDeleteRouter(router({ deployment_status: 'not_deployed' }), [op('running')])).toBe(
      false,
    );
    expect(canDeleteRouter(router({ deployment_status: 'not_deployed' }), [op('failed')])).toBe(
      true,
    );
  });
  it('explains why provisioning is blocked', () => {
    expect(provisionBlocker(router())).toBeNull();
    expect(provisionBlocker(router({ wireguard_public_key: '' }))).toMatch(/public key/);
    expect(provisionBlocker(router({ wireguard_ip: null }))).toMatch(/WireGuard IP/);
    expect(provisionBlocker(router({ is_active: false }))).toMatch(/inactive/);
    expect(provisionBlocker(router(), [op('pending')])).toMatch(/in progress/);
  });
});

describe('checkRows', () => {
  it('lists all six check types, marking never-run ones', () => {
    const checks: RouterOnboardingCheck[] = [
      {
        id: 1,
        router: 'r1',
        check_type: 'ping',
        passed: true,
        details: {},
        checked_at: '2026-09-01T10:00:00Z',
      },
      {
        id: 2,
        router: 'r1',
        check_type: 'radius_auth',
        passed: false,
        details: { outcome: 'rejected' },
        checked_at: '2026-09-01T11:00:00Z',
      },
    ];
    const rows = checkRows(checks);
    expect(rows).toHaveLength(6);
    expect(rows.find((r) => r.type === 'ping')?.status).toBe('passed');
    expect(rows.find((r) => r.type === 'radius_auth')?.status).toBe('failed');
    expect(rows.find((r) => r.type === 'firewall')?.status).toBe('never');
  });
});

describe('router schemas', () => {
  it('builds a create payload without empty optionals', () => {
    const parsed = routerCreateSchema.parse({
      name: 'r',
      ip_address: '10.0.0.1',
      location: '',
      nas_secret: 'sharedsecret',
      wireguard_ip: '',
      wireguard_public_key: '',
      wireguard_port: '51820',
      routeros_username: '',
      routeros_password: '',
      is_active: true,
    });
    const payload = createFormToPayload(parsed);
    expect(payload).toMatchObject({
      name: 'r',
      ip_address: '10.0.0.1',
      nas_secret: 'sharedsecret',
      wireguard_ip: null,
      wireguard_public_key: '',
      wireguard_port: 51820,
      is_active: true,
    });
    expect(payload).not.toHaveProperty('routeros_password_encrypted');
  });
  it('rejects malformed WireGuard keys and short secrets', () => {
    const r = routerCreateSchema.safeParse({
      name: 'r',
      ip_address: '10.0.0.1',
      location: '',
      nas_secret: 'short',
      wireguard_ip: '',
      wireguard_public_key: 'nope',
      wireguard_port: '51820',
      routeros_username: '',
      routeros_password: '',
      is_active: true,
    });
    expect(r.success).toBe(false);
    const paths = r.success ? [] : r.error.issues.map((i) => i.path.join('.'));
    expect(paths).toEqual(expect.arrayContaining(['nas_secret', 'wireguard_public_key']));
  });
  it('produces a minimal PATCH from the edit form', () => {
    const existing = router();
    const parsed = routerEditSchema.parse({
      name: existing.name,
      ip_address: existing.ip_address,
      location: 'Garki',
      wireguard_ip: existing.wireguard_ip,
      wireguard_public_key: existing.wireguard_public_key,
      wireguard_port: '51820',
      routeros_username: existing.routeros_username,
      is_active: true,
    });
    expect(editFormToPatch(parsed, existing)).toEqual({ location: 'Garki' });
  });
});
