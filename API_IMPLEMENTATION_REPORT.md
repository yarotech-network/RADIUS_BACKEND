# Backend API implementation and validation

Scope: the authoritative Django backend in `yarotech-radius-backend`, API v1.
No frontend integration, Git commit, push, production deployment, real payment,
outgoing customer email, or router configuration command was performed.

The implementation closes the backend workflow gaps listed below. The generated
`openapi-v1.yaml` is the field-level request/response contract, including required,
optional, read-only and write-only fields, validation limits, and pagination.
Production readiness remains separate from local implementation and testing.

## Available backend workflows

All paths below are relative to `/api/v1/`.

| Module | Implemented behavior |
|---|---|
| Accounts | Registration, login, current user, password change/reset; refresh-token rotation and blacklisting; authenticated `POST auth/logout/`; case-insensitive email uniqueness; password whitespace preserved. |
| Tenants | Tenant and membership APIs, final-owner protection, immutable membership identity, settings; `GET/PATCH tenants/profile/` for a manager's own contact/profile fields. Counts use distinct aggregates. |
| Plans and vouchers | Tenant-scoped plans; validated generation, manual voucher creation/edit/delete synchronized with RADIUS credential rows; paid, allocated, or used vouchers cannot be edited/deleted; disable remains available. Print escapes HTML; missing PDF support returns an explicit 503. |
| Tenant agent management | `tenant/agents/`: list, retrieve, create, PATCH, `approve/`, `suspend/`. Creation atomically creates a pending agent, hashed user password, wallet, and audit event. |
| Agent self-service | Login/profile, wallet, funding, paginated funding status/history at `agent/wallet/payments/`, voucher generation/history and statistics. Wallet spending and callback credits are transactionally protected. |
| Public catalogue | `public/tenants/{slug}/` and paginated `public/tenants/{slug}/plans/`; inactive tenants/plans hidden. Public purchase rejects inactive tenants. |
| Routers | Registration, filtered lists, audit history, checks, transitions, RADIUS tests; durable provisioning requests and polling; guarded secret replacement; health summaries based on stored data. |
| Payments | Existing public checkout, signed/verified webhooks and callback status; authenticated `payment-recovery/` with `retry/` and `deliver/`; `payment-deliveries/` status polling. Recovery verifies the original reference and never initializes another charge. |
| Subscriptions | Plans, current subscription, checkout and payment status remain supported. Checkout accepts idempotency keys. |
| IoT and WhatsApp routes | Tenant-scoped forms/APIs, filters, audit records; encrypted WhatsApp storage accommodates the ciphertext for the entire accepted token length. |
| Platform | `platform/dashboard/`, `platform/routers/`, `platform/payments/`, `platform/wallet-payments/`, `platform/subscription-payments/`. Voucher receipts, wallet funding and subscription receipts are reported separately. |
| Staff | Platform-controlled `platform/staff-invitations/` and `platform/staff-assignments/`; invitation acceptance at `staff-invitations/accept/`; personal assignment listing at `staff/assignments/`. |
| Audit | Read-only, paginated `audit-events/` and administrator-only `platform/audit-events/`; selected resource mutations record actor, tenant, action and safe metadata. Existing router-specific events remain available. |
| Dashboard and sessions | Revenue units, pending/paid-unfulfilled counts and observation time; bounded live-session results, router identification and filters. Addresses shared across tenants are excluded rather than assigned to either tenant. |

### Staff permissions

Assignments use dedicated staff accounts, not tenant owners, agents or platform
administrators. An assigned staff request must send `X-Tenant-ID` and have the
corresponding service grant. Ordinary tenant members remain bound to their own
membership, regardless of that header.

Available grants: `routers.view`, `routers.test`, `live_sessions.view`,
`live_sessions.disconnect`, `payments.view`, `payments.support`,
`vouchers.generate`, `vouchers.print`. An unrelated or inactive assignment does
not grant access. Payment support permits recovery and delivery commands;
payment viewing permits recovery/delivery status reads.

An invitation returns its random token only when created and stores a digest.
The administrator must share that token securely; invitation creation does not
send email. Tokens expire after three days and are single-use. Existing users
must authenticate as the invited email address. A new recipient submits token,
username and password to create an account with the invited email. No tenant,
role or grant is accepted from the recipient.

### Router commands and secrets

`POST routers/{id}/provisioning/` requires `action: provision|suspend` and returns
202 with an operation ID. Poll `GET router-operations/{id}/`. The command records
the intended WireGuard peer configuration before a worker executes SSH. A
router can have only one pending/running operation. Both the existing signed
internal endpoint and the new queue reject conflicting provisioning work.
Pending provisioning blocks configuration edits, deletion and secret changes.

