# Customer-plan implementation work plan

Scope: module-2 steps 1-2, based on `02-plans-subscriptions.md`. Subscription
commercial-policy decisions and the production importer remain separate.

1. Expand duration to decimal hours, expose canonical rounded seconds, preserve
   public/agent/type/router flags and archive instead of deleting. Default new
   fields preserve this checkout's existing sales availability; the later legacy
   importer must explicitly copy its flags.
2. Freeze terms for every new voucher, including manual and agent issuance.
   Preserve historical enforcement for existing rows; recover duration from issued
   seconds, activation/expiry or persisted RADIUS lifetime before plan edits.
   Block edits requiring unknown historical terms rather than inventing them.
3. Lock plan selection against edit/archive in issuance, agent wallet debit and
   public checkout. Keep already-reserved paid order fulfillment valid after
   retirement. Keep old purchased snapshots readable.
4. Add React duration, visibility, service/router and archive controls; update
   public/agent selection and shared types. Preserve unrelated user edits.
5. Prepare migrations, add behavior tests, run relevant backend/frontend checks,
   document migration/rollout constraints. No existing database is migrated.

Acceptance: fractional-hour input reaches integer-second RADIUS/activation;
private/agent-disabled/archived/IoT plans cannot sell as public hotspot vouchers;
archived plans retain history and cannot reactivate; price/duration/speed/data
edits never rewrite issued terms; cross-tenant router references fail; failed
issuance rolls back wallet/voucher/RADIUS writes; pending paid reservations remain
fulfillable after retirement. New custom rates are enforced; historical empty
rate snapshots retain their previous enforcement mode.

Schema: decimal plan hours, wider rate strings, plan channel/type/router/archive
fields, nullable issued seconds. Changing the duration column requires PostgreSQL
DDL/lock rehearsal and coordinated writer rollout; do not enable fractional plans
on old workers. No claim of rolling-version compatibility or router proof.

Validation: disposable SQLite API/service tests, migration state check, React
component/schema tests, HTTP contracts, TypeScript/build/scoped lint. PostgreSQL
contention, real FreeRADIUS and production restoration remain unverified.


## Implemented behavior and compatibility limits

- Decimal hours (six places) become saved whole seconds, rounded half up. Plan APIs accept fractional hours; a 0.333333-hour plan issues 1200 seconds.
- Separate public/agent flags and hotspot versus IoT/MAC type; tenant-scoped router assignment. IoT metadata and managed device assignment are supported, but a public IoT purchasing flow is not included. Public hotspot checkout excludes IoT plans.
- DELETE /api/v1/plans/{id}/ now archives and returns 204, including referenced plans. GET lists exclude archived records unless `archived=true`; retrieve retains history. Archived plans cannot be edited or reactivated. Django admin uses an explicit archive action.
- Agent sales load authenticated `/api/v1/agent/plans/`, including private agent-enabled plans. No storefront slug is required to sell. Public listings and checkout both enforce public availability. Server-side issuance rechecks availability while holding the plan lock.
- All newly created vouchers save price, duration, cap, speed and device terms. New custom nonempty rates are written to RADIUS; saved historical empty enforcement remains empty. Device capacity is saved and written as Simultaneous-Use; manual API creation accepts 1?10. Public device-count pricing/UI is a later voucher/payment module task.
- Existing version-1 purchase snapshots remain readable. Reserved orders with saved terms remain fulfillable after retirement. Unfulfilled historical orders without snapshots block term changes/archive rather than receiving invented terms.
- Unsnapshotted vouchers recover duration from issued seconds, activation/expiry or RADIUS. Unknown durations block activation/term-changing edits. Existing RADIUS/expiry values are not reset by a plan change. Other historical metadata uses available evidence: a missing original price/data-cap record cannot be proven from current plan data. These records still need reconciliation during import.
- Defaults keep existing NEW-system plans public and agent-enabled. The future legacy importer must map each legacy flag explicitly, convert Decimal NGN to kobo and map router IDs. This migration is not a legacy importer and must never be applied directly to the old portal database.

## User-run deployment preparation (not executed here)

