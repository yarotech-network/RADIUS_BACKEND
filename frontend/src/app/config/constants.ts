export const PAGE_SIZE_DEFAULT = 20;
export const PAGE_SIZE_MAX = 100;
export const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;

export const SEARCH_DEBOUNCE_MS = 350;

/** Polling cadence for live operations (router provisioning, payment deliveries, return pages). */
export const LIVE_POLL_INTERVAL_MS = 3000;
export const SESSIONS_AUTO_REFRESH_MS = 30_000;

export const STORAGE_KEYS = {
  refreshToken: 'yr.auth.refresh',
  accessToken: 'yr.auth.access',
  activeTenant: 'yr.ctx.tenant',
  sidebarCollapsed: 'yr.ui.sidebar',
  pendingCheckout: 'yr.checkout.pending',
  agentStoreSlug: 'yr.agent.storeSlug',
} as const;

/** Business limits mirrored from backend serializers. */
export const LIMITS = {
  voucherBatchMax: 100,
  voucherPrefixMax: 10,
  planNameMax: 100,
  rateLimitMax: 20,
  walletFundingMinKobo: 50_000,
  routerNameMax: 100,
  locationMax: 200,
  usernameMin: 3,
  usernameMax: 150,
  passwordMin: 8,
  phoneMin: 10,
  phoneMax: 20,
  tenantNameMin: 2,
  tenantNameMax: 200,
  shopNameMax: 200,
  deviceNameMax: 200,
} as const;
