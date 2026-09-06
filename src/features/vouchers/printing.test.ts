import { describe, expect, it } from 'vitest';
import { buildPrintSheet, parsePrintHtml } from './printing';

const SERVER_HTML = `
        <html>
        <body>
        <h1>YAROTECH Voucher</h1>
        <p><strong>Username:</strong> WH10000</p>
        <p><strong>Password:</strong> pw&lt;1000&gt;</p>
        <p><strong>Plan:</strong> Daily 1GB</p>
        <p><strong>Duration:</strong> 24 hours</p>
        <p><strong>Status:</strong> unused</p>
        </body>
        </html>`;

describe('parsePrintHtml', () => {
  it('extracts the credential fields from the server print page (entities decoded)', () => {
    expect(parsePrintHtml(7, SERVER_HTML)).toEqual({
      id: 7,
      username: 'WH10000',
      password: 'pw<1000>',
      plan: 'Daily 1GB',
      duration: '24 hours',
    });
  });
  it('returns null when the page has no credentials', () => {
    expect(parsePrintHtml(1, '<html><body><h1>Nope</h1></body></html>')).toBeNull();
  });
});

describe('buildPrintSheet', () => {
  it('renders one card per credential and escapes HTML', () => {
    const html = buildPrintSheet(
      [{ id: 1, username: 'a<b', password: 'p"q', plan: 'Daily', duration: '24 hours' }],
      { tenantName: 'Wuse & Co' },
    );
    expect(html).toContain('Wuse &amp; Co');
    expect(html).toContain('a&lt;b');
    expect(html).toContain('p&quot;q');
    expect(html.match(/<article class="card">/g)).toHaveLength(1);
  });
});
