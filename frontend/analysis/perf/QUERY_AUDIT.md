# Query key / staleness audit — phase 9 (performance)

Scope: every `useQuery` in `src/features/**/queries.ts` + `src/app/**`. Goal per
`06_IMPLEMENTATION_PHASES.md` phase 9: *no duplicate fetches on navigation*.

## Global policy (`src/app/providers/queryClient.ts`)

| Setting | Value | Rationale |
| --- | --- | --- |
| `staleTime` | 30 s (default) | Lists survive sidebar round-trips without refetching |
| `gcTime` | 5 min | Back-navigation within 5 min is instant, no spinner |
| `refetchOnWindowFocus` | `true` | Re-focus is a cheap, user-initiated freshness signal |
| `retry` | never for 4xx; max 2 (exp. backoff, cap 8 s) for network/5xx | Auth/permission/validation errors must not retry |
| mutations `retry` | `false` | Writes are guarded by idempotency keys instead |

## Key taxonomy — one root per feature, colocated `*Keys` factory

| Feature | Root key | Keys | `staleTime` overrides | Polling (`refetchInterval`) |
| --- | --- | --- | --- | --- |
| dashboard | `dashboard` | `stats`, `live(params)` | 30 s both | stats 60 s; live 10 s (paused on Sessions page, off in background) |
| sessions | (dashboard `live`) | `live(params)` | 30 s | 10 s while page open |
| plans | `plans` | `list(params)`, `options(bool)`, `detail(id)` | options 60 s | — |
| vouchers | `vouchers` | `list(params)`, `detail(id)` | 30 s | — |
| payments | `payments` | `list`, `detail`, `recovery…`, `deliveries(id)` | 30 s | deliveries 5 s **only while a delivery is live** |
| routers | `routers` | `list`, `options`, `detail`, `checks`, `health`, `audit`, `operations` | options 60 s | operations 5 s **only while an operation is open** |
| agents | `agents` | `list(params)`, `detail(id)` | 30 s | — |
| devices | `devices` | `list(params)` | 30 s | — |
| audit | `audit` | `list(params)` | 30 s | — |
| settings | `settings` | `profile`, `billing`, `team`, `subscription`, `memberships` | 60 s–5 min | subscription 5 s **only while status is `pending`** |
| storefront | `storefront` | `tenant(slug)`, `plans(slug)`, `checkout`, `status(ref)` | 60 s–5 min | status 5 s **only while pending** |
| agent portal | `agent-portal` | `me`, `stats`, `wallet`, `fundings(params)`, `funding(ref)`, `history(params)` | me 5 min; rest 30 s | funding 5 s **only while pending** |
| platform | `platform` | `stats`, `tenants(list/detail/index)`, `memberships`, `routers`, `payments` ×3, `audit`, `invitations`, `assignments` | 30 s–5 min | — |

**Every paginated list** uses `placeholderData: keepPreviousData` — paging/filtering
keeps the previous rows on screen instead of flashing skeletons.

## No duplicate fetches on navigation — how it is guaranteed

1. **Single source of truth per query.** Each feature exposes a `*Query()`
   factory (key + `queryFn` + `staleTime`) that is shared by its hook and by the
   nav prefetcher (`src/app/navigation/routeQueries.ts`). Hooks only add
   observer-side concerns (`placeholderData`, `enabled`, `refetchInterval`).
2. **Single source of truth for initial params.** Each feature exports
   `*_DEFAULT_PARAMS` / `*_DEFAULT_ORDERING` constants; pages feed them into
   `useListParams` and the prefetcher passes them to the factory, so the
   prefetched entry and the page's first render hash to **the same key**.
3. **Same staleness on both sides.** Prefetch uses the factory's `staleTime`
   (30 s), so a page mounting ≤ 30 s after hover finds *fresh* cached data and
   issues **no second request**. TanStack dedupes concurrent identical fetches,
   and `prefetchQuery` is a no-op while data is fresh.
4. **Audited:** no component fetches with an inline `queryKey`; no duplicated
   key shapes across features; router options (`routers/options`) and plan
   options (`plans/options`) are shared between all consumers that need them.

### Prefetch registry (hover / keyboard focus on nav)

| Route | Prefetched before navigation |
| --- | --- |
| `/` | dashboard `stats` + `live` (page 1, 1 row) |
| `/sessions` | dashboard `live` (page 1) + router options |
| `/plans` | plans list (default ordering `price`) |
| `/vouchers` | vouchers list (`-created_at`) + plan options |
| `/payments` | payments list (`-created_at`) |
| `/agents` | agents list |
| `/routers` | routers list (`name`) |
| `/devices` | devices list + plan options |
| `/audit` | audit list (`-created_at`) |
| `/platform` | platform `stats` + 5 newest tenants |
| `/platform/tenants` | tenants list (default view) |
| `/agent` | agent `me` + `stats` + 5 recent allocations |
| `/agent/wallet` | agent `wallet` + fundings (page 1) |
| `/agent/vouchers` | agent allocation history (page 1) |

All other nav destinations prefetch only their route chunk. The registry is
covered by unit tests (`src/app/navigation/prefetch.test.ts`): every nav item
has a chunk loader, every queried route has a prefetcher and vice versa.

## Invalidation map (mutations → what they refresh)

Mutations invalidate by **root key**, so every dependent list/detail refetches
atomically after writes:

- plans CRUD → `plans` (3 mutations)
- vouchers generate/manual/disable → `vouchers` **and** `dashboard`
- devices CRUD → `devices`
- payments deliver/retry → `payments` (+ `detail`)
- router provisioning/secrets/edits → `routers` (+ detail/health/checks/audit)
- agent portal money ops → `agent-portal` `me`/`stats`/`wallet`/`history`/`fundings`
- platform tenant CRUD → `platform.tenants` + `platform.stats`; memberships,
  invitations and assignments invalidate their own subtrees
- settings team/billing/subscription → `settings` subtrees
- dashboard disconnect → `dashboard.live`

## Findings

- ✅ Keys are colocated, hierarchical and structurally hashed (param objects are
  safe regardless of property order).
- ✅ Polling is bounded and conditional everywhere — nothing polls forever or in
  the background (`refetchIntervalInBackground: false`).
- ✅ The font-family/`prefetch` changes add **zero** requests on navigation; the
  only new requests are the prefetches above, which replace (not duplicate) the
  request the page would otherwise make on mount.
- ⚠️ Watch item: `PLATFORM_RECENT_TENANTS_PARAMS` (`/platform` overview) and the
  tenants list use different key shapes by design (different endpoints shape);
  keep the constants colocated in `features/platform/queries.ts` if the overview
  list ever grows past 5 rows.
