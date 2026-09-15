# WhatsApp signed webhook and durable inbox

## Implementation plan

Reference: `../yarotech-radius-system-current/vouchers/whatsapp_agent.py:182-202,250-270,376-490`. The old handler checks signatures but processes only the first message, handles status callbacks before messages, and deduplicates after changing the sender binding. Stage 15 provides internal routing but no provider endpoint.

Add `/api/v1/whatsapp/webhook/` GET verification and POST raw-body HMAC-SHA256 verification, enabled explicitly by deployment configuration. Bound bodies/batches and validate the entire batch before writing. Process every message/status; commit receipts and routing together before acknowledging. No sending, payments, provider verification, worker dispatch or automatic replay in this stage.

Add independent inbox and sender-watermark tables. Deduplicate by provider phone and event identity before routing, regardless of endpoint configuration version. Encrypt customer payloads, hash sender identities with the existing key and fingerprint canonical payloads using a keyed hash. Endpoint -> receipt -> route -> binding is the lock order; all writers serialize on the endpoint. Database failure rolls back the batch and returns a retryable error. No broker handoff or external calls occur.

Sort batched events by provider timestamp and retain a strictly increasing sender watermark. Delayed or equal-timestamp messages are held without routing; customers may need to repeat ambiguous messages in the next second. Duplicates never refresh a binding. Ready receipts capture tenant, endpoint and binding versions; the future consumer must revalidate these, expiry and entitlement before business effects. Never automatically replay a blocked/stale/conflicting receipt under the latest binding.

Threats: forged identities, tampered bodies, repeated START switching, changed-content event IDs, partial batches, resource exhaustion, stale routing and plaintext leakage. Controls: raw signature before JSON/DB access, bounded schemas, unique identity, atomic locks, watermark, immutable snapshots, encryption and aggregate-only diagnostics. A signed callback does not prove token validity and must not set `verified_at`. Unverified/inactive endpoints retain blocked receipts. Unknown phones are ignored without assuming a tenant.

Targets: WhatsApp models/migration, parser/view, URLs/settings/example configuration, aggregate status command, platform read-only reception status, tests and documentation. Existing legacy rows remain unchanged. Flags default off; schema expansion precedes code rollout. Rollback retains receipts and dedup identities. No live DB migration, service operation or provider message is authorized by this local implementation.

Tests: challenge, signatures, disabled/missing config, malformed/oversized batches, dedup before routing, ordering, tenant isolation/expiry, open holds, encrypted storage, snapshot validity, rollback/retry, summary permissions and migration preservation. PostgreSQL concurrency needs a separate rehearsal.

