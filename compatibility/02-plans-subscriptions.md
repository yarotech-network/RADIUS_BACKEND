# Module 2: plans and subscriptions compatibility map

Mapped on 2026-09-14. This pass changes documentation only.

## Verdict and evidence boundary

The new system has useful additions: bandwidth profiles, purchased subscription
periods, version-checked business-plan edits, print quotas and WhatsApp allowances.
It is **not yet behavior-compatible with the current portal**. Preserve those
additions while fixing the data/entitlement gaps below. Do not import production
plans or switch traffic until the mappings and policy choices are resolved.

Evidence is current local source, not live production behavior:

- **L** = `../../yarotech-radius-system-current`, commit `0d4ca61`, recovered VPS
  source export of `ea2cd24`, including archive migration 0055.
- **N** = new backend, this repository, base `7464430` plus module-1 identity work.
- **F** = `../../yarotech-radius-frontend`, current independent React working tree.
  The nested `frontend/` inside the backend is not the frontend reviewed here.
- The older `yarotech-radius-system/db.sqlite3` is not current production data.
  No current database rows/counts, provider account, router or worker was inspected.
- Existing tests were read as evidence of intended behavior, not rerun in this
  mapping pass. No migrations, application edits or external actions were performed.
- `../../BUSINESS_PLANS_IMPLEMENTATION.md` describes an older creation-only phase;
  current code already has business-plan update/delete and entitlement snapshots.

Source references below use these roots and line numbers at mapping time.

## Domain and ownership map

| Domain | Authoritative facts and writer | Consumers / boundary |
| --- | --- | --- |
| Customer internet plan | Tenant-owned catalogue: price, time, data, speed, sales eligibility. L `vouchers.InternetPlan`; N `apps.vouchers.InternetPlan`. | Tenant UI, public storefront, agent issuance, vouchers and MAC-device services. It is not an operator subscription. |
| Purchased customer access | Voucher/order owns purchased terms, duration and expiry; catalogue edits must not change already issued access. | Payment fulfillment, voucher activation, print and RADIUS. Router enforcement needs separate runtime proof. |
| Operator business plan | Platform-owned catalogue: price/days/router quota; N also owns print and WhatsApp allowances. | Public pricing and tenant subscription checkout; feature descriptions are display text, not enforceable permissions. |
| Operator entitlement | Tenant's subscription and, in N, `SubscriptionPeriod.terms`; payment completion advances the entitlement. | Router admission, print authorization, WhatsApp and billing UI. |
| Settlement | Subscription/customer payment records own references, amounts and processing status; provider verification authorizes fulfillment. | Detailed financial reconciliation belongs to the payment module; plan terms and start dates must be settled here. |
| Service-specific access | N PPPoE plans live in `apps.customers`; MAC devices reference `apps.vouchers.InternetPlan`. | Do not map all legacy `iot_mac` plans into public hotspot plans. Service distinction is required before import. |

Recommendation: keep these as explicit modules within the existing Django system;
there is no evidence in this review requiring independently deployed services.
Operational ownership is assumed to remain with Yarotech's platform administrator;
tenant administrators own their customer catalogue. Confirm support ownership for
failed migration rows and paid-but-unfulfilled purchases before cutover.

## Customer internet-plan behavior

