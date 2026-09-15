# Module 1: users, tenants and permissions

## Implementation update - 2026-09-14

The accepted identity changes are now implemented in the new backend/frontend.
See [implementation and staging runbook](IMPLEMENTATION.md) for current validation,
API changes and prepared migrations. The findings below are the original review
evidence; their original test counts and statements about pending code describe
the pre-implementation state. Data transfer and live parity remain unverified.

## Original review verdict

The new module has useful foundations, but it is not yet a behavior-preserving
replacement for the existing portal. Resolve identity/access differences before
importing users or connecting the new backend to production data.

Scope: authentication, tenant identity, memberships, platform access, account
creation, profile changes and the associated React navigation. This is a review;
no runtime application code, model or migration was changed in this module pass.

Reference versions:

- Current portal: `../yarotech-radius-system-current`, `0d4ca61`, exported from
  VPS `ea2cd24`, with vouchers migrations through 0055. This is the reference now;
  the older `yarotech-radius-system/db.sqlite3` is not a current production backup.
- New backend: `7464430`; frontend: current working tree, with pre-existing local
  modifications left intact.
- No current production database was queried. Source absence/presence is verified;
  the number of real accounts affected is unknown.

## Findings in priority order

### M1-01 — High: inactive memberships cannot be preserved

**Fact:** Legacy `vouchers/models.py:311` defines `TenantUser.is_active` and
`vouchers/access.py:43` resolves tenant membership with active-state and
member/agent conflict checks. New `apps/tenants/models.py:24` has no membership
active flag; `apps/core/api.py:37` checks tenant activity only.

**Consequence:** A direct mapping of an inactive legacy membership to a new
membership would restore tenant access. Deleting that membership instead loses
the relationship and its reactivation semantics. Conflicting member/agent
identities must also be rejected during import rather than resolved by precedence.

**Recommendation:** Add an active-state representation and enforce it consistently
in tenant resolution, permission classes, serializers and React access state.
Keep account activity, tenant activity, membership activity and agent status as
distinct controls. Test suspended member denial, reactivation and conflicting
tenant identities. Preserve the old agent fallback only when its tenant matches.

### M1-02 — High: combined platform-admin/tenant-owner accounts lose a workflow

**Fact:** Legacy `vouchers/access.py:12` requires an explicit platform-management
permission, directly or through a group. Its tenant resolution still permits an
account to own a tenant. The current legacy isolation tests deliberately exercise
such an account in both scoped operational pages and separately authorized platform
pages (`vouchers/tests_operational_tenant_isolation.py:17`).

New `apps/tenants/serializers.py:24` rejects platform administrators as members.
`apps/accounts/models.py:30` gives platform role precedence. React
`src/services/auth/principal.ts:24` derives one principal, and
`src/app/auth/guards.tsx:28` redirects users away from a different surface.

**Local reproduction:** Adding a platform-admin membership through its serializer
is rejected, even though this combination is supported in the existing system.

**Recommendation:** Preserve both capabilities with an explicit workspace/platform
context switch and backend-scoped authorization. Do not grant arbitrary tenant
access because someone is a platform administrator. Translate platform permissions
by semantic codename/app label, never permission IDs or `is_staff` alone. Keep
wallet/credit/complimentary grants separate for the later financial-module review.

### M1-03 — High: email changes retain verification of the old address

**Fact:** `apps/accounts/serializers.py:11` makes email editable through
`apps/accounts/views.py:172`. There is no pending-email or verification transition
in that update path. The new login gates normal users on `email_verified_at`.

**Local reproduction:** PATCH `/api/v1/auth/user/` changes a synthetic user's email
with HTTP 200 while retaining the original non-null verification timestamp.

**Consequence:** The address has changed but its ownership has not been verified.
This weakens the new system's verification guarantee; it is not a legacy behavior
we should preserve.

**Recommendation:** Require fresh proof for email changes, preferably retaining
the old verified address until the replacement is confirmed. Validate normalized
email uniqueness with database-race handling and keep tokens/personal data out of
logs. Test wrong/expired/replayed codes and address conflicts.

### M1-04 — Medium: email sign-in and session choices changed

**Fact:** Legacy `vouchers/forms.py:157` accepts username or case-insensitive email;
`vouchers/views.py:1228` also supports storefront-scoped sign-in and a remember-me
choice. New `apps/accounts/views.py:34` passes the supplied username directly to
Django authentication. React `src/features/auth/pages/LoginPage.tsx` asks only for
username. The current token store persists refresh tokens in localStorage, without
the old remember-me choice.

**Local reproduction:** For a user whose email differs from their username,
username/password returns 200 and email/password returns 401.

**Recommendation:** Restore explicit username-or-email resolution with defined
collision behavior, generic failures and throttling. Preserve or explicitly redesign
remember-me and storefront routing instead of silently changing them. Old tenant
sign-up used email as username, so those accounts may still sign in; this does not
cover all legacy users.

### M1-05 — Medium: platform-created tenants have no owner setup

**Fact:** Legacy `vouchers/views.py:2458` creates the tenant, an owner account and
membership in a transaction, with a password-setup option. New
`apps/tenants/views.py:21` creates a tenant and trial only. The React platform member
panel attaches existing user IDs; this is a different operating workflow.

