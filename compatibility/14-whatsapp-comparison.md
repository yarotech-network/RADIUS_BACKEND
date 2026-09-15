# WhatsApp compatibility: current recovered system to Django/React

## Source and scope

Legacy reference is exclusively `../yarotech-radius-system-current/`. The similarly named older folder is not the reference. New targets are this backend and `../yarotech-radius-frontend/`; the backend's nested frontend is not a target. This is source evidence, not proof of the VPS, Meta account, message delivery or payment health.

## Verified comparison

| Capability | Current recovered system | New system before this pass |
|---|---|---|
| Connection settings | `vouchers/models.py:TenantWhatsAppConfiguration`: encrypted token, unique Meta phone ID, public display number, WABA, language, connection status and timestamps | `apps/whatsapp_routing/models.py:TenantWhatsAppRoute` combines connection and routing; no public display number or provider verification |
| Shared tenant links | `whatsapp_routing/services.py`: signed START token, indexed selector, rotation/revocation; `vouchers/views.py:tenant_whatsapp_sales` exposes link/QR | Random HMAC selector verified by scanning active routes; link incorrectly uses Meta phone ID as public number; no management page |
| Shared endpoint selection | `_shared_whatsapp_configuration()` picks first enabled connected configuration by PK | No explicit shared endpoint selection |
| Sender isolation | Binding scoped by endpoint + hashed customer, configuration, expiry and version; pending purchases prevent tenant switching | Globally unique plaintext phone binding only; no expiry/version or workflow consumer |
| Platform direct sales | `PlatformWhatsAppSalesChannel`: explicit enabled singleton, configuration and tenant must match; verified live own Paystack gate | Missing |
| Conversation workflow | `vouchers/whatsapp_agent.py`: START, MENU, plan choice, email, payment, STATUS, MY VOUCHER, SUPPORT, expiration | Missing |
| Inbound events | Signed raw-body verification, provider message ID deduplication, durable events and worker claims | No WhatsApp webhook or message-event model |
| Payment and fulfilment | Separate order/payment/voucher/delivery states; expected amount/currency and tenant/customer associations | Payment fulfilment exists, but no WhatsApp order adapter; `apps/payments/delivery.py` sends email only |
| Delivery | Outbound queue, provider IDs, sent/delivered/read/failed states, operator retry | Missing WhatsApp delivery pipeline |
| Voucher reminders | Unused and expiring voucher reminders, approved-template configuration, durable reminders, retry/backoff, use-history checks | Missing |
| Operator UI | Tenant sales/QR/orders/settings plus platform connection administration | Capability names and DTOs exist, but no WhatsApp page/navigation |

The existing reminder module concerns voucher usage/expiry. Operator-subscription WhatsApp reminders must be mapped separately; they are not established by that module name.

## Behaviour to preserve and improvements needed

- Retain shared tenant links, dedicated connection records and the explicit platform sales channel as distinct concepts. Do not automatically route an unbound sender to whichever tenant owns the first available number.
- Preserve tenant/customer/order/payment identity throughout delayed events and delivery retries. Block tenant switching while a purchase is unresolved. Never infer historical tenant ownership from a phone number alone.
- Preserve paid rights and issued voucher terms. Expired tenant subscriptions block new catalogue sales and new checkout; they do not revoke existing Wi-Fi vouchers. Already-paid pending fulfilment is a separate recovery obligation.
- Keep financial enablement independent of connection enablement. Preserve payment-owner/subaccount associations rather than rebuilding old orders using today's settings.
- Preserve receipt/message/order IDs, hashes and encrypted recipient data using an explicit identity and encryption-key mapping. Do not print credentials, copy production ciphertext blindly, replay historic messages, or fabricate delivered status.
- Do not copy the old tenant `test_connection` path: it sets connected after a mock check. In the new system, saved credentials must remain unverified until a real provider check succeeds.
- Do not copy payment initialization under a long database transaction from the old conversation processor. Reserve durable operation identity, call the provider outside the lock, and reconcile an uncertain result using the same reference.
- Do not treat sent as delivered. A timeout after provider acceptance is uncertain and must not cause an automatic duplicate voucher message without reconciliation.
- Replace first-connected shared endpoint selection with explicit platform configuration. Preserve existing published selector/signing-key compatibility through a reviewed migration, or provide a deliberate link-replacement rollout.

## Implementation sequence and current bounded pass

1. **Setup visibility and public number correctness (this pass):** add public display number without guessing it from Meta ID; add a real React WhatsApp connection screen using existing tenant-scoped CRUD; protect token secrecy; show saved/unverified and clearly state that sales/webhook delivery is not yet connected. No test-send or purchase buttons pretend the full workflow exists.
2. **Connection/routing separation:** explicit platform shared channel configuration, indexed stable selectors, rotation/revocation/QR, migrated sender bindings with expiry/version and pending-order switching protection. Retain source provenance for old connections/routes.
3. **Webhook and conversations:** verify signatures before parsing; reserve every provider message in a durable inbox before any routing mutation; process all supported messages in a callback; bounded worker claims, retries and recovered leases; reject stale binding events.
4. **Orders and delivery:** connect snapshot-based checkout and verified payment fulfilment, recover paid-but-unfulfilled orders, queue delivery separately, reconcile provider callbacks and ambiguous outcomes.
5. **Reminders and operational review:** voucher reminders first, followed by any separately agreed operator/agent notifications; template eligibility, worker health, pagination, failure visibility and controlled real-provider tests.

