# WhatsApp provider validation and customer workflow

## Plan before implementation

Reference: `../yarotech-radius-system-current/vouchers/whatsapp_agent.py` provider checks (849), conversation transitions (492), orders (668), sending (918), fulfilment (1038); `whatsapp_reminders.py` and reminder configuration at legacy models.py:2307. Preserve START/MENU -> numbered plan -> email -> payment URL, STATUS/PAID/MY VOUCHER/SUPPORT, one-device purchase, verified fulfilment, unused reminder after 24 hours and expiry lead times 2/24/72 hours for short/medium/long plans. New implementation uses snapshots of the displayed choices rather than recalculating numeric selections after a price/order change.

Build: read-only Meta phone/token validation with expected endpoint version and explicit configuration; a durable conversation/order/outbound workflow; bounded worker commands; status/recovery controls; default-off configurable reminders. Keep shared routing and platform-direct sales distinct. No live calls, sending, migrations on existing DBs or service changes during implementation.

Trust boundaries: only signed inbox events enter conversation processing. Revalidate captured tenant/binding/endpoint version and expiry under the endpoint lock. Tenant expiry stops menus/new purchases; already-paid fulfilment and credential delivery use the original order identity. Request bodies never determine prices or payment success. Provider status callbacks affect delivery only. Secrets/content remain encrypted or write-only, and error codes never include provider response bodies.

Transactions: endpoint -> inbox/conversation -> binding/hold -> order/payment/outbound. Create a unique processed-event record/state, purchase hold, frozen payment terms and order atomically. Perform Meta/Paystack calls outside transactions. Snapshot Paystack credentials on the order and reuse them for callback signature verification and reconciliation. Persist claiming state before external calls; stale payment initializations and uncertain sends become unknown, not automatic duplicate attempts. Safe explicitly rejected sends get bounded exponential retries; status callbacks reconcile accepted delivery. Fulfilment reuses the existing locked voucher service. Release a purchase hold only from verified failure or successful fulfilment. Outbox uniqueness deduplicates automatic voucher delivery/reminders independently of inbox dedup.

Operational controls: separate consumer and send flags default off. Meta API version must be configured explicitly for the new provider adapter; no silent use of the old v18 default. Read-only verification does not enable sending or prove receipt/delivery. Support commands and administrative recovery inspect the existing order; no replacement charge is created after an uncertain initialization. Free-form messages require a recent customer message; outside the service window use a configured approved template or hold for recovery. Reminder eligibility must be rechecked against voucher and RADIUS usage evidence without modifying access rights.

Changes: additive WhatsApp models/migration, provider/API/UI, conversation consumer, payment adapter and reconciliation, outbox worker/status handling, reminders/preferences and runbook. Existing payment API contracts remain intact. Migration expansion precedes code; rollback retains durable orders/receipts. Test provider timeouts/mismatch/redirects, tenant/key changes, stale events, menu snapshots, duplicate purchase/fulfilment/delivery, payment account snapshot, window limits, reminder eligibility and failure recovery. Existing DB and real PostgreSQL/router/Meta proof remain distinct from local tests.


## Implemented behavior

The shared-number flow now supports signed START business links, ten stable plan choices per page, MORE, email validation, frozen one-device purchase terms and the original Paystack account. STATUS/PAID checks the existing payment; MY VOUCHER retrieves its fulfilled voucher; SUPPORT gives the tenant contact. Individual tenant connection records remain configuration only: this worker uses the platform shared endpoint.

Provider verification checks the saved phone ID, displayed public number and token against Meta outside the database transaction. A concurrent settings update invalidates the result. This is phone/token verification, not proof of WABA ownership, app subscription, approved templates or actual delivery. The interface labels configured automation separately from a working deployment.

Payment verification checks the original reference, integer amount and NGN currency before reusing existing voucher fulfilment. Unknown initialization never automatically creates a second checkout. Paid fulfilment and credentials remain recoverable after tenant expiry; new menus/purchases and operator activity remain blocked by subscription policy. No RADIUS access policy or existing voucher deadline is changed by this stage.

Delivery uses an encrypted durable outbox. Provider acceptance, sent, delivered and read are distinct. Connection timeouts before sending and rate limits permit bounded retries; ambiguous responses or a worker dying during a send leave an unknown outcome. There is no exactly-once guarantee at Meta: explicit resend requires acknowledgement of possible duplicate delivery and a stable request UUID. A missing provider message ID cannot be reconciled from a status callback alone. Manual recovery never changes payment proof or issues another voucher.

Reminders default off. Tenants configure approved template names/language and timing; customers explicitly opt in using REMINDERS ON. A fresh signed STOP or REMINDERS OFF removes consent for that customer across this shared number, including after binding expiry. It does not send a confirmation or enable any business activity. An already in-flight message cannot be recalled. Queued reminders recheck consent, tenant entitlement, voucher state, expiry, template and language. Unused reminders conservatively stop after any RADIUS authentication attempt because the current unmanaged model lacks a portable reply-status field. Missing accounting evidence due to a database error suppresses the reminder.

