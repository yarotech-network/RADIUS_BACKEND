# Module 18: customer contacts and device history

Status: source comparison and local runtime implementation completed; existing-database activation and legacy transfer remain outstanding. Reference is exclusively `../yarotech-radius-system-current`; the older similarly named folder is not evidence for current behavior.

## Why this module follows WhatsApp

Purchases and voucher issuance now have a durable workflow, but customer identity cannot yet be transferred faithfully. The legacy portal stores explicit customer relationships; the new backend stores payment contact snapshots and separate contact/device directories. A successful replacement must preserve both relationships and anonymous records without treating a typed email or MAC address as proof of a person's identity.

## Source comparison before this implementation

| Area | Current legacy source | New source | Consequence |
|---|---|---|---|
| Customer fields | `vouchers/models.py:2010`: tenant; nullable name, phone, email, MAC; timestamps | `apps/customers/models.py:5`: tenant; required unique per-tenant reference/name; optional contact fields, address, notes, archive timestamp | Unnamed or MAC-only legacy customers cannot pass the current API/import unchanged. There is no target field for the legacy contact MAC. |
| Public checkout | `vouchers/services.py:1104`: explicitly treats supplied email as contact data, creates an independent customer for each new checkout attempt | `apps/vouchers/models.py:206`: PaymentTransaction stores customer_name/email/phone, without a customer FK | Contact snapshots survive, but customer ownership/history does not. A reference-preserving importer needs explicit relationships. |
| WhatsApp checkout | `vouchers/whatsapp_agent.py:680`: get_or_create by tenant and typed email | `apps/whatsapp_routing/conversations.py`: creates a payment/order with contact snapshot and verified sender routing, no Customer relationship | Legacy email reuse is not safe identity proof and can fail when multiple contacts share an email. Future grouping needs an explicit policy. |
| Voucher/payment ownership | `vouchers/models.py:2056,2651`: nullable customer FKs; fulfilment passes payment customer into voucher generation | `apps/payments/recovery.py`: creates voucher from payment terms, with no customer relationship to propagate | Preserve original nullable links in both models; never infer historical ownership from matching email, username or MAC. |
| Contact APIs and imports | Legacy customer may be entirely anonymous | `apps/customers/serializers.py`, `imports.py`: immutable normalized reference, name required; preview token binds CSV, actor and tenant; confirm validates again under lock | Keep the preview/confirm and replay protection. Add unnamed-contact support without fabricating a name. Ordinary CSV import is not a relational legacy importer. |
| Customer UI | Legacy live-user view labels the linked customer | `src/features/customers/CustomerForm.tsx`, `ContactRecordsPage.tsx`: required name/reference and direct name rendering | Anonymous contacts need a display fallback; empty names must not create blank list rows or dialog titles. |
| Device evidence | Legacy customer MAC is a contact field; router accounting is separate evidence | `DeviceAccessSession`, `device_access_sync.py`, `device_access_views.py`: MAC, voucher, router/NAS, times and counters; no Customer FK | Do not turn a contact MAC into a session, a purchase, a voucher binding or a PPPoE service. |
| New PPPoE feature | Not part of the legacy Customer model reviewed here | Customer one-to-one PPPoEService; archiving refuses an unsuspended service | Preserve service links, plan/rate snapshots, lifecycle rules and disconnect reconciliation. Legacy contacts must not receive PPPoE services automatically. |

## Customer transfer contract

- Map every source customer using `(source snapshot identifier, source tenant ID, source customer ID)` to an explicit target tenant/customer ID. Preserve duplicate emails/phones as distinct source records. Matching numeric primary keys alone is not a mapping.
- Give imported contacts a stable reserved reference derived from the source mapping, checked against existing and archived target references. Do not derive it from personal contact data. Collision is a preflight issue, not permission to overwrite or merge.
- Preserve missing names as missing/blank values. Display name fallback: name, phone, email, then customer reference. A fallback is presentation, not a fabricated stored name.
- Preserve original phone/email text and legacy MAC evidence with provenance; do not silently rewrite invalid historical values or use them as authentication. Target validation must distinguish retained historical evidence from newly entered contact data. Validity exceptions are reported by the importer for review.
- Preserve both timestamps. New imports do not imply a new purchase date, activation date or new customer consent.
- Add nullable, protected Customer relationships for payments and vouchers. Validate same-tenant ownership before application writes and before import. Existing target records start with null links; no email-based backfill.
- Preserve source null links as null. An orphan or cross-tenant source FK is quarantined in preflight; do not silently reassign it. Different customer links on a source payment and voucher must be reported, not rewritten.
- Contact archive/restore retains voucher/payment history. It does not disable Wi-Fi credentials or settle/reverse a payment. Keep the existing PPPoE suspension prerequisite.
- Import performs no provider verification, charges, messages, RADIUS writes, router provisioning, trial creation or service renewals.

