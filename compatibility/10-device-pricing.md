# Device selection and reserved pricing

Scope: new storefront purchases and admin batch selection. Expose a server-authoritative max_devices capability; the legacy MULTI_DEVICE_VOUCHERS_ENABLED configuration switch defaults off for these newly exposed channels. Existing manual voucher capacity and already-purchased rights are preserved; agent pricing is unchanged until its commission module is reconciled. Count is devices per voucher, separate from batch quantity. New version-3 terms save base price, device count and total in integer kobo; price retains total meaning for payment verification. Existing version-2 terms and historical reconstruction keep prior semantics. Calculate and bound totals server-side, reserve under the plan lock, pass the same total to the provider and response, fulfill only coherent saved terms, and preserve capacity across later plan edits or feature disablement. React displays selected count/total and stores authoritative reserved totals, using a fresh idempotency key when request payload changes. Validate mismatch, retries, overflow, disabled policy and saved capacity/RADIUS attributes. No existing database migration or provider/router operation is authorized by this local implementation.


## Implemented contract

- Public and authenticated plan responses add `max_devices`. New storefront/batch inputs accept optional `device_limit`, default 1. New public/batch values greater than one require `MULTI_DEVICE_VOUCHERS_ENABLED=True`; the configuration defaults to False and the actual local .env was not changed. The pre-existing manual-voucher capacity path remains 1-10. Agent sales continue to use one device pending the commission review.
- New version-3 issuance snapshots contain integer `base_price`, `device_limit`, `total_price`, `price` (the same total), and NGN currency. Time and data allowance remain those of one voucher; device count controls simultaneous capacity and multiplies the retail price. Generation quantity is a separate multiplier used only for batch face value. Existing saved version-2 orders and reconstructed historical terms retain their old price semantics.
- Checkout reserves the total under the plan lock, bounds it to the supported positive-integer database range, and passes that exact total to the provider. Successful initialization returns amount/device_limit/base_amount. Provider-failure responses retain the reserved amount and reference for reconciliation.
- Fulfillment verifies provider amount/reference/currency and version-3 arithmetic, then writes the saved device count as Simultaneous-Use. Plan edits, operator expiry or switching off new multi-device sales cannot reduce already-purchased capacity. Corrupt snapshots remain recoverable paid evidence without partial voucher issuance.
- React displays count and total before submission, stores the server-returned amount and device count in checkout context, and shows device count with the delivered access code. Batches display per-voucher and total face value. Payload changes get a fresh idempotency key; identical retries retain the key unless the existing provider-failure flow starts a new attempt. Server replay/fingerprint checks remain authoritative.

## Deployment and rollout

No new schema migration is required by this step. Previous prepared migrations must be applied by the user in an isolated rehearsal before deploying the accumulated changes. Deploy matching frontend/backend; do not mix older fulfillment writers with newly reserved version-3 orders. Leave the new-sales feature switch off until the physical router / RADIUS simultaneous-device checks pass. Enabling it allows up to 10 devices for new storefront orders and batches; it does not change agent commission rules. No configuration was changed on the physical router or VPS, no live provider requests were made, and no existing database was migrated.

The actual router test, PostgreSQL locking/replay rehearsal and production feature-switch value remain unverified. Local tests verify persisted RADIUS attributes, not packet-level enforcement.

## Local validation (2026-09-14)

- The device-pricing, purchased-terms, vouchers and subscription-access suite passed 78 tests; one PostgreSQL-only concurrency test was skipped on disposable SQLite.
- The full payments and selected agent service/API suite passed 46 tests. These suites overlap; their counts are not additive.
- All 31 targeted storefront and voucher frontend tests passed after the final retry-state adjustment. Scoped ESLint passed.
- The final TypeScript check and Vite production build passed. Existing Zod annotation and subscription-page mixed-import warnings remain non-blocking.
- Django migration consistency reported no changes detected. No migration was applied to an existing database.

Coverage includes server-calculated totals, device limits and disabled policy, amount overflow, idempotent replay and changed-payload rejection, mismatched payment evidence, corrupt snapshots, preserved older paid terms, batch capacity, frontend selection and authoritative receipt totals.