| Rule | Existing portal | New system | Mapping / consequence |
| --- | --- | --- | --- |
| Price | Decimal naira, 2 decimal places. | Integer kobo. React converts naira input. | Exact Decimal multiplication by 100; never copy the number unchanged or use float rounding. Check target integer range. |
| Duration | Decimal hours with 6 places, converted to rounded whole seconds. | Positive integer hours; API minimum 1; React integer duration. | **High:** fractional-hour plans cannot be preserved by direct mapping. Use canonical seconds or exact decimal duration end-to-end. Never round purchased time silently. |
| Data cap | Nullable `data_limit_mb`. | `data_limit`, 0 means unlimited. | Normalize null/unlimited deliberately; preserve positive MB values. Confirm meaning of legacy zero against actual data. |
| Speed | Nullable string up to 50; nonblank rates written into RADIUS replies at issuance. | Required model string up to 20; RADIUS rate reply only for matching linked bandwidth profiles. | **High:** direct custom-rate import does not reproduce the legacy enforcement path. Preserve supported rate syntax and explicit enforcement mode; flag blank/long/complex values. |
| Visibility | Separate `is_active`, `is_public`, `agent_enabled`. | Only `is_active`; public list exposes all active tenant plans. | **High:** a private or agent-disabled plan can become available through an unintended channel. Restore independent channel eligibility before import. |
| Service type / router | `voucher` or `iot_mac`, plus `public_router`. | Internet-plan API advertises only `hotspot`; MAC devices still use the same plan FK; PPPoE has its own model. | Preserve service type/router restrictions. Do not infer type from the plan name. |
| Code configuration | Prefix up to 6 and per-plan `voucher_code_format`. | Prefix up to 10; generator uses a fixed alphabet/8-character suffix. | Prefix fits, format policy does not map. Preserve all existing codes verbatim; new-code format is a voucher-module handoff. |
| Retire / archive | Delete archives, disables sales/public/agents, retains relationships; archived rows cannot reactivate normally. | Unused plan can hard-delete; referenced plan deletion returns validation error; inactive plan can reactivate. | **High:** deactivation is not equivalent to archival. Add archive state/actions consistently across API/admin/issuance. |
| Existing voucher duration | `issued_duration_seconds` survives catalogue edits. | `Voucher.service_terms` falls back to current plan if `purchased_terms` is null. Manual/agent issuance leaves it null. | **High:** unused issued access can activate for the edited duration. Snapshot all issuance paths and import issued seconds/expiry, not today's catalogue duration. |
| Public purchase terms | Legacy order stores price/device details; issued duration is fixed when voucher is created. | Checkout snapshots plan terms; paid customer fulfillment passes those terms even when plan later becomes inactive. | Keep the new checkout snapshot improvement. Define treatment of already-started purchases when archiving. |
| Device count / price | Voucher issuance allows 1-10 devices; public order total multiplies base price by reserved device count. | Shared generator fixes `device_limit=1`; public checkout charges one plan price. | **High:** preserve bought device capacity and order totals. Finish endpoint/pricing behavior jointly with voucher/payment module. |

Evidence: L `vouchers/models.py:1713-1787`, `:2038-2111`;
L `vouchers/services.py:689`, `:911-1021`, `:1053-1117`;
L `vouchers/agent_services.py:149`, `:439-461`.
N `apps/vouchers/models.py:27-42`, `:50-121`;
N `apps/vouchers/serializers.py:6-53`, `apps/vouchers/views.py:27-47`;
N `apps/vouchers/services.py:15-68`, `apps/vouchers/terms.py:1-11`;
N `apps/tenants/public_api.py:36-37`, `apps/payments/views.py:39-49`;
F `src/features/plans/planSchema.ts:14-66` and
`src/features/plans/pages/PlansPage.tsx:279-284`.

## Operator business-plan and subscription behavior