## Future-purchase decision

Accepted user decision: every future WhatsApp purchase gets an independent contact, matching the legacy storefront. Request retries reuse the existing purchase and contact. No verified-sender grouping will be introduced.

Neither option merges contacts by typed email, by names, across tenants, or by a device MAC. Existing historical links remain exactly mapped either way. If verified-sender grouping is selected, it needs a separate tenant/sender identity mapping, uniqueness and concurrent-create tests; it must not update one contact merely because its email matches.

## Device-history compatibility boundaries

Retain the new device-history feature: distinct vouchers used are not session counts, repeated/interim accounting updates must not inflate counters, and absence of recent accounting is not proof that a device is offline. The current sync retains maximum counters/last-seen values and refuses reassignment of existing evidence. It also rejects ambiguous router address ownership and requires router and voucher tenant to match.

The current synchronizer scans accounting history and serializes under its sync record; incremental sync/index tuning needs separate measured work. It reads `Radacct.sessionid`, while the legacy/standard deployment may expose `acctsessionid`; this is an unresolved target-schema compatibility gate, not a reason to rename a production column based on local source. Inspect the real restored PostgreSQL schema and FreeRADIUS queries before deployment.

Device code-history endpoints return credential-equivalent access codes to authorized tenant users. Customer linking must not broaden those permissions or expose codes in public customer/checkout responses. Contact summaries and purchase history should show masked/non-credential identifiers; revealing credentials must continue through the established authorized workflow.

## Ordered implementation plan

1. Resolve future WhatsApp contact grouping. No other customer-transfer rule above depends on that choice.
2. Prepare additive customer compatibility fields, nullable customer links and explicit provenance/identity mapping. Preserve reference uniqueness and introduce no uniqueness on email/phone/MAC. Write populated-migration preservation tests, leaving existing databases untouched.
3. Implement one transactional contact-linking path used by storefront/WhatsApp reservation and voucher fulfilment. The chosen contact, payment and idempotency outcome must commit together. Replays retain the original links; no external calls inside these transactions. Preserve historical purchase contact snapshots when a directory entry changes.
4. Extend tenant-scoped API serializers and CSV preview/confirm for optional names and retained MAC evidence. Keep mass-assignment rejection, immutable references, archive rules and cross-tenant checks. Expose a bounded, read-only contact purchase history without secrets.
5. Update contact forms, fallback labels and purchase-history display. Include tenant and principal identity in contact query keys, and reset selected contact/form state on a workspace change. Existing device-history keys already include scope; the contact directory currently uses the broad `customers` key and needs explicit scoping review.
6. Implement a versioned read-only-source importer separately from ordinary customer CSV creation, preserving stable source mappings and source FK links. Preview counts, orphan/collision reports and reconciliation totals must precede any target writes.
7. Validate PostgreSQL constraints/locking and real RADIUS accounting on a restored database, then integrate into the whole-system cutover rehearsal.

## Acceptance tests and threats

| Risk | Required control and test |
|---|---|
| Email/name collision merges people | Two same-email customers remain distinct; no public request can select an existing contact by email or client-supplied ID. |
| Cross-tenant history exposure | Scope contact, voucher, payment and device queries; reject foreign contact IDs; include counts, pagination, filters and archived records in negative tests. |
| Duplicate purchase creates orphan contacts | Existing request replay returns the original payment/contact pair; failed reservation rolls back the new contact. PostgreSQL concurrent replay test required. |
| Anonymous legacy contact lost | Null/blank name/contact examples import with stable references and readable UI fallbacks, without fabricated identity. |
| MAC inferred as person or access grant | Retaining a legacy contact MAC writes no session, voucher binding, RADIUS row or service. A shared/randomized MAC never merges people. |
| Profile edit changes historical receipt | Customer edits leave purchase contact snapshots and payment/voucher ownership unchanged. |
| Cached data crosses workspace boundary | Switch workspace/principal while list/detail/edit request is in flight; old responses cannot populate the new workspace. |
| Archive destroys rights | Archive retains histories and voucher usability; active PPPoE service still requires suspension first. |
| Sensitive history leaks | No password, access code, encrypted secret, provider payload or email delivery body in contact-history summaries. |
| Import retry mutates history | Repeated source mapping has no duplicates; changed source evidence is reported, not silently overwritten; dry run has no target or external effects. |

