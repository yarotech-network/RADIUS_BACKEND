# Agent credit allocations, repayments and reversals

## Verified comparison

The recovered application's `vouchers/agent_services.py` issues operator-approved batches on credit, increases a separate outstanding-debt account, and snapshots allocation prices. A repayment belongs to one allocation, cannot exceed its remaining debt or the account balance, and uses a tenant-unique external reference. Ledger entries retain actor, method, date, note and resulting balance. Reversal is a separate entry and disables eligible unused vouchers without deleting financial history. Previously recorded repayments are retained; no automatic cash refund is made. Explicit Django permissions control adjustments and reversals.

At the start of this comparison, the new application's `AgentCreditAccount` and `AgentCreditLedger` were dormant model/admin structures. Its signed `current_balance`, optional credit limit and generic signed ledger do not implement issuance, per-allocation repayments or reversal. Its `AgentVoucherAllocation` represents one voucher, whereas the old allocation represents a batch. There is no safe one-to-one table import or inference of old repayments from current wallet history. Wallet top-ups are not debt repayments.

Accepted prior policy: future agent prices use each agent's configured commission, rounded per voucher. Preserve every existing balance and allocation; do not recalculate debt from today's plan price or commission.

## Accepted decisions

1. Require a configured, active per-agent credit limit for future issuance. The agent's configured commission reduces the debt charge per voucher.
2. Cancellation disables every eligible unused voucher in the allocation and clears only remaining debt. Prior repayments stay recorded. There is no automatic refund or wallet credit, including when an allocation was fully repaid.

The user explicitly selected both policies. Used, expired, bound, imported/uncertain or historically authenticated vouchers cannot be reversed through this workflow.

## Implementation map

- Keep operator-issued credit separate from the agent's prepaid wallet sale flow. Agents may read their own obligations but cannot grant themselves credit or record their own receipt of repayment.
- Preserve the existing signed account and ledger data until reconciliation. Negative balances and account/ledger differences require review, not coercion to zero. A nonzero balance without matching ledger history may be an opening balance; the audit cannot classify it as corruption.
- Introduce a batch-level credit obligation linked to existing per-voucher allocation records. Store quantity, original unit charge/retail/rate, total debt, amount repaid, due date, creator and reversal evidence. Do not fabricate those values for historical rows without source evidence.
- Add typed, linked debt movements with before/after balances, actor and immutable transaction evidence. Repayment external references must be unique within the tenant. Partial repayment updates allocation and account together. Retried issuance, repayment and reversal require durable request identity and payload matching.
- Apply tenant scope before object lookup. Reuse the repository's active membership/access gate and explicit financial authority; map old fine-grained permissions before exposing adjustments to delegated staff. Freeze arbitrary credit balance/ledger edits once the audited workflow replaces them.
- Use consistent agent/account/allocation/voucher lock ordering, and let the shared trusted activation service contend on the same voucher rows during reversal. Reject reversal when activation, expiry, use, device binding or accounting history indicates consumption. Imported vouchers whose history is uncertain require reconciliation. Persist cancelled voucher status and local RADIUS credential removal atomically; live FreeRADIUS enforcement remains a separate prerequisite.
- Add operator credit controls and paginated obligation/repayment history to the agent detail screen, plus read-only obligations for agents. Preserve entered amounts and request keys after uncertain outcomes. Display money in naira while sending/storing integer kobo.

## Read-only preflight

```sh
python manage.py audit_agent_credit_compatibility
```

The command reads only existing new-system columns. It reports counts and IDs requiring mapping/reconciliation; it neither changes balances nor calls a router/provider. It is not an audit of the old application's differently named tables. Recovered database debt/repayment export and explicit identity mapping remain required before cutover.

## Planned verification