**Local reproduction:** POST `/api/v1/tenants/` returns 201; the resulting tenant
has zero owner memberships.

**Recommendation:** Provide an atomic tenant-and-owner setup workflow and reliable
invitation/recovery delivery. It should return a truthful pending-delivery state if
email fails. Keep the new final-owner protection for subsequent changes. Verify
the legacy password-setup mechanism itself before reusing it: its newly created
owner has an unusable password, while Django reset forms normally filter those out.
Do not assume that old email delivery worked merely because the option exists.

### M1-06 — Medium: tenant identity fields and import limits differ

**Fact:** Legacy `vouchers/models.py:15` stores distinct `name` and `business_name`,
slug length 120 and phone length 30. New `apps/tenants/models.py:5` stores one name,
slug length 50 by Django default and phone length 20. New user email has a
case-insensitive unique constraint; legacy `auth.User` does not require unique email.

**Recommendation:** Preserve business identity and existing storefront slugs, or
provide explicit aliases. Preflight lengths and duplicate/blank emails. Never
truncate a slug, fabricate an email, merge users or grant privileges automatically.
The older local database's three users do not prove production meets these limits.

## Useful new foundations to retain

- Django remains the authoritative access boundary; React capability checks are
  presentation controls, not a substitute for server-side tenant isolation.
- Owner/manager/staff roles, explicit staff service grants and tenant assignment
  checks are present. The new staff feature should remain additive.
- Membership identity changes are rejected; final-owner removal uses a transaction
  and tenant lock (`apps/tenants/views.py:69`). PostgreSQL concurrency remains untested.
- Public registration has an email-proof workflow with bounded attempts and
  transactional workspace creation (`apps/accounts/registration.py`). The older
  `/auth/register/` endpoint also remains; review both as supported entry points.
- JWT refresh rotation, blacklist-after-rotation and password-change revocation
  checks are configured. Logout checks refresh-token ownership.
- React clears cached queries on sign-out and tenant switches. Preserve that
  protection when introducing a context switch for combined-role accounts.

These are source-backed observations and focused-test results, not a claim of
comprehensive security or production readiness.

## Ownership and implementation boundaries

| Responsibility | Authority and affected areas |
| --- | --- |
| Account credentials, verification, session lifecycle | `apps/accounts` services/API; React auth consumes results |
| Tenant identity and active membership | `apps/tenants`; shared tenant resolver used by every operational module |
| Explicit platform and delegated service capabilities | Permission policies and staff assignments; never arbitrary request tenant IDs |
| Imported identity mappings | Dedicated import service/command, read-only source and separate destination |
| Trials/paid access and financial privileges | Separate subscription/financial review; importing an owner must not grant a new trial or financial authority |

Use one modular Django application for these boundaries. Nothing in this review
justifies splitting authentication/tenants into independently deployed services.
First centralize policy and remove inconsistent checks. Membership lists currently
serialize related user/tenant fields without explicit `select_related`; measure
query growth and add a regression query budget when implementing the fixes.

## Ordered changes and acceptance checks

1. Establish a permission/membership mapping for existing identities, including
   combined roles, inactive membership, agent fallback and explicit financial grants.
2. Add compatible tenant/membership fields and migrations; preserve data lengths,
   links and identifiers. Prepare migrations without applying them to `hotspot`.
3. Centralize tenant-context checks and expose capabilities needed by React. Update
   navigation, membership controls and cache isolation together.
4. Restore email login and the owner-setup workflow; fix email-change verification.
   Keep newly added signup proof and staff delegation.
5. Add behavior tests: cross-tenant denial, inactive identity denial, combined-role
   context separation, final-owner concurrent changes, duplicate email handling,
   verification replay, failed invitation delivery and account recovery.
6. Rehearse data mapping on a disposable PostgreSQL restore. Compare identity/link
   counts and effective capabilities; test existing password hashes using the actual
   configured hashers. Retire old sessions/reset links during cutover; don't import
   old JWT/session tables or revive pending OTPs.

## Verification performed

- 34 existing backend tests passed: `apps.accounts.tests`, `apps.tenants.tests`,
  `apps.core.tests`, with database overridden to disposable in-memory SQLite and
  local-memory cache. Existing schema-generation warnings remain for agent access
  code typing and the device-access viewset; they were not silently suppressed.
- 22 existing frontend tests passed: `src/services/auth/principal.test.ts` and
  `src/app/__tests__/authFlow.test.tsx`. The first sandbox run failed before loading
  Vite; the permitted run outside that restriction succeeded.
- `compatibility/probe_identity.py` reproduced the API/model observations above
  against a freshly migrated in-memory database. It prints status/count facts,
  never tokens, passwords or production records. Re-run from the backend with:

```powershell
.\venv\Scripts\python.exe compatibility\probe_identity.py
```

These passing tests verify existing implementation paths, not legacy parity.
No production database migration, live SMTP, browser E2E, PostgreSQL locking test,
data transfer, router action or deployment was performed. Application fixes remain
to be implemented. Start with M1-01/M1-02 before moving to plans and vouchers.
