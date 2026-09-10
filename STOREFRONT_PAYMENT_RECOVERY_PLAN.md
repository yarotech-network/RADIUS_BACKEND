# Storefront payment recovery

Confirmed locally: pending storefront payments have no verification evidence; recent payments 16 and 17 are confirmed successful by the tenant Paystack account, while 15 is abandoned. Voucher generation creates local RADIUS credentials and does not require a router.

Implement anonymous reference-scoped POST /payments/verify/ alongside read-only callback GET. Use saved tenant, amount and reference, not client-supplied purchase fields; validate provider envelope/reference/integer amount/NGN. Throttle public verification, preserve no-store responses and existing unused-code disclosure rules. Reuse atomic fulfillment and its unique delivery job; retain verified evidence if code generation fails. Add payment_verified to distinguish paid-unfulfilled from awaiting payment. Verify on page opening and explicit retry; continue GET polling until code exists. Retain remembered references while fulfillment is incomplete. No physical router configuration or outbound email worker execution.

Validate no-router success, provider failure/mismatch, unknown reference, duplicate fulfillment, used-code nondisclosure and paid-unfulfilled retry; frontend recovery, polling and safe messages. Then reconcile only provider-confirmed local purchases through the tested service. No unverified payment is marked successful.


## User-directed pause

The user switched back to page enhancements before the storefront recovery test-writing command executed. Service/API/frontend edits are saved, but new regression tests and payment reconciliation were not completed. Two recent provider-confirmed payments were inspected read-only and were not fulfilled by this work. Do not treat the storefront recovery feature as validated or released.
