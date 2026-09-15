# Code format settings and bounded generation

Implement plan/business format settings and saved order format/prefix. Preserve existing plans with explicit legacy readable format, and use legacy generation for old orders without format snapshots. Plan choice tenant_default resolves when terms are reserved. Add numeric/alphabetic/alphanumeric generators with cryptographic randomness, legacy/numeric eight-character bodies and alphabetic/alphanumeric six-character bodies matching legacy defaults, alphanumeric prefix up to 10 (existing readable format also retains API-supported hyphens/underscores), total <=32, mixed format guaranteed to contain both classes. No rewriting issued credentials. Add case-insensitive voucher uniqueness with a read-only duplicate preflight; migration must stop for conflicting historical identities rather than normalize them. Check existing RADIUS, PPPoE and MAC identities during generation. Bound candidate retries to 100; savepoint handles insert races, outer transaction preserves complete batch atomicity. Existing external writers to other identity namespaces still require cutover coordination. Prepare migrations only. Implement React plan and business settings; test old/new order snapshots, format choice, collisions, rollback and permission/schema contracts. Device pricing and agent commission remain subsequent work.


## Implemented settings and compatibility

Business settings expose `default_voucher_code_format`. Plans expose `voucher_code_format`, including `tenant_default`. Existing plan/business rows default to `legacy`; they do not silently inherit a changed policy. The React settings and plan forms expose the choices. Numeric bodies have 8 digits; alphabetic and mixed bodies have 6 characters, matching the recovered portal defaults; the existing readable mixed body remains 8 characters. New explicit formats uppercase prefixes; issued strings are never changed. Existing readable-format API prefixes may retain hyphens/underscores, which remain a known mismatch with the inspected legacy RADIUS alphanumeric gate; physical-router/RADIUS verification stays pending.

New order snapshots store the resolved format and prefix. Changing plan or business settings afterwards does not change fulfillment. Old paid snapshots without either key use the previous readable generator and prior empty-prefix behavior. Historical voucher term reconstruction does not invent a code-format snapshot from today's plan. Format choices describe the random body after the prefix.

Voucher name uniqueness is enforced case-insensitively after migration, including retained deleted records. Generation checks current RADIUS check/reply records, PPPoE names and compact MAC identities, bounds attempts to 100 per voucher, and retries voucher insert collisions inside a savepoint. If generation fails, the outer transaction rolls back the whole batch and credentials. The voucher constraint does not provide a cross-table uniqueness guarantee against concurrent independent MAC/PPPoE writers; coordinate these at cutover and retain the namespace audit requirement.

## Prepared migrations and operator commands

Prepared, not applied to an existing database:
- `tenants/0003_voucher_code_formats.py`
- `vouchers/0007_voucher_code_formats.py` (depends on tenant settings migration and voucher preservation migration).

Run the read-only conflict check before migration; it uses only pre-existing username/id columns:

```text
python manage.py audit_voucher_code_identities
python manage.py migrate --plan
```

The voucher migration independently repeats the conflict check and stops rather than renaming codes. Review conflicts and rehearse on an isolated restored PostgreSQL database before the user runs `python manage.py migrate`. Unique-index creation requires a planned write window; no online/index-lock timing claim is made. Do not run old and new fulfillment workers together after accepting format-specific orders. Reversing schema changes after new orders exist requires a compatible application rollback and reconciliation, not dropping snapshots.

The source importer, device pricing, agent commission changes and physical-router verification are not included in this step. No provider calls, emails or router changes were made.

## Local validation

70 distinct backend tests passed across voucher/purchased-term/subscription regressions plus a separate migration conflict rehearsal; one PostgreSQL activation-concurrency test was skipped on SQLite. The final code-format tests were rerun after the indexed case-insensitive lookup change. All 27 affected frontend tests passed on the final run; an earlier profile-loading timeout passed on rerun without application changes. Typecheck, scoped ESLint, production build and migration consistency checks passed. Only disposable test databases were migrated. No existing database, payment provider or physical router was changed.
