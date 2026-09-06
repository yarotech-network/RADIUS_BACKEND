# 03 — Frontend Architecture

Target: a standalone repository (`yarotech-radius-frontend`) — React 19 + TypeScript (strict) + Vite + Tailwind CSS v4 + React Router v7 (data-less, component routes) + TanStack Query v5. The backend is consumed exclusively through `/api/v1/`.

---

## 1. Three applications, one codebase

The backend's roles map to **three distinct experiences** with different navigation, not one app with hidden buttons:

| Surface | Route prefix | Who | Layout |
|---|---|---|---|
| **Workspace** | `/` (dashboard, vouchers, routers, …) | owner, manager, staff member, platform staff (with tenant selected) | Sidebar + header (desktop), rail (tablet), bottom nav + drawer (mobile) |
| **Platform console** | `/platform/*` | platform admin | Same shell, dark-blue accent header, its own nav |
| **Agent portal** | `/agent/*` | agent | Mobile-first: top bar + bottom tabs; centred column on desktop |
| **Public** | `/login`, `/register`, `/s/:slug`, `/pay/result`, `/pricing`, `/accept-invitation`, `/reset-password` | anyone | Minimal centred layout |

Route-level `lazy()` per surface **and** per feature page; the login bundle never includes workspace code.

---

## 2. Directory structure

```
src/
├── app/
│   ├── router/            routes.tsx, guards (RequireAuth, RequireRole, RequireTenantContext), lazy boundaries
│   ├── providers/         QueryProvider, AuthProvider, TenantContextProvider, ToastProvider, ThemeTokens
│   ├── layouts/           WorkspaceLayout, PlatformLayout, AgentLayout, PublicLayout, (+ nav configs)
│   └── config/            env.ts (VITE_API_BASE_URL, VITE_PAYSTACK_RETURN_*), constants.ts
│
├── features/
│   ├── auth/              login, register, agent-login, forgot/reset, accept-invitation, select-tenant
│   ├── dashboard/         tenant overview (stats + attention + activity)
│   ├── sessions/          live sessions + disconnect
│   ├── plans/             plan catalogue CRUD
│   ├── vouchers/          inventory, generate, detail, print/pdf, disable, custom voucher
│   ├── payments/          transactions, recovery & delivery
│   ├── routers/           inventory, register, detail tabs (onboarding, vpn, tests, secrets, history), operations
│   ├── agents/            tenant-side agent management
│   ├── devices/           MAC devices
│   ├── settings/          general, billing, team, integrations (WhatsApp), subscription, profile, security
│   ├── audit/             tenant audit log
│   ├── agent-portal/      home, wallet, sell, vouchers, profile
│   ├── platform/          overview, tenants, routers, payments, staff, audit
│   └── public/            storefront, checkout, payment result, pricing
│
│   each feature =  api.ts (typed service)  ·  hooks.ts (TanStack Query hooks + query keys)
│                   mappers.ts (API → view model, when non-trivial)  ·  components/  ·  pages/
│
├── components/
│   ├── ui/                Button, IconButton, Input, Select, Textarea, Checkbox, Switch, Badge, Card,
│   │                      Dialog, Drawer/Sheet, Tabs, Tooltip, DropdownMenu, Skeleton, Spinner, Alert, Toast
│   ├── forms/             Field, FormSection, MoneyInput (₦↔kobo), DurationInput, RateLimitInput, MacInput, PasswordInput
│   ├── tables/            DataTable (desktop) + RecordList (mobile cards) driven by one column/record config,
│   │                      Pagination, FilterBar, SearchInput (debounced), SortHeader
│   ├── feedback/          EmptyState, ErrorState, PageSkeleton, StatusBadge maps, ConfirmDialog, InlineNotice
│   └── navigation/        Sidebar, NavRail, BottomNav, TopBar, Breadcrumbs, UserMenu, TenantSwitcher
│
├── services/
│   ├── api/               http.ts (fetch wrapper: base URL, auth header, tenant header, refresh, error normalisation,
│   │                      idempotency, blob support), errors.ts (ApiError + problem parsing), pagination.ts, query-string.ts
│   └── auth/              tokenStore.ts (memory + localStorage), session.ts (bootstrap, refresh single-flight, logout)
│
├── lib/
│   ├── formatting/        money (kobo), dates (relative/absolute), bytes, duration, mac, ip
│   ├── validation/        zod schemas mirroring backend serializer rules
│   └── utilities/         cn, debounce hook, idempotency key generator (crypto.randomUUID), clipboard, download
│
└── types/                 api/*.ts — one file per backend domain, hand-written from openapi-v1.yaml
                           (enums as string unions, envelopes, error shape)
```

