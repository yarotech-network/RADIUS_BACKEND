import { inject } from 'vitest';
import type { TokenPair } from '@/types/api';
import { tokenStore } from '@/services/auth/tokenStore';
import type { LiveTokens, LiveUser } from './liveUsers';

declare module 'vitest' {
  export interface ProvidedContext {
    liveTokens: LiveTokens;
  }
}

/** Token pair for a harness user, signed in once per run by `vitest.liveSetup.ts`. */
export function liveTokens(user: LiveUser): TokenPair {
  const pair = inject('liveTokens')?.[user];
  if (!pair)
    throw new Error(`No live tokens for "${user}" — is the backend harness running on :8000?`);
  return pair;
}

/** Run `fn` with another harness user's tokens, then restore the previous ones. */
export async function asLiveUser<T>(user: LiveUser, fn: () => Promise<T>): Promise<T> {
  const previous: TokenPair = {
    access: tokenStore.getAccess() ?? '',
    refresh: tokenStore.getRefresh() ?? '',
  };
  tokenStore.set(liveTokens(user));
  try {
    return await fn();
  } finally {
    tokenStore.set(previous);
  }
}
