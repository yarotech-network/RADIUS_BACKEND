/** Typed access to Vite environment variables. */
const raw = import.meta.env;

function stripTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}

export const env = {
  apiBaseUrl: stripTrailingSlash(raw.VITE_API_BASE_URL || '/api/v1'),
  appName: raw.VITE_APP_NAME || 'Yarotech RADIUS',
  /**
   * Slug of the storefront whose internet plans are showcased on the public
   * landing page (`/`). Empty → the customer plans section is hidden.
   * Read lazily (getter) so tests can stub the variable after import.
   */
  get featuredStorefrontSlug(): string {
    return raw.VITE_FEATURED_STOREFRONT_SLUG || '';
  },
  isDev: raw.DEV,
  isProd: raw.PROD,
};
