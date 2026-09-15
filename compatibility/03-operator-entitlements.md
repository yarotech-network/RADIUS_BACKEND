# Operator subscription compatibility

Approved 2026-09-14: preserve 30-day future trials, active-router counting and immediate upgrades; preserve existing trial deadlines and paid rights. Existing module-1/module-2 edits remain in place.

Implementation plan:
1. Version the internal trial plan so only new assignments become 30 days. No backfill or migration of existing deadlines.
2. Centralize active-router usage; require an active subscription (explicit platform-tenant exemption). Count only active rows; check capacity on creation and inactive-to-active transitions under the tenant lock. New backend has hard deletion, not the legacy deleted_at field.
3. Activate paid upgrades immediately if no remaining contracted allowance is reduced. Carry remaining paid time forward. Same-plan renewals and reductions queue after existing periods. Trial-to-paid purchases start immediately. Preserve historical periods as superseded records and one payment-to-period link.
4. Return active-router usage through the subscription API; explain activation/renewal timing in React. No new endpoints or fields are needed.
5. Test trial preservation, renewal/upgrade/reduction timing, duplicate completion, missing subscriptions, router reactivation, expiry and tenant isolation. Use disposable SQLite; prepare no live data changes. PostgreSQL contention and provider/router proof remain separate.

Evidence: legacy vouchers/subscriptions.py:57,81,195; new apps/subscriptions/trials.py, entitlements.py, services.py, serializers.py; routers/views.py create/update; React settings/pages/SubscriptionSettingsPage.tsx. The legacy implementation switches every different plan immediately; preserving already-paid rights means reductions are deliberately queued here. Structured router/print/WhatsApp allowances define an upgrade; price or marketing text alone does not.

Scope boundary: this step changes operator entitlement controls already enforced for router slots, print authorizations and WhatsApp. It does not install a broad expiry middleware, disconnect purchased customer access, implement complimentary grants, import historical subscriptions or change public voucher purchasing. The complete expiry action matrix and historical import remain explicit subsequent work.


## Ownership and transaction map

| Boundary | Owner and contract | Failure handling |
| --- | --- | --- |
| Trial creation | `trials.assign_new_tenant_trial`; tenant creation calls it within its transaction. Internal code `signup-trial-v2-30-days`; old v1 records remain. | Existing subscription wins; no deadline reset or automatic legacy trial grant. |
| Entitlement reads | `entitlements.entitlement_terms` reads saved current period; the existing manual-row fallback remains. | Missing or expired subscription denies controlled operations; inactive tenant also denies. Only an explicitly marked active platform tenant has the no-subscription exemption. |
| Router capacity | `router_usage` counts active routers; create/reactivate takes the tenant lock before writing the router. Subscription API uses the same counter. | Limit failure returns 403 with no activation; inactive creation requires an active subscription but consumes no slot. Deactivation/read remains available after expiry. |
| Payment completion | Subscription service locks payment then tenant; saved checkout terms determine purchased allowances. Existing provider verification remains outside this transaction. | Duplicate successful payment is a no-op. Period creation and activation commit together. Old periods remain as superseded history when upgraded. |
| React billing | Existing subscription response includes effective terms and upcoming periods; no shape or route change. | Current allowance and usage labels now say active routers; existing error/retry and payment recovery stay available. |

Upgrade timing is an intentional compatibility choice: old legacy different-plan payments replaced the period immediately, losing remaining time in some cases. The new behavior activates only non-reducing changes immediately and carries remaining paid days forward. Price, name and marketing features do not override structured allowances. A future prepaid period with stronger allowances prevents an immediate change that would reduce those rights. Trial-to-paid starts the paid term immediately without stacking free days onto it; tenants remaining on trial keep their original deadlines. Manual/historical rows without period snapshots still require provenance review before import.

## Validation (2026-09-14)

- PASS: 80 backend tests across operator compatibility, trials, subscription APIs/services/limits, registration, router APIs and WhatsApp routing. Includes 12 new policy tests. All used a disposable in-memory SQLite database; existing databases were not migrated.
- PASS: 42 frontend tests covering settings, historical 15-day trial display, subscription recovery, allowance labels and storefront pricing.
- PASS: TypeScript plus Vite production build, scoped ESLint, Django system check and `makemigrations --check --dry-run` (no changes). Build emitted nonfatal dependency annotation warnings.
- Prepared, NOT RUN on PostgreSQL: concurrent router reactivation regression added to `ConcurrentLimitTests`, alongside existing creation/printing/payment/trial contention tests. A broad initial SQLite run reached the pre-existing threaded registration test and failed with unavailable-table behavior across thread connections; it was excluded from the supported SQLite validation, not treated as passing concurrency evidence.
- Fixtures that relied on missing-subscription unlimited access now create explicit paid subscriptions. Router limit cases send explicit active values rather than relying on HTML-form Boolean omission. Platform tenant-creation fixture supplies module-1's required owner fields. No application contracts were weakened to satisfy those tests.

## Deployment preparation and outstanding work

No new migration is needed for this step. The previous modules' migrations remain prepared and unapplied. Deploy these policy changes with their matching React labels and remove old application workers from service; mixed old/new subscription completion code can disagree about timing.

Before enabling the policy against real data, identify every non-platform tenant lacking a subscription, every manual row without a historical period snapshot, and future prepaid periods. Reconcile them from verified historical records; do not grant a new trial or fabricate unlimited access. The recovered old portal database still needs its own ID/status/complimentary-grant import mapping. Do not run this code against the old schema.

On an isolated PostgreSQL test configuration, run:

```sh
python manage.py test apps.subscriptions.test_operator_compatibility apps.subscriptions.test_trials apps.subscriptions.test_entitlements apps.subscriptions.tests --settings=config.test_settings
```

That command creates a test database; confirm its configured host/name first. Rehearse duplicate subscription callbacks, simultaneous first payments, competing create/reactivate requests and renewals during upgrades. Verify real provider recovery without replaying historical payments or sending customer messages. Measure tenant-lock wait and history size; upgrade checks inspect all remaining periods.

Rollback should retain new trial/period history and use compatible corrected code. Restarting the old policy code would reopen missing-subscription access, count inactive routers again and queue upgrades differently. Database restoration after new sales requires payment reconciliation; do not delete new periods or reverse earlier migrations to mimic a code rollback.

Production readiness remains **NOT VERIFIED**: PostgreSQL contention, restored production data, provider callbacks, router enforcement, operational monitoring and rollback rehearsal have not been exercised. Next: define the full expiry action matrix and historical subscription/complimentary-grant mapping before building the importer. Existing customer access is not disconnected by this step.
