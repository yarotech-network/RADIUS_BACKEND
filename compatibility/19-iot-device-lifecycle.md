# Module 19: IoT/MAC registration and operator renewals

## Plan before implementation

Reference only: ../yarotech-radius-system-current/vouchers/models.py:1871, mac_devices.py, views.py:3690 and services.py:1778. Legacy has UUID devices, optional plans, permanent/expiring access, active/suspended/expired/revoked/deleted states, retained audit history and globally unique active MACs. New apps/iot_devices currently has integer IDs, a required plan, globally unique MAC forever, is_active only, hard deletion and no renewal ledger. Registration currently performs no RADIUS authorization writes.

Accepted renewal policy: keep unused time using max(now, existing deadline) plus selected IoT plan duration. Operator renewals are explicit service grants, not recorded payments. Suspended remains suspended; revoked/deleted cannot renew until an explicit permitted state change. Customer/public paid IoT purchase fulfilment is a separate integration from this operator workflow.

Implement an additive lifecycle/version/deletion/legacy-UUID/snapshot representation, optional permanent plans, active-MAC uniqueness, strict canonical MAC validation, retained removal, explicit versioned/idempotent lifecycle and renewal APIs, renewal history, scoped React controls and truthful network status. Preserve imported identity/limits/deadlines rather than deriving legacy rights from mutable plan defaults. Existing inactive rows map to suspended; do not invent why they were inactive. Do not reassign current integer IDs or rewrite old router IDs. Leave migrations unapplied to existing databases.

Authorization: member read, manager/owner writes, tenant-owned router/plan, active unarchived IoT plan for new grants, router restriction checks. Use device row locks, version checks and the database active-MAC constraint; external I/O never occurs inside these transactions. Repeated renewal requests use the existing command key and cannot add time twice. Date and snapshot arithmetic is server-owned; no client-supplied duration/price/payment proof.

Network boundary: this stage updates the application registry only. It must not claim that disabling a registry record disconnects a live session. No radcheck/radreply writes, CoA, router login or service restart here. Source FreeRADIUS policy/SQL synchronization, data-cap enforcement and physical-router proof remain required before network activation. Accounting remains observational and must not assign shared MAC history to an arbitrary retained record.

UI: optional permanent plan, only IoT plans for new selections, explicit suspend/reactivate/revoke/renew controls, confirmation and stable request keys, retained deleted history, version-conflict reload and read-only renewal history. Scope caches/selections by principal and tenant. Tests: normalization, cross-tenant denial, retention, inactive duplicates/active collision, no access side effects, time preservation, expired restart, suspended/revoked behavior, request replay/stale versions, snapshot/history retention, populated migration and React workflow regressions.


## Implemented behavior and contracts

The source comparison is against `yarotech-radius-system-current`, not the older sibling folder. This is the registration/operator-grant stage for the Django/DRF backend and React client, intended for tenant managers on the eventual Ubuntu/Nginx deployment. The physical router and the legacy PostgreSQL database were not contacted. Public paid IoT orders, authorization SQL, accounting enforcement, CoA, migration import tooling and target deployment are outside this stage.

