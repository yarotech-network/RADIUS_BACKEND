# Agent wallets and commissions

## Comparison and accepted policy

The recovered `yarotech-radius-system-current/vouchers/agent_services.py` calculates agent cost with Decimal ROUND_HALF_UP, subtracting commission from retail. Its normal plan-based path uses the tenant default; historical assignments may use a saved cost. It writes a wallet transaction, batch and per-voucher financial snapshots together. Funding may include separate fees. It also supports generation freezes, credit/complimentary allocations and repayment/reversal ledgers.

The new `apps/agents/services.py` previously debited full retail and left commission_earned at zero despite a per-agent commission_rate and manager editing UI. Its payment completion already locks payment then wallet and is replay-safe by success status, but it lacks a wallet movement ledger. React previews retail as wallet cost and replaces a sale key after every error, including uncertain network outcomes.

User decision (2026-09-15): retain each agent's configured rate for future sales. Commission is the retained retail margin, not an extra wallet credit. Existing balances, historical allocations and rates are not recalculated.

## Implementation plan

1. Calculate integer-kobo discounted cost centrally, round each voucher cost HALF_UP, validate rate 0-100, and snapshot retail/rate/discount on each new allocation. Keep agent sales single-device for this pass; reject unsupported counts explicitly.
2. Add wallet movement records (previous balance, amount, next balance, category, opaque reference) for new sales and successful funding in the same atomic transaction. Add nullable links on existing financial records, without inventing historical movements. Protect linked records from deletion and make financial admin records read-only.
3. Expose server-calculated agent catalogue cost/margin and a paginated, agent-scoped GET wallet transactions endpoint. Show cost, margin and movement history in React. Retain the same sale key on uncertain failures and prevent changed payloads from bypassing an unresolved sale; allow a fresh attempt following a definite validation rejection.
4. Verify rounding, zero/full commission, sufficient discounted funds, rollback, immutable snapshots, funding duplicate completion, tenant isolation and API replay; test frontend pricing, receipt, history and uncertain retries. Prepare migration, never apply it to existing databases.

## Boundaries and rollout

The sale atomic unit covers agent/plan/wallet locks, wallet debit, ledger, vouchers, local RADIUS rows and allocations on the default connection. Lock order remains agent -> plan -> wallet; funding uses payment -> wallet. No external request belongs inside this unit. Failure rolls everything back; caller instances must be refreshed. The existing API command reservation is separate: an ambiguous command remains pending for reconciliation rather than blindly reexecuting. No automatic transaction retries are added. PostgreSQL contention/deadlock and commit ambiguity require rehearsal on disposable PostgreSQL, beyond SQLite verification.

Catalogue values are previews; charging recalculates under locks. Sale results and saved allocations are authoritative. Paired frontend/backend deployment is required for the new charging semantics. Old imported assignments with negotiated costs need an explicit mapping before cutover. Do not map legacy naira plan prices to kobo without conversion; wallet and ledger amounts already use kobo.

Remaining compatibility work: legacy funding fees/minimum/maximum and provider reconciliation, generation freezes, credit/complimentary allocations, repayments/reversals, assignment limits and financial-history import. This pass does not silently import or reset these obligations. Existing new-system funding limits and 1-100 batch limit are preserved pending those reviews. Tenant-level agent_commission_percent is not the source of future per-agent pricing.

## Delivered API and operational contract

- Agent catalogue responses add `agent_cost`, `commission_amount` (integer kobo) and `commission_rate` (decimal string). Retail `price` remains unchanged. Agent `max_devices` is always 1, even when storefront multi-device purchases are enabled.
- Allocation responses add nullable `retail_price`, `commission_rate_snapshot` and `wallet_transaction`. A 100% commission creates zero-debit sale evidence and no artificial credit. Monthly commission totals use the business-local date boundary.
- `GET /api/v1/agent/wallet/transactions/` uses standard bounded page pagination, orders by descending creation time/id, and scopes by authenticated agent. POST is not allowed. Fields are id, opaque reference, category, amount, previous_balance, new_balance and created_at; no provider payload or voucher credential is returned.
- Wallet, funding and sale admin records are read-only. Existing agent user/tenant identity cannot be reassigned through admin. ORM protection retains linked wallet movements and vouchers; raw database administrators remain outside these application controls. The old unsafe wallet credit/debit instance helpers were removed; financial callers must use the transactional services.
- Wallet completion now requires verified status, exact reference, strict integer amount and currency at the service boundary as well as the existing signed webhook/provider verification. Successful old payments remain no-ops without manufacturing historical ledger entries. Overflow stops before committing a balance change.
- React stores the pending sale key and request in session storage scoped to user/tenant. It retries the same operation after network/server uncertainty, including a remount/reload in that tab; changed payloads are blocked until resolved. A definite 400 validation failure permits a new attempt. Authentication, throttling and pending-command responses do not discard an uncertain key. This is not a global lock across independent tabs/devices. A server crash between sale commit and API-command completion still requires reconciliation; no automatic replay of an ambiguous command was added.

## Prepared migration and rehearsal

`agents/0003_wallet_movements_and_commission_snapshots.py` depends on the previous voucher compatibility migrations. It adds nullable allocation snapshots/links, a new movement table, history index and arithmetic constraint, plus ORM deletion protection. There is no balance/history backfill or commission-rate reset. Existing new-system monetary columns remain bounded to 2,147,483,647 kobo; larger legacy balances need an explicit schema/import decision before cutover.

On an isolated restored PostgreSQL rehearsal, inspect the complete pending migration plan and generated SQL first:

```sh
python manage.py migrate --plan
python manage.py sqlmigrate agents 0003
```

Do not run these migrations on the old template application's incompatible schema. Resolve earlier voucher identity preflights before rehearsal. Production engine/version, table sizes, lock queues, replica lag and required lock/statement timeouts have not been measured here. New foreign-key/index work on allocation and funding tables needs that review. No production DDL safety or duration claim follows from the local SQLite test.

Expand schema before deploying the matching application pair. Old binaries can tolerate the nullable columns, but mixed financial writers would omit ledger movements and charge different prices: stop old sales/funding writers before enabling the new code. Preserve a verified backup and an isolated restore. After new movements exist, retain the expanded schema and prefer a forward fix; reversing this migration would erase financial evidence. Reverting to old charging code also requires stopping sales and explicit reconciliation.

## Validation (2026-09-15)

- Final isolated SQLite regression run: 128 tests discovered, 125 passed, three PostgreSQL-only concurrency tests skipped. Scope: agents, payments, vouchers, subscription access gate. Includes fresh test-schema creation, upgrade preserving populated wallet/allocation rows, rounding, duplicate suppression, rollback, funding evidence, arithmetic constraints and agent-scoped reads.
- Agent frontend suites: 27 passed. Covers discounted affordability, actual receipt values, uncertain retry/remount, changed-payload blocking, wallet-history pagination and manager screens.
- Scoped ESLint, TypeScript and the production Vite build passed. Existing Zod annotation and subscription-page mixed-import warnings remain non-blocking.
- Django migration consistency: no changes detected. Both working-tree whitespace checks passed.
- NOT VERIFIED: PostgreSQL lock/concurrency/DDL rehearsal, production-size queries, live provider delivery, physical-router enforcement and legacy data import. No existing database migration, production deployment, payment request or router change was performed.

Next compatibility pass: agent funding fees and verification/reconciliation, followed by credit allocations and historical ledger import.