## Local baseline and release status

Baseline tests are run against a disposable SQLite database with local cache and no external provider effects. This validates the existing customer/PPPoE/device behavior only; it does not validate the proposed compatibility changes or production accounting.

The baseline customer suite passed 23 tests before changes. The implementation below adds compatibility behavior and migrations, but no existing database, legacy record, provider or router was changed. Actual legacy transfer and PostgreSQL/RADIUS rehearsal remain separate prerequisites for replacement.


Implementation scope for this pass: optional names, retained contact MAC/source identity, protected nullable customer links, atomic per-purchase contacts for storefront and WhatsApp, safe paginated purchase history, scoped contact UI, migration and regression tests. The whole-system legacy importer and real PostgreSQL/RADIUS rehearsal remain a separate deployment stage; prepare representation and mapping without running an import.


## Implemented result

- `apps/customers/purchases.py` reserves an independent customer and payment in one transaction. Both storefront and WhatsApp use it. New references use a random `P-` identifier without personal data. A separate checkout attempt creates a separate contact even when name, email, phone and verified WhatsApp sender match. Existing idempotency keys/inbox receipts reuse the original payment and contact. Without a storefront idempotency key, a new POST remains a separate attempt under the existing API contract.
- Payment and voucher now have nullable protected customer links. Verified fulfilment checks tenant/link consistency and propagates the payment contact to its newly generated voucher inside the fulfilment transaction. Inconsistent existing links fail for reconciliation; they are not silently rewritten. Historical unlinked purchases remain unlinked.
- Customer names can be blank. The serializer and UI use name -> phone -> email -> reference for display, without writing the fallback as a name. Customer references remain required for manual/CSV creation, immutable and unique within a tenant including archived contacts.
- `mac_address` retains up to 32 characters as descriptive contact evidence. It is deliberately not parsed as verified device identity, not globally unique and not used for RADIUS authorization, routing or automatic contact merging. CSV keeps required reference/name headers, permits blank names and accepts an optional mac_address column.
- `legacy_source` and `legacy_id` provide a protected provenance pair for the later importer. The pair must be complete and unique within source/target tenant; ordinary API/CSV users cannot set it. Existing rows receive no guessed source identity. Source names/IDs and timestamps still require the versioned import stage.
- GET `/api/v1/customers/{id}/purchases/` is manager/owner-only and tenant-scoped. It uses standard bounded page pagination and exposes only payment ID, integer kobo amount, payment status, dates, purchased plan name and verified fulfilment boolean. No payment/provider reference, email, voucher username/password or raw provider response is returned. Staff retain ordinary read-only contact visibility without gaining financial history access.
- Contact UI caches include principal and tenant; a workspace change remounts local selections/forms. Purchase history has loading, empty, error/retry and pagination states. The delayed-old-response test proves previous customer detail does not appear in the newly selected workspace.
- Editing or archiving a contact preserves purchase contact snapshots, voucher credentials and RADIUS rows. Existing PPPoE archive rules and device-history accounting logic remain intact.

## Prepared migrations and activation

New migration files:

- `customers/0004_customer_legacy_id_customer_legacy_source_and_more.py`
- `vouchers/0008_paymenttransaction_customer_voucher_customer.py`

They are **not applied to any existing database**. The customer migration adds blank-default MAC/source fields, a nullable source ID, provenance constraints and optional-name validation. The voucher migration adds nullable FK columns/indexes. No migration backfills customer links or sends messages. Full table/constraint/index lock cost depends on the target PostgreSQL tables; local SQLite execution is not target DDL proof.

Before deployment, back up and restore the intended new database into an isolated PostgreSQL environment, inspect schema/volume and review the migration plan. Do not point migration commands at the legacy portal database by assumption. In the correct backend service environment, the operator's commands are:

