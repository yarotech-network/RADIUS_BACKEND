# Yarotech RADIUS — Frontend analysis & plan (Phase 1 deliverable)

> Status: **analysis complete, awaiting review. No frontend application code has been written yet.**

| Doc | Contents |
|---|---|
| [01_BACKEND_AUDIT.md](./01_BACKEND_AUDIT.md) | What the backend actually does: apps, models, relationships, auth, **role/permission matrix**, cross-cutting contracts (pagination, errors, idempotency, tenant header, money, secrets), 10 traced workflows, response shapes |
| [02_API_FEATURE_MAP.md](./02_API_FEATURE_MAP.md) | All 93 API paths → frontend feature → screen → user action, grouped by surface |
| [03_FRONTEND_ARCHITECTURE.md](./03_FRONTEND_ARCHITECTURE.md) | Three surfaces (Workspace / Platform console / Agent portal) + Public; folder structure; data flow; HTTP client & auth/session design; caching policy; forms; tables; testing |
| [04_DESIGN_SYSTEM.md](./04_DESIGN_SYSTEM.md) | Colour tokens (white / blue / dark-blue), typography, status vocabulary, component inventory, responsive layout matrix, accessibility |
| [05_API_GAPS.md](./05_API_GAPS.md) | 22 backend gaps that constrain the UI, with the exact evidence and the honest fallback for each |
| [06_IMPLEMENTATION_PHASES.md](./06_IMPLEMENTATION_PHASES.md) | Phases 2–11 with definitions of done, verification approach, and new-repo hand-off |

## Executive summary

**The product.** A multi-tenant hotspot/ISP voucher platform on FreeRADIUS. Tenants (operators) define internet plans, issue vouchers whose credentials are written to RADIUS, onboard MikroTik-style routers through a state machine with optional WireGuard provisioning, monitor and disconnect live sessions, sell through agents (wallet funded via Paystack) and to the public (Paystack checkout + webhook fulfilment), and subscribe to the platform. Platform admins manage tenants, staff grants and read cross-tenant reports. Everything is JWT-authenticated, tenant-scoped server-side, paginated (`count/total_pages/current_page/results`), carries a `problem` error envelope, and supports optional `Idempotency-Key` on commands.

**Roles discovered (none invented).** `platform_admin`, tenant `owner` / `manager` / `staff`, `agent`, `platform_staff` (per-tenant service grants, requires `X-Tenant-ID`). The full matrix is in `01 §5`. Managers and owners are nearly identical; owners additionally manage the team and subscription checkout; tenant staff are read-only; agents only see their own wallet/vouchers.

**Proposed frontend.** One React + TypeScript (strict) + Vite + Tailwind v4 + React Router + TanStack Query codebase with three role-specific experiences:

- **Workspace** (`/`): Dashboard · Vouchers · Plans · Live sessions · Payments (+ Recovery) · Routers (+ Operations) · Agents · Devices · Audit · Settings (General, Billing, Team, Integrations, Subscription, Profile, Security).
- **Platform console** (`/platform`): Overview · Tenants · Router fleet · Payments (voucher / wallet / subscription) · Staff (invitations & grants) · Audit.
- **Agent portal** (`/agent`, mobile-first): Home · Sell · Wallet · My vouchers · Profile.
- **Public**: Login/Register/Reset/Accept-invitation, storefront `/s/:slug`, checkout, payment result, pricing.

**Most important gaps found** (details in `05`): agents cannot list plans or read generated voucher passwords via the API; there is no user search (membership/staff creation needs a numeric user id); voucher passwords are only obtainable through the print/PDF endpoints; no time-series or telemetry data exists (so no charts or online/offline indicators); Paystack return URLs must be configured in the Paystack dashboard. The UI will expose exactly what the API supports and will label these limits rather than fake them.

## Decisions I'd like confirmed before Phase 2

1. **Stack details**: React 19 + React Router v7 + TanStack Query v5 + Tailwind v4, headless components written in-repo (no shadcn/MUI), `react-hook-form` + `zod`, `lucide-react` icons, no chart/PDF/grid libraries. OK?
2. **Agent plan discovery** (gap #1): accept the storefront-slug workaround in the agent portal now, and request a tiny backend follow-up (`tenant_slug` on `agents/me/` or `GET agent/plans/`)?
3. **Voucher credentials** (gap #2): rely on `print/` HTML (+ client-side bulk print) in the workspace; agents see usernames only — acceptable for v1?
4. **Repository hand-off**: build under `frontend/` in this branch, then move verbatim to the new `yarotech-radius-frontend` repository at the end (or earlier if you create it and want me to push there).
