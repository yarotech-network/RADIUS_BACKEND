/** Typed access to Vite environment variables. */
const raw = import.meta.env;

function stripTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}

export const env = {
  apiBaseUrl: stripTrailingSlash(raw.VITE_API_BASE_URL || '/api/v1'),
  appName: raw.VITE_APP_NAME || 'Yarotech RADIUS',
  isDev: raw.DEV,
  isProd: raw.PROD,
} as const;