Cover tenant and role denial, configured credit policy, per-unit rounding, immutable charge snapshots, insufficient credit, rollback after partial voucher issuance, duplicate request replay, duplicate external repayment reference, overpayment rejection, repayment/reversal race, used-voucher reversal rejection and preservation of historical signed balances. Run populated-schema upgrade tests in an isolated database. SQLite tests cannot establish PostgreSQL row-lock or physical-router enforcement guarantees.

## Implemented workflow

- Owner: Agents > select agent > Credit account. Configure limit/activity with a reason; existing debt is not editable. Issue discounted credit vouchers, record money already received against an allocation, and cancel eligible allocations after explicit confirmation of amounts/no refund.
- Agent: Wallet > View credit account. Read own balance, paginated allocations and ledger; no financial write endpoints are available to agents or managers. Mapping delegated legacy financial permissions is deferred.
- API: `/api/v1/tenant/agents/{id}/credit/` (GET/PATCH), `credit-batches/`, `credit-history/` (GET), `credit-issue/`, `credit-repay/`, `credit-reverse/` (POST). Own-agent reads: `/api/v1/agent/credit/`, `batches/`, `history/`.
- Commands require a UUID `request_key`; the tenant/key is durable and payload-bound. Receipts also require a tenant-unique external reference, amount, method and received date. No Paystack request is made. The browser saves the command before sending and reuses it after an uncertain result or same-tab reload. Browser storage failure prevents submission. Closing the tab/clearing storage requires manual ledger reconciliation before re-entering an uncertain transaction.
- Reversal requires `expected_outstanding` and `expected_repaid`, rejecting stale confirmation after another repayment. Account configuration compares prior limit/activity/existence to avoid overwriting a concurrent change.
- New batches link existing per-voucher allocations through a nullable FK. New typed movement evidence links the original signed ledger. Creator/receipt/cancellation actors and before/after balances are retained. Existing signed balances and ledger entries are not backfilled or recalculated. Unmatched account/ledger totals and negative historical balances block new commands pending reconciliation.
- Issuance updates vouchers, per-voucher allocations, debt and ledger together. Repayment updates batch and debt together. Reversal updates batch, voucher status, local radcheck/radreply and ledger together, with no wallet mutation. These transactions cover the default database only and make no network calls.
- Lock order is agent, issuance plan, account, batch, then voucher rows ordered by ID. Activation uses the same voucher lock. Cross-agent receipt/request conflicts are additionally constrained by tenant-wide database uniqueness. A deadlock/connection failure rolls back the local transaction; retry the entire command using the same UUID. Concurrent PostgreSQL tests must pass on the target engine before release.
- Credit/admin balances and financial history cannot be edited through Django admin. Cancelled credit allocations are excluded from the agent's monthly commission sum, while original allocation price snapshots remain intact.

## Migration and rollout

Prepared migration: `agents/0005_agentcreditbatch_agentvoucherallocation_credit_batch_and_more.py`. It adds new tables and a nullable FK; it does not synthesize historical obligations. It has not been applied to an existing local or production database.

After a verified backup and a populated PostgreSQL rehearsal, inspect `python manage.py migrate --plan`, then apply the reviewed migrations with `python manage.py migrate` before starting the new backend and frontend. Earlier pending compatibility migrations are prerequisites; review the whole plan. New credit writes must wait for financial-data reconciliation and the shared RADIUS database/activation integration to be verified.

Rollback application code with the expanded schema retained. Do not reverse migration 0005 after new credit records exist: removing these tables would discard financial evidence. Recover/forward-fix with a reconciled backup or a separately reviewed data plan.

Unverified release prerequisites: production PostgreSQL upgrade/locking, old database identity and allocation/repayment mapping, concurrent repayment versus reversal/physical authentication, physical-router enforcement, real browser accessibility/visual review, and operational backup/restore. Local tests do not establish those guarantees.

## Local verification and release verdict

Release verdict: **NOT READY for production**. This assessment covers the current uncommitted credit workflow in the top-level backend/frontend checkouts, intended for tenant owners and agents on the eventual Ubuntu/PostgreSQL/FreeRADIUS deployment. Financial balances, voucher access and receipt history are sensitive. The recovered legacy checkout and live systems were not changed.

