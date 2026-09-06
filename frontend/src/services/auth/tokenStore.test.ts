import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tokenStore } from './tokenStore';

describe('tokenStore', () => {
  beforeEach(() => tokenStore.clear());

  it('persists refresh in localStorage and access in sessionStorage', () => {
    tokenStore.set({ access: 'a', refresh: 'r' });
    expect(window.localStorage.getItem('yr.auth.refresh')).toBe('r');
    expect(window.sessionStorage.getItem('yr.auth.access')).toBe('a');
    expect(tokenStore.hasSession()).toBe(true);
    tokenStore.clear();
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
  });

  it('notifies subscribers on change', () => {
    const listener = vi.fn();
    const unsubscribe = tokenStore.subscribe(listener);
    tokenStore.setAccess('x');
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    tokenStore.clear();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
