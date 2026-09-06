# Yarotech RADIUS — Frontend

Management UI for the Yarotech RADIUS API (multi-tenant hotspot / ISP voucher platform).
React 19 · TypeScript (strict) · Vite 7 · Tailwind CSS v4 · React Router v7 · TanStack Query v5.

> This document is the living reference for the frontend. It is updated at the end of every
> implementation phase. The original analysis (backend audit, API → feature map, design system,
> API gaps, phase plan) lives in [`analysis/`](./analysis/README.md).

**Status:** Phases 2 (Foundation), 3 (Shell & auth) and 4 (Core operations) complete. Phases 5–11
pending — see
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

### Routing & guards (`app/router`, `app/auth/guards.tsx`)

```
RootLayout (error boundary)
├─ RedirectIfAuthenticated → PublicLayout: /login /agent/login /register /forgot-password /reset-password
├─ RequireBooted → PublicLayout: /accept-invitation /s/:slug /pay/result /pricing (+ /__dev/ui in dev)
└─ RequireAuth
   ├─ PublicLayout: /select-tenant /no-access
   ├─ RequireSurface(platform)  → PlatformLayout  /platform/*
   ├─ RequireSurface(agent)     → AgentLayout     /agent/*
   └─ RequireSurface(workspace) → WorkspaceLayout /  (dashboard, vouchers, plans, payments, routers, …)
```