| Rule | Existing portal | New system | Mapping / decision |
| --- | --- | --- | --- |
| Catalogue identity | `name`, unique `slug`, description, display order, provider plan code. | `name`, `features`, price ordering, version; internal trial code. | Preserve legacy identifiers and descriptive/provider metadata in explicit fields or an import ledger. Do not reuse `internal_code`: non-null values are excluded from public pricing/checkout. |
| Price / duration | `price_kobo` bigint, integer days. | `price` positive integer, integer days; paid-plan API price >0. | Kobo is already the same unit here: **do not multiply by 100**. Validate range/free legacy plans. |
| Router limit | `router_limit`; null unlimited; counts active, nondeleted routers. | `max_routers`; null unlimited; counts all registered rows, including inactive. | **High policy difference:** deactivating a router frees an old-system slot but not a new one. Preserve old count policy unless explicitly changed. |
| New quotas | No corresponding fields on inspected legacy subscription plan. | Daily voucher print limit, WhatsApp flag; snapshot by period. | Keep enhancements, but do not silently restrict an existing paid entitlement. Define imported defaults and future-sale policy. |
| Trial | 30 days, no catalogue plan, stored trial timestamps; router allowance from configuration (fallback 1). | 15-day internal plan, 1 router, 50 prints/day, WhatsApp off. | **High:** preserve existing trial end dates. Choose future-signup policy separately. Never run signup trial assignment as a generic importer. |
| Missing subscription | Ordinary tenant access denied by old subscription policy. | `entitlement_terms()` allows unlimited routers/prints and WhatsApp when no subscription exists. | **High:** a missed import row becomes an entitlement bypass. Use explicit platform exemption and fail-closed ordinary-tenant policy. |
| Expiry | Middleware restricts ordinary portal actions, with billing/recovery/public exceptions; agent issuance also checks access. | Entitlement checks occur at router admission, print and WhatsApp; no equivalent blanket gate in reviewed plan/voucher paths. | Build an endpoint/action policy matrix. Expiry should not accidentally prevent renewals or revoke paid customer access. |
| Same-plan renewal | Extends future expiry if same plan, otherwise base is provider `paid_at`. | Any active subscription extends from its expiry; snapshots become a future period. | Same-plan renewal broadly aligns; compare delayed verification start time explicitly. |
| Different-plan purchase | Starts at provider paid time; changes current subscription plan immediately. | Queues after current active period, including trial; current allowances remain until period boundary. | **High policy difference:** an upgrade bought today may not increase today's router allowance. Decide immediate upgrade vs scheduled change; preserve existing periods. |
| Settlement timestamp | Records provider paid time/transaction ID; uses paid time for activation base. | Completion uses local now when no active subscription; payment has local completed time. | Delayed verification can produce different entitlement dates. Preserve source timestamps and document the chosen basis. |
| Complimentary access | Audited grant model, reason, actor, expiry, activation source/reference. | No equivalent grant model/action in inspected subscription module. | **High migration gap:** retain complimentary validity and audit provenance; never manufacture a successful payment for a free grant. |
| Catalogue edits | Subscription references live plan fields. | Optimistic version check; freezes old/manual terms; periods keep purchased allowances. | Keep the new protection. Historical snapshots cannot be reconstructed merely from today's edited catalogue. |
| Catalogue deletion | Plan FK protected by historical subscriptions/payments. | Referenced plans protected; inactive business plans excluded from new checkout. | Broadly aligned; preserve inactive history and references. |
| State / timestamps | Subscription can be pending, plan/start/expiry nullable; source and trial metadata recorded. | Plan/start/expiry required; trial is a status + boolean. | Explicit transformation required; preserve pending/cancelled records without inventing paid entitlements. |
| Payment history | initialized/successful/failed/abandoned, provider transaction ID, paid/processed timestamps, verification metadata. | pending/success/failed, reference, amount, completed time and period link. | Maintain a lossless reconciliation ledger for fields without destinations; classify abandoned explicitly. |

Evidence: L `vouchers/models.py:1074-1230`,
L `vouchers/subscriptions.py:42-95`, `:195-283`,
L `vouchers/middleware.py:10-65`;
N `apps/subscriptions/models.py:5-95`, `trials.py:11-40`,
`entitlements.py:24-42`, `services.py:15-76`,
`views.py:31-37`, `:61-78`, `:142-191`, `serializers.py:19-77`.
F `src/features/settings/pages/SubscriptionSettingsPage.tsx:210-245` displays
effective terms and upcoming periods; `src/features/platform/pages/BusinessPlansPage.tsx:255-304`
exposes the new limits. These new UI semantics must be kept in sync with any policy fix.

## Data-transfer contract

| Source fact | Target / required handling |
| --- | --- |
| Legacy tenant and plan primary keys | Stable old-to-new ID ledger; validate every FK before writes. Do not assume matching IDs mean matching records. |
| Internet-plan naira price | Exact kobo conversion, integral result and target range check. |
| Business-plan kobo price | Rename/map without currency conversion. |
| Fractional hours / issued seconds | Preserve exact effective seconds; schema/API support required first. |
| Active/public/agent/archive/type/router | Preserve independently; unsupported flags are blockers, not default-true values. |
| Voucher purchased time/speed/data/device limits | Use issued contract and existing enforcement evidence. Keep activated/expiry timestamps and credentials; do not reset the clock. |
| Paid subscription | Preserve effective start/end and current allowances in an initial historical period; no new payment processing. |
| Trial with null plan | Explicit internal historical trial representation or schema support; preserve original deadline and trial-used state. |
| Complimentary subscription | Preserve reason/actor/source/reference in grant record or auditable migration ledger. |
| Missing/pending/cancelled subscription | Explicit state handling; never exploit the no-subscription unlimited fallback. |
| Payment reference/provider ID/history | Preserve unique references and amounts; map status and retain provider/timestamp provenance. Never replay old successful payments to build history. |

