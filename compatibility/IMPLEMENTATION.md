# Module 1 implementation and staging runbook

Date: 2026-09-14. Scope: uncommitted identity changes on backend base `7464430`
and the matching React working tree. Unrelated frontend edits are preserved.
The recovered `yarotech-radius-system-current` source is unchanged.

## Implemented

- Username-or-email login without rewriting passwords; ambiguous matches rejected.
- Tenant business display name (150 characters), slug (120), phone (30); user phone
  (30). Existing storefront slugs cannot be changed through tenant updates.
- Suspend/reactivate memberships without deleting relationships. The final active
  owner cannot be removed, suspended or demoted through membership endpoints.
  Tenant locks serialize mutations and the acting owner is rechecked under lock.
- Combined platform administrator/tenant owner with **My workspace / Platform**.
  React clears cached queries on switching and remembers the choice per account
  for the browser tab. The server enforces the selected role. Forged context or
  tenant headers grant no rights. HTTP retries preserve their original context.
  Conflicting tenant/agent identities fail closed.
- Atomic tenant, owner and trial creation. The owner has no usable password until
  completing an emailed setup link. Delivery follows commit; failure retains a
  visible pending account and retry action. Ordinary registration OTP verification
  cannot bypass pending owner setup.
- Email replacement requires the current password and proof sent to the new email.
  The old address and verification state stay intact until confirmation. HMAC-only
  codes expire in ten minutes, allow five wrong attempts, cannot be replayed or
  used by another account, and have a one-minute resend cooldown. Delivery failure
  expires the undelivered code. Failed attempts survive transaction completion.
- Tenant creation/membership audit events without credentials; pending setup status
  is queried with the tenant list, avoiding one extra query per tenant.

This prepares schemas/workflows for compatibility. It does not import legacy data,
prove old password-hasher support, resolve real identity collisions, or establish
complete legacy permission parity. Signup proof and delegated staff grants remain.
Session lifetime and remember-me policy are unchanged.

## API changes

Paths are relative to `/api/v1/`.

| Endpoint | Contract |
| --- | --- |
| `POST auth/login/` | `username` accepts username or email. |
| `GET auth/user/` | Adds `is_platform_admin`, `workspace_role`, `membership_active`. |
| `PATCH auth/user/` | Direct email replacement returns 400; use proof flow. |
| `POST auth/email-change/` | `{email, password}`; 200 accepted delivery, 503 delivery failure. |
| `POST auth/email-change/confirm/` | `{code}`; 200 updated, 400 invalid/expired/unavailable proof. |
| `POST tenants/` | Requires `owner_email`, `owner_username`; 201 includes `owner_delivery_status` (`sent`/`failed`). |
| `GET tenants/`, `GET tenants/:id/` | Adds `business_name`, `owner_setup_pending`. |
| `POST tenants/:id/resend-owner-setup/` | Platform only; 200 sent, 503 failed, 400 no pending owner. |
| `PATCH tenant-memberships/:id/` | Accepts `is_active`; authoritative final-active-owner protection. |

Authenticated clients send `X-Access-Context: platform` or `workspace`. Omission
means platform for admins; ordinary members keep their existing access. An admin
needs workspace context and active membership for tenant services. This header is
a role selection, not authentication. CORS permits it.

Coordinate backend/frontend rollout: old tenant-create clients need owner fields;
old direct-email-edit clients need proof flow. Duplicate tenant-create submissions
return uniqueness errors, not idempotency-response replays. Refresh the list after
uncertain creation, then retry setup for the existing tenant.

## Migrations prepared, not applied to existing databases

- `accounts/0006_identity_compatibility`: pending-owner flag, wider phone,
  one pending email-change record per user.
- `tenants/0002_identity_compatibility`: business name, wider slug/phone,
  active membership flag.

Flags have database defaults for preceding-code inserts. No deletions, password
rewrites or legacy-table changes. Defaults do not import legacy suspension states;
the later importer must map them. PostgreSQL size/locking/history is unverified.

Use a separate new-system staging database. Do not point this backend at legacy
`hotspot` or fake its migration history.

1. Configure staging and confirm effective database name, host and port before
   writes. Take and test a backup of that target.
2. Set `PASSWORD_RESET_FRONTEND_URL` to the staging frontend reset route, retaining
   `{uid}` and `{token}` placeholders. Configure sender/provider and a mail sink
   for rehearsal. Verify shared cache throttling and production Django settings.