1. Restore a fresh production backup into an isolated rehearsal database; record PostgreSQL version, table sizes, schema, RADIUS columns, worker topology and backup/restore evidence. Compare old source and actual data before any importer is approved.
2. For an existing NEW-system database, inspect `python manage.py migrate --plan` and `python manage.py sqlmigrate vouchers 0005` against that isolated configuration. Rehearse all pending migrations, including module-1 dependencies. Never use `--fake` to fit the old schema.
3. The integer-to-decimal ALTER can rewrite the plan table and needs an exclusive DDL lock. Measure lock wait, runtime, disk/WAL and row counts on the restored database. Rehearse bounded lock/statement timeouts; abort on excessive wait rather than queueing production traffic. Archive backfill work can lock many vouchers per plan, so measure high-volume plans too.
4. Stop old application writers/workers for the final new-system schema transition. Apply the reviewed migration set, deploy the matching backend/frontend, and only then enable fractional plans. This implementation does not support mixed old/new writers. Keep the old portal and its database separate during rehearsal.
5. After the schema exists, run `python manage.py audit_plan_compatibility` against the rehearsal database. It is read-only, reports IDs only, and exits nonzero for unknown durations/orders. A successful duration audit is not proof of original prices, caps or production import completeness.
6. Reconcile exceptions before enabling edits. Rehearse private/public/agent visibility, archived history, half-hour activation, old issued codes, payment replay and failure recovery on real PostgreSQL and an isolated RADIUS/router. Require exact balance, expiry, cap and row-count comparisons.
7. Before cutover, verify backup restoration and record the tested revisions of both repositories. Monitor purchase failures, issuance failures, audit exceptions, lock waits and API latency. Validate health and smoke paths through Nginx.

Rollback: keep the expanded schema and roll forward to corrected compatible code if possible. Old code does not understand fractional duration, sales-channel flags or archives; do not simply restart it after new writes. Reversing 0005 can round fractional values and drop archive/snapshot metadata. A full restore is only safe with writes stopped and a reviewed reconciliation plan for payments/vouchers created since the backup. No automatic downgrade or destructive rollback was run.

## Verification evidence and remaining gates

Scope: uncommitted local module-2 changes on backend base 7464430 plus existing module-1 work, and the matching top-level React repository; no VPS access, real payment, email or router action. Operator subscriptions (trial length, router-count rules, upgrade timing and complimentary grants) retain their existing policy.

| Gate | Status | Evidence / limit |
| --- | --- | --- |
| Correctness | PASS | Plan compatibility API/service tests: snapshots, archive, availability, fractional seconds, legacy rename. |
| Validation | PASS | Authoritative duration, device-capacity and tenant-router checks plus negative tests. |
| Authentication | PASS | Existing authenticated manager/agent permissions; account compatibility regression tests. |
| Authorization | PASS | Cross-tenant plan/router rejection and private/agent catalogue tests. |
| Transactions | PASS | Local voucher/RADIUS/payment failure rollback tests. |
| Concurrency | NOT VERIFIED | Plan locks implemented; PostgreSQL contention tests not run here. |
| Idempotency | PASS | Existing mocked webhook/recovery replay regression tests; no duplicate vouchers. |
| Database constraints | PASS | Disposable migration execution and archive constraint; migration state check. |
| Indexes | NOT VERIFIED | Archive index prepared; production query plans and selectivity unmeasured. |
| Migration safety | NOT VERIFIED | PostgreSQL ALTER/lock/restore rehearsal required above. |
| Error handling | PASS | Unknown historical terms reject changes atomically; frontend error/retry tests. |
| Logging | NOT VERIFIED | Existing audit/error paths retained; production collection/redaction not exercised. |
| Metrics | NOT VERIFIED | Production failure/latency/lock alerting not exercised. |
| Tests | PASS | Local results recorded below; external runtime limits remain separate. |
| Performance | NOT VERIFIED | Legacy term recovery can perform several queries per unsnapshotted voucher; large-plan freeze locks need rehearsal. |
| Accessibility | NOT VERIFIED | Component role/label tests cover controls; browser keyboard/screen-reader checks not performed. |
| Backwards compatibility | NOT VERIFIED | Local saved-term contracts tested; real legacy import and mixed-runtime operation not proven. |
| Documentation | PASS | Module map, this implementation record and operator runbook. |
| Deployment safety | NOT VERIFIED | Nginx/VPS/worker smoke checks not run. |
| Rollback strategy | NOT VERIFIED | Sequence documented; restored-data recovery not rehearsed. |

Production verdict: **NOT READY** pending the listed environment and data checks. No existing database migrations applied.


Local validation (2026-09-14): 93 backend regressions passed on disposable SQLite, followed by the final 15-test plan suite (14 repeated plus one audit test): **94 distinct backend tests**. Django system checks passed and `makemigrations --check --dry-run` reported no changes. Unmanaged RADIUS tables were disposable test fixtures. Two existing threaded PostgreSQL wallet tests were excluded from the SQLite validation after exhibiting SQLite table-lock failures; no PostgreSQL concurrency success is claimed.

Frontend: **82 distinct tests** passed across plans, agent portal, vouchers, storefront and devices. The initial parallel run had timing failures; the single-worker run passed 80/82, and the remaining two new plan tests passed after fixing selectors (final plan-page suite 5/5). Production `npm run build` (TypeScript + Vite) and scoped ESLint passed. Build emitted existing dependency annotation warnings, not errors. No real browser/router/provider proof is claimed. Final backend plan suite passed after the admin archive action and activation-order review fixes.
