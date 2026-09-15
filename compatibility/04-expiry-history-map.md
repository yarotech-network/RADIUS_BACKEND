# Expiry actions and historical subscription mapping

Date: 2026-09-14. Scope: source-backed mapping and a read-only target-database audit. No importer, expiry middleware, new grant endpoint, schema migration or live data change is implemented in this step. Repositories: recovered `yarotech-radius-system-current` and top-level `yarotech-radius-backend` / `yarotech-radius-frontend`. Previous compatibility work remains in place.

## Superseding user decision

The user subsequently required a full dashboard/API/new-sales lock after operator expiry, including public purchases and agent sales. See `05-subscription-gate.md` for the implemented policy. The proposal below records the earlier mapping and is superseded wherever it allowed operational reads or new sales after expiry. The user confirmed that existing vouchers continue until their normal expiry; new storefront plans stay hidden until operator renewal.

## Findings and decision status

**Fact:** legacy `vouchers/middleware.py:10` allows billing/recovery routes and skips unauthenticated requests; its agent branch allows generation and wallet workflows independently of operator subscription expiry. Therefore a blanket "expired tenant cannot use any API" restriction would break legacy public/agent behavior. Existing staff/superuser bypasses must not be copied as implicit tenant authority.

**Fact:** new `apps/subscriptions/entitlements.py:24` denies missing/expired subscriptions for router slots, print authorization and WhatsApp. The new expiry command calls `SubscriptionService.expire_due_subscriptions`, which updates subscription status only. It does not disable vouchers, erase RADIUS credentials or alter router configuration.

**Fact:** new `apps/payments/recovery.py:29` fulfills verified customer orders from saved terms independently of operator subscription state (tenant suspension is a separate gate). Preserve that boundary.

**High-priority mapping blockers:** missing pending/null subscription representation; missing grant provenance; source payment references up to 120 characters versus target 100; no source provider transaction identity/currency/paid timestamp columns in target payments; historical original allowances cannot be inferred from today's catalogue.

**Open decision:** whether expired operators continue receiving new public purchases and agent sales. Recommended compatibility option: preserve both. User has been asked; no change to these paths is authorized by silence. Already-paid orders and already-issued customer access remain protected either way.

## Expiry action matrix

These are proposed target rules unless explicitly marked as implemented. Normal tenant scope, permissions, account suspension and service-level expiry always still apply. "Allow" does not bypass those checks.

| Action | Valid operator subscription | Missing / expired / cancelled operator subscription | Current implementation / work needed |
| --- | --- | --- | --- |
| Login, logout, password recovery | Allow | Allow | Preserve authentication routes; no subscription middleware redirect. |
| View billing, pricing, pending payments; renew / verify | Allow authorized owner | Allow authorized owner | Existing subscription API, checkout and verify endpoints remain reachable. |
| View operational history and reconcile paid orders | Allow | Allow read/recovery | Keep tenant permission checks. This is more usable than legacy page-wide blocking and does not issue new unpaid access. |
| New public voucher purchase | Allow when plan public/sellable | OPEN: recommended allow | Legacy exempts public flow; new checkout currently has no operator-subscription gate. |
| Agent wallet funding, new voucher sale | Allow active authorized agent | OPEN: recommended allow | Legacy agent exemptions; new wallet/issuance retain agent/tenant/plan and balance checks. No automatic balance freeze. |
| Fulfill an already-verified paid customer order | Allow | Allow | Existing saved terms and idempotent recovery; do not require a second payment. |
| Existing customer login/session, access-code recovery | Allow until customer contract ends | Allow until customer contract ends | Operator expiry must not reset customer expiry, disable purchased codes or disconnect sessions. Real RADIUS verification still required. |
| Operator manually issues new unpaid vouchers | Allow within normal rules | Recommended block | New manual/generate API and shared service need an explicit action gate; not implemented by this map. Agent/customer exceptions must be selected from server-owned flow, not caller-supplied flags. |
| Create/activate a router | Allow within active-router allowance | Block | Implemented in module 3; includes reactivation. |
| Read router health, deactivate/suspend, rotate compromised secrets | Allow | Allow authorized safety/recovery actions | Existing API permissions; ensure a future expiry gate retains these paths. |
| Provision new router service or add/extend IoT/PPPoE access | Allow within product rules | Recommended block new access | Requires action-specific gates in router provisioning and customer/device services. Existing customer service remains independent. |
| Change catalogue, add staff/agents, expand service | Allow authorized manager/owner | Recommended block expansion; allow disabling/revoking | Needs action-specific checks; never prevent removing access or archiving a sale. |
| New operator print authorization / new WhatsApp token | Allow within saved allowance | Block | Implemented entitlement checks. |
| Download already-purchased credential document | Allow authorized holder | Recommended allow recovery without new issuance | Current operator print endpoint still calls entitlement checks. Separate credential recovery from new print quota; do not expose another tenant's credentials. Agent client rendering must be reviewed separately. |
| Platform reconciliation / complimentary grant | Explicit platform permission | Explicit platform permission | Never infer platform access from no tenant, Django staff flag or a missing subscription. New grant workflow does not yet exist. |

