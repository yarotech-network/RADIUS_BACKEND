# Paystack explicit return URLs

Scope: issue 1 only. Current shared initialization omits callback_url and relies on the Paystack dashboard. Three frontend routes already exist and returned HTTP 200 locally.

Implementation: PAYSTACK_CALLBACK_ORIGIN supplies a trusted origin; derive fixed paths for vouchers, subscriptions and wallet funding. Require an absolute HTTP/HTTPS origin without credentials, path, query or fragment; require explicit HTTPS configuration in production. Pass callback_url through the existing Paystack client. Preserve API responses, server price selection, tenant/platform Paystack credentials, idempotency and webhook fulfilment. No migrations or changes to payment settlement.

Tests: exact destinations in each initialization flow, outgoing provider JSON, invalid origins and production HTTPS validation. Existing payment, subscription and agent regression tests. Live Paystack payment not run. Update environment examples and operational documentation.

Validation: 36 targeted backend tests passed, including outbound callback URLs for all three checkout flows, browser-supplied URL rejection, origin validation and existing webhook/payment behavior. Local HTTP probes returned 200 for all three frontend return paths. Real Paystack redirect verification remains pending.


Follow-up (7 September 2026): business subscription missing-webhook recovery is implemented via an authenticated POST verify endpoint and tenant tracker verification. A previously pending local test payment was confirmed directly with Paystack and activated through the idempotent service. See BUSINESS_PLAN_LIMITS_PLAN.md for validation. This does not claim a browser redirect smoke test or implement recovery for the other payment flows.