## First-pass impact and validation plan

Backend: additive nullable-compatible display field, explicit non-secret token-presence output, validation, corrected URL helper and duplicate-tenant creation error. Existing routes/tokens/bindings remain unchanged. Schema before backend, backend before frontend. Do not apply to the existing database during this comparison.

Frontend: `/whatsapp` under existing WhatsApp capabilities, scoped query cache, explicit save, write-only replacement token held only in component memory, read-only view for staff, truthful incomplete integration state. No network request to Meta, Paystack or customers is part of setup saving.

Tests: display number differs from provider ID; missing public number yields no link; invalid input rejected; token not returned; duplicate setup returns validation error; tenant/role isolation and expiry; UI create/update/read-only and saved-state explanation; TypeScript/lint/build. Shared routing, live token verification, webhook processing, payment delivery, reminders and PostgreSQL migration remain separate unverified steps.

## First-pass result and activation

The WhatsApp sidebar entry and `/whatsapp` page are implemented for the existing capabilities. Staff see a read-only view; managers/owners can save/update connection details. Tokens stay write-only and are retained when omitted from PATCH. No provider connection status is fabricated. Tenant selection scopes the cache and resets form state. The corrected helper returns no customer link when the public number is missing.

Prepared migration: `whatsapp_routing/0003_tenantwhatsapproute_display_number.py`, additive with a blank database default. Existing Meta ID, encrypted token and routing secret remain unchanged in the populated-schema test. The migration is **not applied** to any existing local/production database. After reviewing the complete migration plan and a database backup, apply the reviewed schema before running the updated backend, then run the updated frontend. Do not guess display numbers or rewrite published legacy links as part of that schema step.

Local verification: 10 backend tests passed using a disposable SQLite database, including populated migration preservation. All 14 tests across the WhatsApp page and navigation shell passed. The shell fixture now supplies the active-subscription response required by the existing access gate; production access controls were not weakened. Scoped ESLint and the TypeScript/Vite build passed. Migration drift check reported no changes. Live provider, browser visual/accessibility, production PostgreSQL migration and shared routing tests have not been performed.

## Readiness gate

**NOT READY for production WhatsApp sales.** This pass implements setup and mapping only. The inbound/order/outbound/reminder workflow is still missing from the new system.

| Gate | Status | Evidence or remaining step |
|---|---|---|
| Correctness | PASS | Setup/API and public-number helper tests passed; sales excluded from this first pass. |
| Validation | PASS | Numeric Meta ID, public number format, blank token and duplicate-tenant cases tested. |
| Authentication | NOT VERIFIED | Existing auth reused; live credential/session handling not exercised. |
| Authorization | PASS | Manager write, staff denial and cross-tenant lookup tests; UI staff read-only. |
| Transactions | PASS | Existing audited CRUD and tenant lock retained; no external calls in saving. |
| Concurrency | NOT VERIFIED | Duplicate serial requests tested; target PostgreSQL contention not tested. |
| Idempotency | NOT VERIFIED | Existing generic create command wrapper retained; uncertain network creation needs reload/reconciliation, not a new sales attempt. |
| Database constraints | PASS | Tenant one-to-one retained; additive migration tested with populated state. |
| Indexes | NOT VERIFIED | No new lookup pattern for setup; eventual stable routing selector index still required. |
| Migration safety | NOT VERIFIED | SQLite preservation passed; production table locks/backup/rehearsal remain. |
| Error handling | PASS | Validation errors, duplicate setup rejection and truthful unverified status covered. |
| Logging | NOT VERIFIED | Existing audits reused; production retention and log review outstanding. |
| Metrics | NOT VERIFIED | Provider/queue metrics are part of the later worker implementation. |
| Tests | PASS | Local setup tests, lint and build passed; full WhatsApp integration not yet implemented. |
| Performance | NOT VERIFIED | One route per tenant; no load or provider queue benchmark. |
| Accessibility | NOT VERIFIED | Labelled controls and component interactions tested; real keyboard/screen-reader/zoom pass outstanding. |
| Backwards compatibility | NOT VERIFIED | Existing new-system secrets preserved; legacy shared routes/orders/bindings still require mapping. |
| Documentation | PASS | Current-folder evidence, gaps, behaviour, implementation sequence and migration notes recorded here. |
| Deployment safety | NOT VERIFIED | No release or live configuration change performed. |
| Rollback strategy | NOT VERIFIED | Retain the additive field on application rollback; production restore untested. |
