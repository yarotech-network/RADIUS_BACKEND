# Yarotech RADIUS — Frontend

Web application for the Yarotech RADIUS hotspot platform: tenant workspace (dashboard, plans,
vouchers, live sessions, routers, agents, payments), platform console and mobile-first agent portal.
It consumes the existing Django REST API (`RADIUS_BACKEND`, `/api/v1/`) and contains **no business
logic of its own** — the backend is the source of truth.

- Stack: React 19 · TypeScript (strict) · Vite 7 · Tailwind CSS v4 · React Router 7 · TanStack Query 5 · react-hook-form + zod · Vitest + Testing Library + MSW
- Documentation: [`FRONTEND.md`](./FRONTEND.md) (architecture, data layer, auth, design system, testing, phase log)
- Backend analysis that drives the UI: [`analysis/`](./analysis/README.md) (audit, API→feature map, architecture, design system, **API gaps**, phase plan)

## Quick start

```bash
# Node 22 (see .nvmrc); npm ≥ 10
npm ci
cp .env.example .env          # VITE_API_BASE_URL=/api/v1 and the dev proxy target
npm run dev                   # http://localhost:5173 — /api and /health are proxied to VITE_DEV_PROXY_TARGET
```

| Script                     | Purpose                                                                     |
| -------------------------- | --------------------------------------------------------------------------- |
| `npm run dev`              | Vite dev server with API proxy                                              |
| `npm run typecheck`        | `tsc -b` (strict, `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`) |
| `npm run lint`             | ESLint (typescript-eslint, react-hooks v7, jsx-a11y)                        |
| `npm run format`           | Prettier (write)                                                            |
| `npm test`                 | Unit + component tests (jsdom, MSW — no network)                            |
| `npm run test:integration` | Contract tests against a live API on `127.0.0.1:8000` (see below)           |
| `npm run build`            | Production build to `dist/` (route-level code splitting)                    |
| `npm run analyze`          | Build with a bundle treemap (`stats.html`)                                  |

## Configuration

| Variable                | Default                 | Notes                                                                                                                                    |
| ----------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL`     | `/api/v1`               | Relative when served behind the same origin as Django; full URL for a separate origin (add it to `CORS_ALLOWED_ORIGINS` on the backend). |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Dev server only.                                                                                                                         |
| `VITE_APP_NAME`         | `Yarotech RADIUS`       | Display name.                                                                                                                            |

## Verifying against the real backend

`harness/` contains a SQLite settings module, the SQL for the unmanaged FreeRADIUS tables and a
seed script (one user per role) so the **unmodified** backend can run locally without PostgreSQL.
See [`harness/README.md`](./harness/README.md); then `npm run test:integration`.

## Project layout

```
src/
├── app/          router, auth provider + guards, shells (workspace / platform / agent / public), navigation
├── components/   design system — ui primitives, data (table, pagination, filters), feedback, layout
├── features/     one folder per domain: api.ts → queries.ts → components/ → pages/
├── services/     HTTP client (JWT refresh, X-Tenant-ID, Idempotency-Key), auth session, token store
├── lib/          formatting (kobo, bytes, dates), validation (zod), forms, utilities
├── types/api/    TypeScript contracts mirroring the backend serializers
└── test/         MSW server, render helpers, fixtures
```

## Deployment

`npm run build` produces static files. Serve `dist/` from Nginx (or any static host) with SPA
fallback to `index.html`, and either proxy `/api/` to Gunicorn on the same origin or point
`VITE_API_BASE_URL` at the API origin. Production hardening (CSP, caching headers, health checks)
is part of the final phase — see the phase log in `FRONTEND.md`.
