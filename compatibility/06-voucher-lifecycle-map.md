# Voucher lifecycle and customer access compatibility

Date: 2026-09-14. Source comparison only: recovered `yarotech-radius-system-current`, top-level `yarotech-radius-backend` and matching React frontend. No schema changes, database writes, deployment, payment calls or router actions in this pass. The imported source does not prove which RADIUS configuration currently runs on the VPS.

## Accepted policy

Operator expiry blocks application operations and new storefront/agent sales. Existing issued vouchers remain valid under their own original terms and deadlines. Renewal restores the public catalogue. Operator expiry must not delete voucher credentials, restart voucher time, or disconnect paid customers. Existing tenant suspension and voucher disable rules are separate from subscription expiry.

## Verdict and ownership

Keep one Django application with explicit voucher, payment, customer and RADIUS responsibilities. Preserve issued identities and deadlines before expanding generation options. Highest deployment risk: the new source does not yet demonstrate the old verified first-authentication activation contract.

| Boundary | Authority and writers | Readers / dependencies |
| --- | --- | --- |
| Voucher issuance | Voucher service creates identity, purchased terms and credentials atomically | Admin/agent issuance, verified payment fulfillment, printing |
| Customer order | Payment service reserves price/device terms; verified settlement fulfills once | Storefront and provider callback/recovery |
| First use and deadline | Trusted successful authentication must finalize once against a locked voucher | RADIUS, customer access, dashboard history |
| Device binding | Authentication establishes binding; authorized reset records actor/reason | Router authorization and customer support |
| Historical transfer | Dedicated importer preserves source facts and provenance | Application and RADIUS after cutover |

## Evidence and gaps

| Priority | Area | Existing portal evidence | New system evidence | Required compatibility action |
| --- | --- | --- | --- | --- |
| Critical | First-use activation | `vouchers/expiry_contract.py:finalize_authenticated_voucher` requires a trusted verified-credential assertion and NAS address, locks the voucher, respects stricter stored Expiration and calls PostgreSQL `expiry_finalize` | `apps/vouchers/services.py:activate_voucher` checks an in-memory unused status; `Voucher.activate` calculates a fresh deadline. Source search found a test caller but no production caller | Trace deployed FreeRADIUS configuration; implement and test a trusted activation boundary with fresh row locking, NAS scope, one-time deadline and remaining timeout. Never activate from a catalogue view, payment or accounting observation |
| High | Historical states | `vouchers/models.py:Voucher` has unused, sold, active, used, expired, disabled plus first/last-use and accounting identifiers | Target has unused, active, expired, disabled and activation/expiry timestamps | Preserve sale and consumption evidence separately; never map sold or used blindly to unused. Quarantine consumed records with unknown deadline for review |
| High | Device lock | Legacy voucher has lock flag, MAC/NAS binding, reset count/actor and `VoucherDeviceBindingAudit` | Target Voucher contains device_limit but no equivalent binding/reset provenance | Preserve source bindings and audits; distinguish simultaneous capacity from a device lock. Do not silently unlock imported vouchers |
| High | Credential identity | Legacy username/password support 64 characters; collision lookup checks archived vouchers, RADIUS and MAC identities case-insensitively | Target supports 50 characters and generation checks exact current voucher usernames | Inventory lengths and collisions before import; widen capacity before transfer if required. Preserve credentials byte-for-byte; no normalization or regeneration of issued codes |
| High | Public device pricing | Legacy `reserve` flow in `vouchers/services.py` freezes device_limit and multiplies base amount by device count | Target payment serializer has no device selection; checkout uses one plan price; service supports 1-10 devices | Add device selection through frontend, serializer, immutable order terms, amount verification and fulfillment together; never infer historic paid quantity from current plan price |
| Medium | New code formats | Legacy `generate_voucher_code` supports numeric, alphabetic and alphanumeric with tenant/plan defaults and bounded attempts | Target fixed eight-character alphabet; frontend generation offers plan/quantity/prefix | Preserve old format configuration and add matching controls. Keep secure random generation and bounded collision retries across identity namespaces |
| High | Deletion/history | Legacy retains soft-deletion actor/reason/type and uses an active-record manager | Target has no matching deleted/provenance fields | Map historical tombstones explicitly; retain identity reservations and financial/access evidence. Do not resurrect deleted credentials |
| Medium | Batch device capacity | Shared target generator and manual serializer accept 1-10 devices | Target `VoucherGenerateSerializer` and React batch form omit device_limit | Expose capacity consistently and enforce bounds at every issuance path |

Source anchors: legacy `vouchers/models.py:2038`, `vouchers/services.py:503`, `vouchers/services.py:909`, `vouchers/services.py:1053`; target `apps/vouchers/models.py:97`, `apps/vouchers/services.py:34`, `apps/vouchers/serializers.py:VoucherGenerateSerializer`, `apps/payments/serializers.py:InitializePaymentSerializer`; frontend `src/features/vouchers/pages/GenerateVouchersPage.tsx`, `src/features/storefront/pages/CheckoutPage.tsx`. Line positions may move with later edits.

## Transactions, failures and scale

| Scenario | Containment / recovery | Responsible module |
| --- | --- | --- |
| Duplicate first authentication | Lock current voucher; preserve first activation and absolute deadline; subsequent accepts return remaining time | Voucher/RADIUS |
| Forged or wrong-tenant NAS request | Deny before state changes; authenticate service caller and validate NAS ownership | Router/RADIUS |
| RADIUS credential write failure during issuance | Roll back voucher and local credentials together; external delivery only after commit | Voucher/payment |
| Payment replay or edited plan | Fulfill once from saved order terms; do not charge again or recalculate bought rights | Payment |
| Unknown historical deadline or ambiguous identity | Read-only preflight report with record IDs; quarantine instead of guessing | Importer |
| Operator expires during customer use | New sale denied; existing voucher deadline and credentials unaffected | Subscription/voucher |
| Timer delay | Authentication must enforce deadline independently of cleanup timer | RADIUS/voucher |

Use per-voucher locks rather than global issuance locks for activation. Bound identity retries and maintenance batches; measure query plans and accounting volume on the restored PostgreSQL database before claiming capacity. Throughput, RTO and RPO remain unmeasured.

## Implementation order and acceptance checks

1. Preserve historical state, identity lengths, device bindings and deletion/audit provenance with additive migrations prepared for user execution. Build a read-only preflight inventory first; do not import into the old live schema.
2. Establish the trusted first-authentication contract and deployed RADIUS integration. PostgreSQL tests must cover simultaneous first logins, forged requests, wrong NAS, disabled/deleted vouchers, stricter historical Expiration and repeated authentication without extension.
3. Add code-format and batch device controls while keeping all existing issued credentials unchanged. Test case-insensitive cross-namespace collisions and bounded retries.
4. Add public device pricing end to end with immutable terms, mismatch rejection, replay-safe fulfillment and expiry-gated checkout.
5. Add authorized device-binding recovery with audit history; test cross-tenant denial and retention of paid time.
6. Rehearse import and router authentication on an isolated PostgreSQL/RADIUS environment. Verify sold-but-unused, active, consumed, expired, disabled, deleted and ambiguous source records. Restore/rollback retains the old application and database; no mixed old/new writers during final cutover.

Local unit tests alone cannot establish FreeRADIUS enforcement. No runtime change or new test execution was needed for this mapping pass. Historical subscription provenance/import remains an outstanding task from module 4 and must join the final migration rehearsal.
