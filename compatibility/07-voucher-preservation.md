# Voucher preservation and activation foundation

Implement additive credential capacity (64), sold/used states, first-use/consumption, deletion and device-binding evidence. Retain legacy provenance in an internal JSON field, excluded from public serializers. No import or data normalization. Preserve existing stored deadlines and fail closed on consumed vouchers without one. Activation is a trusted in-process service requiring verified credentials and unambiguous active tenant NAS; no request may supply a trusted boolean. Production RADIUS adapter/deployment remains a separate verification gate. Lock the current voucher, never trust stale model state, and never extend an existing deadline. Preserve stricter stored Expiration and do not consult operator subscription state. Device-bound legacy records must not silently become unbound. Surface sold/used states in React. Add read-only preflight reporting IDs only. Generate migrations without applying to any existing database. Validate isolated lifecycle tests and affected voucher/payment/frontend tests; PostgreSQL concurrency and physical router validation are not local SQLite proof.

## Implemented contract

- `0006_voucher_lifecycle_preservation` adds nullable/internal preservation fields, widens credentials to 64 characters, and retains sold/used status values. Existing credentials and deadlines are not transformed. Legacy generated-by, customer source IDs, accounting identifiers, deletion actor/reason and device-reset audit evidence must be carried by the future importer into `legacy_provenance`; preserve raw source IDs there and map bound NAS into the target FK. This is storage preparation, not a completed data transfer.
- `finalize_authenticated_voucher` requires a trusted server assertion plus a unique active NAS owned by the tenant. It locks the current voucher, refuses disabled/deleted/expired or ambiguous consumed-without-deadline records, preserves stored deadlines and stricter historical RADIUS Expiration, and returns remaining timeout. Replayed authentication cannot extend time. It requires the original bound MAC for locked vouchers and establishes the first binding atomically.
- `Voucher.activate` and `VoucherService.activate_voucher` now deny calls without trusted verification/NAS context. They are internal functions, not public HTTP endpoints. No API accepts `credential_verified`. The deployed FreeRADIUS integration must call the trusted service through a separately authenticated adapter and apply its timeout/rejection before this is production complete. No adapter or VPS config is changed here.
- Operator subscription state is deliberately absent from customer activation. Tenant suspension is still enforced.
- Internal history/binding fields are not exposed or writable by voucher serializers. The public `can_edit` result lets React hide edits for retained historical records. Deleted records are excluded from the operational voucher API while their identity remains reserved in the table. Existing hard deletion of pristine, nonhistorical unused records retains its prior behaviour.
- `python manage.py audit_voucher_compatibility` reads the selected target database and emits counts plus at most 100 record-ID samples. It never outputs usernames/passwords or mutates data. It detects consumed records without deadlines, unknown states, incomplete bindings, invalid device capacity and import review flags. It is not a substitute for the source identity/collision inventory.

## Migration and activation sequence

Migrations are prepared only. Inspect and rehearse on a separate restored NEW-system PostgreSQL database, never on the old portal schema:

```text
python manage.py migrate --plan
python manage.py sqlmigrate vouchers 0006
python manage.py migrate
python manage.py audit_voucher_compatibility
```

These commands are for the user's isolated rehearsal and later approved cutover; they were not run against any existing database here. Deploy matching frontend/backend and stop old writers before cutover. Do not reverse this migration after preserved data has been loaded: reversing would drop history and narrow credentials. Rollback uses the retained pre-cutover database and application, with a separate write freeze/reconciliation plan.

Remaining deployment gates: source data inventory and importer, PostgreSQL concurrent-first-authentication test, authenticated RADIUS adapter and real router enforcement, preservation of source accounting evidence during import, and backup/restore rehearsal. Code-format and public device pricing changes are subsequent steps and are not included here.

## Local validation

2026-09-14: 62 backend tests discovered across vouchers, purchased payment terms and subscription access; 61 passed and the PostgreSQL-only simultaneous-activation test was skipped on SQLite. All 20 focused frontend voucher tests passed. TypeScript checking, scoped ESLint and production build passed. Migration consistency check reported no missing migrations. Tests used disposable databases only; migration 0006 was not applied to an existing database. Generated build reported existing dependency annotation and subscription-page chunking warnings, with successful completion. Production RADIUS and PostgreSQL concurrency remain NOT VERIFIED.
