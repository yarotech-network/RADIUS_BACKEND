import { afterEach, describe, expect, it, vi } from 'vitest';
import { installGlobalErrorReporting, reportError, setErrorSink } from './errorReporter';

describe('errorReporter (phase 11)', () => {
  afterEach(() => {
    setErrorSink(null);
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('routes errors to the installed sink with context', () => {
    const sink = vi.fn();
    setErrorSink(sink);
    const error = new Error('boom');
    reportError(error, { source: 'test' });
    expect(sink).toHaveBeenCalledExactlyOnceWith(error, { source: 'test' });
  });

  it('never throws when the sink itself throws', () => {
    setErrorSink(() => {
      throw new Error('sink failure');
    });
    expect(() => reportError('anything', { source: 'test' })).not.toThrow();
  });

  it('restores the default sink on setErrorSink(null)', () => {
    setErrorSink(null);
    // Default sink in a DEV environment logs to console.error — must not throw.
    expect(() => reportError(new Error('quiet'), { source: 'test' })).not.toThrow();
  });

  it('POSTs a JSON report to the configured endpoint in production', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubEnv('DEV', false);
    vi.stubEnv('VITE_ERROR_REPORT_ENDPOINT', 'https://errors.example.com/report');
    setErrorSink(null); // ensure the default sink is active
    reportError(new Error('boom'), { source: 'test' });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://errors.example.com/report');
    expect(init.method).toBe('POST');
    expect(init.keepalive).toBe(true);
    const body = JSON.parse(String(init.body)) as {
      detail: { message?: string };
      context: { source: string };
    };
    expect(body.detail.message).toBe('boom');
    expect(body.context.source).toBe('test');
  });

  it('does nothing in production when no endpoint is configured', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubEnv('DEV', false);
    vi.stubEnv('VITE_ERROR_REPORT_ENDPOINT', '');
    setErrorSink(null);
    reportError(new Error('boom'), { source: 'test' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('installs window-level handlers exactly once', () => {
    const sink = vi.fn();
    setErrorSink(sink);
    installGlobalErrorReporting();
    installGlobalErrorReporting(); // idempotent — must not double-install
    window.dispatchEvent(new ErrorEvent('error', { error: new Error('page boom') }));
    expect(sink).toHaveBeenCalledExactlyOnceWith(new Error('page boom'), {
      source: 'window.error',
    });
  });
});