```bash
python manage.py showmigrations customers vouchers
python manage.py migrate --plan
python manage.py sqlmigrate customers 0004
python manage.py sqlmigrate vouchers 0008
python manage.py migrate
python manage.py check --deploy
```

Review the full plan because other previously prepared modules may also be pending. Deploy the schema before starting the new backend/WhatsApp worker, and use the matching frontend with unnamed-contact fallbacks. Rehearse one ordinary checkout and one WhatsApp checkout with test providers, repeat the same request, verify exactly one contact/payment pair per logical attempt, fulfil it, inspect the linked voucher and retained receipt snapshot, and archive/restore the contact. Wi-Fi access and PPPoE state need their own target tests.

Rollback should retain the additive columns and contact/payment/voucher links. Do not unapply the migrations after new linked purchases exist; doing so discards provenance/history. Old writers may create unlinked records during a mixed-version interval. Keep those null and reconcile explicitly rather than retrospectively merging by email. Reverting code does not undo external payments or messages. Restore/reconciliation has not been exercised against production.

## Validation and release gates

Final local validation on 2026-09-15: the broader customer/payment/WhatsApp/subscription-access run completed 149 tests (148 passed, one PostgreSQL-only test skipped). A final 10-test contact regression run passed, including one additional foreign-plan privacy test: 149 distinct backend tests passed across these runs. All 16 distinct customer/PPPoE/device-history UI tests passed across the full and focused runs. Full frontend ESLint and the TypeScript/Vite production build passed. Migration drift reported no changes. Populated expansion preservation passed on disposable SQLite. The build retains existing non-blocking Zod annotation and subscription-page import warnings. Source current-folder comparison and local behavior are distinct from actual legacy data transfer. **Not approved as production-ready or as a completed import.**

| Gate | Status | Evidence / remaining work |
|---|---|---|
| Correctness | PASS (local) | Independent purchases, retry reuse, link propagation, unlinked-history preservation and archive behavior. |
| Validation | PASS (local) | Optional names/MAC evidence, bounded CSV, immutable references and protected provenance inputs. |
| Authentication | PASS (regression) | Existing authenticated APIs and subscription gate regression suite retained. |
| Authorization | PASS (local) | Tenant-scoped contacts/history; staff history denied; foreign contact issuance rejected. |
| Transactions | PASS (local) | Duplicate payment reservation rolls back its new contact; verified fulfilment retains atomic voucher links. |
| Concurrency | NOT VERIFIED (PostgreSQL) | Existing idempotency/inbox uniqueness used; actual multi-connection PostgreSQL races remain to rehearse. |
| Idempotency | PASS (local) | Public checkout key replay and WhatsApp receipt replay retain the original contact. |
| Database constraints | PASS (local) | Reference uniqueness, provenance uniqueness/pair checks and protected nullable FKs. Cross-table tenant consistency is an application/import invariant, not a composite database FK. |
| Indexes | NOT VERIFIED (target) | FK indexes support history lookup; target query plans and table scale unmeasured. |
| Migration safety | NOT VERIFIED (target) | Populated SQLite preservation passes; PostgreSQL lock/DDL/restore rehearsal pending. |
| Error handling | PASS (local) | Conflicting links fail instead of reassigning; normal API errors and UI retries retained. |
| Logging | NOT VERIFIED (target) | No new raw-PII/provider logging; deployed logging/retention needs inspection. |
| Metrics | NOT VERIFIED (target) | Existing monitoring reused; contact/import reconciliation metrics require the later import stage. |
| Tests | PASS (local) | Regression and targeted results below; isolated DB/provider mocks only. |
| Performance | NOT VERIFIED (target) | Paginated history with related-object loading; accounting sync remains a whole-history scan. |
| Accessibility | NOT VERIFIED (full) | Labeled forms, readable fallback and UI interaction tests; visual/screen-reader rehearsal pending. |
| Backwards compatibility | PASS (local schema) | Existing contact fields, payment amounts, voucher credentials/status and absent links survive expansion. Actual legacy dataset not imported. |
| Documentation | PASS | Decision, field/relationship mapping, runtime behavior, activation and rollback recorded. |
| Deployment safety | NOT VERIFIED (target) | Migrations prepared only; no service restart, provider contact or deployment performed. |
| Rollback strategy | NOT VERIFIED (target) | Retain additive schema and financial history; production restore rehearsal pending. |
