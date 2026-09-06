/**
 * Vitest globalSetup (runs in Node, see tsconfig.node.json) for the live-API suite: signs each
 * harness user in ONCE and shares the token pairs with every test file via `provide()`, so the
 * whole run stays under the backend's anonymous login throttle (10/min per IP). No-op unless
 * LIVE_API=1.
 */
import { LIVE_USERS, type LiveTokens } from './src/test/liveUsers';

const PASSWORD = 'Passw0rd!2026';

export default async function setup(project: {
  provide: (key: 'liveTokens', value: LiveTokens) => void;
}) {
  if (process.env.LIVE_API !== '1') return;
  const base = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1';
  const tokens: LiveTokens = {};
  const login = (username: string) =>
    fetch(`${base}/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    });
  for (const username of LIVE_USERS) {
    let res = await login(username);
    if (res.status === 429) {
      // Back-to-back runs share the 10/min anonymous login budget: wait it out once.
      const wait = Math.min(Number(res.headers.get('Retry-After') ?? 60) + 1, 65);
      console.warn(`[live] login throttled; waiting ${wait}s before continuing`);
      await new Promise((resolve) => setTimeout(resolve, wait * 1000));
      res = await login(username);
    }
    if (!res.ok) {
      console.warn(
        `[live] login as ${username} failed with ${res.status}; tests needing it will fail`,
      );
      continue;
    }
    const body = (await res.json()) as { access: string; refresh: string };
    tokens[username] = { access: body.access, refresh: body.refresh };
  }
  project.provide('liveTokens', tokens);
}
