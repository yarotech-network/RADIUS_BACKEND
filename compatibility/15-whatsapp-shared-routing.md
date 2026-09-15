# WhatsApp shared routing and sender isolation

Reference: `../yarotech-radius-system-current/whatsapp_routing/{models,services}.py` and `vouchers/whatsapp_agent.py:accept_inbound_webhook`. Preserve the signed START format and pending-purchase switching rule, using explicit platform endpoint selection instead of first-connected configuration. This pass does not implement the Meta webhook, conversations, purchases or sending.

Implementation plan: add independent shared endpoint, tenant entry route, endpoint-scoped sender binding and durable purchase hold tables. Preserve existing connection/plaintext binding tables without inferred mappings. Platform admins configure the shared endpoint; tenant managers create/rotate/revoke their own link using expected versions. Shared tokens use the recovered source HMAC format and a dedicated configured key, with indexed unique selector lookup. Customer identities use keyed hashes, not plaintext or unkeyed telephone hashes. Imported route selectors can retain their published format with the original signing key after an explicit provenance-aware import; no import runs here.

Every bind/resolve is an internal service for a future signature-verified, deduplicated inbox; no HTTP endpoint accepts customer-provided identity as trusted routing authority. Endpoint -> entry route -> sender binding -> hold/payment is the write lock order. Endpoint locking serializes first binding creation, endpoint changes and competing tenant switches; this conservative per-endpoint serialization must be measured before scaling. External calls never occur inside these transactions. Binding expiry, version, route selector and endpoint version all must match. Open purchase holds survive binding expiry and block business switching. A hold is reserved before provider initialization and released only from matched persisted failed payment or successful fulfilled payment. These helpers must be wired into the next order adapter; they are not proof that that adapter already exists.

UI: platform endpoint settings and tenant preview/rotate/revoke controls, explicit confirmation for invalidating links, no claim of a live bot. GET creates no records. API writes use expected versions; repeated stale writes cannot silently rotate again. Settings save never sets provider verification. Connection changes clear verification and invalidate prior binding versions. No credentials in output/audit. Tenant subscription expiry stops new binds/resolution without changing voucher rights or deleting open holds.

Checks: token tampering/rotation/revocation, endpoint and tenant isolation, sender expiry, stale queued versions, pending and paid-unfulfilled switching blocks, configured-key failures, unverified endpoint rejection, API roles/tenants, schema preservation, UI states/confirmation, lint/typecheck/build. Migrations prepared only. PostgreSQL contention, live verification, import/reconciliation, QR/Meta webhook and payment/worker integration remain separate release prerequisites.

## Implemented contract

- `GET/PUT /api/v1/platform/whatsapp/shared-endpoint/`: platform administrator only; explicit singleton endpoint, encrypted write-only token, public number distinct from Meta ID. PUT requires `expected_version` (null only for first creation). Omitted token preserves the saved token. Every save clears provider verification and changes the endpoint version. Unresolved purchase holds prevent changing the Meta phone identity.
- `GET/POST /api/v1/whatsapp/entry-route/`: authenticated tenant manager scope; POST action `create`, `rotate` or `revoke`, with `expected_version`. Stale writes return 409. GET has no side effects. Creation/rotation require WhatsApp entitlement; new customer binding and resolution also enforce entitlement.
- Both summaries report `sales_available: false`. No API permits an administrator to claim provider verification by setting a flag. The platform page is `/platform/whatsapp`; tenant controls are under **Manage business link** on `/whatsapp`. Replacement/revocation requires confirmation. Links are private previews, with no QR distribution yet.
- `shared_routing.py` supplies internal bind, versioned resolve, reserve and release helpers. These are not connected to the current purchase endpoints. A future order adapter must reserve before payment initialization, deduplicate inbound events before binding mutations, and capture endpoint/binding versions before queued work runs. Never derive authority from an unverified inbound sender field.
- Release requires the same tenant/reference and persisted `verified_at`, plus a failed payment or a successful payment linked to that tenant's voucher. Pending, unverified and paid-unfulfilled records keep the hold. Release works after subscription expiry. Call after payment commit, outside payment-first lock scopes; retry failed reconciliation durably. Provider initialization failures without a verified payment outcome deliberately retain the hold until a recovery workflow can establish the outcome. A returned already-released reservation is not permission to initialize a new purchase with the same reference.
- Rebinding the same tenant after timeout may create a new binding version while retaining the old purchase hold. The hold belongs to the original reference and tenant, and still blocks switching; payment recovery must use that recorded identity rather than the latest conversation version.

