import { describe, expect, it } from 'vitest';
import {
  describeRateLimit,
  formatBytes,
  formatDataLimit,
  formatDuration,
  formatHours,
  formatKobo,
  formatRelative,
  humanise,
  koboToNairaInput,
  normaliseMac,
  parseNairaToKobo,
} from './index';

describe('money', () => {
  it('formats kobo as naira', () => {
    expect(formatKobo(125_050)).toMatch(/1,250\.50/);
    expect(formatKobo(50_000, { compact: true })).toMatch(/^₦?\s?500$|NGN\s?500/);
    expect(formatKobo(null)).toBe('—');
  });
  it('parses naira input to integer kobo', () => {
    expect(parseNairaToKobo('1,500')).toBe(150_000);
    expect(parseNairaToKobo('₦ 1500.5')).toBe(150_050);
    expect(parseNairaToKobo('12.345')).toBeNull();
    expect(parseNairaToKobo('abc')).toBeNull();
    expect(parseNairaToKobo('')).toBeNull();
    expect(koboToNairaInput(150_050)).toBe('1500.50');
    expect(koboToNairaInput(150_000)).toBe('1500');
  });
});

describe('units', () => {
  it('formats bytes, data limits and durations', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1_536_000_000)).toBe('1.4 GB');
    expect(formatDataLimit(0)).toBe('Unlimited');
    expect(formatDataLimit(1536)).toBe('1.5 GB');
    expect(formatDataLimit(500)).toBe('500 MB');
    expect(formatDuration(93_784)).toBe('1d 2h');
    expect(formatDuration(3_725)).toBe('1h 2m');
    expect(formatDuration(59)).toBe('59s');
    expect(formatHours(24)).toBe('1 day');
    expect(formatHours(168)).toBe('7 days');
    expect(formatHours(1)).toBe('1 hour');
    expect(formatHours(36)).toBe('36 hours');
  });
  it('describes RouterOS rate limits and normalises MACs', () => {
    expect(describeRateLimit('5M/10M')).toBe('5 Mbps up · 10 Mbps down');
    expect(describeRateLimit('512k/1M')).toBe('512 Kbps up · 1 Mbps down');
    expect(describeRateLimit('weird')).toBe('weird');
    expect(normaliseMac('aa-bb-cc-dd-ee-ff')).toBe('AA:BB:CC:DD:EE:FF');
    expect(normaliseMac('aabbccddeeff')).toBe('AA:BB:CC:DD:EE:FF');
  });
  it('humanises identifiers', () => {
    expect(humanise('vpn_failed')).toBe('VPN failed');
    expect(humanise('waiting_for_vpn')).toBe('Waiting for VPN');
    expect(humanise('router.transition')).toBe('Router transition');
  });
});

describe('dates', () => {
  it('formats relative times', () => {
    const now = Date.UTC(2026, 8, 6, 12, 0, 0);
    expect(formatRelative(new Date(now - 3 * 3_600_000), now)).toMatch(/3 hours ago/);
    expect(formatRelative(new Date(now + 2 * 86_400_000), now)).toMatch(/in 2 days/);
    expect(formatRelative(new Date(now - 5_000), now)).toBe('just now');
    expect(formatRelative(null)).toBe('—');
  });
});
