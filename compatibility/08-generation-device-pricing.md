# Voucher generation and device pricing comparison

Date: 2026-09-14. Comparison of recovered production source (`yarotech-radius-system-current`) with the top-level Django/DRF backend and React frontend. Physical MikroTik testing is paused; no VirtualBox/VPS topology is assumed. This pass changes documentation only. Source defaults do not establish deployed feature-flag values.

## Verdict

The next implementation should preserve plan-controlled code formats and complete device selection through order reservation, provider amount and fulfillment together. Keep agent discount/commission accounting as an explicit financial rule: copying the public retail formula into wallet debit would overcharge agents relative to the inspected legacy service. Keep a modular Django application; no new service deployment is justified by this comparison.

## Verified comparison

| Area | Existing portal | New system | Consequence / recommendation |
| --- | --- | --- | --- |
| Code format | `vouchers/services.py:544` supports numeric, alphabetic and alphanumeric. `create_radius_voucher` reads persisted plan format; reserved paid-order format takes precedence. Older pending orders without a format snapshot fall back to tenant default | `apps/vouchers/models.py:Voucher.generate_access_code` uses a fixed eight-character alphabet; no plan format field | Medium: add persisted plan format and tenant default for creation/import. Freeze format on new orders. Do not reinterpret already-issued codes or silently change older pending orders |
| Code identity | Legacy `voucher_identity_exists` checks all voucher rows, RADIUS and MAC identities case-insensitively; generator bounds attempts and handles insert collisions | `apps/vouchers/services.py:generate_vouchers` tests exact voucher usernames in an unbounded loop; database uniqueness prevents duplicate exact inserts but a race can abort the batch | High: bounded retries using savepoints; reserve identities across relevant namespaces including retained deleted vouchers. Never uppercase or regenerate imported credentials |
| Prefix | Legacy normalized uppercase alphanumeric prefix, max 6; random body supports format-specific lengths through 32 | Target accepts optional prefix up to 10; admin UI exposes it | Preserve issued strings. Validate generated total length against the actual authentication contract; model capacity 64 does not prove the current RADIUS 1-32 alphanumeric gate accepts newly generated longer codes |
| Device capacity | Legacy forms/services allow 1-10 only when `MULTI_DEVICE_VOUCHERS_ENABLED` is on; source setting defaults off (`config/settings.py:172`) | Shared target generator accepts 1-10 and writes Simultaneous-Use. Batch request, agent sale and storefront form do not expose capacity | High: one server-authoritative capability policy and matching UI; omitted count remains one. Production flag value is unknown |
| Public price | Legacy public reservation stores base amount, device count and total; total = base kobo x devices | `apps/payments/views.py:InitializePaymentView` stores and sends `plan.price`; payment serializer has no device count | High: update validated input, snapshot, provider amount, response and frontend receipt together. Never accept a client-supplied monetary total |
| Snapshot meaning | Legacy separates base, total and format snapshot | `apps/vouchers/terms.py:snapshot_plan` stores price=plan.price and device_limit. `apps/payments/recovery.py:36` requires purchased_terms.price == payment.amount | High: define a versioned order snapshot with explicit base/total. Merely multiplying payment.amount would cause fulfillment rejection. Preserve version-2 snapshot meaning for existing records |
| Agent wallet charge | `vouchers/agent_services.py:generate` calculates commission-adjusted cost with Decimal ROUND_HALF_UP, then multiplies retail/cost by device count and quantity; preserves snapshots and supports assignment path | `apps/agents/services.py:generate_voucher_from_wallet` debits plan.price x quantity and records plan.price per allocation | High financial compatibility gap: preserve applicable commission source, rounding and assignment rules before broadening agent device selection. Do not treat agent commission_rate field presence as proof it affects debit |
| Checkout display | Legacy reservation records bought quantity and total | React `CheckoutPage.tsx` sends no device count and saves plan.price in pending checkout | Display devices and total before payment; use authoritative reserved total in pending receipt and recovery |
| Subscription expiry | Agreed user policy stops new sales and hides storefront plans until renewal | Existing gate enforces new purchase/issuance restrictions | Preserve the gate on every issuance channel and continue honoring existing issued vouchers independently of operator expiry |

