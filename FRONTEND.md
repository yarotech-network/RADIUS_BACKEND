# Yarotech RADIUS — Frontend

Management UI for the Yarotech RADIUS API (multi-tenant hotspot / ISP voucher platform).
React 19 · TypeScript (strict) · Vite 7 · Tailwind CSS v4 · React Router v7 · TanStack Query v5.

> This document is the living reference for the frontend. It is updated at the end of every
> implementation phase. The original analysis (backend audit, API → feature map, design system,
> API gaps, phase plan) lives in [`analysis/`](./analysis/README.md).

**Status:** Phase 2 (Foundation) complete. Phases 3–11 pending — see
[`analysis/06_IMPLEMENTATION_PHASES.md`](./analysis/06_IMPLEMENTATION_PHASES.md).

---

## 1. Getting started

```bash
cp .env.example .env        # VITE_API_BASE_URL defaults to /api/v1 (proxied to Django in dev)
npm install
npm run dev                 # http://localhost:5173  (dev-only UI gallery at /__dev/ui)
```

| Script              | Purpose                                                   |
| ------------------- | --------------------------------------------------------- |
| `npm run dev`       | Vite dev server; proxies `/api` and `/health` to Django   |
| `npm run build`     | `tsc -b` + production bundle to `dist/`                   |
| `npm run typecheck` | Strict TypeScript across app + node configs               |
| `npm run lint`      | ESLint (typescript-eslint, react-hooks v7, react-refresh) |
| `npm run test`      | Vitest + Testing Library + MSW (jsdom)                    |
| `npm run format`    | Prettier (with the Tailwind class sorter)                 |
| `npm run analyze`   | Build with `rollup-plugin-visualizer` → `stats.html`      |

### Environment variables

| Variable                | Default                 | Notes                                                                                                                                                            |
| ----------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL`     | `/api/v1`               | Relative when Nginx serves UI + API from one origin; absolute (`https://api.example.com/api/v1`) otherwise — add the UI origin to Django `CORS_ALLOWED_ORIGINS`. |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Dev-server proxy target only.                                                                                                                                    |
| `VITE_APP_NAME`         | `Yarotech RADIUS`       | Display name.                                                                                                                                                    |

No secrets are ever placed in the frontend. Paystack keys, router secrets and WhatsApp tokens are
write-only fields on the backend and are never echoed back.

---

## 2. Architecture

### 2.1 Layers

```
route component  →  feature hook (TanStack Query)  →  feature API service  →  services/api/http.ts
      ↑ UI only          ↑ cache keys, invalidation       ↑ typed endpoints        ↑ fetch, auth, errors
```

- **Components never call `fetch` or the http client directly.** They use a feature hook.
- **Feature hooks** own query keys (`features/<name>/queries.ts`) and invalidation rules.
- **Feature API services** (`features/<name>/api.ts`) are thin typed wrappers around `http`.
- **`services/api/http.ts`** is the single transport: base URL, `Authorization`, `X-Tenant-ID`,
  `Idempotency-Key`, JSON/blob/text parsing, single-flight token refresh, error normalisation.

### 2.2 Directory layout

```
src/
  app/                config (env, constants), providers (QueryClient, Toast), router, RootLayout
  components/
    ui/               primitives: Button, Input, Select, Textarea, Checkbox, Switch, FormField, Badge,
                      Card, Dialog (modal + drawer), ConfirmDialog, Menu, Tabs, SegmentedControl,
                      Tooltip, Avatar, Skeleton, Spinner, Stat, DescriptionList, CopyButton
    data/             DataTable (table ⇄ mobile cards), Pagination, SearchInput (debounced),
                      FilterBar, useListParams (URL-backed list state)
    feedback/         Alert, Toaster/useToast, EmptyState, ErrorState, QueryBoundary, ErrorBoundary
    layout/           PageHeader, Section, StatusBadge + statusVocabulary
  features/           one folder per user-facing feature (api.ts, queries.ts, components, pages)
    dev/              UiGalleryPage — dev-only, excluded from production routes
  lib/
    formatting/       money (kobo ⇄ naira), dates (+relative), units (bytes, durations, rate limits)
    validation/       zod schemas mirroring backend serializer rules; applyApiErrors() for RHF
    utilities/        cn(), idempotency keys, useDebouncedValue, clipboard, download/print helpers
  services/
    api/              http.ts, errors.ts (ApiError), queryString.ts
    auth/             tokenStore.ts, session.ts (login/bootstrap/logout), principal.ts (roles, can())
  styles/index.css    Tailwind v4 @theme tokens + base + utilities
  test/               MSW server, renderWithProviders()
  types/api/          hand-written API contracts, one file per backend domain
```

### 2.3 Data & caching policy

- Lists: `staleTime` 30 s, refetch on window focus, `placeholderData: keepPreviousData` for paging.
- Detail: 30 s; live data (sessions, operations, deliveries, payment return pages) polls at 3 s /
  30 s and stops on terminal states.
- Retries: never on 4xx; network/5xx retried twice with backoff. Mutations never auto-retry.
- Every mutation invalidates the smallest sensible key prefix and shows a toast.

---

## 3. HTTP client contract (`services/api/http.ts`)