## Migration and activation

Prepared `0004_sharedwhatsappendpoint_tenantwhatsappentryroute_and_more.py` creates four independent tables and indexed uniqueness for selectors, endpoint/customer hashes and purchase references. It does not import or modify legacy rows. The migration preservation test covers existing connection secrets and plaintext sender records and confirms the new tables start empty. No existing development or production database was migrated.

On a disposable PostgreSQL restore first, review `python manage.py migrate --plan`, then run `python manage.py migrate`. The full plan may contain prior module migrations; review all of it before changing an existing database. Start the matching frontend/backend together only after schema creation. Application rollback can leave these additive tables in place; do not reverse the migration after recording routes or holds, since reversal deletes them. Rehearse restore separately.

Configure separate random secrets of at least 32 bytes through the deployment secret store: `WHATSAPP_TENANT_ROUTING_SIGNING_KEY` and `WHATSAPP_SENDER_HASH_KEY`. Preserve them across releases. The sender hash key fingerprint is pinned to the endpoint; changing it rejects routing and configuration edits until explicit reconciliation, preventing open holds from being bypassed through new hashes. The signing key must match the old deployment if an explicit import preserves its published selectors; source code alone does not contain that production key. Existing unkeyed legacy sender hashes cannot be silently converted to keyed hashes without verified source identities. No automatic mapping or key fallback was added.

Do not set `verified_at` manually to enable sales. The next stage must implement provider verification, signed webhook ingestion and replay-safe message processing. Then connect conversation/order creation and durable outbound delivery. Shared platform routing is separate from the old platform-direct-sales channel, which remains to be compared and ported.

## Readiness gate

Local validation on 2026-09-15: 23 backend WhatsApp tests passed on a disposable in-memory SQLite database, including populated migration preservation. Migration drift check reported no changes. The 17 frontend WhatsApp/navigation tests passed; after correcting a TypeScript-only test selector option, the three shared-routing tests passed again. Full frontend ESLint and the TypeScript/Vite production build passed. Vite emitted non-blocking dependency annotation and existing subscription-page import warnings. No PostgreSQL race, live provider, router, deployed worker or browser visual validation was performed.

**Not ready for live WhatsApp sales.** This stage delivers setup and internal routing protections only.

| Gate | Status | Evidence / remaining work |
|---|---|---|
| Correctness | PASS | Local routing, hold lifecycle, stale version, expiry and API tests. |
| Validation | PASS | Strict numbers, signed token format, expected versions, safe purchase references. |
| Authentication | NOT VERIFIED | Existing authentication reused; no live identity-provider/session test. |
| Authorization | PASS | Platform-only endpoint and tenant-scoped manager controls tested. |
| Transactions | PASS | Explicit local atomic boundaries; no external calls while holding locks. |
| Concurrency | NOT VERIFIED | Endpoint lock design inspected; PostgreSQL race/locking tests still required. |
| Idempotency | PASS | Serial duplicate reservations and stale settings writes tested; inbox dedup still unimplemented. |
| Database constraints | PASS | Unique selector, reference and endpoint/customer; singleton check generated. |
| Indexes | PASS | Unique lookups replace selector scans in the new routing layer; production query plans unmeasured. |
| Migration safety | NOT VERIFIED | Populated SQLite preservation tested; PostgreSQL rehearsal/restore outstanding. |
| Error handling | PASS | Stale writes, missing verification, unavailable routes and unresolved holds rejected. |
| Logging | NOT VERIFIED | Safe audit payloads exclude tokens/senders; production logging review pending. |
| Metrics | NOT VERIFIED | No provider or worker metrics yet. |
| Tests | PASS | Local backend and frontend tests; lint and build evidence recorded below. |
| Performance | NOT VERIFIED | Endpoint-wide serialization requires load measurement before scaling. |
| Accessibility | NOT VERIFIED | Labelled inputs and confirmation interactions tested; real assistive technology pass pending. |
| Backwards compatibility | NOT VERIFIED | Source START format retained, existing new-system tables preserved; production import not rehearsed. |
| Documentation | PASS | Contracts, lock order, setup boundaries and release prerequisites documented. |
| Deployment safety | NOT VERIFIED | No deployment, provider call or live message performed. |
| Rollback strategy | NOT VERIFIED | Retain additive schema on code rollback; production restore untested. |
