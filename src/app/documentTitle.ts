/**
 * Route → document title map (phase 10, WCAG 2.4.2 "page titled").
 *
 * Auth, storefront, agent-portal and platform pages already set their own
 * titles via effects. This map covers the workspace routes (and detail pages)
 * so every screen is titled. Applied from RootLayout — the parent effect runs
 * after child effects, so this map must only contain routes whose pages do
 * NOT set a title themselves.
 */
const TITLES: Record<string, string> = {
  '/dashboard': 'Overview · Yarotech RADIUS',
  '/sessions': 'Live sessions · Yarotech RADIUS',
  '/plans': 'Plans · Yarotech RADIUS',
  '/vouchers': 'Vouchers · Yarotech RADIUS',
  '/vouchers/generate': 'Generate vouchers · Yarotech RADIUS',
  '/payments': 'Payments · Yarotech RADIUS',
  '/payments/recovery': 'Payment recovery · Yarotech RADIUS',
  '/routers': 'Routers · Yarotech RADIUS',
  '/routers/new': 'Register router · Yarotech RADIUS',
  '/routers/operations': 'Router operations · Yarotech RADIUS',
  '/devices': 'Devices · Yarotech RADIUS',
  '/agents': 'Agents · Yarotech RADIUS',
  '/audit': 'Audit log · Yarotech RADIUS',
};

const PREFIX_TITLES: readonly [prefix: string, title: string][] = [
  ['/vouchers/', 'Voucher · Yarotech RADIUS'],
  ['/routers/', 'Router · Yarotech RADIUS'],
  ['/agents/', 'Agent · Yarotech RADIUS'],
  ['/settings', 'Settings · Yarotech RADIUS'],
];

export function titleForPathname(pathname: string): string | null {
  const exact = TITLES[pathname];
  if (exact) return exact;
  return PREFIX_TITLES.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? null;
}