---

## 3. Data flow

```
Page / component
   ↓ (props, no fetching)
Feature hook            useVouchers(params) / useDisableVoucher()      TanStack Query — keys, caching, invalidation
   ↓
Feature API service     vouchersApi.list(params) → Promise<Paginated<Voucher>>  (pure functions, typed)
   ↓
HTTP client             http.get/post/patch/delete/blob                   auth, tenant header, refresh, errors
   ↓
Backend /api/v1
```

Rules:
- Components never import `http` directly.
- Services return **typed API shapes**; mappers (`mappers.ts`) convert to view models only where the UI needs derived data (e.g. router "next valid states", recovery "attention level", voucher "editable?").
- Query keys are colocated per feature: `vouchersKeys.list(params)`, `vouchersKeys.detail(id)`. Mutations invalidate precisely (list + detail + dashboard stats when relevant).

### Caching / fetching policy

| Data | staleTime | Notes |
|---|---|---|
| Current user, tenant profile, plans (small, stable) | 5 min | Plans are reused in selects across vouchers/devices/agents |
| Paginated lists | 30 s, `placeholderData: keepPreviousData` | Filters live in URL search params → shareable, back-button friendly |
| Dashboard stats, live sessions | 15 s; sessions optional auto-refresh (30 s) while tab visible | `refetchOnWindowFocus` on |
| Router operation / payment delivery in live state | `refetchInterval` 3 s until terminal status | Stops automatically |
| Print HTML / PDF | not cached (blob) | `Cache-Control: no-store` from server |

- Search inputs debounce 350 ms before updating the URL param (which drives the query).
- `page_size` default 20 (server default), selectable 20/50/100 (server max 100).
- No client-side "fetch everything" — plan selects use `page_size=100` with `is_active=true` (tenant plan catalogues are small); if `total_pages > 1` the select gains a search box that queries `?search=`.

---

## 4. HTTP client contract

```ts
http.request<T>({ method, path, query?, body?, idempotent?, tenantId?, responseType?: 'json'|'blob'|'text' })
```
- Base URL from `VITE_API_BASE_URL` (default `/api/v1` so Vite dev proxy → Django; production served from same origin via Nginx or a full URL).
- Adds `Authorization: Bearer` from the token store; adds `X-Tenant-ID` when the active tenant context is a platform-staff assignment.
- On **401** (and not a refresh/login call): join the single in-flight refresh; retry once; if refresh fails → `session.logout('expired')` → router redirects to `/login?reason=expired`.
- On **429**: surface `retryAfterSeconds` from `Retry-After`.
- Idempotent commands: when `idempotent: true`, the hook generates a key **once per logical action** (per mutation invocation), reuses it on transport retries, and never regenerates after a timeout/503. A 409 with `command_id` is surfaced as "still processing — check status".
- Errors normalise to `ApiError { status, code, message, fields: Record<string,string[]>, retryAfter?, raw }` using `problem` first, then `detail`/`error`/field arrays. Network failures → `status: 0, code: 'network'`.
- Response envelope helpers: `Paginated<T>`, `LiveUsersResponse`.

---

## 5. Authentication & session

