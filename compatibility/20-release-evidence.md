# Coordinated staging candidate ? 2026-09-15

Verdict: **NOT READY for production replacement**. This assessment covers the current working backend/frontend, public IoT additions, private RADIUS adapter, WhatsApp PostgreSQL corrections and operator-run staging/import tools. Reference source: `../yarotech-radius-system-current`. No deployment, existing-database migration, live provider call, message or physical-router change was performed in this work. Tests created/dropped disposable PostgreSQL databases only.

## Current validation

- Backend: final complete `apps` discovery ran **570 tests, OK, 1 skipped** (569 passed). The skipped test is the opt-in password-reset browser harness, which targets the separate embedded frontend. It is not proof of the current React app's browser behavior.
- PostgreSQL tests include payment replay, wallet/credit concurrency, first voucher activation, IoT competing checkout/duplicate verification, migration preservation, import rollback/replay and WhatsApp workflows. Local PostgreSQL 18.6; VPS version/locking behavior and restored data still require rehearsal.
- Frontend complete run: **369 passed / 370**, with the sole failure a required-label selector in the newly added IoT test. That selector was corrected; subsequent storefront/payment run **28/28 passed**, including both new IoT cases and the changed recovery UI. Earlier missing subscription fixtures and WhatsApp route-prefetch entries were fixed. No final all-files rerun after the selector correction is claimed.
- Frontend lint and production build passed after recovery changes, using `VITE_API_BASE_URL=/api/v1`. The build still reports dependency annotation and subscription-page chunking warnings; these were not treated as proof of load performance.
- Migration drift: `makemigrations --check --dry-run` reported no changes. Three new migrations are prepared, not applied to any existing database: core 0002 import evidence, IoT 0004 public purchases/payment-linked grants, vouchers 0009 standard RADIUS column model state. Disposable tests apply migrations normally.
- Three compatibility inventory tests passed. Staging settings loaded with synthetic configuration and rejected a non-staging database/default Redis DB. Shell syntax checks passed for manage, backup and restore scripts. Nginx, systemd and FreeRADIUS cannot be runtime-validated on this Windows host.
- OpenAPI generation still reports serializer/authenticator warnings across existing endpoints; exported schema completeness is not claimed.

## Review findings addressed

IoT orders now freeze price/duration/router/provider identity, require a signed ownership capability for renewal, retain paid-but-unfulfilled evidence, and create at most one grant per payment. Duplicate checkout reservations cannot create another committed payment/contact for the same initial MAC/device version. Existing suspensions are retained and unused time is added. Provider checkout references/URLs are validated before redirect.

Private RADIUS endpoints require a separate token, validate the trusted NAS source and MAC identity, reject ambiguous ownership, and separate credential lookup from post-auth activation. Existing valid vouchers survive operator-subscription expiry. Settings flags and templates do not prove enforcement; rate/cap/accounting/reauth must be exercised on the physical router. Revocation is checked at the next authentication, with a maximum 300-second session timeout; immediate CoA is not claimed.

WhatsApp worker and recovery queries now lock their own rows explicitly instead of PostgreSQL's nullable joined rows. Recovery selects the original frozen payment account for WhatsApp/IoT. Dashboard/customer/recovery reporting recognizes paid device fulfilment. Staging blocks live Paystack keys, restricts WhatsApp recipients, writes email to protected files, starts with loopback-only service networking, and keeps consumers disabled. VPS enforcement of service network controls must be checked before importing live router identities.

The old settings hardcode `hotspot`/port5433. `legacy_export_settings.py` overrides those explicitly for a restored database and read-only transactions. Export includes every discovered table except ephemeral browser sessions; unknown business tables reach the mapping report rather than disappearing through a prefix filter.

## Readiness gates

| Gate | Status | Evidence or remaining work |
| --- | --- | --- |
| Correctness | NOT VERIFIED | Local workflow tests pass; complete restored-data and physical-router behavior unverified. |
| Validation | PASS | IoT type/MAC/ownership/price/reference/unknown-field checks and negative tests. |
| Authentication | NOT VERIFIED | Private token and app regression tests pass; installed FreeRADIUS PAP/CHAP chain unverified. |
| Authorization | PASS | Tenant/NAS ownership, renewal capability, subscription gates and existing authorization regressions. |
| Transactions | PASS | Atomic grants/import rollback and PostgreSQL row-lock corrections tested. |
| Concurrency | PASS | Independent PostgreSQL competing-writer tests pass; network device-limit acceptance remains under authentication/performance. |
| Idempotency | PASS | Request replay, unique reservations/grants and import identity tests pass. |
| Database constraints | PASS | New unique/FK constraints applied in disposable PostgreSQL tests. |
| Indexes | NOT VERIFIED | Constraints create indexes; production-size query plans/accounting scans not measured. |
| Migration safety | FAIL | Automatic complete legacy mapping and real financial/relationship reconciliation are unfinished. |
| Error handling | PASS | Negative provider outcomes retain original references/evidence; failed imports roll back. |
| Logging | NOT VERIFIED | Candidate suppresses credential-bearing access URLs; VPS error-log behavior/permissions not inspected. |
| Metrics | NOT VERIFIED | No observed staging alert delivery, worker-backlog monitoring or service SLO evidence. |
| Tests | PASS | Local backend suite and frontend full/focused evidence above; external acceptance listed separately. |
| Performance | NOT VERIFIED | No agreed concurrency target or production-like load run. |
| Accessibility | NOT VERIFIED | Form/status component tests pass; full browser/keyboard/mobile journey not audited. |
| Backwards compatibility | FAIL | Legacy settlement/ledger/permissions/raw-RADIUS mappings are not yet complete. |
| Documentation | PASS | Plan, operator runbook, import limitations and RADIUS acceptance instructions supplied. |
| Deployment safety | NOT VERIFIED | Separate paths/role/database/cache/service/templates prepared; VPS execution unverified. |
| Rollback strategy | NOT VERIFIED | Protected backup and empty-target restore commands prepared; actual restore/reconciliation not run. |

## Blocking handoff

The draft import plan contains no guessed business mappings. The engine refuses unmapped operational/financial records and unmanaged SQL targets. It retains source evidence encrypted, but that does not by itself make the new operational reports compatible. Finish historical payment/settlement cardinality, wallet reversals/running balances, credit repayments/cancellations, account permissions/verification, encryption-key ownership, issued rights, queued WhatsApp work and raw RADIUS/NAS mapping against the restored snapshot before approving a full transfer.

Next operator work: follow the [VPS staging runbook](../deploy/staging/README.md), first confirming isolated ports/cache/database and installing the candidate. Export from the restored legacy copy, then share only redacted schema/count/coverage output. Keep the raw archive and keys private. Complete the mappings and rolled-back import rehearsal before target apply. Provider test credentials, approved WhatsApp test recipients, the physical router, backup/restore, monitoring and measured load acceptance follow; no production switch is included.
