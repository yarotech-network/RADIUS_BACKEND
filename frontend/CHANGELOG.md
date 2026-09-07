# Changelog

Notable changes to the Yarotech RADIUS frontend. Format follows
[keepachangelog.com](https://keepachangelog.com/en/1.1.0/); versions follow
[semver](https://semver.org/). Dates are UTC.

## [0.2.0] — 2026-09-07

### Added — email verification & public landing page (phase 12)

- New tenants verify their email with a 6-digit OTP before the account unlocks:
  registration returns no tokens, `/verify-email` collects the code (paste
  support, auto-submit, resend with a 60 s cooldown) and signs the owner
  straight into the workspace on success. Login answers `403
email_not_verified` and forwards to the verification step.
- Public landing page at `/` (hero, featured storefront plans for customers,
  subscription plans for businesses, about section); the workspace overview
  moved to `/dashboard`. The featured storefront is configured with
  `VITE_FEATURED_STOREFRONT_SLUG`.
- Two-sided authentication design (`AuthSplitLayout`): form on one side,
  dashboard preview and feature highlights on the other — applied to sign-in,
  agent sign-in, registration and email verification.

## [0.1.0] — 2026-09-07

First release: complete operator workspace, agent portal, public storefront and
platform console on top of the existing Django REST API (`RADIUS_BACKEND`,
`/api/v1`). The frontend contains no business logic of its own.

### Added — analysis & foundation (phases 1–2)

- Backend audit, API→feature map, architecture, design system, API gaps and the
  11-phase implementation plan (`analysis/`).
- Vite 7 + TypeScript (strict, `exactOptionalPropertyTypes`,
  `noUncheckedIndexedAccess`) + Tailwind CSS v4 token set, ESLint/Prettier,
  Vitest + Testing Library + MSW.
- Typed API contracts (`types/api`), HTTP client with JWT refresh single-flight,
  `X-Tenant-ID` context, `Idempotency-Key` support and a normalised error
  envelope; auth session + token store; formatting/validation libraries; the UI
  component library (buttons, inputs, dialogs/drawers, menus, tabs, DataTable
  with responsive cards, toasts, badges) and a dev-only component gallery.

### Added — shell & auth (phase 3)

- Router with auth/surface/capability guards, four layouts (workspace, agent,
  platform, public), login / agent login / register / forgot & reset password /
  accept invitation / select-tenant, responsive navigation (sidebar rail +
  mobile bottom bar + "More" drawer), SQLite harness for live backend tests.

### Added — core product (phases 4–8)

- Dashboard + live sessions (disconnect), plans CRUD, vouchers (generate, print,
  bulk print, detail, disable, custom vouchers), payments with recovery &
  delivery board, audit log, routers (stepped registration, health, onboarding,
  VPN provisioning with operation polling, RADIUS tests, secrets rotation),
  agents directory, devices registry, settings (general, billing, team with
  last-owner guard, subscription with Paystack checkout).
- Agent portal (home, wallet funding with Paystack return polling, sell with
  cost preview, my vouchers, profile) and public storefront, checkout, payment
  result and pricing pages (mobile-first, Lighthouse-oriented).
- Platform console: cross-tenant overview, tenants (CRUD, activation,
  memberships), router fleet, payments across all sources, staff invitations
  with one-time tokens and grants editor, platform audit.
- Credential delivery follow-up: the storefront result page surfaces the single
  access code with connect steps; agent sell/history and voucher detail show the
  access code.

### Added — performance (phase 9)

- Bundle budgets enforced in CI (`npm run size-check`): initial JS **133.5 kB
  gzip** (budget 150 kB), largest lazy chunk **36.7 kB** (budget 120 kB) —
  report in `analysis/perf/BUNDLE_REPORT.md`.
- Font fix: single latin-subset Inter Variable woff2 (48 kB vs 218.5 kB for all
  subsets) registered under the family name the stack actually references (the
  font previously loaded but never applied).
- Navigation prefetch on hover/focus: route chunks for every nav destination,
  query prefetch for top routes using the same factories and default params as
  the pages (no duplicate fetches) — audit in `analysis/perf/QUERY_AUDIT.md`.

### Added — responsive & accessibility hardening (phase 10)

- WAI-ARIA keyboard patterns for Tabs and SegmentedControl (roving arrows),
  Menu closes on Tab and restores focus to its trigger, mobile "More" drawer
  manages focus in/out, document titles for every route, 404 title.
- Full QA checklist with computed contrast ratios: `analysis/QA_CHECKLIST.md`.

### Added — production readiness (phase 11)

- Multi-stage `Dockerfile` (nginx static + same-origin `/api` proxy template),
  `.dockerignore`, gzip + immutable asset caching + SPA fallback in `nginx.conf`.
- Error reporting funnel: React error boundaries, `window.onerror` and
  unhandled rejections → `reportError` (console in dev, optional
  `VITE_ERROR_REPORT_ENDPOINT` in production).
- CI (typecheck · lint · format · test · build · bundle-budget check), this
  changelog, and the expanded `FRONTEND.md` (performance, a11y and deployment
  strategies).
