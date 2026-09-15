# Legacy replacement compatibility review

## Current status after source recovery

The current tracked VPS source has now been recovered into
`../yarotech-radius-system-current`, published privately as
`Saeed-uthman/yarotech_portal` at `0d4ca61` (source export of VPS `ea2cd24`). It includes
migrations through 0055. Use this folder for behavioral comparisons from now on.
The older SQLite snapshot below remains historical inventory evidence only.

[Module 1: users, tenants and permissions](01-users-tenants-permissions.md) contains
the first current-source comparison, six compatibility/security findings, the
ordered implementation work, 34 passing focused backend tests, 22 passing frontend
tests and a disposable API probe. The accepted runtime identity fixes are now implemented; see
[implementation and staging runbook](IMPLEMENTATION.md). Data-transfer validation
remains outstanding. Current tracked source availability is resolved; production data
freshness, PostgreSQL rehearsal and migration safety are not yet verified.

## Objective and boundary

[Module 2: plans and subscriptions](02-plans-subscriptions.md) maps customer-plan
fields, sales channels, issued access, business-plan quotas, trials, renewals,
complimentary grants and the data-transfer contract. This is a source-backed map;
module-2 application changes and production-data rehearsal have not been performed.

Replace the Django-template portal after the new Django/DRF and React system has
passed verification. Preserve existing business behavior, improve reliability,
security, scalability and efficiency, and retain the intentionally added features.
Review and implement one module at a time. Shared live database operation is not
the target. An empty-database deployment is not a successful legacy replacement.

No application models, API contracts, frontend behavior, migrations or existing
database records were changed by this initial comparison. This directory contains
inspection tooling and findings, not an importer or a deployment approval.

## Evidence and freshness

- Imported reference: `../yarotech-radius-system`, no Git metadata, source and
  SQLite snapshot through `vouchers/0043_whatsapp_voucher_reminders`.
- New local backend: revision `7464430` at inspection, clean before this work.
- VPS backend revision previously supplied by the user: `8dc5d2e`. It is not the
  same as the current local backend; the final tested revision must be deployed.
- Existing VPS: PostgreSQL database `hotspot`, port 5433. User-supplied migration
  output reaches `vouchers/0055_archive_internet_plans`, and includes old
  `radius_integration` history and `whatsapp_routing` models missing from the copy.
- `imported-snapshot-inventory.json` records local table/column/index/foreign-key
  metadata, counts, migration names and a SHA-256 digest. No row contents,
  credential defaults or connection passwords are included.
- The imported database was opened with SQLite `mode=ro`, `query_only=ON`, and a
  transaction. Its file hash was unchanged after the inspection.

| Imported snapshot records | Count |
| --- | ---: |
| Users | 3 |
| Tenants | 1 |
| Tenant memberships | 2 |
| Subscription plans | 3 |
| Tenant subscriptions | 1 |
| Subscription payments | 2 |
| Internet plans / vouchers / routers / customers / agents | 0 each |
| Application tables including Django tables | 53 |
| RADIUS SQL tables | 0 |

Local aggregate checks found no blank or case-insensitively duplicated user
emails, no inactive memberships, one user without a membership, and one tenant
subscription missing at least one of plan/start/end. These are local findings;
they say nothing about current production records. A user without a membership
must not automatically be made a platform administrator.

## Module comparison and acceptance requirements

| Module | Verified differences | Required compatibility work |
| --- | --- | --- |
| Accounts and access | Old `auth_user` versus new `accounts_user`; new case-insensitive unique email constraint. Old platform access uses explicit `vouchers.access_platform_management` permission; new system uses a platform-admin flag and service assignments. | Map permission semantics explicitly, preserve compatible password hashes, reject ambiguous identities, retain inactive accounts and negative permission cases. Never derive platform privilege merely from staff/superuser flags or absent membership. Do not copy numeric permission/content-type IDs between schemas. |
| Tenants and memberships | Old `vouchers_tenant` and `vouchers_tenantuser` versus new `tenants_tenant` and `tenants_membership`. Old membership has `is_active`; new membership does not. Old tenant has `business_name`; new tenant does not. | Preserve display/business identity and suspended-membership behavior; test cross-tenant reads/writes and conflicting agent/member identities before transferring records. |
| Internet plans | Same table name, different contracts: decimal NGN versus integer kobo, decimal hours versus whole hours, nullable `data_limit_mb` versus zero-unlimited `data_limit`, rate-limit length 50 versus 20. Old source also distinguishes voucher/IoT plans and public router restrictions. | Exact Decimal money conversion; preserve fractional durations without rounding entitlement away; preserve rate limits, visibility, service type and router restrictions. Reconcile archive/code-format behavior against the newer VPS source. |
| Vouchers | Same table name. Old credentials allow 64 characters, new 50. Old statuses include `sold` and `used`, new choices do not. Old usage/customer/audit fields differ. New code has purchased service-term snapshots. VPS has later device-binding, deletion and issued-duration fields missing from the imported copy. | Preserve credentials and expiry/usage/device limits exactly. Add appropriate representation and enforcement for old states. Never turn sold/used/deleted vouchers into available vouchers or recalculate purchased expiry from a changed plan. Rehearse active and expired examples. |
| Customers | Old nullable contact fields and MAC address versus new required name/reference and separate device-access history. | Preserve contacts and links; define stable references without fabricating contact identities. Preserve anonymous customer semantics where used. |
| Routers | Old integer primary key versus new UUID; different onboarding state sets and credential formats. Old secret store has `enc:v1:` and its own key setting. | Stable ID mapping, preserved foreign keys and disabled/unverified states, controlled secret re-encryption using source and target keys locally. No provisioning, peer installation or router contact during import. |
| RADIUS | Tables absent from the SQLite copy. New unmanaged `Radacct.sessionid` and `Radpostauth.pass_reply` names differ from standard/legacy accounting representation; runtime SQL columns still require inspection. | Verify real PostgreSQL columns and FreeRADIUS queries before changing ORM mappings. Rehearse authentication, accounting, expiry, device binding and disconnects. `managed=False` does not guarantee application code cannot write a table. |
| Subscriptions | Old nullable plan/start/end and pending/complimentary/trial source states versus new required plan/dates and period/terms records. | Preserve entitlements, limits, trial use and payment history without inventing activation dates or granting a free trial. Local snapshot already contains an incomplete legacy subscription. |
| Payments | Different fields, state sets, settlement/verification evidence and voucher relationship cardinality. New voucher payment is one-to-one; old model permits multiple payments per voucher. | Reconcile exact amounts/references/relationships, pending and fulfilled states, snapshots and duplicate protection. Import must not charge, verify externally, send delivery messages or replay callbacks. Preserve financial evidence. |
| Agents | Old credit and wallet ledgers include different balances, allocation grouping, reversals, costs and audit fields. | Reconcile balances against ledgers and preserve debt signs, allocations and reversals. A balance-only import is not sufficient. |
| WhatsApp | Legacy configuration/messages/orders/reminders and newer VPS routing differ from the new app. | Preserve tenant routing, delivery evidence and outstanding work. Disable replay and unsolicited messaging in migration rehearsal. Use current VPS source to establish scope. |
| Added features | New backend includes bandwidth profiles, PPPoE, service snapshots and device history not represented by the imported schema. | Retain features, define defaults and mappings explicitly, and test legacy behavior alongside new behavior. Do not silently reinterpret an old hotspot plan as a new service type. |