- Existing integer device IDs, router/tenant relations, deadlines, VLANs and descriptions remain. `legacy_uuid` is a nullable, protected provenance slot for the later UUID mapping/import; no source device is imported or guessed by this migration.
- Registration now retains active/suspended/expired/revoked/deleted states. `status` in API responses projects elapsed timed deadlines as expired. Existing inactive rows map to suspended, without guessing a reason. `is_active` remains a stored registration flag; it is not a connectivity indicator and the existing boolean filter is not an effective-expiry filter.
- DELETE retains the record and its history, hides it from the default list, and releases its active MAC reservation. Add `include_deleted=true` to the list to view removed records. Detail and manager renewal-history reads remain available; deleted registrations cannot be edited, renewed or reactivated.
- Plans may be null, including manually dated registrations. New grants require an active tenant-owned router and, when a plan is selected, an active/unarchived `iot_mac` plan with a compatible router restriction. Editing metadata alone preserves legacy plan assignments even if they are no longer offered. New timed registrations need a future explicit deadline; renewal duration is always taken from the selected plan.
- Unicast MAC addresses are normalized on writes. Zero/broadcast/multicast values are rejected. The database allows retained inactive duplicates but enforces one active registration per canonical MAC globally. This is registration uniqueness, not proof that existing voucher/RADIUS usernames are compatible; the later authorization integration must reconcile all SQL identity owners before enabling MAC authentication.
- New registration/plan-change/renewal snapshots preserve configured plan name, duration in whole seconds, rate, data cap and configured price. The price is informational, not money received. No mutable-plan backfill is applied to historical records with unknown limits. Direct operator expiry editing remains supported and audited; only the explicit renewal command creates a renewal ledger entry.
- PUT/PATCH require `expected_version`; stale or missing update versions return 409. DELETE requires `?expected_version=N` (missing/invalid is 400, stale is 409). Successful changes increment the device version.
- POST `/api/v1/iot-devices/{id}/lifecycle/` accepts `{action, expected_version}` where action is suspend/reactivate/revoke/delete. Reactivation validates a future timed deadline and current plan/router eligibility. A revoked device cannot be changed to suspended to bypass explicit reactivation.
- POST `/api/v1/iot-devices/{id}/renew/` accepts `{plan, expected_version}` and requires `Idempotency-Key`. It retains unused time using `max(now, expires_at) + duration_seconds`, restarts elapsed rights from now and preserves suspension. Revoked/deleted/permanent registrations cannot renew. Plan snapshots, deadline, version, ledger and audit are transactional; no payment, voucher or SQL authorization rows are written.
- GET `/api/v1/iot-devices/{id}/renewals/` returns bounded, newest-first history with old/new deadlines, immutable grant terms and timestamps. It is manager/owner-only; ordinary tenant members retain registration reads. Cross-tenant object reads/writes are denied. Django admin is read-only for devices to prevent bypassing the versioned lifecycle APIs.
- Device, plan-option, router-option and renewal-history caches include actor and tenant; workspace changes reset open selections/forms. Renewal retries retain the original key, payload and version. Status controls show a confirmation action; removal explains retained history. The UI states explicitly that network enforcement is not connected to these controls. API `network_enforcement=not_connected` describes that integration boundary, not observed router connectivity.
- Accounting checks all retained registrations for the requested canonical MAC/NAS pairs, including records outside the current page. Ambiguous history returns unavailable/null, never an arbitrary registration's totals. The new `(tenant, mac_address_compact)` index supports this lookup; the existing tenant-owned NAS guard remains.

## Migration and operator activation (not executed)

Prepared: `apps/iot_devices/migrations/0003_devicerenewal_alter_macdevice_options_and_more.py`. It adds state/version/provenance/snapshot fields, the renewal ledger, active-MAC uniqueness and the tenant/MAC lookup index, while allowing optional plans. Its transactional preflight/backfill retains original MAC strings and rights, populates compact identity/state, and aborts on invalid historical MACs or active canonical collisions. Errors identify record IDs, not credentials. Reconcile collisions explicitly; do not silently deactivate existing devices to make migration pass.

Do not run this migration against the legacy portal database just because table names look similar. First restore a backup of the intended new database into isolated PostgreSQL, inspect the full pending plan and rehearse the populated migration. The commands, in that backend's service environment, are:

```bash
python manage.py showmigrations iot_devices
python manage.py migrate --plan
python manage.py sqlmigrate iot_devices 0003
python manage.py migrate
python manage.py check --deploy
```

These commands are for the operator's reviewed rehearsal/activation; none were applied to an existing database here. `sqlmigrate` does not execute the Python preflight. Migration 0003 depends on earlier router, tenant and voucher compatibility migrations, so inspect all dependencies and locks. Table rewrites/index builds/backfill size need target measurement.

Quiesce IoT writers and deploy the matching backend/frontend together after the schema step. Old API writers do not populate canonical identity/state/version and must not overlap with new writers. Retain prior deployed artifacts and a restorable backup. Smoke test one fresh timed device, one suspended renewal, an expired renewal, repeated request keys, stale edits, active collision, removed history and tenant denial. Use only a test tenant and keep network authorization disabled until its separate integration has passed.