Encrypted data includes inbox/outbox payloads, order recipient, checkout URL and payment account snapshot. Existing financial PaymentTransaction records still store customer email/phone in their established fields; this stage does not claim that every contact field in the application is encrypted. API recovery lists omit message content, access tokens and voucher credentials. Keep the Fernet key and routing/hash keys with the protected backup: losing them prevents recovery. There is no automatic retention purge; receipts, financial orders and deduplication evidence remain available.

## API and worker contract

All paths below are relative to `/api/v1/`:

- POST `platform/whatsapp/shared-endpoint/verify/`: platform admin; `{expected_version}`; 409 for stale configuration, 400 for unsuccessful validation. It makes a read-only Meta request and never sends a message.
- GET/PUT `whatsapp/reminders/`: tenant manager; full settings with `expected_version` on PUT. Missing route is not created implicitly; stale updates return 409; enabling a reminder requires its template name.
- GET `whatsapp/orders/?page=1`: tenant-scoped paginated states, with no secrets/contact payloads.
- POST `whatsapp/orders/{id}/recover/`: `{action: "recheck"|"resend", request_id: UUID, acknowledge_duplicate_risk: boolean}`. Resend requires acknowledgement, paid fulfilment and the original verified phone number. The UUID deduplicates resend requests. Recheck is a repeatable scheduling request, not a new financial transaction.
- `process_whatsapp --limit 25`: processes bounded inbox, payment, reminder, outbound and receipt batches. Default-off consumer flag gates work. Send flag separately gates Meta sends. **Consumer-on/send-off is not a financial dry run:** it can initialize/verify existing queued purchases and fulfil them. `whatsapp_inbox_status` is the read-only diagnostic.

Claims are committed before external calls and abandoned claims become recoverable after five minutes. Payment reconciliation backs off from 30 seconds to one hour and stops for operator recovery after 20 attempts. Safe send retries stop after five attempts. Reminders are scanned at most every 15 minutes per eligible order. Per-recipient messages are ordered; one endpoint lock serializes state changes. Provider I/O runs outside that lock. Performance and PostgreSQL concurrent-worker behavior still require target-environment testing.

## Migration and deployment runbook (not executed)

The additive migration is `0006_sharedwhatsappendpoint_verification_attempt_and_more`. Migrations 0003-0006 have not been applied to the user's existing database. This migration does not import legacy WhatsApp orders, credentials or consent. Do not treat legacy consent as opt-in for the new system without an explicit import/reconciliation plan.

1. Back up the target database and required encryption/configuration keys; restore into an isolated PostgreSQL rehearsal database. Validate the existing RADIUS table layout there. Use only the intended new backend database, not the old production database by assumption.
2. Keep webhook, consumer and send flags false. Review the migration plan and apply the additive migrations before starting code that queries the new tables. Using the target service environment:

   ```bash
   python manage.py showmigrations whatsapp_routing
   python manage.py migrate --plan
   python manage.py migrate
   python manage.py check --deploy
   python manage.py whatsapp_inbox_status
   ```

