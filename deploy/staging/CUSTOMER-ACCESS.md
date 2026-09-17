# Customer workspace staging rollout

Deploy the backend release before the frontend. Do not edit the live legacy database or FreeRADIUS configuration. No schema changes are required by this release.

## Read-only diagnosis before activation
Run on the VPS using the staging wrapper:

```bash
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-manage shell < /opt/yarotech-radius-staging/current/backend/deploy/staging/diagnose_customer_access.py
systemctl list-timers --all --no-pager '*device*'
```

No accounting rows means investigate the staging RADIUS accounting path first. Rows without MACs cannot become device identities. Accounting with zero device rows indicates a missing/failed sync or unmatched/ambiguous NAS ownership. A successful login alone does not prove accounting delivery. Do not manufacture sessions or customer identities.

## Install worker after promoting backend

```bash
(
set -euo pipefail
cd /opt/yarotech-radius-staging/current/backend/deploy/staging
for unit in yarotech-staging-device-sync.service yarotech-staging-device-sync.timer; do
  test ! -e "/etc/systemd/system/$unit"
done
systemd-analyze verify yarotech-staging-device-sync.service yarotech-staging-device-sync.timer
install -m 0644 yarotech-staging-device-sync.service yarotech-staging-device-sync.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start yarotech-staging-device-sync.service
systemctl enable --now yarotech-staging-device-sync.timer
journalctl -u yarotech-staging-device-sync.service -n 25 --no-pager
systemctl list-timers --all --no-pager yarotech-staging-device-sync.timer
)
```

Promote the frontend only after `/api/v1/customer-access/` works for an authenticated tenant. Confirm a successful purchase appears before login, then one controlled physical-router session produces Start/Interim/Stop accounting and corresponding device, usage and connection changes. Check repeated intervals do not duplicate sessions or bytes. Provider purchase must use test mode.

## Contract
`GET /api/v1/customer-access/` and `GET /api/v1/customer-access/{voucher_id}/` are read-only and tenant scoped. Pagination matches existing APIs. Filters: search, status, activity, source (admin/agent/customer), plan, router, start/end (inclusive local purchase/issue dates). Used is historical and overlaps expired/disabled. No credentials in list responses; detail follows owner/manager visibility. Lists expose synced_at and sync_fresh. Null buyer fields are represented by empty strings for anonymous users.

## Rollback
Restore the previous frontend then backend release; disable the added timer with `systemctl disable --now yarotech-staging-device-sync.timer`. Preserve existing device evidence. No DB rollback is needed. Monitor worker exit status and sync_fresh; never treat old open sessions as proven offline.

## Local validation (2026-09-17)

- PASS: customer access, device history and voucher lifecycle suite: 31 tests, one PostgreSQL-specific test skipped on isolated SQLite. Final customer access rerun: 14 tests passed.
- PASS: 14 focused frontend tests, TypeScript check and production build.
- PASS: existing contacts retained, list credentials masked, staff detail redaction and cross-tenant list/detail rejection tested.
- N/A: schema migration; no models changed.
- NOT VERIFIED: VPS accounting diagnosis, staging timer installation, PostgreSQL behavior/query plans at production volume, browser/physical-router end-to-end acceptance.
- Production readiness: NOT READY until those staging checks pass. Local implementation is ready for staging validation.

Sold is a purchase-history filter: successful same-tenant voucher payments remain included after use, expiry or disabling. Explicit legacy sold records are retained. Pending/failed purchases, free issuance, and activation alone do not establish a sale. The returned status remains the current effective code status.