Implementation direction: retain the modular Django application and place authoritative action checks in shared services. DRF checks explain denials early; frontend hides/disables unavailable actions and links to billing, but cannot be the enforcement layer. Do not copy legacy path-name middleware into a token-authenticated API: callbacks, workers and shared service calls have different actors. Use a stable `subscription_required` code and structured action identifier in a future API contract, while retaining server-side authorization.

## Historical mapping by record

| Legacy source | New target / handling | Validation and blockers |
| --- | --- | --- |
| Tenant ID and subscription PK | Explicit source-to-target ledger; target one-to-one tenant subscription | Never assume equal numeric IDs mean the same tenant. Reject unresolved tenant links. |
| Business subscription plan ID | Mapped `SubscriptionPlan` plus immutable period terms | Historical allowances require evidence; current catalogue alone is insufficient. |
| `price_kobo` / `amount_kobo` | Target kobo values without multiplying by 100 | Source positive-big-integer payment amounts can exceed target positive-integer range. Block overflow; do not round or clamp. Confirm source plan column from schema inventory. |
| `status=active`, `activation_source=paid` | `status=active`, `is_trial=False`, preserved current start/end and period | Runtime expiry uses the original end; normalize elapsed records to expired while retaining raw source state in ledger. No provider call or complete_payment invocation. |
| `status=active`, `activation_source=trial`, null plan | Historical internal plan/saved allowance representation, `status=trial`, original trial dates | Must not call `assign_new_tenant_trial`: that would grant new time and new terms. Preserve original trial-used evidence even after conversion to paid. Current target lacks those provenance fields. |
| Complimentary active subscription | Active period with `payment=NULL` linked to preserved grant provenance | Never fabricate a successful payment to represent a free grant. Source/reference, reason, actor and grant window must remain distinguishable from paid and trial access. |
| Expired subscription | Expired record with original dates and history | Do not renew or activate during import. Null dates need review; target dates are required. |
| Cancelled subscription | Cancelled record and preserved historical periods | A future expiry date must not reactivate cancelled access. |
| Pending subscription, null plan/start/end | Non-entitled historical state with raw source record retained | Target has no pending status and requires plan/dates. Needs additive representation; do not coerce to active/trial, invent expiry, or create placeholder paid access. |
| Missing subscription | Explicit reconciliation exception | No automatic free trial, unlimited allowance or platform privilege. |
| `starts_at`, `expires_at` | `started_at`, `expires_at`; period window when proven | Preserve aware timestamps and instants; verify source timezone for naive values. Reject reversed windows, overlaps and unsupported gaps. |
| `trial_started_at`, `trial_ends_at` | Additive provenance / historical ledger | Retain independently of current paid state; new `is_trial` alone loses trial history. |
| `activation_source`, `activation_reference`, `amount_paid_kobo`, `auto_renew` | Preserve raw source facts in explicit historical metadata | Do not treat legacy auto_renew=True as authorization to create a new recurring provider charge. |
| Subscription payment `paystack_reference` | Exact immutable payment reference | Source max 120, target max 100: expand target or use approved external-reference representation before import; never truncate/hash the provider-facing reference. |
| Payment `successful` + validated processed evidence | Historical receipt status success, with correct period linkage when provable | Never call completion/webhook logic to reconstruct history: it extends subscriptions. A successful receipt does not prove the duration/sequence of every past period. |
| Payment initialized/failed/abandoned | Preserve source state and recovery eligibility | Target lacks abandoned/initialized distinctions. An abandoned attempt is not proof no settlement happened; keep external reference and provenance for later reconciliation. |
| `currency`, provider transaction ID, channel, `paid_at`, `processed_at` | Additive receipt provenance; `completed_at` corresponds to local processing | Keep provider paid time separate from processing time. Non-NGN requires explicit handling. Preserve source nonblank provider-ID uniqueness. |
| Raw verification metadata | Reviewed, minimal allowlisted provenance | Do not export bearer credentials, card details or full provider payloads into general logs/ledgers. Preserve approved evidence in controlled storage. |
| Complimentary grant tenant/plan/actor FKs | Three explicit ID mappings | Preserve historical actor identity without granting that actor new platform privileges. Unknown actor is an exception, not reassignment to the importing administrator. |
| Grant audit reference / reason / start / end | Append-only grant provenance plus its entitlement period | Preserve full 120-character reference and original reason; protect from duplicate application and deletion. New target grant model/API absent. |

