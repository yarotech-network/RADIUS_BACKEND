import { useCallback, useSyncExternalStore } from 'react';
import { STORAGE_KEYS } from '@/app/config/constants';

/**
 * Gap #1: the agent API never tells the portal which storefront (tenant slug) the agent sells for,
 * and `GET plans/` is 403 for agents. The plan catalogue therefore comes from the public
 * `public/tenants/<slug>/plans/` endpoint, keyed by a slug the agent enters once (or that arrives
 * as `?store=<slug>` on a link from their operator). Persisted per browser.
 */
const listeners = new Set<() => void>();
const SLUG_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$/;

function read(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEYS.agentStoreSlug);
  } catch {
    return null;
  }
}

function write(slug: string | null) {
  try {
    if (slug) localStorage.setItem(STORAGE_KEYS.agentStoreSlug, slug);
    else localStorage.removeItem(STORAGE_KEYS.agentStoreSlug);
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener('storage', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
}

/** Accepts a bare slug or a full storefront URL (`https://…/s/<slug>`); returns null when invalid. */
export function normaliseStoreSlug(input: string): string | null {
  let value = input.trim().toLowerCase();
  const match = value.match(/\/s\/([a-z0-9-]+)/);
  if (match?.[1]) value = match[1];
  value = value.replace(/^\/+|\/+$/g, '');
  return SLUG_PATTERN.test(value) ? value : null;
}

export function useStoreSlug() {
  const slug = useSyncExternalStore(subscribe, read, () => null);
  const setSlug = useCallback((next: string | null) => write(next), []);
  return [slug, setSlug] as const;
}

export const storeSlugStore = { read, write };