| Concern        | Behaviour                                                                                                                                                                                                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth header    | `Authorization: Bearer <access>` unless `anonymous: true`.                                                                                                                                                                                                                      |
| Refresh        | On 401: one shared refresh request (`/auth/token/refresh/`) for all concurrent callers; the **rotated** refresh token is stored immediately (old one is blacklisted server-side); the original request is retried once. If refresh fails → tokens cleared → `onSessionExpired`. |
| Tenant scoping | `X-Tenant-ID` from `setActiveTenantHeader()` (platform staff only). Pass `tenantId: null` to suppress.                                                                                                                                                                          |
| Idempotency    | `idempotencyKey` option → `Idempotency-Key` header. Keys are generated **once per user action** (`newIdempotencyKey()`) and reused on retries; `response.replayed` mirrors `Idempotency-Replayed: true`.                                                                        |
| Errors         | Every non-2xx → `ApiError { status, kind, code, message, fields, retryAfterSeconds, commandId }` built from the backend `problem` envelope, falling back to `detail` / `error` / field arrays. Never exposes HTML bodies or stack traces.                                       |
| Bodies         | `json` (default), `blob` (PDF), `text` (print HTML), `void` (204/DELETE).                                                                                                                                                                                                       |
| Query strings  | `toQueryString()` drops `null`/`undefined`/`''`; booleans → `true`/`false`.                                                                                                                                                                                                     |

`ApiError.kind`: `network | validation | unauthorized | forbidden | not_found | conflict | throttled | unavailable | server | unknown`.
`ErrorState` and `errorMessage()` render friendly copy per kind; forms use `applyApiErrors()` to map
`fields` onto react-hook-form inputs and return leftovers as a form-level alert.

---

## 4. Authentication & session

- **Storage:** access token in memory (mirrored to `sessionStorage`), refresh token in
  `localStorage` (7-day session; backend rotates + blacklists).
- **Bootstrap:** `bootstrapSession()` → silent refresh if needed → `GET /auth/user/` →
  `derivePrincipal()`. Platform staff additionally load `GET /staff/assignments/`.
- **Agent login** returns `agent{}` not `user{}`, so the app always follows up with `/auth/user/`.
- **Logout:** clear tokens first, then best-effort `POST /auth/logout/` (blacklists the refresh).
- Password change/reset revokes all tokens server-side → the UI signs out and redirects to login.

### Principal & capabilities (`services/auth/principal.ts`)

`Principal` is a discriminated union: `platform_admin | member(owner|manager|staff) | agent | platform_staff | none`.
`can(principal, capability)` maps to the backend permission matrix
([`analysis/01_BACKEND_AUDIT.md` §5](./analysis/01_BACKEND_AUDIT.md)):

- owner ⊇ manager ⊇ staff (staff = read-only + print);
- platform staff capabilities come from the active assignment's service grants;
- platform admin only has `platform.admin` (tenant-scoped data 403s without membership).

**Frontend permission checks are UX only** — they hide/disable actions to avoid guaranteed 403s.
The backend authorises every request.

---

## 5. Design system

Tokens live in `src/styles/index.css` (`@theme`) and are documented in
[`analysis/04_DESIGN_SYSTEM.md`](./analysis/04_DESIGN_SYSTEM.md).

- **Palette:** white surfaces on `canvas #F6F8FB`; `brand-600 #1D4ED8` for primary actions/links;
  **dark blue `brand-950 #0B1F3F` only** for the sidebar, headings, brand badges and toasts.
- **Status vocabulary:** `StatusBadge` maps every backend enum (voucher, payment, recovery,
  delivery, agent, router onboarding/deployment, subscription, invitation) to one tone; unknown
  values degrade to neutral with a humanised label.
- **Money:** all API amounts are integer **kobo**; `formatKobo()` renders ₦; inputs accept naira and
  convert with `parseNairaToKobo()`.
- **Motion/decoration:** no gradients, minimal shadows (only floating overlays), respects
  `prefers-reduced-motion`.
- **Responsive:** `DataTable` renders a real table ≥ `md` and stacked cards below; forms are single
  column on mobile; dialogs become bottom sheets, drawers go full-width.
- **Accessibility:** native `<dialog>` for focus trapping, `FormField` wires `aria-describedby` /
  `aria-invalid`, sortable headers expose `aria-sort`, toasts use `aria-live`, all icon buttons have
  labels.

---

## 6. Testing

- Unit tests sit next to the code (`*.test.ts(x)`); `npm test` runs them in jsdom with MSW
  (`src/test/server.ts`) — **no real network**, and unhandled requests fail the test.
- `renderWithProviders()` wraps components with QueryClient, Toast and a MemoryRouter.
- Phase 2 coverage: http client (headers, refresh single-flight, rotation, replay, blob/text),
  error normaliser, token store, principal/`can()`, formatters, zod schemas, `applyApiErrors`,
  `DataTable`, `FormField`, UI gallery smoke.

---

## 7. Phase log

| Phase | Status | Notes                                                                                                                        |
| ----- | ------ | ---------------------------------------------------------------------------------------------------------------------------- |
| 1     | ✅     | Analysis approved (`analysis/`).                                                                                             |
| 2     | ✅     | Toolchain, tokens, API types, http/auth services, formatting/validation libs, component library, dev gallery, 43 unit tests. |
| 3     | ⏳     | Shell & auth (guards, layouts, login/register/reset/invite/select-tenant, navigation).                                       |
| 4–11  | ⏳     | See phase plan.                                                                                                              |

### Toolchain notes

- `typescript` pinned to `~5.9` (typescript-eslint peer range `<6.1`); Vite 7 with
  `@vitejs/plugin-react` 5 (Vite 8 was released but the plugin/vitest matrix is not yet uniform).
- `react-router` pinned to `^7` per the approved plan (v8 exists; not adopted).
- Chunking: `react` (react, react-dom, react-router), `query`, `forms` (RHF + zod, loaded only by
  routes with forms). Baseline shell: ~112 kB gzip JS incl. React + Router, 7.7 kB CSS.