Protocol references: [Meta webhook SDK documentation](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/) and [Meta payload reference](https://www.postman.com/meta/whatsapp-business-platform/folder/tduohwq/webhook-payload-reference). No dependency on the archived SDK is introduced. Main Meta Graph webhook documentation returned HTTP 429 during inspection; no live provider test was performed.

## Implemented contract and operating notes

- GET requires `hub.mode=subscribe`, the configured verification token, and a numeric challenge. It returns the challenge as plain text with no-store caching. It never changes endpoint verification or sales status.
- POST requires `X-Hub-Signature-256: sha256=<hex HMAC>` over the exact request bytes. Body limit: 256 KiB. Event/change limits: 100. Malformed signed envelopes return 400; bad signatures return 403; oversized bodies return 413; disabled/missing configuration or failed persistence returns 503 with Retry-After 60. A 200 means every relevant receipt committed or was deduplicated, not that a reply or purchase succeeded.
- Inbound identities use phone number ID + message ID. Status identities also include status and provider timestamp so delivery progression is retained. Canonical payload fingerprints detect changed-content reuse. Exact duplicates increment only a receipt counter; conflicts flag the original receipt and never perform a second routing mutation. Identities survive configuration version changes.
- Message state: `ready` means routing succeeded and a future consumer is needed; `blocked` means no valid selection, pending-purchase policy, expired entitlement or unavailable endpoint; `stale` means ordering/freshness failed; `unsupported` means an unsupported message type. `status` is a delivery receipt, with no financial or outbound delivery mutation. `conflict` requires investigation. No state in this release sends a reply.
- Freshness window is seven days with five minutes of future clock tolerance. Strict per-sender monotonic timestamps intentionally hold distinct same-second messages. Preserve watermarks and dedup keys; do not clear them as a routine retry mechanism. A future consumer must reject stale routing snapshots under the same endpoint lock and cannot treat the binding foreign key's current tenant as the event's historical tenant.
- Unverified endpoints accept encrypted blocked receipts, but neither GET verification nor signed POST sets `verified_at`. No automatic replay is provided: replaying old selections without order reconciliation would be unsafe. Provider connection validation and conversation/order processing remain required before public use.
- Unsupported message payloads are retained encrypted but not interpreted; media is never fetched. Valid signed callbacks for other phone IDs are counted as ignored, not routed into the first available tenant. The old platform-direct-sales fallback has not been enabled.

Read aggregate diagnostics with `python manage.py whatsapp_inbox_status`. This command performs no mutations and emits no phone numbers, bodies, signed entry links or message identifiers. It reports state counts, duplicate total, latest receipt and oldest ready receipt. `consumer_enabled` is false in this stage. Before launch, the platform operator must monitor 400/403/503 responses, conflict and blocked counts, endpoint lock contention, inbox growth and oldest-ready age; alerting and thresholds are not deployed here. Provider retries can repeat an accepted event after a lost HTTP response; the unique identity makes this harmless.

## Deployment and rollback

Prepared migration: `0005_whatsappinboundevent_whatsappsenderwatermark.py`; no existing database was migrated. It creates two tables with a unique event key, unique endpoint/phone/customer watermark, protected foreign keys and a state/received-time index. Populated migration tests preserve old connection secrets, shared selectors, binding versions and unresolved holds. There is no data import, table rewrite or backfill. PostgreSQL DDL/lock duration, existing tenant/endpoint FK locks and restore behavior still require a disposable production-like rehearsal.

Review `python manage.py migrate --plan` on a disposable restore before running `python manage.py migrate` there. Apply the reviewed schema before deploying the matching application. Existing prior-module migrations may also appear in that plan. Retain the additive tables on application rollback; reversing 0005 after intake would delete receipts and replay protection.

Deployment settings: keep `WHATSAPP_WEBHOOK_ENABLED=False` until schema, secrets, endpoint identity and reception tests have been checked. `WHATSAPP_APP_SECRET` is the Meta app secret; `WHATSAPP_WEBHOOK_VERIFY_TOKEN` is a separate high-entropy secret configured identically in Meta and the server. Routing keys and the stable Fernet key from stages 14/15 are also required. Do not put these values in frontend environment variables, query examples, source control or tickets. Use the exact HTTPS callback path above, without a redirect.

The Nginx HTTPS template now disables access logging on the exact callback and enforces the body limit. The systemd template loads `deploy/ubuntu/gunicorn.conf.py`, whose access format uses the path-only `U` atom and omits query strings/referers. [Gunicorn documents these atoms here](https://gunicorn.org/reference/settings/#access_log_format). The old default request-line log included the verification token query. A local synthetic formatting check confirmed query credentials are omitted. On the target host, update the actual templates/paths/port, run `nginx -t` and systemd configuration checks, and inspect proxy/application/error/APM logs with a disposable verification token before enabling intake. No Nginx/systemd change, restart or live Meta callback occurred here.

## Validation and readiness

Local evidence on 2026-09-15: 41 backend WhatsApp tests passed, including signature/CSRF behavior, whole-batch rollback/retry, dedup before routing, ordering, encryption and populated migration preservation. One PostgreSQL concurrent-delivery test is prepared and skipped on SQLite. Migration drift check reported no changes. Seven WhatsApp UI tests passed; full frontend ESLint and TypeScript/Vite build passed. The build retains non-blocking dependency annotation and existing subscription-page import warnings.

Scope: local webhook reception, durable receipts, routing integration, platform configuration status and deployment templates. **NOT READY for live WhatsApp sales.** Provider verification, conversation/order consumers, sending, target PostgreSQL and actual deployment remain unverified or unimplemented.

| Gate | Status | Evidence or prerequisite |
|---|---|---|
| Correctness | PASS | Whole-batch, duplicate, stale selection and rollback tests pass within this reception scope. |
| Validation | PASS | Signed envelopes, identity/timestamp/phone bounds, malformed second-event and size-limit tests. |
| Authentication | PASS | Raw-body signature and challenge tests; browser CSRF exemption requires provider signature. |
| Authorization | PASS | Configured phone only, tenant route/entitlement enforcement, unchanged platform-admin summary permission. |
| Transactions | PASS | Receipt, watermark and binding rollback together on injected DB failure. |
| Concurrency | NOT VERIFIED | PostgreSQL duplicate-delivery test prepared, not run locally. |
| Idempotency | PASS | Duplicate/conflict handling precedes routing; configuration changes do not erase identity. |
| Database constraints | PASS | Unique identity and watermark generated; migration preservation tested on SQLite. |
| Indexes | NOT VERIFIED | Declared lookup/queue indexes inspected; target query plans unmeasured. |
| Migration safety | NOT VERIFIED | Populated preservation passed; target DDL, locks and restore not rehearsed. |
| Error handling | PASS | No 200 on persistence failure; safe errors and retry response tested. |
| Logging | NOT VERIFIED | Aggregate application logs and access templates implemented; target error/APM logs need validation. |
| Metrics | NOT VERIFIED | Read-only diagnostics implemented; alerts and monitoring integration not deployed. |
| Tests | PASS | 41 backend, 7 frontend tests, lint and build pass; PostgreSQL test explicitly skipped. |
| Performance | NOT VERIFIED | Bounded batch/body; serialized endpoint contention and provider acknowledgement latency need load tests. |
| Accessibility | NOT VERIFIED | Status text uses existing UI; no live screen-reader/visual check. |
| Backwards compatibility | NOT VERIFIED | Old rows preserved and source START format retained; real legacy import and Meta payload rehearsal pending. |
| Documentation | PASS | Contract, states, keys, retention, rollout and replay restrictions documented. |
| Deployment safety | NOT VERIFIED | Reception disabled by default; Nginx/Gunicorn/systemd validation on VPS outstanding. |
| Rollback strategy | NOT VERIFIED | Additive-table retention documented; real restore not tested. |