`POST routers/{id}/replace-secrets/` requires `current_password` and
`expected_updated_at`; provide at least one of `nas_secret` or
`routeros_password_encrypted`. The latter accepts an empty string to explicitly
clear it. These inputs are plaintext over authenticated HTTPS; the backend
encrypts them. Ciphertext cannot be submitted as a replacement. Secrets never
appear in router responses or audit metadata. A stale version returns 409.
If a deployed NAS secret is replaced, the NAS SQL record is updated atomically.
Actual router/FreeRADIUS configuration and reload coordination still require an
operational deployment procedure.

`routers/{id}/health/` returns configuration/onboarding state, recorded checks,
last-seen and observation timestamps. `online` is null and
`telemetry_available` is false. CPU load, uptime, model, WireGuard handshake,
latency, traffic, restart and inferred per-router online-user totals are not
invented from last-seen data.

### Payment recovery and delivery

Recovery validates provider status, original reference, amount and NGN currency.
Verified evidence is retained when voucher fulfillment fails, yielding
`paid_unfulfilled`. Concurrent recovery produces one voucher and one set of
credential rows. Provider verification remains outside the fulfillment lock.

Delivery is an explicit authenticated command after fulfillment. States are
`pending`, `sending`, `accepted`, `failed`, `unknown`. `accepted` means acceptance
by the configured email backend, not delivery to an inbox. A timeout/crash can
leave an unknown outcome. The worker never automatically resends that message.
Repeating an accepted/unknown delivery requires
`acknowledge_duplicate_risk: true`. Payment and delivery history remain separate.
There is no public resend/recovery endpoint.

### Idempotency and errors

Commands marked with an `Idempotency-Key` parameter in OpenAPI support durable
duplicate suppression. Keys remain optional for existing v1 clients; clients
should generate an unpredictable key for each logical command and reuse it on
transport retries. Accepted syntax is 16–128 ASCII letters, digits, `_ . : -`.
Keys are scoped to authenticated actor, tenant context, method and path. The
request fingerprint is an HMAC; plaintext request bodies are not retained.

- Same key and payload after completion: replay the original status/body with
  `Idempotency-Replayed: true`.
- Same key with another payload: 409.
- In-flight or ambiguous command: 409 with command ID and `Retry-After`.
- Known API errors are retained as completed outcomes. Do not automatically
  replace a key after a timeout or 503; check payment/operation state first.
- Reservations are not automatically expired or deleted. Removing a reservation
  can permit execution again. An operator must reconcile ambiguous records
  against domain records/provider results before any manual repair. Never
  blindly clear processing records or replay a financial command.

API failures retain existing v1 fields and add
`problem: {code, message, fields}`. Database/provider unavailability is reported
without SQL, credentials or infrastructure details. CORS accepts the idempotency
and tenant-selection headers.

## Contract changes requiring later frontend alignment

These changes are intentional; this task did not migrate consumers.

1. Router `audit/` and agent voucher `history/` now return paginated envelopes:
   `count`, `total_pages`, `current_page`, `results`.
2. Live sessions retain `users` but `count` is the total matching count; pages,
   observation time and `source: radius_accounting` are included. Filters are
   `username`, `router`, `page`, `page_size`.
3. Regular router PATCH/PUT cannot replace secrets; use `replace-secrets/`.
4. Agent self-service cannot create/delete profiles or change privileged fields.
5. Voucher editing/deletion cannot alter paid, allocated or used credentials.
6. Refresh rotation blacklists old refresh tokens; logout revokes the submitted
   refresh token. Existing access tokens last until expiry; password changes
   revoke them through the configured password-revocation check.
7. Long/invalid fields, inactive resources and conflicting identities now return
   validation/conflict errors. Missing PDF support returns 503 instead of HTML
   pretending to be a PDF.

Collections use bounded pagination (default 20, maximum 100). A router's finite
set of onboarding checks remains a small array. Public catalogue, plans, router
lists, payment views, agents, memberships and histories expose relevant filters
or search. API schema pagination matches the actual envelope.

## Local verification and migration evidence

Validation uses Python 3.12, Django 5.2.17 and PostgreSQL 18.6 at READ COMMITTED.
API tests use `config.test_settings` and the isolated `test_yarotech_radius`
database. External provider/SMTP/SSH calls are replaced at their boundaries;
concurrency and transactional RADIUS credential writes use real PostgreSQL.
The opt-in password-reset browser test is outside this API-only task.

Final command results are recorded in `API_VALIDATION_RESULTS.txt`.

