import { STORAGE_KEYS } from '@/app/config/constants';

/**
 * Access token lives in memory (mirrored to sessionStorage so a reload does not need a refresh
 * round-trip); the refresh token lives in localStorage for the 7-day session. The backend rotates
 * and blacklists refresh tokens, so an old copy is useless after one use.
 */
type Listener = () => void;

let accessToken: string | null = null;
const listeners = new Set<Listener>();

function safeGet(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}
function safeSet(storage: Storage | undefined, key: string, value: string | null) {
  try {
    if (value === null) storage?.removeItem(key);
    else storage?.setItem(key, value);
  } catch {
    /* storage unavailable (private mode / quota) — memory copy still works */
  }
}

function session(): Storage | undefined {
  return typeof window !== 'undefined' ? window.sessionStorage : undefined;
}
function local(): Storage | undefined {
  return typeof window !== 'undefined' ? window.localStorage : undefined;
}

function notify() {
  for (const listener of listeners) listener();
}

export const tokenStore = {
  getAccess(): string | null {
    if (accessToken === null) accessToken = safeGet(session(), STORAGE_KEYS.accessToken);
    return accessToken;
  },
  getRefresh(): string | null {
    return safeGet(local(), STORAGE_KEYS.refreshToken);
  },
  set(tokens: { access: string; refresh: string }) {
    accessToken = tokens.access;
    safeSet(session(), STORAGE_KEYS.accessToken, tokens.access);
    safeSet(local(), STORAGE_KEYS.refreshToken, tokens.refresh);
    notify();
  },
  setAccess(access: string) {
    accessToken = access;
    safeSet(session(), STORAGE_KEYS.accessToken, access);
    notify();
  },
  clear() {
    accessToken = null;
    safeSet(session(), STORAGE_KEYS.accessToken, null);
    safeSet(local(), STORAGE_KEYS.refreshToken, null);
    notify();
  },
  hasSession(): boolean {
    return Boolean(this.getRefresh());
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