Source references: legacy `vouchers/models.py`, `vouchers/access.py`,
`vouchers/services.py`, `vouchers/paystack_crypto.py`, `routers/secret_store.py`;
new `apps/accounts/models.py`, `apps/core/api.py`, `apps/tenants/models.py`,
`apps/vouchers/models.py`, `apps/customers/models.py`, `apps/routers/models.py`,
`apps/agents/models.py`, `apps/subscriptions/models.py`.

## Working implementation sequence

1. **Source recovered; database rehearsal pending.** The current tracked VPS source
   is now available as described above. Obtain a current schema inventory;
   rehearse against a separately restored PostgreSQL backup when transferring data.
2. Review accounts/tenants/permissions end to end. Capture expected old behavior
   and new feature additions, then implement the schema/service/API changes and
   transfer mapping with denial and cross-tenant regression tests.
3. Review plans, vouchers, customers, routers/RADIUS, subscriptions/payments,
   agents and WhatsApp in dependency order. For each module, list field/state
   mappings, unsupported records, source-of-truth rules and acceptance tests.
4. Build a versioned importer targeting a separate database, source read-only,
   with preflight validation, stable ID mapping, explicit transaction boundaries,
   restart/retry safety, reconciliation counts/totals, and no external effects.
5. Rehearse on PostgreSQL with representative data. Verify credentials and
   permissions, paid/expired entitlements, financial reconciliation, RADIUS and
   new feature behavior. Keep source backup and previous application recoverable.
6. Plan the final write freeze/delta transfer and switch the application,
   FreeRADIUS SQL connection, workers and callbacks together with defined ownership.
   Observe real health and workflows before retiring the old system.

## Run the read-only inventory

From this backend directory in PowerShell:

```powershell
.\venv\Scripts\python.exe compatibility\inspect_database.py --sqlite ..\yarotech-radius-system\db.sqlite3
.\venv\Scripts\python.exe -m unittest discover -s compatibility -p 'test_*.py' -v
```

For the VPS, first copy **only** `inspect_database.py` to
`/tmp/yarotech-inspect-database.py`. Then use the old project's correctly configured
Django shell (the same environment previously used to inspect `hotspot`):

```bash
cd /home/yarotech/yarotech-radius-portal
./venv/bin/python manage.py shell -c "import runpy; runpy.run_path('/tmp/yarotech-inspect-database.py')['print_django_inventory']()"
```

The PostgreSQL collector enforces a read-only repeatable-read transaction, a
15-second per-statement timeout and a 2-second lock timeout. It prints schema and
counts, not data records or passwords. It performs count scans, so run it outside
peak traffic. A timeout is an incomplete inventory, not a compatibility pass.
The PostgreSQL path has not been executed on the VPS in this work.

## Validation and current verdict

- PASS: three local tests cover source-file preservation, record/default secrecy,
  foreign keys/unique metadata, unusual identifiers and missing-file handling.
- PASS: the actual imported snapshot was inventoried without changing its hash.
- NOT VERIFIED: PostgreSQL collector execution, actual production row contents,
  import/migration rehearsal, API/React behavioral parity and live router flows.
- NOT READY for data transfer or deployment: current source is recovered, but
  module 1 has unresolved behavior gaps and there is no current PostgreSQL data
  rehearsal. No compatibility importer or runtime compatibility patch is claimed.

Module 2 implementation and deployment preparation: [02-implementation.md](02-implementation.md).

Operator entitlement policy and local validation: [03-operator-entitlements.md](03-operator-entitlements.md).

Expiry action matrix, historical receipt/grant mapping and read-only audit: [04-expiry-history-map.md](04-expiry-history-map.md).
