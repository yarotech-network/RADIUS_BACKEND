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
  devices (register/normalise MAC, remove, staff read-only), payments (status filter, drawer
  deep-link, staff vs manager hand-off), recovery (attention banner, retry 503 with idempotency key,
  409 acknowledgement → resend with flag, platform staff without `payments.support` read-only),
  audit (labels/tones, “You”/“User #n”/“System”, details expansion, action/actor filters) and the
  settings tabs (partial PATCHes, write-only Paystack keys, add-by-user-ID with `tenant`, last-owner
  guards, 404 → “no subscription”, checkout 503 → reference polling), the agent portal (storefront
  connect + 404 slug, sell with charge preview / insufficient-balance guard / plan-field error /
  usernames-only result, wallet fund dialog with quick amounts + floor/ceiling errors + Paystack
  redirect + return polling, vouchers status filter, profile diff-PATCH) and the public storefront
  (catalogue, checkout validation + idempotent `buy/` + 503 handling + missing plan, payment result
  pending → success / failed / 404 / no-reference fallback, pricing active-only). MSW picks the
  **first** matching handler, so per-test overrides must be listed before shared defaults in
  `server.use()`. Tests that exercise a Paystack redirect stub `window.location` (`vi.spyOn(window,
'location', 'get')`) and assert on `assign()`.

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

## 7c. Money, accountability & administration (Phase 6)

| Screen                                           | Endpoints                                                                                                                | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Payments `/payments`                             | `payments/transactions/` (+`status`, `search`, `ordering`), `…/{id}/`                                                    | Read-only purchase history for every member. Row → drawer (`?payment=<id>`; `/payments/:id` redirects there so links are shareable). Managers get a hand-off to recovery for successful payments.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Recovery `/payments/recovery`                    | `payment-recovery/` (+`status`, `plan`, `search`), `retry/`, `deliver/`, `payment-deliveries/?payment=`                  | Manager+ (`payments.recovery.view`; platform staff via `payments.view`). “Needs attention” = paid without voucher or failed email (client-side on the current page — the API cannot filter on the computed statuses). **Re-verify** POSTs `retry/` with an `Idempotency-Key`: 503 = provider unreachable (nothing changed), 409 = verification/plan mismatch. **Email credentials** follows the server rules in `paymentRules.ts`: only `success` + voucher; if the last delivery was accepted/unknown the UI asks for the duplicate-risk acknowledgement up front (and also on a 409 that says so) and resends with `acknowledge_duplicate_risk: true`. Delivery history polls every 5 s while a delivery is pending/sending. Actions need `payments.recovery.act` (`payments.support` grant for staff). |
| Audit log `/audit`                               | `audit-events/` (+`action`, `actor`, `search`, `ordering`)                                                               | Manager+. Curated labels/tones for the known action keys (`auditVocabulary.ts`), unknown keys humanised. Resource keys `app.model:pk` parse into deep links (voucher, router, agent, payment). Actor shows **You** / `User #n` / **System** (gap #20: the API returns ids only; “Mine” filter uses the principal's id). Details JSON is rendered as key/value rows in an expandable panel (`DataTable renderExpanded`).                                                                                                                                                                                                                                                                                                                                                                                   |
| Settings → General `/settings/general`           | `tenants/profile/` (GET/PATCH), `auth/change-password/`                                                                  | Business profile form (manager+) sends only changed fields. **Your account** shows the numeric user ID with a copy button (owners add teammates by ID — gap #3) and the change-password form; the API's `old_password` error lands on its field. Because SimpleJWT runs with `CHECK_REVOKE_TOKEN`, **every token issued before the change is rejected afterwards** — the form therefore re-logs in with the new password (`signIn`) and falls back to a sign-out with a message if that fails.                                                                                                                                                                                                                                                                                                            |
| Settings → Billing `/settings/billing`           | `tenants/settings/` (GET/PATCH)                                                                                          | Paystack keys are write-only: fields start blank with placeholder “Unchanged” and are only included in the PATCH when typed; the response never echoes them. Commission %, voucher prefix and max top-up (₦ → kobo) validated to the serializer's limits.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Settings → Team `/settings/team`                 | `tenant-memberships/` (+`role`), `POST`, `PATCH {role}`, `DELETE`                                                        | Every member can see the team; writes are owner-only (`team.manage`). Add-by-user-ID **must send `tenant` = own tenant id** (the serializer requires it even for owners — gap #27). The sole owner's role select and remove button are disabled client-side and the server's “final tenant owner” 400 is surfaced verbatim if reached. “Already exists” / “does not exist” field errors are reworded.                                                                                                                                                                                                                                                                                                                                                                                                     |
| Settings → Subscription `/settings/subscription` | `subscriptions/` (404 → none), `pricing/`, `subscriptions/checkout/` (idempotent), `subscriptions/payments/{reference}/` | Current plan card (trial/expired states) + pricing grid. Checkout is owner-only: 200 opens `authorization_url` in a new tab and stores `?reference=`; 503 keeps the returned reference too (the pending `SubscriptionPayment` exists — gap #28). The tracker polls the reference every 5 s and invalidates the subscription on success.                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

`/settings` and `/settings/profile` redirect to `/settings/general`; the tab strip in `SettingsLayout`
only lists tabs the principal can open and each tab is additionally route-guarded.

## 7d. Agent portal & public storefront (Phase 7)

The agent portal (`/agent/*`, `AgentLayout`: top bar + bottom tabs, single column ≤ 48 rem) is
phone-first because agents sell from shops. Every call goes through `features/agent/api.ts`
(`agentPortalApi`) with `tenantId: null` — agents have no membership, so no `X-Tenant-ID` is ever
sent. The public pages (`features/storefront/`) use `anonymous: true` and work with or without a
session.

| Screen                                            | Endpoints                                                                                                         | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home `/agent`                                     | `agents/me/`, `agent/dashboard/`, `agent/vouchers/history/?page_size=5`                                           | Balance (dark-blue stat), sold today / total, two primary actions (Sell, Fund → `/agent/wallet?fund=1`), last five sales. The **Commission this month** card is only rendered when the value is > 0 because the backend never computes it (gap #5). If no storefront is connected yet the connect card is shown inline.                                                                                                                                                                                                                                                                                                                        |
| Sell `/agent/sell`                                | `public/tenants/<slug>/plans/` (catalogue), `agent/wallet/balance/`, `POST agent/vouchers/generate/` (idempotent) | **Gap #1:** agents get 403 on `plans/` and the API never tells them their tenant's slug, so the portal asks once for the operator's storefront link (`StoreLinkForm` → verified with `public/tenants/<slug>/`, stored in `localStorage` `yr.agent.storeSlug`, `useStoreSlug()`). Plans render as radio cards; quantity 1–100; the wallet charge (price × quantity) is previewed and the button is disabled when it exceeds the balance. Errors: `plan_id` field error (plan not in the agent's tenant/inactive), `Insufficient wallet balance` → warning with a funding link. One `Idempotency-Key` per attempt, rotated after every response. |
| Sale result (same page)                           | —                                                                                                                 | Lists each voucher’s **access code** (username == password for vouchers issued after the credential-delivery change; `access_code` in the response) with copy actions, "Copy all codes" and print. Legacy rows (`access_code: null`) fall back to the username with an honest note that the operator issues that password.                                                                                                                                                                                                                                                                                                                     |
| Wallet `/agent/wallet` (+ `/agent/wallet/return`) | `agent/wallet/balance/`, `agent/wallet/payments/?status&reference`, `POST agent/wallet/fund/` (idempotent)        | Balance stat + top-up history (status filter, pagination). **Fund** dialog (`?fund=1`): quick amounts ₦1 000–₦10 000, naira input → kobo, local floor ₦500; the tenant ceiling comes back as an `amount` field error. 200 → `window.location.assign(authorization_url)` after saving the reference locally (`pendingCheckout`, key `yr.checkout.pending`); 503 → warning with the reference (a pending row exists — same pattern as subscriptions). `FundingTracker` polls `?reference=` every 5 s until success/failed. `/agent/wallet/return` (Paystack return URL, gap #9) restores the reference from the URL or from local storage.       |
| My vouchers `/agent/vouchers`                     | `agent/vouchers/history/?status=`                                                                                 | Allocation history (username, amount charged, “Paid from wallet / On credit / Free”, sold time) with the voucher-status filter the API supports. Footer explains where passwords come from.                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Profile `/agent/profile`                          | `agents/me/`, `PATCH agents/{id}/` (phone, shop_name), `auth/change-password/` → `agent/login/`                   | Account facts (status badge, commission rate read-only, agent id), shop form (diff-only PATCH; `commission_rate` is ignored by the serializer), connected storefront card (verify/disconnect), password change (shared `ChangePasswordForm` with `loginKind="agent"` so the re-login after `CHECK_REVOKE_TOKEN` uses `agent/login/`), sign out.                                                                                                                                                                                                                                                                                                |
| Storefront `/s/:slug`                             | `public/tenants/<slug>/`, `public/tenants/<slug>/plans/?ordering=price&page_size=100`                             | Operator name + plan cards (price, validity, data, speed). 404 slug → dedicated not-found screen; plans are only requested once the tenant resolves. Empty catalogue → empty state.                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Checkout `/s/:slug/checkout/:planId`              | `POST buy/` (idempotent, anonymous)                                                                               | Email required (receipt + credentials), name/phone optional, order summary card. 200 → save `{kind:'voucher', reference, slug}` locally and redirect to Paystack; 503 → “temporarily unavailable” with the reference, key rotated; unknown plan → “no longer available”.                                                                                                                                                                                                                                                                                                                                                                       |
| Payment result `/pay/result?reference=`           | `payments/callback/?reference=`                                                                                   | Polls every 5 s while `pending` (manual “Check again”), then: **success + `access_code`** → `AccessCodePanel` (code, copy, plan summary, “How to connect” steps, masked email the copy went to); **success without a code** (voucher already used, or a legacy voucher) → username only + “already used / emailed to …”; **failed/abandoned** → not charged; 404 → “could not find this payment”. Accepts `trxref` too and falls back to the locally remembered voucher checkout when Paystack drops the query string; clears it once settled.                                                                                                 |
| Pricing `/pricing`                                | `pricing/`                                                                                                        | Active platform plans with features and a **Get started** → `/register` CTA (read-only catalogue).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

Money never originates in the frontend: every amount shown comes from the API in kobo, the only
client-side arithmetic is the sale preview (`sellCost`) which the backend re-validates.

## 7e. Platform admin console (Phase 8)

`/platform/*` (`PlatformLayout`, dark-blue "platform" accent) is reachable only by
`platform_admin` principals (`RequireCapability capability="platform.admin"`); the backend enforces
`IsPlatformAdmin` on every endpoint used here, so the guard is UX only. Admins have **no tenant
context**: every call in `features/platform/api.ts` (`platformApi`) passes `tenantId: null` so no
`X-Tenant-ID` header is ever sent. The console is deliberately an _administration_ surface — the
tenant-scoped operational data (vouchers, plans, sessions) stays in each operator's workspace,
because the API only exposes the `platform/*` read models to admins (gap #22).

A cached **tenant index** (`useTenantIndex`, pages through `tenants/?page_size=100` once, 5-minute
staleness) backs the `TenantSelect` filter on every list page and the `useTenantName()` lookup,
because the platform lists return tenant _ids_ only.

| Screen                                | Endpoints                                                                                                                                    | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview `/platform`                  | `platform/dashboard/`, `tenants/?is_platform_admin=false&page_size=5`                                                                        | Tenants (active), routers (onboarded), agents, vouchers; revenue by source (voucher sales with pending count, wallet top-ups, subscriptions) — all figures straight from the API in kobo. Newest five operator tenants + quick links.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Tenants `/platform/tenants`           | `tenants/` (`search`, `is_active`, `is_platform_admin`), `POST tenants/` (idempotent)                                                        | Defaults to **operators only** (`is_platform_admin=false`); the "Kind" filter can show the platform's own tenant or everything. **New tenant** dialog: name, slug (auto-suggested with `slugify()` until edited; `^[a-zA-Z0-9_-]+$` like the backend `SlugField`), contact fields, active switch. Slug conflicts come back as a `slug` field error. Success navigates to the detail page.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Tenant detail `/platform/tenants/:id` | `tenants/{id}/`, `PATCH`, `DELETE`; `tenant-memberships/?tenant=`, `POST`/`PATCH`/`DELETE tenant-memberships/`                               | **Overview** tab: profile facts, member/voucher counts, cross-links (`/platform/routers?tenant=`, `/platform/payments?tenant=`, `/platform/staff?tenant=`, `/platform/audit?tenant=`), **Deactivate/Reactivate** (`PATCH is_active`, confirm dialog) and a **Danger zone** delete — `DELETE tenants/{id}/` is a _hard_ delete that cascades everything, so the dialog requires typing the slug. The platform tenant can neither be deactivated nor deleted from the UI. **Members** tab (`?tab=members`): same rules as workspace Team (last-owner guard client- and server-side, role select, remove) plus an **Add member** dialog by numeric user id (no user search endpoint — gap #34). Agent/staff/admin accounts are rejected with a translated `user` error.                                                                                                                                                   |
| Router fleet `/platform/routers`      | `platform/routers/` (`tenant`, `onboarding_state`, `deployment_status`, `is_active`, `search`)                                               | Read-only; reuses `RouterStateBadges`. Tenant column links to the tenant page. Onboarding actions stay inside the operator workspace.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Payments `/platform/payments`         | `platform/payments/`, `platform/wallet-payments/` (`wallet__agent__tenant`), `platform/subscription-payments/` (+ `pricing/` for plan names) | Three source tabs (`?source=vouchers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | wallet  | subscriptions`) over one URL-backed filter state (tenant, status, reference search); each tab only fetches when active. "Abandoned" exists for voucher sales only and is dropped when switching. Subscription payments have no search parameter server-side, so the search box is hidden there. |
| Staff access `/platform/staff`        | `platform/staff-assignments/` CRUD, `platform/staff-invitations/` list/create/`revoke`                                                       | **Assignments** tab: user, tenant link, service chips, active badge; **Edit grants** (services checklist grouped Routers/Live sessions/Payments/Vouchers + active switch; diff-only PATCH — user/tenant are immutable by API design) and **Revoke** (DELETE). **Invitations** tab: status (an overdue `pending` row is displayed as _expired_ client-side), expiry, **Revoke** (idempotent; invitations cannot be deleted — 405). **Invite staff** posts `{email, tenant, services}` and shows the **one-time link** `/accept-invitation?token=…` with a copy button and an explicit "shown once, not e-mailed" warning (the response is `Cache-Control: no-store`; GET never returns the token). The client requires ≥ 1 service even though the API accepts `[]` (gap #35). **New assignment** is for staff accounts that already exist (`non_field_errors` translated: member/agent/admin account, duplicate pair). |
| Audit `/platform/audit`               | `platform/audit-events/` (`tenant`, `action`, `actor`, `search`, `ordering`)                                                                 | Shares `AuditLogView` with the workspace audit page; adds a tenant filter/column ("Platform" for tenant-less rows) and platform deep-links (`tenant` → tenant page, `staffassignment`/`staffinvitation` → staff page). Vocabulary now covers the generic `<model>.created                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | updated | deleted`events emitted by`AuditedCrudMixin`(plans, routers, devices, vouchers) and`command.executed`.                                                                                                                                                                                           |

## 8. Verifying against the real API

The backend needs PostgreSQL + FreeRADIUS in production. For frontend verification a
**SQLite harness** runs the Django code of the branch under test (`harness/` in this repo — see
its README: a settings module that swaps the database, a SQL file that creates the unmanaged
`rad*` tables, and a seed script with one user per role — `admin`, `owner`, `manager`, `staff`,
`pstaff` (2 tenants), `pstaff1` (1 tenant), `agent` (active, wallet seeded), `agent2` (pending),
`nobody` — plus payments in every state (`PAY-FULFILLED-001`, `PAY-FULFILLED-CODE-001`,
`PAY-UNFULFILLED-002`, …), two open `radacct` sessions and the `WH` voucher prefix).

`npm run test:integration` runs `src/integration/*.integration.test.tsx` against `127.0.0.1:8000`.
A Vitest `globalSetup` (`vitest.liveSetup.ts`) signs the harness users in **once** and shares the
token pairs with every file (`liveTokens()` / `asLiveUser()` in `src/test/liveSession.ts`; the
`agent` user signs in through `agent/login/`), so a full run only spends ~8 of the 10/min anonymous
login budget; if a run follows another too closely the setup waits out the `Retry-After` once. It
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
Phase 6 (`phase6.integration.test.tsx`) adds: transactions list/filter/search/detail (staff 200,
recovery/audit 403), recovery retry → 503, deliver 409 guards (“only fulfilled”, “acknowledge”) and
202 with the acknowledgement flag, audit filters by action/actor/resource, profile + billing PATCH
round-trips (keys never echoed, commission > 100 → field error), team add (missing `tenant` → 400,
duplicate → field error) → role change → last-owner 400 → manager 403 → remove, subscription 404 →
pricing → checkout 503 with a pollable pending reference (manager 403), and a change-password
round-trip. Phase 7 (`phase7.integration.test.tsx`, agent session) adds: profile/stats/wallet/history
agreeing on one balance, the public tenant + plans (ordering/search) + 404 slug + anonymous pricing,
agent generate (wallet debited by price × quantity, `access_code` == `voucher_username` with the `WH` tenant prefix, `Idempotency-Replayed` on the
same key, foreign plan → `plan_id` field error, quantity 101 → 400), funding floor/ceiling errors and
503 with a pending top-up findable by reference, public `buy/` → 503 with a pending reference that
`payments/callback/` reports as `pending` (seeded `PAY-FULFILLED-001` → `success` + username with `access_code: null` because that voucher has a legacy password; seeded `PAY-FULFILLED-CODE-001` → `access_code` == `voucher`, `code_revealed: true`, masked email; unknown → 404), agent
self-PATCH (other agents 404, `plans/` 403, manager → 403 on agent endpoints) and the agent/storefront
pages rendering live data. Phase 8 (`phase8.integration.test.tsx`, admin session) adds: stats +
every tenant (platform tenant flagged) + fleet/money/audit lists with tenant filters honoured,
owner/platform-staff → 403 on `platform/*`, tenant create (duplicate slug → field error) → PATCH
`is_active` → agent account rejected as member → hard delete → 404, last-owner demote/remove → 400,
invitation create (token present once, absent from list) → invalid service 400 → revoke twice,
assignment create → duplicate 400 → member account 400 → grants PATCH → revoke, and the overview /
tenants / staff pages rendering live data. Paystack is unreachable from the harness, so retry,
checkout, funding and buy always end in 503 there.

> The harness `admin` user must have `is_platform_admin=True` (a Django superuser alone gets 403 on
> every `platform/*` endpoint); the seed script sets it.

---

## 9. Phase log

| Phase | Status | Notes                                                                                                                                                                                                                                                                                    |
| ----- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | ✅     | Analysis approved (`analysis/`).                                                                                                                                                                                                                                                         |
| 2     | ✅     | Toolchain, tokens, API types, http/auth services, formatting/validation libs, component library, dev gallery, 43 unit tests.                                                                                                                                                             |
| 3     | ✅     | Shell & auth (guards, layouts, login/register/reset/invite/select-tenant, navigation), SQLite harness, live tests.                                                                                                                                                                       |
| 4     | ✅     | Dashboard, plans, vouchers (generate/print/detail), live sessions.                                                                                                                                                                                                                       |
| 5     | ✅     | Routers (list/register/detail/operations), agents (directory/detail), devices. 109 unit + 21 live tests.                                                                                                                                                                                 |
| 6     | ✅     | Payments + recovery board, audit log, settings (general/account, billing, team, subscription). 132 unit + 28 live tests.                                                                                                                                                                 |
| 7     | ✅     | Agent portal (home, sell, wallet + Paystack return, vouchers, profile) and public storefront/checkout/result/pricing. 157 unit + 35 live tests.                                                                                                                                          |
| 8     | ✅     | Platform console: overview, tenants (CRUD, activation, hard delete, members), router fleet, payments (3 sources), staff (invitations with one-time token, assignments/grants), platform audit. 173 unit + 42 live tests.                                                                 |
| 8b    | ✅     | Credential delivery follow-up (with backend PR): storefront result page shows the single access code + connect steps while the voucher is unused and says where the email went; agent Sell/history and workspace voucher detail show `access_code`; gaps #2/#10 resolved, #40/#41 added. |
| 9–11  | ⏳     | Performance, responsive & a11y hardening; production readiness.                                                                                                                                                                                                                          |

### Toolchain notes

- `typescript` pinned to `~5.9` (typescript-eslint peer range `<6.1`); Vite 7 with
  `@vitejs/plugin-react` 5 (Vite 8 was released but the plugin/vitest matrix is not yet uniform).
- `react-router` pinned to `^7` per the approved plan (v8 exists; not adopted).
- Chunking: `react` (react, react-dom, react-router), `query`, `forms` (RHF + zod, loaded only by
  routes with forms). Baseline shell: ~112 kB gzip JS incl. React + Router, 7.7 kB CSS.
