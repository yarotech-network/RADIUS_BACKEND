# Business plan CRUD and enforced entitlements

Status: approved implementation completed and validated locally on 7 September 2026. Production deployment and browser checkout smoke test remain unverified.

## Confirmed request

Platform administrators manage business subscription plans with create, list/detail, edit, deactivate/reactivate and delete operations. Fields include name, price, duration in days, maximum routers, WhatsApp enabled, daily voucher printing maximum, additional feature text and published status. Public and tenant subscription pages display the same structured plan limits. Existing subscribers receive edited limits on renewal, not immediately (confirmed by user).

## Baseline before implementation and impact

- apps/subscriptions/models.py has SubscriptionPlan, TenantSubscription and SubscriptionPayment. Payments retain price but currently read duration from a mutable plan during completion.
- BusinessPlanViewSet currently provides admin-only list/create. Existing public pricing returns active plans.
- NASDeviceViewSet.perform_create is the router registration entry point. Existing AuditedCrudMixin supplies auditing and transaction boundaries.
- WhatsAppRouteViewSet configures routes; generate_route_url and model token resolution are the runtime route entry points. No complete messaging worker was found in this module; this work cannot claim enforcement in external integrations that bypass it.
- VoucherViewSet.print/pdf currently serves credentials through GET. The frontend fetches those documents sequentially and assembles a print sheet. The server cannot observe physical printer output or prevent copies of saved documents.

## Approved policies

1. Count distinct voucher IDs authorized for printing per tenant per Africa/Lagos calendar day. Same-day reprints are free. A whole selected batch must fit; reject it without partially consuming the allowance. Authorization counts even if the user later cancels the browser print dialog. This is a print-preparation allowance, not physical-sheet metering.
2. Count all registered routers, including inactive ones. Null limits mean unlimited; zero prevents new registrations/print authorizations. Do not automatically delete existing excess routers after a downgrade.
3. Preserve current access during migration: existing plans receive unlimited router/print limits and WhatsApp enabled, matching existing behavior. Existing subscriptions and pending payments receive snapshots of the currently stored terms; historical terms unavailable in the database cannot be reconstructed. Accounts without subscriptions retain legacy access until explicitly enrolled.
4. For subscribed tenants, expiry blocks new router registration, new print authorization and WhatsApp use; history and existing router records remain accessible. WhatsApp can always be disabled or deleted even when not included.
5. Delete only unreferenced plans. A plan referenced by any subscription/payment/entitlement period returns 409 with a deactivation alternative. Deactivation removes it from purchase choices without revoking a paid period.

## Data and payment design

- Add structured plan limits and a revision/version for optimistic update conflicts.
- Save immutable terms with each payment before contacting Paystack, including name, amount, duration and limits. Lock the plan row while snapshotting so edits and checkout are consistent.
- Preserve current paid subscription terms independently of the mutable catalogue.
- Model effective entitlement periods so an early renewal starts at the already-paid expiration rather than changing limits immediately. Serialize renewal fulfillment by locking the tenant, preserve duplicate-webhook protections, and append the purchased period once. Two renewals must preserve both purchased durations.
- Backfill current subscriptions as the active period and existing pending payments with current stored plan terms. Inactive/cancelled subscriptions retain history but do not grant access.
- Add a daily voucher authorization ledger with a unique tenant/day/voucher identity. Preserve usage if a voucher is deleted later that day.

## API and enforcement

- Extend /api/v1/platform/business-plans/ with GET detail, PATCH/PUT and DELETE. IsPlatformAdmin remains authoritative. Validate bounded integer limits, positive price/duration, booleans and feature strings. Mutations retain audit and idempotency conventions. Stale revision updates return 409, rather than overwriting another admin.
- Add an authenticated tenant-scoped POST /api/v1/vouchers/authorize-print/ for a batch of IDs; enforce existing printing grants, check all IDs belong to the selected tenant, lock the tenant and reserve only newly counted IDs atomically.
- GET print/pdf stays read-only. For limited subscriptions it requires a valid authorization for that day. Legacy unlimited consumers remain compatible. This closes bypasses of the normal frontend flow without making GET consume quota.
- Router creation takes the same tenant lock before checking and saving. Apply a consistent lock order across registration, printing, subscription fulfillment and entitlement changes.
- WhatsApp creation/enabling and runtime link/token handling check effective entitlements. Read/disable/delete remain available for maintenance.
- Tenant subscription response exposes effective terms, current registered-router count, today's prepared-voucher count, limit and reset timezone. No sensitive payment/provider data is exposed.

## Frontend delivery