The existing N `subscriptions/0004_backfill_purchased_terms` reads the **new**
database's current catalogue. It is not a legacy importer and cannot prove what an
old purchase originally promised. N `vouchers/0004` adds nullable purchased terms
without backfilling all historical vouchers. Reconciliation must compare customer
contracts, not only counts. Unknown terms require review, not silent guessing.

## Transaction and failure map

| Boundary / scenario | Current behavior, exposure and required check |
| --- | --- |
| Issue voucher while plan is archived | L locks/rechecks sellability. N ordinary issuance reads active plan without the equivalent archive state/plan lock. Serialize archive and issuance; test both interleavings. |
| Checkout then catalogue edit/deactivation | N captures customer/subscription terms before provider call; fulfillment uses snapshots. Retain this. Test paid reservations after deactivation/archive explicitly. |
| Provider timeout / lost webhook | N keeps payment reference; subscription verify can recover. Never ask customer to pay again solely because callback was lost. Financial reconciliation is a payment-module handoff. |
| Duplicate verified callback | Both systems have processed/success guards; N locks payment and tenant and links one period per payment. Verify concurrent delivery on PostgreSQL. |
| Subscription expiry | N expiry command changes status; runtime entitlement calculation also checks time. Command deployment/freshness unverified. Define action gates and monitoring. |
| Quota contention | N print authorization uses tenant lock, per-day uniqueness and Lagos date; router checks need the same transaction discipline. Existing concurrency tests are source evidence only. |
| Partial import | Quarantine invalid rows and reconcile dependent records before enabling a tenant. Missing subscription must not grant unlimited use. |
| Rollback after new sales | Stop writes and reconcile the delta before routing back. Code rollback cannot undo purchases or provider events. Restore rehearsal required. |

Scale/operations: volumes are unknown. Catalogue-edit backfills iterate linked
payments/subscriptions inside a transaction and can hold locks as history grows;
measure on a production-sized PostgreSQL restore. Set operator-owned alerts for
pending paid fulfillment, missing entitlement rows, expired-but-enabled services,
quota denials and worker freshness. RPO/RTO and alert thresholds remain open;
no load or live-router claims are made here.

## Decision log and implementation order

Accepted scope: replace the old portal after success, preserve customer workflows
and purchased rights, retain useful new features, and review module by module.
No shared live database or automatic migration is authorized by this mapping.

Recommended work order:

1. **Customer-plan compatibility:** exact duration, sales channels, service/router
   scope and irreversible archive state; update both API and React controls.
2. **Issued-access preservation:** snapshot all issuance paths, import issued
   seconds/device caps and speed enforcement, retain existing codes/expiry.
3. **Operator entitlement policy:** resolve missing-subscription handling, router
   counting, trial rules, upgrade timing and expiry action matrix.
4. **Historical mapping:** complimentary grants, pending/null states, provider
   references and subscription periods with an explicit import ledger.
5. **Verification:** prepare migrations only; rehearse on a separate PostgreSQL
   database and test concurrency, delayed callbacks, archives, snapshots, scopes,
   existing vouchers and frontend flows. No direct import into the live legacy DB.

Open decisions for discussion (recommendations, not implemented changes):

- Preserve every existing trial deadline; separately choose 30 vs 15 days for future signups.
- Count active nondeleted routers to preserve the old commercial allowance, unless
  the new all-registered-router rule is explicitly intended.
- Choose immediate upgrades or queued plan changes. Do not silently reinterpret
  a paid upgrade; same-plan early renewals should preserve unused paid time.
- Apply new print/WhatsApp limits to future purchases; preserve imported contracted
  access unless an explicit transition policy says otherwise.
- Define which actions are blocked after operator expiry while allowing billing,
  recovery and already purchased customer access to behave as intended.

First implementation recommendation: customer-plan compatibility and issued-term
preservation, before moving on to vouchers/payment migration. This document is a
map for that discussion, not deployment approval or a completed importer.

2026-09-14 follow-up: operator policy decisions accepted and implemented locally; see [03-operator-entitlements.md](03-operator-entitlements.md) for exact scope, preserved rights and unverified deployment checks. The earlier open-decision list above records the mapping-stage state.