- Tokens: access in memory + `sessionStorage` mirror for reload; refresh in `localStorage` (7-day lifetime; the backend rotates + blacklists so a stolen old refresh is useless after one use). Both cleared on logout.
- **Bootstrap** (`AuthProvider`): if a refresh token exists → refresh → `GET auth/user/` → derive `principal`:
  ```ts
  type Principal =
    | { kind: 'platform_admin'; user }
    | { kind: 'member'; user; role: 'owner'|'manager'|'staff'; tenantId; tenantName }
    | { kind: 'agent'; user }
    | { kind: 'platform_staff'; user; assignments: StaffAssignment[]; activeTenantId?: number }
    | { kind: 'none'; user }
  ```
  For `platform_staff`, load `GET staff/assignments/` and require a tenant selection (persisted per user in localStorage).
- **Guards**: `RequireAuth` → `RequireSurface('workspace'|'platform'|'agent')` → per-route `can(...)` for UX gating. Unauthorised surfaces redirect to the principal's home (`/`, `/platform`, `/agent`, or `/select-tenant`).
- **Capability helper** (`can(principal, capability)`) mirrors the backend matrix (`01_BACKEND_AUDIT.md §5`), including platform-staff grants (`routers.view`, …). Used for nav visibility, button enable/disable and inline "You don't have permission" notices. The backend remains the authority — every 403 is still handled.
- Password change → tokens revoked server-side → the UI signs out with an explanatory message.

---

## 6. Forms

- `react-hook-form` + `zod`. Schemas mirror serializer constraints (e.g. quantity 1–100, prefix ≤10, funding ≥ 50 000 kobo, MAC 12 hex digits, WireGuard key 44-char base64 decoding to 32 bytes, port 1–65535, duration ≥1, commission 0–100 with 2 dp).
- Money fields accept naira with decimals and submit **integer kobo**.
- Server field errors (`ApiError.fields`) are mapped onto fields via `setError`; non-field messages render in a form-level `Alert`.
- Submit buttons disable while pending; Enter-key double submits are prevented by mutation `isPending`.
- Secrets fields are "write-only" UI: show "Configured / Not configured" (when inferable) and a "Replace" affordance; never pre-fill.

---

## 7. Tables & large data

- One `DataTable` config renders a real `<table>` ≥ `md`, and a prioritised `RecordList` (card per row with primary/secondary/meta slots + actions menu) below `md`.
- Server pagination everywhere the backend paginates. No client-side sorting on server-paginated data (sort → `?ordering=` only where the backend supports it).
- Virtualisation is unnecessary at ≤100 rows/page; the only unbounded arrays (`routers/{id}/checks/` ≤6, generate result ≤100) are small.

---

## 8. State that is not server state

- URL search params: list filters, page, tab, drawer selection (`?voucher=123`).
- Small React contexts: auth principal, active tenant context, toast queue, sidebar collapsed (persisted).
- No global store library needed; TanStack Query owns server state.

---

## 9. Environment & dev workflow

- `.env`: `VITE_API_BASE_URL=/api/v1` (dev proxy to `http://127.0.0.1:8000`), `VITE_APP_NAME`, `VITE_PAYSTACK_RETURN_NOTE` (optional copy).
- Vite `server.proxy` forwards `/api`, `/health` to Django; `server.host=0.0.0.0` and `allowedHosts: true` for preview hosts.
- Scripts: `dev`, `build` (tsc -b && vite build), `preview`, `lint`, `typecheck`, `test` (Vitest + Testing Library for hooks, http client, formatters, guards), `analyze` (rollup-plugin-visualizer, dev only).
- Bundle guardrails: no chart library (dashboard metrics are counts/amounts — a chart would imply time series the API doesn't provide), no data-grid library, icons via `lucide-react` tree-shaken imports, dates via `Intl` + a tiny relative-time helper (no date-fns/moment), no PDF library (server renders PDFs).

---

## 10. Testing strategy (what will be automated in the new repo)

- Unit: money/date/bytes formatters, error normaliser, idempotency key reuse, refresh single-flight, `can()` matrix, router state-machine helper, zod schemas.
- Component: DataTable/RecordList switching, forms mapping server errors, guards redirecting by principal.
- Integration (MSW): auth bootstrap, voucher generate flow, router onboarding tab, recovery actions.
- Type-safety: `tsc --noEmit` in CI; API types are hand-maintained against `openapi-v1.yaml` with a script that diffs schema paths vs. `services` usage to catch drift.