- Admin business-plan directory with details, create/edit forms, active status and protected delete confirmation. Inputs distinguish unlimited from zero; all restrictions are labelled plainly.
- Public landing/pricing and tenant subscription cards show duration, router maximum, WhatsApp availability and daily voucher allowance from structured fields, not marketing text.
- Current tenant subscription shows the purchased effective limits and usage; early-renewal future terms are identified separately.
- Printing authorizes the entire batch before credential fetches. Quota errors remain visible and do not fall through to misleading partial-print success. Credential document failures permit safe same-day retry.

## Migration and deployment

Use additive migrations and an explicit backfill with bounded iteration. Inspect local database engine, affected row counts and pending payments before applying. Test migrations on a disposable PostgreSQL database first. Deploy the migrated backend and verify the new contract before frontend rollout. Do not enable catalogue edits until existing subscription/payment snapshots are populated. A coordinated backend cutover is needed if old workers could still complete payments using live plan terms. Retain additive schema during rollback; do not discard payment or usage history. Production deployment/migration execution is a separate operational step, not implied by local tests.

## Required verification

- Admin CRUD authorization, inactive visibility, protected deletion and stale-update conflict.
- Existing subscription terms survive catalogue edits; pending checkout uses saved price/duration/limits; early renewal preserves the current period; duplicate/concurrent renewals retain all purchased time exactly once.
- Router cap under concurrent creates and across tenants, zero/unlimited, expired subscriptions and downgrade behavior.
- WhatsApp create/enable/resolve boundaries and permitted maintenance.
- Print daily boundary in Africa/Lagos, same-day replay, batch atomicity, concurrent last-slot requests, cross-tenant IDs, deleted-voucher usage preservation and unauthorized direct print/PDF requests.
- Migration/backfill round-trip on test data, model migration consistency and relevant backend regressions.
- Frontend CRUD/forms, public/tenant limits, subscription usage and print error recovery; lint, TypeScript/build and browser responsive checks where tooling is available.


## Resumed payment completion

The user resumed business-plan completion to resolve successful Paystack payments remaining pending. Local migrations through 0005 are applied. Add an owner-only, tenant-scoped POST payment verification endpoint using the platform Paystack key. Validate provider envelope, exact reference, integer amount and NGN currency before calling the existing atomic, idempotent subscription fulfillment service. Provider calls must occur outside database locks; GET remains read-only. Rate-limit verification and preserve pending on unavailable or mismatched responses.

The subscription tracker verifies once on opening a pending reference and on explicit Check now, refreshes purchased terms after success, and retains an actionable retry message during provider failure. Validate missing-webhook recovery, repeated delivery, tenant/role boundaries, mismatches and unavailable provider; finish the existing business-plan checks. Inspect existing local test payments using provider evidence and reconcile only verified successes. Production rollout remains separate.


## Completion evidence - 7 September 2026

- PASS: 112 backend tests across subscriptions, payments, WhatsApp routing and core APIs, including migration backfill, admin CRUD, term snapshots, quota concurrency, missing-webhook recovery, provider mismatch/failure, owner isolation and verification throttling.
- PASS: 46 frontend tests across settings, business plans, voucher pages, public storefront/pricing and landing page. Recovery tests exercise automatic verification, retry and subscription cache refresh.
- PASS: scoped ESLint, TypeScript/production build and bundle budgets (134.8 kB initial JS gzip; 36.7 kB largest lazy chunk).
- PASS: local migrations through 0005 applied; makemigrations --check --dry-run reports no changes; Django system check reports no issues.
- PASS: direct Paystack test-mode verification confirmed one existing pending subscription payment. Reverification through the new service activated it, with exactly one purchased period. Three other pending records could not be verified and were left unchanged. No new charge was initiated; no references or keys are recorded here.
- NOT VERIFIED: production deployment/migrations, production webhook delivery, full browser redirect smoke test and physical printer output. The existing explicit callback URL configuration remains required. Deploy backend before frontend; retain payment/period/usage history on rollback.

Recovery API: POST /api/v1/subscriptions/payments/{reference}/verify/ is owner-only and tenant-scoped, limited to 10 requests/minute per user. It returns the existing payment serializer on verified success or a provider non-success state; 503 means verification unavailable, 409 means mismatched payment details, and neither activates a subscription. Only provider-confirmed success calls the same atomic fulfillment service used by webhooks. Repeated verified requests cannot extend twice. GET payment status remains read-only. Opening a pending reference and Check now invoke verification; successful verification refreshes purchased allowances.


## Browser validation follow-up

Actual Chromium browser checks passed for owner login, checkout initialization, confirmed-payment return, reload, 390px layout, injected verification failure with keyboard retry, duplicate real verification and login preserving the payment reference. Database expiry and the single purchased period were unchanged. Paystack hosted completion was blocked by Cloudflare security verification; no bypass was attempted. QA sessions were revoked and the temporary QA tenant/account disabled, preserving test history. See the sibling frontend BUSINESS_PLAN_BROWSER_QA.md for boundaries and the remaining normal-browser hosted checkout check. Production deployment remains unverified.