3. Set `WHATSAPP_GRAPH_VERSION` to a currently supported version for the Meta app. Configure `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, stable independent `WHATSAPP_TENANT_ROUTING_SIGNING_KEY` and `WHATSAPP_SENDER_HASH_KEY`, and `FERNET_KEY` in protected server configuration. Verify the target checkout's Paystack callback URL configuration. Never put these secrets in React variables or source control.
4. Save and verify the platform shared phone/token in the UI. Create one test tenant entry link. Apply the stage-16 exact HTTPS callback/proxy logging settings and verify the actual webhook subscription using the test setup. Verify Meta template approvals separately. The unused template body needs two text parameters: tenant name and plan name. Expiry needs three: tenant name, plan name, expiry ISO timestamp.
5. Prepare `deploy/ubuntu/yarotech-radius-whatsapp.service` and `.timer` for the actual service user, working directory, Python executable and environment path. The supplied paths are `/opt/yarotech-radius/backend` and `/etc/yarotech-radius/backend.env`; the VPS checkout currently discussed uses `/var/www/test.yarotech.com.ng/yarotech-radius-backend`, so adapt before installing. Do not point this worker at `/home/yarotech/yarotech-radius-portal`.
6. On the isolated setup, enable intake and consumer/send flags with test provider accounts/recipients, then run one bounded batch manually. Turning on sends can contact customers: review pending outbox counts first. Test the complete START -> selection -> email -> checkout -> verified payment -> voucher -> delivery receipt cycle, expiry blocking, STOP, duplicate callbacks, interrupted workers and recovery. Verify Wi-Fi login separately on the physical router.
7. After successful rehearsal, install the reviewed units and activate only the WhatsApp worker for this backend. With the files adapted and the service environment prepared:

   ```bash
   sudo install -m 0644 deploy/ubuntu/yarotech-radius-whatsapp.service /etc/systemd/system/
   sudo install -m 0644 deploy/ubuntu/yarotech-radius-whatsapp.timer /etc/systemd/system/
   sudo systemd-analyze verify /etc/systemd/system/yarotech-radius-whatsapp.service /etc/systemd/system/yarotech-radius-whatsapp.timer
   sudo systemctl daemon-reload
   sudo systemctl enable --now yarotech-radius-whatsapp.timer
   sudo systemctl status yarotech-radius-whatsapp.timer
   sudo journalctl -u yarotech-radius-whatsapp.service --since '10 minutes ago'
   ```

   The timer waits ten seconds after a completed batch; its own service instances do not overlap. Restart the specific new backend API service when changing its environment. No blanket restart of other hosted systems is needed. Monitor oldest unprocessed inbox age, payment `unknown/recovery`, outbound `unknown/failed/blocked`, timer failures, and provider receipts. Configure target alerts before public rollout.

Rollback: turn consumer/send flags off and stop the timer; stop intake if necessary. Preserve tables, keys, order references and receipt history. Do not reverse the additive migration or delete claims/orders to make queues look empty. An in-flight request can still finish after disabling flags. Reconcile unknown outcomes against the original provider account before any explicit resend or cancellation. A full database restore after external payments/messages needs separate financial reconciliation; code rollback alone cannot undo those effects.

## Protocol references

[Meta phone-number lookup](https://www.postman.com/meta/whatsapp-business-platform/request/li0unxe/get-phone-number-by-id) and [Meta text-message API](https://www.postman.com/meta/whatsapp-business-platform/request/0arw2jw/send-text-message-with-preview-url) inform the fixed-host adapter. The implementation uses a conservative 24-hour free-form window and requires configured approved templates for scheduled reminders, consistent with [WhatsApp Business messaging policy](https://whatsappbusiness.com/policy/). Template approval and supported API version must be checked against the actual account before activation.

## Validation and readiness

Local validation on 2026-09-15: 69 WhatsApp tests passed, with one PostgreSQL-only concurrency test skipped on SQLite. Another 45 payment/subscription-access regression tests passed in the broader run. All 23 distinct WhatsApp/navigation UI tests passed across the full and focused runs; frontend ESLint and the TypeScript/Vite production build passed. Migration drift check reported no changes. Populated 0005-to-0006 migration preservation passed on a disposable database. The build retains existing non-blocking Zod annotation and subscription-page import warnings. No live Meta, Paystack, PostgreSQL deployment, or physical-router proof is implied. Production status is **NOT VERIFIED / NOT READY for public activation** until the deployment and provider rehearsal is completed.

| Gate | Status | Evidence / remaining work |
|---|---|---|
| Correctness | PASS (local) | Menu, frozen payment terms/account, verified fulfilment and recovery tests. |
| Validation | PASS (local) | Invalid email, changed price, checkout host, rich-message shape and provider mismatch tests. |
| Authentication | PASS (local) | Signed webhook regression suite and real JWT expiry-gate tests. |
| Authorization | PASS (local) | Tenant-scoped recovery, platform-only verification, binding and entitlement revalidation. |
| Transactions | PASS (local) | Durable claims/holds/outbox and real disposable voucher/RADIUS-row creation. |
| Concurrency | NOT VERIFIED | Endpoint locking and uniqueness implemented; SQLite does not prove PostgreSQL locking. |
| Idempotency | PASS (local) | Replayed inbound, fulfilment, safe retry, unknown-outcome and manual resend identity tests. Provider exactly-once delivery is not claimed. |
| Database constraints | PASS (local) | Unique source event, payment, hold, processed event and outbound deduplication keys. |
| Indexes | NOT VERIFIED | Queue indexes present; target EXPLAIN/load checks remain. |
| Migration safety | NOT VERIFIED (target) | Populated SQLite expansion preserves prior configuration, inbox and watermark; PostgreSQL DDL/restore rehearsal pending. |
| Error handling | PASS (local) | Generic provider errors, bounded retries, explicit ambiguous states; no silent replacement payment. |
| Logging | NOT VERIFIED (target) | Aggregate diagnostics and secret-free worker failures; proxy/APM configuration needs target verification. |
| Metrics | NOT VERIFIED (target) | Inbox/order/outbound counts implemented; target alert delivery not configured here. |
| Tests | PASS (local) | Final counts below; provider calls mocked and PostgreSQL-specific test skipped. |
| Performance | NOT VERIFIED | Bounded fair batches; single-endpoint contention/provider throughput unmeasured. |
| Accessibility | NOT VERIFIED (full) | UI role/label/confirmation tests pass; manual keyboard/screen-reader review pending. |
| Backwards compatibility | NOT VERIFIED (live import) | Existing payment regression tests and populated migration tests pass; no legacy data import executed. |
| Documentation | PASS | Behavioral differences, contract, activation, templates, consent and rollback documented. |
| Deployment safety | NOT VERIFIED (target) | Flags default off; worker units prepared, not installed/enabled. |
| Rollback strategy | NOT VERIFIED (target) | Retain data and reconcile external outcomes; actual restore exercise pending. |
