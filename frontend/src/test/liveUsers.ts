/** Harness users whose sessions `vitest.liveSetup.ts` opens once per live run (no app imports here: shared with the Node globalSetup). */
export const LIVE_USERS = ['owner', 'manager', 'staff', 'pstaff', 'nobody'] as const;
export type LiveUser = (typeof LIVE_USERS)[number];
export type LiveTokens = Partial<Record<LiveUser, { access: string; refresh: string }>>;