The local `yarotech_radius` database was backed up, restored to a temporary
database, upgraded through 19 pending migrations, rolled back, and upgraded
again. The restored account count was preserved. The temporary database was
removed. The verified migrations were then applied locally with lock/statement
timeouts; counts were preserved across 12 existing business models.

Backup:
`C:\Users\dell\AppData\Local\Temp\yarotech-api-backup-i2pd95x6\before-api-migrations.dump`

The same directory contains the previous local environment configuration. Keep
both files private. The weak local Django/JWT signing key was replaced; existing
local tokens and reset links need to be reissued. The Fernet encryption key was
preserved. The inherited shell value `DEBUG=release` is invalid; validation
commands explicitly use `DEBUG=False` without changing machine-wide variables.

## Worker operation

Run with the backend virtual environment and the appropriate environment:

```powershell
$env:DEBUG = 'False'
.\venv\Scripts\python.exe manage.py process_router_operations --limit 20
.\venv\Scripts\python.exe manage.py process_payment_deliveries --limit 20
```

These commands cause real SSH/email effects when jobs exist. They were validated
with tests and zero-item batches; no real job was dispatched in this task.
Schedule repeated bounded batches under a supervised deployment worker.

Router jobs use five-minute leases and attempt fencing. Expired leases may be
retried because WireGuard set/remove converges on the stored desired state.
Failed jobs expose a safe error code and require a deliberate new command.
Email jobs left sending for over five minutes become unknown, never automatic
resends. `EMAIL_TIMEOUT` defaults to 30 seconds. Configure SMTP rather than
treating console-backend acceptance as actual email delivery.

Watch pending age, failed router operations, unknown deliveries, paid-unfulfilled
payments and processing API commands. Production alert thresholds, ownership and
scheduling must be configured in the actual deployment environment.

## Production readiness gate

Verdict: **NOT READY for production deployment**. Backend implementation and local
verification do not prove provider activation, device behavior, consumer
compatibility or production operational readiness.

| Gate | Status | Evidence / remaining work |
|---|---|---|
| Correctness | PASS | API behavior, worker outcomes, recovery and regression tests. |
| Validation | PASS | Required/optional field contracts, limits, secret handling and malformed-body tests. |
| Authentication | PASS | Login/reset suite, refresh revocation and logout tests; local signing key strengthened. |
| Authorization | PASS | Tenant, role, staff-grant and cross-tenant session-address tests. |
| Transactions | PASS | Real PostgreSQL rollback of wallet, voucher and credential writes. |
| Concurrency | PASS | Independent connections test double spending, funding, fulfillment and command exclusion. |
| Idempotency | PASS | Replay, changed-body conflict, pending exclusion and conservative ambiguous outcomes. |
| Database constraints | PASS | Unique email/command/assignment/active-job constraints and migration validation. |
| Indexes | NOT VERIFIED | Constraint/FK indexes exist; production-scale query plans are not measured. |
| Migration safety | NOT VERIFIED | Local backup/restore/upgrade/rollback passed; production data size and lock budget are unknown. |
| Error handling | PASS | Provider/database errors, invalid payloads and uncertain delivery tests. |
| Logging | NOT VERIFIED | Safe audit/operation records exist; deployment retention and access controls are not verified. |
| Metrics | NOT VERIFIED | State/backlog records are queryable; production alerting and worker monitoring are not configured here. |
| Tests | PASS | See final recorded suite/schema/check results; browser integration excluded by scope. |
| Performance | NOT VERIFIED | Bounded results, joins and aggregates improved; no production load test performed. |
| Accessibility | N/A | Backend API scope; no frontend UI was modified. |
| Backwards compatibility | NOT VERIFIED | Breaking consumer changes are listed above; consumer integration intentionally deferred. |
| Documentation | PASS | Field-level OpenAPI, behavior changes, commands, recovery limits and backup recorded. |
| Deployment safety | NOT VERIFIED | No production deployment or real provider/device smoke test was authorized or performed. |
| Rollback strategy | NOT VERIFIED | Local restore and schema reversal tested; new long ciphertext cannot safely fit old short columns. Production rollback requires a planned forward fix or restored backup and stopped workers. |

Before production: validate real Paystack verification/webhooks, SMTP delivery,
WireGuard/RouterOS/FreeRADIUS schemas and counter policies, RADIUS authentication
and disconnect behavior; coordinate client changes; configure workers, HTTPS,
secrets, monitoring and the production migration/rollback window.

Still intentionally outside implemented scope: support cases, customer CRM,
invoices, usage reports, reconciliation, router approval requests, public
resend/recovery, advanced WhatsApp conversations/orders, business-plan limits and
speculative router telemetry. These must not be presented as working API features.