## Ownership and contracts

- Plan/tenant configuration owns future code-format defaults and available device counts. UI reads these capabilities; hiding a field is not enforcement.
- Issuance owns one identity, immutable service capacity and atomic voucher/RADIUS credential writes. Count of vouchers and devices per voucher are distinct dimensions.
- Payment reservation owns base amount, device count, total, selected code format and provider reference. Provider verification must match reserved reference, currency and integer amount before fulfillment.
- Agent service owns commission source, debit amount and allocation snapshots. Its wallet ledger is not interchangeable with public retail receipts.
- Existing vouchers and paid-order records remain historical authority. Catalogue edits do not change their code, capacity, deadline or paid total.

Proposed additive requests: optional integer device_limit, default 1, on batch generation/public checkout/agent sale only when supported. Reject booleans, fractions, zero and values over the configured cap. Code format is controlled by the persisted authorized plan, not an arbitrary public checkout override. Return authoritative base/device/total values from checkout initialization for display. Freeze paid-order format even if the plan is edited before provider confirmation.

## Transaction and failure map

| Failure | Required result | Owner |
| --- | --- | --- |
| Concurrent generation chooses same code | Bounded retry inside savepoint; no partial batch or duplicate credential | Issuance |
| Plan edit during checkout | Lock plan, reserve one coherent set of terms, commit before provider I/O | Payment |
| Retried checkout | Same idempotency key plus same device count yields same order; mismatched payload must not reuse a differently priced result | Payment/API |
| Payment amount differs from reserved total | No voucher issuance; preserve reconciliation evidence | Verification |
| Provider timeout after initialization | Retain reference and pending state; reconcile without a second charge | Payment recovery |
| RADIUS write fails after wallet debit | Roll back debit, voucher and allocation together | Agent/issuance |
| Tenant expires between display and submission | Reject new order/issuance without charging | Subscription/payment |
| Feature flag changes while payment is pending | Honor already-reserved paid capacity; apply new cap to new orders only | Payment/issuance |

Use bounded batch sizes and collision attempts. Avoid holding database locks during provider network calls. PostgreSQL contention, identity collision frequency, throughput and provider latency remain unmeasured; no scale/readiness claim follows from this source comparison.

## Proposed implementation sequence

1. Add plan/tenant format configuration, format snapshots and bounded identity generation. Include React plan settings. Preserve all imported credentials and existing pending-order behavior.
2. Add server capability reporting and device selection to manual/batch/public paths. Preserve one-device default; do not enable multi-device sales implicitly from a schema change.
3. Version public purchase snapshots and implement base x device total end to end. Preserve old snapshot readers. Include price-change, flag-change, duplicate callback and amount-mismatch tests.
4. Complete agent commission/wallet mapping before enabling its multi-device path. Test default versus assigned-plan commission, rounding, insufficient balance and debit rollback. This is the next financial-module review, not an assumed percentage change.
5. Rehearse additive migrations/import on a separate PostgreSQL database. Verify local physical-router simultaneous-use enforcement before enabling multi-device sales. Cutover must avoid mixed old/new fulfillment writers; retain the old database for rollback and reconcile any new transactions before reverting.

Example acceptance cases: a 50,000-kobo public plan for three devices reserves 150,000 kobo; capacity=3 is written on the voucher; later plan edits do not alter that order. Separately, if the applicable agent commission is 20%, per-device cost is 40,000 kobo and three devices cost 120,000 kobo before multiplying by voucher quantity. This example does not establish any tenant's configured commission.

## Decisions and validation status

Accepted: preserve old business behaviour and issued rights; no new storefront purchase after operator expiry; physical router test remains paused. Recommendation: preserve the effective legacy multi-device feature flag and stage activation after router verification. Unknown: current deployed flag value, applicable tenant commission values and the exact final RADIUS code-length contract for the new deployment. None is inferred from source defaults.

Validation in this pass: traced source forms, configuration, generation, agent charging, target order initialization/snapshot/verification, and React checkout payload/receipt. No runtime changes or tests were needed for this documentation-only comparison. Existing migration 0006, importer and RADIUS integration remain pending deployment work.
