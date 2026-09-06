import { setupServer } from 'msw/node';

/** Shared MSW server for unit tests. Handlers are added per test with `server.use(...)`. */
export const server = setupServer();
