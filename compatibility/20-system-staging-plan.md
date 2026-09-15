# Coordinated replacement and VPS staging work

User authorization: implement remaining work together and prepare commands for the user to run on an isolated VPS staging setup. Do not deploy, run migrations against existing databases, contact live payment/message providers, or alter the physical router in this local execution.

Reference: ../yarotech-radius-system-current. Preserve existing rights, finance and contacts; keep unused IoT renewal time; block new sales after operator expiry but allow previously purchased voucher use.

## Inspected gaps and impact plan

1. Public IoT purchases: existing PaymentTransaction/recovery/webhook flow issues vouchers only. Add a protected IoT purchase extension, frozen terms/provider account and device identity, authenticated renewal capability, single fulfilment ledger, safe public result, plan catalogue and checkout controls. Scope prices/duration/router on the server; retain paid-unfulfilled evidence and retry the original payment. Do not infer device ownership from a typed MAC.
2. RADIUS: existing voucher lifecycle has no HTTP adapter; PPPoE has a private REST boundary; IoT is registry-only. Add fail-closed private REST adapters, NAS/tenant/MAC validation, immutable caps/timeouts and trusted post-auth voucher activation. Supply separate FreeRADIUS staging configuration without replacing the active server. Reconcile actual accounting columns before target activation; no assumptions about the legacy DB schema.
3. Migration: current folders contain mappings and read-only inventory, not a complete importer. Prepare a versioned archive/mapping/import workflow with read-only source export, protected identity mapping, exact financial conversion, dry-run coverage/orphan/conflict reports, and atomic target-only writes. Unsupported source records must block full-replacement approval, never disappear. No provider calls or queue replay during transfer.
4. Compatibility sweep: inspect report/recovery and permissions across source/new modules; resolve concrete defects and record unresolved mappings explicitly.
5. VPS staging: isolated application/database/Redis namespace/services/hostname; environment templates, migration preflight, worker gates, health/backup/restore and end-to-end acceptance commands. User runs commands; no automatic production service edits. Local PostgreSQL service detected; only disposable test databases may be created for validation.

Tests: public IoT amount/snapshot/replay/ownership/tenant cases; RADIUS fail-closed auth/expiry/cap/NAS tests; populated mapping and ledger reconciliation; isolated PostgreSQL competing-writer tests; frontend checkout/result and existing voucher regressions; full applicable local tests/lint/build. Real provider/webhook/router/Nginx/restore/load tests are operator-run acceptance gates and cannot be marked passed from local tests.

Implementation order: payment/device representation and services -> RADIUS boundary -> public UI -> migration tooling -> staging scripts -> integrated validation and explicit remaining gates. No fixed completion claim until evidence is collected.


## Implementation status

Implemented public IoT checkout and signed renewal ownership, frozen provider/plan terms, one payment/grant identity, PostgreSQL competing-writer checks, private HotSpot/MAC RADIUS adapters, standard accounting-column model state, purchase-aware recovery/customer/dashboard reporting, staging provider isolation, candidate FreeRADIUS configuration, package builder, backup/schema checks, read-only restored-source export, and atomic explicit-plan import/rehearsal. Fixed PostgreSQL nullable-join row-lock errors in WhatsApp order, outbound and recovery paths; repaired migration-test cleanup to restore current schema and updated unrelated fixtures for paid subscription access.

The importer is a **reviewed-plan engine, not a completed whole-database translator**. It rejects unknown/missing mappings and unsupported raw SQL targets. It retains each source record encrypted with source/target identities and exact declared totals, but aggregate totals alone are not proof of per-agent balances, permissions or operational equivalence. A full replacement remains blocked on actual restored-source mapping and reconciliation.

Specific mappings still to finish with the restored snapshot: historical payment settlement fields and voucher cardinality; wallet adjustment/reversal categories and running balances; credit allocations/repayments/cancellations and configured limits; source permissions and account verification; source encryption-key ownership; immutable issued voucher/IoT rights; legacy pending WhatsApp jobs and deduplication; raw RADIUS rows and complete tenant/NAS identity mapping. Do not replace these with synthetic default values or archive operational money records as evidence-only.

The staging hostname in the runbook is a suggestion requiring DNS setup, not an observed deployment. The actual physical router has not been connected to this candidate. FreeRADIUS parser/configuration, real authentication/accounting, provider callbacks, backup restore, load and monitoring remain operator-run acceptance work.
