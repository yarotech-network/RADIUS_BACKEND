/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_PROXY_TARGET?: string;
  readonly VITE_APP_NAME?: string;
  /** Set by `npm run test:integration` only. */
  readonly LIVE_API?: string;
  readonly LIVE_API_THROTTLE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