- `RequireAuth` stores the requested path in `location.state.from`; `RedirectIfAuthenticated` is the
  **only** place that navigates after sign-in (to `from` if it is a same-origin path, else the
  principal's home). Sign-in pages never call `navigate`, so there are no duplicate redirects.
- `RequireSurface` sends principals to their own surface (`homePathFor`) and forces platform staff
  without a selected tenant to `/select-tenant`.
- Every page is a `lazy()` chunk; the login bundle does not include workspace code.

### Shells (`app/shell`)

| Surface   | < md                                        | md–lg                       | ≥ lg                                              |
| --------- | ------------------------------------------- | --------------------------- | ------------------------------------------------- |
| Workspace | top bar + 4-item bottom bar + "More" drawer | 72 px icon rail + top bar   | 256 px dark-blue sidebar (collapsible, persisted) |
| Platform  | same, dark-blue top bar                     | rail                        | sidebar                                           |
| Agent     | top bar + 5 bottom tabs                     | centred column, inline tabs | centred 3xl column                                |
| Public    | centred card                                | —                           | —                                                 |

Navigation items declare the capabilities that make them visible (`app/navigation/navConfig.ts`);
`visibleGroups()` filters per principal, so tenant staff never see Agents/Audit/Settings and platform
staff only see the areas their grants cover. Platform staff get a tenant switcher in the top bar.

### Feature module pattern (`features/<name>/`)

```
api.ts          endpoint calls only (paths, params, response types) — no React
queries.ts      TanStack Query keys + hooks (useX / useCreateX …); invalidation lives here
*Schema.ts      zod form schemas + form⇄API mappers (naira→kobo, MB→data_limit …)
*Rules.ts       pure business rules mirrored from the backend (e.g. which vouchers are editable)
components/     feature-specific UI (forms, pickers, row actions)
pages/          route components (default export, lazy-loaded); own URL state via useListParams
```

Pages never call `http` directly; forms use `useFormSubmit()` (`lib/forms`) so API field errors
land on the right input and throttling is reported consistently. Commands that create or mutate
send an `Idempotency-Key` minted once per form instance (`newIdempotencyKey`), so a retried submit
replays instead of duplicating.

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
- Coverage so far: http client (headers, refresh single-flight, rotation, replay, blob/text), error
  normaliser, token store, principal/`can()`, formatters, zod schemas, `applyApiErrors`, `DataTable`,
  `FormField`, UI gallery smoke, **auth flows per role** (owner/staff/admin/agent/platform staff/
  no-role, wrong password, 429 countdown, redirect-back, sign-out, expired refresh) and the
  responsive shells (bottom bar, drawer, collapse persistence, skip link).
- Feature pages are tested through MSW with the real route tree (`renderPage()`): plans, vouchers,
  dashboard, routers (list filters, state-machine buttons, 409 busy notice, stale-secrets reload,
  RADIUS test 503), agents (create with idempotency key, field errors, approve, sales tab) and
  devices (register/normalise MAC, remove, staff read-only). MSW picks the **first** matching
  handler, so per-test overrides must be listed before shared defaults in `server.use()`.

## 7. Core operations (Phase 4)

| Screen                        | Endpoints                                                                     | Notes                                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Dashboard `/`                 | `dashboard/stats/`, `dashboard/live-users/?page_size=1`                       | Six stat cards, recovery alert for paid-unfulfilled orders (managers), quick links. No trends (gap #6).        |
| Plans `/plans`                | `plans/` CRUD                                                                 | Search/`is_active`/ordering in URL; drawer form (duration presets, ₦ → kobo); delete falls back to deactivate. |
| Vouchers `/vouchers`          | `vouchers/` (+`status`,`plan`,`search`,`ordering`), `disable/`, `print/`      | Status tabs, plan filter, row menu gated by state (`voucherRules.ts`), multi-select → **one print sheet**.     |
| Generate `/vouchers/generate` | `vouchers/generate/` (idempotent)                                             | Plan picker + quantity presets + prefix; result screen lists usernames and offers **Print all**.               |
| Voucher `/vouchers/:id`       | `vouchers/{id}/`, `PATCH`, `DELETE`, `disable/`                               | Edit only when pristine (`?edit=1` drawer), type-to-confirm delete.                                            |
| Sessions `/sessions`          | `dashboard/live-users/` (10 s polling, pausable), `…/disconnect/`, `routers/` | Router filter, username search, disconnect with confirmation; 503 when CoA is unreachable is shown as-is.      |

Printing: the server only reveals passwords through the per-voucher HTML page. `features/vouchers/printing.ts`
parses each page and renders a 2-column A4 sheet (`buildPrintSheet`) into a hidden iframe (`printHtml`),
fetching sequentially with progress and collecting failures instead of aborting.

## 7b. Network & partners (Phase 5)

| Screen                           | Endpoints                                                                                                                                  | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Routers `/routers`               | `routers/` (+`onboarding_state`, `deployment_status`, `is_active`, `search`, `ordering`)                                                   | Badges combine onboarding state + deployment + inactive; “VPN” column; staff see the list read-only.                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Add router `/routers/new`        | `POST routers/` (idempotent)                                                                                                               | 4-step form (basics → RADIUS secret → WireGuard → RouterOS). Steps validate independently; server field errors jump back to the offending step.                                                                                                                                                                                                                                                                                                                                                                                      |
| Router `/routers/:id`            | `routers/{id}/`, `health/`, `checks/`, `audit/`, `transition/`, `provisioning/`, `replace-secrets/`, `test/`, `router-operations/?router=` | Tabs: **Onboarding** (stepper + only the transitions `ROUTER_TRANSITIONS` allows + 6 checks incl. never-run), **VPN** (provision/suspend with blocker reasons, 5 s polling while an operation is open, 409 → notice), **Secrets** (write-only; `expected_updated_at` optimistic lock → 409 offers reload), **RADIUS test** (429 countdown from `Retry-After`, 503 shown as service down), **History** (audit timeline). Health shows “Telemetry not available” (gap #9). Edit/Delete honour the server's busy/deployed guards (409). |
| Operations `/routers/operations` | `router-operations/?router&status&action`                                                                                                  | Cross-router log of provision/suspend runs; live while any operation is pending/running.                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Agents `/agents`                 | `tenant/agents/` (+`status`, `search`, `ordering`)                                                                                         | Manager-only. Drawer creates the agent as **pending**; commission sent as a 2-dp decimal string.                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Agent `/agents/:id`              | `tenant/agents/{id}/`, `PATCH`, `approve/`, `suspend/`, `vouchers/?search=<username>`                                                      | Approve / re-activate / suspend with confirmation; edit phone/shop/commission; **Vouchers sold** tab reuses the voucher list search and keeps rows where `agent === id` (gap: no dedicated agent filter).                                                                                                                                                                                                                                                                                                                            |
| Devices `/devices`               | `iot-devices/` (+`is_active`, `plan`, `search`), `POST`/`PATCH`/`DELETE`                                                                   | MAC-allow-listed equipment on a plan until an expiry; MAC normalised client-side to the server's `AA:BB:CC:DD:EE:FF`; datetime-local ↔ ISO conversion; staff read-only.                                                                                                                                                                                                                                                                                                                                                              |

Router permissions follow the backend exactly: list/retrieve for every member, everything else
`IsTenantManager`; platform staff get `routers.view` (health/checks/audit) and `routers.test` from
their service grants. Viewer-only principals never call the manager-only operations endpoint
(`useRouterOperations(params, enabled)`).

## 8. Verifying against the real API

The backend needs PostgreSQL + FreeRADIUS in production. For frontend verification a
**SQLite harness** runs the unmodified Django code (`radius-harness/` outside the repo: a settings
module that swaps the database, a SQL file that creates the unmanaged `rad*` tables, and a seed
script with one user per role — `admin`, `owner`, `manager`, `staff`, `pstaff` (2 tenants),
`pstaff1` (1 tenant), `agent`, `agent2` (pending), `nobody`).

`npm run test:integration` runs `src/integration/*.integration.test.tsx` against `127.0.0.1:8000`
and has confirmed: login/refresh rotation + blacklist, `problem` envelopes, field-error shapes,
`X-Tenant-ID` gating for platform staff, agent login shape, `Idempotency-Replayed` replay and 409 on
payload mismatch, the login throttle (`LIVE_API_THROTTLE=1`, consumes the 10/min budget), plan CRUD,
the voucher lifecycle (generate → print parse → disable → edit/delete rules → 404), live-users
filtering/validation, disconnect → 503 without a reachable NAS, the Phase 4 pages rendering live
data (`pages.integration.test.tsx`), and — Phase 5 (`phase5.integration.test.tsx`) — router
create → state-machine transitions (invalid → 400) → health/checks/audit → PATCH (secrets rejected)
→ replace-secrets (stale 409, wrong password 400, success) → delete, deployed router delete → 409,
agent create (duplicate → field error) → approve → edit → suspend → filtered list, device MAC
normalisation → filters → patch → delete, and staff receiving 403 on manager-only endpoints.

---

## 9. Phase log

| Phase | Status | Notes                                                                                                                        |
| ----- | ------ | ---------------------------------------------------------------------------------------------------------------------------- |
| 1     | ✅     | Analysis approved (`analysis/`).                                                                                             |
| 2     | ✅     | Toolchain, tokens, API types, http/auth services, formatting/validation libs, component library, dev gallery, 43 unit tests. |
| 3     | ✅     | Shell & auth (guards, layouts, login/register/reset/invite/select-tenant, navigation), SQLite harness, live tests.           |
| 4     | ✅     | Dashboard, plans, vouchers (generate/print/detail), live sessions.                                                           |
| 5     | ✅     | Routers (list/register/detail/operations), agents (directory/detail), devices. 109 unit + 21 live tests.                     |
| 6–11  | ⏳     | Payments & recovery, audit log, settings/team/subscription; agent portal; public storefront; platform admin; hardening.      |

### Toolchain notes

- `typescript` pinned to `~5.9` (typescript-eslint peer range `<6.1`); Vite 7 with
  `@vitejs/plugin-react` 5 (Vite 8 was released but the plugin/vitest matrix is not yet uniform).
- `react-router` pinned to `^7` per the approved plan (v8 exists; not adopted).
- Chunking: `react` (react, react-dom, react-router), `query`, `forms` (RHF + zod, loaded only by
  routes with forms). Baseline shell: ~112 kB gzip JS incl. React + Router, 7.7 kB CSS.