3. From the new backend environment, manually review then apply:

   ```bash
   python manage.py migrate --plan
   python manage.py migrate
   python manage.py check --deploy
   ```

4. Start the matching backend and frontend behind Nginx; verify API routing, HTTPS,
   readiness, login and both context directions.
5. Rehearse the later importer on disposable PostgreSQL data. Compare identities,
   links, slugs, suspension and effective permissions. Test known old passwords
   with configured hashers. Resolve username/email collisions explicitly. Do not
   transfer old sessions, JWTs or OTPs.
6. Test competing owner mutations and email confirmations on PostgreSQL, approved
   test-mailbox delivery, setup expiry/replay and post-suspension denial.

No commands above were run against an existing database. Tests migrated only
disposable in-memory databases. No live server, router, payment or recipient changed.

## Recovery

Keep the old portal authoritative until rehearsal and required modules pass.
Record backend/frontend artifacts and configuration. Before new writes, traffic
can revert to the old portal; after writes, freeze and reconcile the delta before
switching back. A preceding backend does not enforce the new suspension/context/
email rules: do not restore it with affected identity endpoints publicly writable.
Prefer a forward fix or tested artifact/configuration/database restore in maintenance.
Do not reverse length expansions after importing longer values without checking
truncation. Previously sent emails cannot be recalled.

## Validation

- 113 focused backend tests passed in SQLite: accounts, email proof, registration,
  tenant isolation, core contracts and API workflows. Identity/tenant tests rerun
  after the final query/login fixes: 27 tests passed.
- Migration-state check found no missing migrations; Django system checks passed.
  Existing agent/device OpenAPI warnings remain.
- 81 distinct frontend tests passed across the final runs: the combined run passed
  80/81, with one incorrect refresh URL in the new HTTP test fixture; after fixing
  that fixture, all 13 HTTP tests passed. The other 68 tests were already passing.
  TypeScript, production build and scoped ESLint passed. Dependency annotation
  warnings were nonfatal. The stale settings navigation assertion was aligned with
  the existing layout; no settings navigation behavior changed for that correction.
- Broad discovery reached six explicitly PostgreSQL-only tests and a registration
  concurrency test that hit SQLite locking. Those are not passing concurrency
  evidence and must run on PostgreSQL in staging.
- Final code review covered permissions, transaction boundaries, proof replay,
  setup bypass, context retries, migrations and matching React contracts.

Production verdict: **NOT READY** pending the evidence below. Local PASS entries
do not establish complete legacy replacement readiness.

| Gate | Status | Evidence / remaining action |
| --- | --- | --- |
| Correctness | PASS | Local identity, failures and workflow tests. |
| Validation | PASS | Server serializers, proof, length and final-owner checks. |
| Authentication | NOT VERIFIED | Local proof/login pass; imported accounts/hashers need rehearsal. |
| Authorization | PASS | Local cross-tenant, suspension and context-denial tests. |
| Transactions | PASS | Atomic creation and rollback tests; delivery after commit. |
| Concurrency | NOT VERIFIED | Locks implemented; PostgreSQL competing-writer proof missing. |
| Idempotency | PASS | Sequential proof replay and duplicate creation denied; retry does not create accounts. |
| Database constraints | PASS | Unique identities/slug, one pending record per user; disposable migrations pass. |
| Indexes | NOT VERIFIED | Per-row setup query removed; production query plans not tested. |
| Migration safety | NOT VERIFIED | Expansion/state check passes; live data, locks and restore untested. |
| Error handling | PASS | Invalid proof, duplicate email, delivery failure/retry tests. |
| Logging | NOT VERIFIED | Audit/redacted warnings exist; operational retention/correlation unverified. |
| Metrics | NOT VERIFIED | Establish pending setup, delivery failures, auth/API error monitoring. |
| Tests | NOT VERIFIED | Local tests pass; PostgreSQL/provider/real-browser evidence missing. |
| Performance | NOT VERIFIED | Build passes; real workload/database latency unmeasured. |
| Accessibility | NOT VERIFIED | Labelled controls/semantic tests; keyboard/screen-reader/zoom checks remain. |
| Backwards compatibility | NOT VERIFIED | Coordinated rollout documented; actual import/mixed-version rehearsal remains. |
| Documentation | PASS | Contracts, migration sequence, limitations and recovery here. |
| Deployment safety | NOT VERIFIED | Not deployed; Nginx/runtime/release verification remains. |
| Rollback strategy | NOT VERIFIED | Documented requirements; restoration/reconciliation not rehearsed. |
