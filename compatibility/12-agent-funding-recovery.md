# Agent funding recovery and fees

## Comparison and plan

The recovered application stores requested wallet credit separately from the fee-inclusive provider charge and has an explicit-ID reconciliation command. The new system has duplicate-safe completion and a wallet ledger, but funding status polling only reads local rows; missed webhooks cannot be recovered by agents. Its timeout message incorrectly claims no charge occurred.

Implement shared server verification outside database locks, then locked completion through AgentService. Scope the POST verification action to the authenticated agent before any provider call. Preserve the existing GET polling contract and payment references. Validate reference, currency and strict integer amount before interpreting terminal provider states. Pending, unknown, mismatch and unavailable responses must not credit or erase an earlier success. Reuse the existing locked completion to make webhook/manual recovery converge. Provide a bounded explicit-ID command, read-only by default, and tests using mocked providers only.

User decision: support percentage plus flat funding fees, both defaulting to zero. Preserve existing funding limits (minimum 50,000 kobo and configured maximum), amounts and successful/failed/pending records. Existing pending payments currently rely on the tenant's effective Paystack credentials; key-rotation compatibility requires separate review.

Atomic boundary: provider I/O happens before the local transaction; completion locks payment then wallet and commits payment success, ledger and balance together. A concurrent webhook may finish while verification is in flight; failure-state updates must recheck success under the payment lock. No email, router or provider charge is performed by verification. A lost recovery response can be retried against the same payment reference.

Validation scope: matched and mismatched provider evidence, delayed success, repeated recovery, wrong-agent access, provider outage, terminal-state race with webhook, dry-run command and frontend recovery/cache refresh. PostgreSQL concurrency and live-provider delivery remain separate rehearsal requirements.

## Implemented contracts

- Tenant settings add `agent_funding_fee_percent` (0-100) and `agent_funding_flat_fee` (integer kobo), with zero database/application defaults. Billing settings display the flat fee in naira and convert it to kobo on submission.
- New top-ups save versioned credit/fee/total/currency terms. The percentage fee rounds HALF_UP to whole kobo before adding the flat fee. Amount plus fee is bounded to 2,147,483,647 kobo. Existing new-system payments with NULL terms remain fee-free at their recorded amount, regardless of later configuration. Legacy application payments that included fees must have their original credit/fee/total mapped during import; do not classify them as fee-free NULL-term payments.
- `GET /api/v1/agent/wallet/policy/` exposes minimum, maximum, fee_percent, flat_fee and currency. The funding form shows wallet credit, fee and total separately. `expected_total` is optional for fee-free payments, required when a fee applies, and compared to the calculated total under the settings lock before creating a payment or contacting Paystack. A missing/changed quote returns 400 and the frontend refreshes it. Older clients therefore cannot silently initialize a fee they did not show.
- Funding initialization sends the saved total to Paystack and returns `amount` (wallet credit), `fee`, `total_amount`, reference and checkout URL. Provider-unavailable responses retain reference and totals. Matching webhook and manual verification credit only `amount`, through the same locked payment/wallet/ledger transaction.
- `POST /api/v1/agent/wallet/verify/` accepts only the payment reference as a business input. It looks up the caller's own payment before contacting the provider, uses a 10/minute user throttle, returns the funding representation on success/pending/verified failure, 404 for inaccessible payments, 409 for mismatched evidence, and 503 for provider unavailability. Existing successful payments are no-ops. Verified failure cannot overwrite a concurrent success; later verified success can recover a failed payment.
- GET polling remains read-only. Check now invokes server verification, updates the tracked payment and refreshes wallet/ledger/history queries. The form retains its request key and quoted total after uncertain failures; a known provider reference is saved for status recovery. Definite 400 rejection allows a fresh request. Initializations with an unresolved provider outcome may still need operator reconciliation; no automatic new charge is attempted by verification.

## Operator recovery and deployment

The command accepts at most 20 explicit IDs. Inspect first (no provider calls or credits):

```sh
python manage.py reconcile_agent_wallet_funding --payment-id 123
```

Only after identifying the intended payment, perform verification/recovery:

```sh
python manage.py reconcile_agent_wallet_funding --payment-id 123 --apply
```

Output contains IDs/status/credit amounts, not secrets or provider payloads. Unresolved selected payments cause a nonzero command exit. Repeating recovery does not credit a completed payment again.

Prepared migrations: `tenants/0004_agent_funding_fees.py` and `agents/0004_agent_funding_fees.py`. Both are unapplied to existing databases. Expand schema and deploy the matching frontend/backend and webhook workers before enabling nonzero fees. Older fulfillment code compares provider payment to wallet credit and cannot handle fee-inclusive payments. Do not run mixed old/new payment writers once nonzero fees are enabled. Preserve the schema and saved terms on rollback; reverting these columns after accepting payments would lose their pricing evidence.

No legacy data import, credential rotation, chargeback/reversal accounting, credit allocation or funding-limit policy change is included. Historical provider credentials and provider transaction identities still require review before importing old unsettled payments. Actual PostgreSQL DDL/lock timing, provider integration and production recovery were not exercised here.

## Local validation (2026-09-15)

- Broad agents/payments/subscription-access run: 78 tests, 76 passed and two PostgreSQL-only concurrency tests skipped on disposable SQLite. Final focused funding run: all nine tests passed, including the added fee-inclusive webhook test and conditional quote requirement. The runs overlap (77 distinct backend passes overall).
- Agent and billing-settings frontend suites: 41 passed. After correcting a fixture scope error caught by TypeScript, its focused provider-outage test passed again.
- Scoped ESLint, TypeScript and production Vite build passed. Existing Zod annotation and subscription-page mixed-import warnings remain non-blocking.
- Migration consistency reported no changes detected; working-tree whitespace checks passed. Migrations ran only against disposable test databases, never an existing database.
- NOT VERIFIED: production PostgreSQL schema/locking/recovery rehearsal, live provider verification, historical-payment import and deployment. All provider calls in tests were mocked.

Next module: agent credit allocations and repayment/reversal accounting, preserving existing obligations during migration.
