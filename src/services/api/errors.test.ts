import { describe, expect, it } from 'vitest';
import { ApiError, apiErrorFromResponse, errorMessage, parseRetryAfter } from './errors';

const headers = (init?: Record<string, string>) => new Headers(init);

describe('apiErrorFromResponse', () => {
  it('prefers the problem envelope message and code', () => {
    const err = apiErrorFromResponse(
      409,
      {
        problem: { code: 'http_409', message: 'Router is busy.', fields: {} },
        detail: 'Router is busy.',
        command_id: 'abc',
      },
      headers({ 'Retry-After': '5' }),
    );
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe('conflict');
    expect(err.code).toBe('http_409');
    expect(err.message).toBe('Router is busy.');
    expect(err.retryAfterSeconds).toBe(5);
    expect(err.commandId).toBe('abc');
  });

  it('maps DRF field errors into fields and surfaces non_field_errors as the message', () => {
    const err = apiErrorFromResponse(
      400,
      {
        problem: {
          code: 'http_400',
          message: 'Check the submitted fields.',
          fields: {
            quantity: ['Ensure this value is less than or equal to 100.'],
            non_field_errors: ['Plan is inactive.'],
          },
        },
        quantity: ['Ensure this value is less than or equal to 100.'],
        non_field_errors: ['Plan is inactive.'],
      },
      headers(),
    );
    expect(err.kind).toBe('validation');
    expect(err.fields['quantity']).toEqual(['Ensure this value is less than or equal to 100.']);
    expect(err.fieldMessage('quantity')).toContain('100');
    expect(err.message).toBe('Plan is inactive.');
    expect(err.hasFieldErrors).toBe(true);
  });

  it('falls back to legacy detail/error keys when there is no envelope', () => {
    expect(
      apiErrorFromResponse(
        403,
        { detail: 'You do not have permission to perform this action.' },
        headers(),
      ).message,
    ).toMatch(/permission/);
    expect(apiErrorFromResponse(400, { error: 'Plan is required' }, headers()).message).toBe(
      'Plan is required',
    );
  });

  it('flattens nested serializer errors one level', () => {
    const err = apiErrorFromResponse(400, { services: { 0: ['Invalid choice.'] } }, headers());
    expect(err.fields['services']).toEqual(['Invalid choice.']);
  });

  it('never leaks HTML bodies or stack traces', () => {
    const err = apiErrorFromResponse(502, '<html><body>Bad gateway</body></html>', headers());
    expect(err.kind).toBe('server');
    expect(err.message).not.toContain('<html>');
    expect(errorMessage(err)).toBe(err.message);
  });

  it('maps 429 and 503 to friendly kinds with generic messages when empty', () => {
    expect(apiErrorFromResponse(429, null, headers({ 'Retry-After': '60' })).kind).toBe(
      'throttled',
    );
    expect(
      apiErrorFromResponse(429, null, headers({ 'Retry-After': '60' })).retryAfterSeconds,
    ).toBe(60);
    expect(apiErrorFromResponse(503, null, headers()).kind).toBe('unavailable');
  });
});

describe('parseRetryAfter', () => {
  it('handles seconds and dates', () => {
    expect(parseRetryAfter('12')).toBe(12);
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter('garbage')).toBeNull();
    const soon = new Date(Date.now() + 30_000).toUTCString();
    expect(parseRetryAfter(soon)).toBeGreaterThanOrEqual(28);
  });
});
