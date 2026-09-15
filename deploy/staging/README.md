> Domain clarification: the requested deployment is frontend `test.yarotech.com.ng` and backend `shop.yarotech.com.ng`. Read [TEST-SHOP.md](TEST-SHOP.md) first. The combined-domain Nginx/TLS example below is superseded for that topology; the existing shop site must be inspected before any change.

# VPS staging handoff ? operator-run commands

Status: **candidate, not approved for production cutover**. Use the separate staging setup you selected. Nothing here has been executed on your VPS. The current legacy system and its database remain the production authority. The new import engine requires an explicit reviewed mapping; its draft is not a complete migration plan.

Suggested staging hostname: `stage-radius.yarotech.com.ng`. Confirm DNS points to your VPS before the TLS step. Existing `test.yarotech.com.ng`, ports 8000/8001 and the live FreeRADIUS service are outside this package. Staging uses loopback port 8020, database `yarotech_radius_staging`, Redis DB 9, and its own systemd service. Confirm DB 9 and port 8020 are unused before proceeding; use a separately configured Redis instance if DB 9 is occupied. Do not flush a shared Redis server.

## 1. Build the local candidate after checks pass

From the parent workspace in Windows PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Users\dell\OneDrive\Desktop\yarotech-softwares\yarotech-updated-radius' -ErrorAction Stop
Push-Location .\yarotech-radius-frontend -ErrorAction Stop
$env:VITE_API_BASE_URL = '/api/v1'
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
Pop-Location
.\yarotech-radius-backend\venv\Scripts\python.exe .\yarotech-radius-backend\deploy\staging\build_package.py
```

The candidate is written under `staging-artifacts` with its SHA256. It includes current tracked/untracked source and the built frontend, excludes runtime databases/keys/backups, and records per-file hashes and repository revisions. It is not a substitute for a secret scan or clean release commit. Review its manifest before upload; do not upload the legacy source archive with this code artifact. Keep build-time frontend secrets out of all `VITE_*` variables. Transfer the exact archive and `.sha256` to `/home/yarotech/` using SCP from Windows; replace `YOUR_VPS_HOST` and the filename:

```powershell
scp .\staging-artifacts\yarotech-staging-TIMESTAMP.tar.gz .\staging-artifacts\yarotech-staging-TIMESTAMP.tar.gz.sha256 root@YOUR_VPS_HOST:/home/yarotech/
```

## 2. VPS preflight and isolated directories

Run on the VPS as root. Stop on any error and share only redacted output.

```bash
ss -ltnp | grep ':8020 ' || true
systemctl is-active postgresql redis-server
redis-cli -n 9 DBSIZE
cd /home/yarotech
sha256sum -c yarotech-staging-TIMESTAMP.tar.gz.sha256
apt update
apt install -y python3-venv python3-dev build-essential libpq-dev postgresql-client redis-server
groupadd --system --force yarotech-staging
id yarotech-staging || useradd --system --gid yarotech-staging --home /var/lib/yarotech-radius-staging --shell /usr/sbin/nologin yarotech-staging
install -d -m 0755 /opt/yarotech-radius-staging/releases
install -d -m 0750 -o root -g yarotech-staging /etc/yarotech-radius-staging
install -d -m 0750 -o yarotech-staging -g www-data /var/lib/yarotech-radius-staging
install -d -m 0700 -o yarotech-staging -g yarotech-staging /var/lib/yarotech-radius-staging/mail /var/lib/yarotech-radius-staging/backups
```

DBSIZE zero alone does not prove Redis DB9 is unassigned: inspect existing application configuration privately. Never paste passwords, tokens, private keys, provider payloads or raw source exports into chat.

Choose the release directory matching the archive, then extract ONLY the reviewed package into that new directory:

```bash
release_dir=/opt/yarotech-radius-staging/releases/yarotech-staging-TIMESTAMP
mkdir "$release_dir"
tar -xzf /home/yarotech/yarotech-staging-TIMESTAMP.tar.gz -C "$release_dir"
ln -s "$release_dir" /opt/yarotech-radius-staging/current
python3 -m venv /opt/yarotech-radius-staging/venv
/opt/yarotech-radius-staging/venv/bin/pip install -r "$release_dir/backend/requirements-production.txt"
install -m 0640 -o root -g yarotech-staging "$release_dir/backend/deploy/staging/backend.env.example" /etc/yarotech-radius-staging/backend.env
```

The `ln -s` intentionally fails if an existing staging release is present; use a reviewed release-switch procedure instead of overwriting it. Application source is root-owned/readable, while only the staging state directory is writable by the service. Dependency installation is not yet a locked-wheel, reproducible production build; retain `pip freeze`, runtime versions and artifact hash with acceptance evidence.

Create a NEW role/database, never reuse the production role/password:

```bash
sudo -u postgres createuser --pwprompt yarotech_radius_staging
sudo -u postgres createdb --owner=yarotech_radius_staging yarotech_radius_staging
/opt/yarotech-radius-staging/venv/bin/python -c "import secrets; from cryptography.fernet import Fernet; print('SECRET_KEY='+secrets.token_urlsafe(64)); print('FERNET_KEY='+Fernet.generate_key().decode()); print('RADIUS_REST_TOKEN='+secrets.token_urlsafe(48))"
nano /etc/yarotech-radius-staging/backend.env
```

Keep generated values private. Fill all placeholders, matching DB password, and keep payment keys blank, WhatsApp flags false and RADIUS/IoT flags false. Quote values containing spaces or shell metacharacters; the file is sourced by the manage wrapper as well as read by systemd. Preserve the new FERNET_KEY with encrypted backups. The old key is supplied separately and privately only for reviewed field re-encryption.

## 3. Prepare the empty database and service

These commands migrate **only the new staging DB**. They are provided for you to execute; no existing local or VPS database has been migrated by this work.

```bash
install -m 0750 -o root -g yarotech-staging "$release_dir/backend/deploy/staging/manage.sh" /usr/local/bin/yarotech-staging-manage
install -m 0750 -o root -g yarotech-staging "$release_dir/backend/deploy/staging/backup.sh" /usr/local/bin/yarotech-staging-backup
install -m 0750 -o root -g yarotech-staging "$release_dir/backend/deploy/staging/restore.sh" /usr/local/bin/yarotech-staging-restore
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-manage check --deploy
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-manage migrate --plan
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-manage migrate --noinput
install -m 0644 "$release_dir/backend/deploy/staging/yarotech-radius-staging.service" /etc/systemd/system/yarotech-radius-staging.service
systemctl daemon-reload
```

Before generating any vouchers, create the standard unmanaged RADIUS tables in this EMPTY staging database using the installed FreeRADIUS PostgreSQL schema, after privately reviewing its SQL. See [RADIUS acceptance setup](freeradius/README.md). Django migrations alone do not create those tables. Run `sudo -u yarotech-staging /usr/local/bin/yarotech-staging-manage check_radius_schema` after installing the reviewed schema. Do not import old radcheck/radacct into a running consumer.

For synthetic UI tests use `createsuperuser` after migrations. For a full replacement rehearsal use a fresh staging DB with NO users/tenants; do not seed it first. Do not delete a populated staging database to resolve an importer refusal; create a new named staging DB instead.

## 4. Nginx and TLS for staging only

```bash
install -m 0644 "$release_dir/backend/deploy/staging/nginx.conf.template" /etc/nginx/sites-available/yarotech-radius-staging
ln -s /etc/nginx/sites-available/yarotech-radius-staging /etc/nginx/sites-enabled/yarotech-radius-staging
nginx -t
systemctl reload nginx
certbot --nginx -d stage-radius.yarotech.com.ng
nginx -t
systemctl reload nginx
systemctl start yarotech-radius-staging
curl --fail https://stage-radius.yarotech.com.ng/health/live/
curl --fail https://stage-radius.yarotech.com.ng/health/ready/
```

Do not start the backend before HTTPS is ready. Inspect the active staging server block to ensure HTTP redirects to HTTPS, proxy headers are set by Nginx, and `/api/v1/radius/` is blocked externally. API access logs are disabled because payment and reset URLs carry private references. Restrict who can read application error logs. Health endpoints check infrastructure, not complete payment/router behavior. Service is not enabled at boot until acceptance.

## 5. Legacy data rehearsal

Restore a consistent production backup to a separate legacy rehearsal DB ending `_staging`. The imported legacy settings hardcode database name `hotspot` and port `5433`; setting `DB_NAME` alone will NOT switch them. The supplied `legacy_export_settings.py` explicitly overrides that connection and forces read-only transactions. Keep its consumers and outbound network disabled. Use the legacy project's Python environment and `manage.py`, not the new backend's model definitions:

```bash
# Run from the legacy checkout after restoring to a separate database.
# Set these variables privately for a role that can SELECT from the restored tables.
export SOURCE_EXPORT_DB_NAME=yarotech_legacy_staging
export SOURCE_EXPORT_DB_USER=yarotech_legacy_reader
export SOURCE_EXPORT_DB_PORT=5432
read -rs -p 'Restored-source reader password: ' SOURCE_EXPORT_DB_PASSWORD
export SOURCE_EXPORT_DB_PASSWORD
PYTHONPATH="/opt/yarotech-radius-staging/current/backend/deploy/staging:${PYTHONPATH:-}" DJANGO_SETTINGS_MODULE=legacy_export_settings YAROTECH_EXPORT_PATH=/private/source.json ./venv/bin/python manage.py shell -c "exec(open('/opt/yarotech-radius-staging/current/backend/compatibility/export_legacy.py').read())"
unset SOURCE_EXPORT_DB_PASSWORD
```

Copy the private export into a staging-user-readable mode0600 path outside the code release. Retain the exporter SHA256 and table counts. Confirm `excluded_tables` contains no business data. Generate a mapping draft and coverage report:

```bash
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-manage legacy_transfer --source /var/lib/yarotech-radius-staging/source.json --draft /var/lib/yarotech-radius-staging/import-plan.json
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-manage legacy_transfer --source /var/lib/yarotech-radius-staging/source.json --plan /var/lib/yarotech-radius-staging/import-plan.json
```

STOP here until the mapping is completed and reviewed. The draft deliberately contains no guessed business mappings. A complete replacement must resolve old account roles/verification, integer-to-UUID router relationships, preserved rights, wallet and credit ledger semantics, historical settlement fields, payment-to-voucher cardinality, pending WhatsApp work, and raw RADIUS rows. The current engine rejects unsupported/unmanaged targets; it cannot yet transfer the whole legacy database automatically. See [remaining evidence and mapping gaps](../../compatibility/20-system-staging-plan.md).

After a complete reviewed plan exists, `--rehearse` performs all target writes inside a rolled-back transaction. It must report zero unmapped records and exact financial reconciliation. Only then use `--apply --reviewed-plan-sha256 HASH` with the hash reported by coverage, against the same empty staging DB. Supply `--source-key-file PRIVATE_PATH` when the plan contains explicit re-encryption transformations. No provider calls, queue replay, trial extension or password reset belongs in an import.

## 6. Staging acceptance and rollback

Keep all imported work paused. The initial systemd service restricts network access to loopback to prevent imported router addresses from reaching live equipment. Verify that the VPS kernel/systemd actually enforce these rules before importing records (`systemctl show yarotech-radius-staging -p IPAddressDeny -p IPAddressAllow`, inspect the journal, and perform an expected-denied egress test from the service context). For provider or physical-router tests, add only explicitly reviewed destination IPs using a staging service drop-in and restart this staging service; retain `IPAddressDeny=any`. DNS hostnames cannot be used as IPAddressAllow values. Reconfirm current provider addresses and isolate test router records before allowing egress. No allowlist is prefilled because those destinations have not been verified here. Staging rejects non-test Paystack keys and refuses WhatsApp sends outside its explicit test-recipient allowlist; email writes to protected local files. Use fresh synthetic test orders and your provider's test credentials. Review every worker command with `--help` and its pending rows before running it. Do not enable blanket maintenance/payment/message/router timers over an imported snapshot.

Record PASS/FAIL/NOT VERIFIED with date, release hash and sanitized evidence for:

- Owner/staff/agent/platform login and tenant isolation; expiry routes to payment and hides storefront plans while existing valid vouchers still authenticate.
- Voucher/agent wallet/credit sales, configured commissions/fees/limits, repayment and cancellation totals, reports and recovery; unauthorized and cross-tenant requests must fail.
- Public voucher and IoT checkout, provider test webhook signature, amount/currency checks, duplicate callback, timeout recovery, one fulfilled grant, no double charge; IoT renewal retains unused time and suspension.
- WhatsApp test sender purchase, separate purchase contact, duplicate inbound event, uncertain send recovery, retry limits, reminders, opt-out and expired-tenant sales gate.
- Physical router PAP/CHAP, voucher first use/expiry, MAC identity, accounting, rate/cap/device limits, tenant ownership, disconnect and reconnect; use the separate RADIUS candidate.
- API/DB/Redis/provider outages, process restart, worker backlog recovery, database locking and simultaneous requests, expected concurrent-user load with measured latency/error targets.
- Backup AND isolated restore: verify hash and `pg_restore --list`, create a second empty restore DB ending `_staging`, restore with `--no-owner --no-privileges --exit-on-error`, then compare row counts, financial totals and key-decryption checks. Never restore over the source or active staging DB. Archive readability alone is not restore proof.

```bash
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-backup
sudo -u postgres createdb --owner=yarotech_radius_staging yarotech_restore_REHEARSAL_staging
sudo -u yarotech-staging /usr/local/bin/yarotech-staging-restore /var/lib/yarotech-radius-staging/backups/TIMESTAMP.dump yarotech_restore_REHEARSAL_staging
systemctl status yarotech-radius-staging --no-pager
journalctl -u yarotech-radius-staging -n 100 --no-pager
```

For a failed staging candidate, stop only `yarotech-radius-staging` and its explicitly added staging workers, retain the database/evidence, and restore the prior compatible staging code/config/backup into a separate staging DB as needed. Do not reverse schema migrations blindly. The old production service remains available throughout this rehearsal. Final cutover needs a write freeze, last consistent snapshot, complete import/reconciliation, provider callback and NAS endpoint switch, smoke tests and an agreed rollback boundary for newly accepted payments. None of those production steps is authorized or performed by this package.