The new payment-to-period relationship is one-to-one. Old receipts may not contain enough data to reconstruct all superseded upgrade periods; do not invent one period per receipt solely to satisfy the target relationship. Design an explicit historical-receipt representation for those records before import. Current catalogue-based backfills cannot establish original commercial rights.

## Proposed import ledger and write boundary (not implemented)

Ledger uniqueness: `(source_system, source_table, source_pk)`. Record source extraction/version, a canonical record digest, target type/ID, mapped tenant ID, disposition (`ready`, `quarantined`, `applied`, `verified`), reason codes and reconciliation timestamps. Keep exact external references in a dedicated controlled field; normal reports contain IDs/counts only. Do not store passwords, payment secrets or complete source rows in generic audit JSON.

- Extract from a consistent read-only source snapshot; inspect real PostgreSQL columns first. Recovered source files are not the current production database.
- Validate all IDs, state, dates, amounts, reference lengths, uniqueness and contracted terms before writes. Quarantine ambiguous records and their dependants.
- Future importer: tenant-scoped atomic batches under the same tenant lock used by subscription completion; unique ledger entry and target writes commit together. Check digest on replay; changed-source records require review rather than duplicate insertion.
- Never call payment verification, email delivery, trial assignment, complimentary activation service, router provisioning or RADIUS writes during historical import.
- Write snapshots and provenance before enabling a tenant. Verify counts AND balances/time windows/allowances/reference integrity, not merely successful inserts.
- Rehearse on a separate restored PostgreSQL database. Stop writers for final capture/cutover; reconcile the delta. After new sales, rollback requires financial reconciliation rather than deleting imported rows.

## Read-only target audit

Added `python manage.py audit_subscription_compatibility`. Run only after earlier target schema migrations exist, with the intended target configuration. It performs SELECTs only; it neither creates a subscription nor renews one, and has no provider/network calls.

It reports counts and at most 20 IDs per exception type: missing non-platform subscriptions, invalid windows, overlapping/gapped live periods, active subscriptions without current snapshots, uncovered expiry, incomplete period snapshots, cross-tenant payment links, unsnapshotted payments and successful payments without a period. Exit is nonzero when exceptions exist. A clean report is structural evidence only: it does not prove original prices, imported grant provenance, semantic correctness of snapshot values or production readiness. Legitimate historical receipts without provable periods require an explicit future representation, not fabricated periods to clear this audit.

Scale: streams subscriptions/payments/periods in batches of 500; uses per-subscription period queries and per-payment linkage checks. It is an offline/rehearsal diagnostic, not an API request or a production health probe. Counts can race with live writes; use a quiescent restored database or a read-only consistent snapshot for reconciliation. Production volume, query plans, RPO/RTO and lock-time targets remain unmeasured.

Validation: 5 disposable SQLite tests passed for clean state/platform exception, missing subscription, overlap, successful receipt without period, cross-tenant links, no raw customer/reference output and unchanged records. No existing database was queried or migrated; no live payment/router/provider calls occurred.

Next implementation sequence: settle public/agent expiry policy; implement the action-specific expiry gates and credential-recovery exception with API/frontend tests; prepare additive historical provenance/pending-state/grant schema; then build a dry-run-first importer and PostgreSQL replay/concurrency rehearsal. Mapping complete; runtime expiry enforcement and historical import are not complete.