Rollback: freeze IoT writes, retain the expanded schema/history, and use a compatible backend/frontend rollback artifact. Do not simply re-enable old IoT writers or reverse 0003 after new data exists: optional plans/inactive duplicate MACs may violate the old schema, and reversal would discard renewal/state/provenance evidence. If database restore is required, reconcile all writes since the backup before restoring. PostgreSQL migration timing, simultaneous renewals/active claims and restore rehearsal remain outstanding.

## Review and validation evidence

Working-tree self-review covered serializers, locks, active uniqueness, retained admin/API deletion, canonical accounting attribution, frontend request retries and cross-workspace caches. Fixed findings included a revoked-to-suspended reactivation bypass, stale plan/router reads for grants, arbitrary accounting ownership across pages and UI removal text claiming network disconnection. No deployment or physical-router success is claimed.

Local results on 2026-09-15: the 40-test backend run passed for IoT, voucher code identity reservation, subscription access, customer device accounting and populated customer/IoT migration preservation. Focused rechecks passed for the final grant-validation changes, fractional expired renewals, anonymous denial and archived/restricted plans: 43 distinct backend tests passed across these runs. Nine device UI tests passed, including network retry request identity and removed-history controls. Full ESLint and the TypeScript/Vite production build passed. Existing non-blocking Zod annotation and subscription-page import warnings remain. Existing live integration tests were adjusted for the new versioned/retained contract but were not run against a live backend.

| Gate | Status | Evidence / remaining work |
|---|---|---|
| Correctness | PASS | Local renewal, suspension, retained deletion and snapshot tests; source/registry scope only. |
| Validation | PASS | Canonical unicast MAC, version, tenant plan/router, deadline, plan eligibility and protected fields tested. |
| Authentication | PASS | Existing authenticated API protection; focused anonymous denial test. |
| Authorization | PASS | Tenant-scoped objects, manager-only writes/history, staff denial and read-only admin. |
| Transactions | PASS | Local ledger failure rolls back deadline/version; lifecycle and audit share atomic boundaries. |
| Concurrency | NOT VERIFIED | PostgreSQL multi-connection device/plan/router locks and simultaneous MAC claims need target rehearsal. |
| Idempotency | PASS | Durable command replay and changed-payload conflict; UI retries preserve key/payload/version. |
| Database constraints | PASS | Active canonical uniqueness and protected ledger FK tested on SQLite. Tenant relation consistency additionally enforced in services. |
| Indexes | NOT VERIFIED | Tenant/MAC index and FK indexes prepared; target query plans not measured. |
| Migration safety | NOT VERIFIED | Populated SQLite preservation/preflight rollback pass; PostgreSQL DDL/lock/backup rehearsal pending. |
| Error handling | PASS | Stale/conflicting writes and invalid grants fail without success or partial history; UI error/retry states tested. |
| Logging | NOT VERIFIED | Audits record versions/grant source without new raw credential logging; deployed logging/retention not inspected. |
| Metrics | NOT VERIFIED | Existing command/audit infrastructure reused; target dashboards/alerts not exercised. |
| Tests | PASS | Disposable database and mocked HTTP checks; no real network/provider proof. |
| Performance | NOT VERIFIED | Bounded histories and indexed identity lookup; target sizes and latency unmeasured. |
| Accessibility | NOT VERIFIED | Labeled forms, confirmation controls and DOM interaction tests; full keyboard/screen-reader/mobile review pending. |
| Backwards compatibility | NOT VERIFIED | Local existing-record preservation verified; source UUID/data transfer not implemented. Matching client/server cutover required for versioned writes and retained DELETE. |
| Documentation | PASS | Accepted renewal rule, source mapping, registry boundary, migration plan and rollback recorded. |
| Deployment safety | NOT VERIFIED | No migration of existing DB, restart, deployment or physical router operation performed. |
| Rollback strategy | NOT VERIFIED | Retain expanded schema and disable incompatible writers; target restore rehearsal pending. |

**Production verdict: NOT READY.** This registry/operator-renewal stage does not implement network enforcement or paid public IoT fulfilment. Those integrations and target PostgreSQL/physical-router evidence remain required before replacing the old operational system.