The complete agent backend suite ran against a disposable SQLite database: 54 tests discovered, 50 passed, 4 skipped (database-locking tests). It includes the populated-schema expansion test preserving a signed credit balance, ledger and existing allocations without inventing batch mappings. All 33 tests across the credit component, operator agent pages and agent portal suites passed, including unchanged retry identity and restored requests. Scoped ESLint, TypeScript and the production Vite build passed. The final 17 credit workflow tests passed after API schema annotations; all 9 credit paths were generated and the request/account contracts checked. Migration drift check reported no changes. PostgreSQL results must be recorded separately.

| Gate | Status | Evidence / remaining requirement |
|---|---|---|
| Correctness | PASS | Credit workflow tests cover partial/full repayment, remaining-debt cancellation, immutable price snapshots, configured limits and wallet preservation. |
| Validation | PASS | Typed serializers enforce amount, quantity, date, receipt, UUID and stale-confirmation inputs; service validates available credit and allocation state. |
| Authentication | NOT VERIFIED | Existing authenticated API stack reused; tests force authentication, not live token/session expiry. |
| Authorization | PASS | Owner-only writes, cross-tenant denial, manager denial, own-agent read scoping and denied agent writes tested. |
| Transactions | NOT VERIFIED | Injected issuance/reversal failures roll back local financial/voucher/RADIUS writes; production engine and shared connection still need rehearsal. |
| Concurrency | NOT VERIFIED | Two new concurrent credit tests are prepared but skipped on SQLite; repayment/reversal and physical authentication contention need target-engine tests. |
| Idempotency | PASS | Durable tenant/key and receipt constraints, payload matching, sequential replay and browser saved-request recovery tested. Concurrent behavior remains under the concurrency gate. |
| Database constraints | PASS | Migration applies in isolated tests with protected links, batch arithmetic checks and tenant-wide request/receipt uniqueness. |
| Indexes | NOT VERIFIED | FK and uniqueness indexes present; representative PostgreSQL query plans and large-ledger aggregation not measured. |
| Migration safety | NOT VERIFIED | Populated SQLite preservation passed; PostgreSQL locks, actual production rows and operational timing unverified. |
| Error handling | PASS | Invalid/stale amounts reject, injected failure rolls back, uncertain browser outcomes retain the original request. Missing RADIUS tables fail closed. |
| Logging | NOT VERIFIED | Actor-bound movements and configuration audit events exist; production log access, retention and incident correlation not exercised. |
| Metrics | NOT VERIFIED | Production failure/latency/reconciliation monitoring has not been verified for the new commands. |
| Tests | PASS | Local agent API/service/migration and frontend component regressions passed; live tests explicitly excluded from this local evidence. |
| Performance | NOT VERIFIED | Pagination limits responses, but realistic load, lock waits and ledger sizes remain unmeasured. |
| Accessibility | NOT VERIFIED | Labelled native controls and component interaction tests exist; real-browser keyboard, screen-reader, zoom and responsive checks remain. |
| Backwards compatibility | NOT VERIFIED | New APIs are additive and migration preserves existing rows; recovered legacy financial identity/batch/receipt mappings remain unrehearsed. |
| Documentation | PASS | This document records chosen policy, endpoints, commands, migration sequence, recovery limits and rollback constraints. |
| Deployment safety | NOT VERIFIED | No deployment/restart occurred; immutable release, shared RADIUS enforcement and staging smoke tests remain. |
| Rollback strategy | NOT VERIFIED | Retain expanded schema on code rollback; actual backup restore and reconciliation rehearsal remain. |

Before cutover: reconcile legacy financial exports, rehearse all prerequisite migrations on a populated PostgreSQL copy, run real concurrency/activation checks against the shared RADIUS database, then exercise owner/agent browser workflows and verified backup recovery. Do not drop the new financial tables to roll back after credit transactions have been recorded.
