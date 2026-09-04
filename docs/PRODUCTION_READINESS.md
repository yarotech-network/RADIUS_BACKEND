# Production readiness and release runbook

This document defines the minimum release gates for the Yarotech Radius backend.
Passing local tests is necessary but does not by itself authorize a production release.

## Required configuration

Run production with `DJANGO_SETTINGS_MODULE=config.production_settings`. Copy the
variable names from `.env.example` into the deployment secret/configuration store;
do not deploy the example values or commit real secrets.

Production settings fail at startup when `SECRET_KEY` is missing/short or when
`ALLOWED_HOSTS` is empty or contains `*`. Set `TRUST_X_FORWARDED_PROTO=True` only
when a trusted reverse proxy removes client-supplied `X-Forwarded-Proto` and sets
the header itself.

Start HSTS with the supplied short duration only after HTTPS and redirects have
been verified. Increase it deliberately; enable subdomains and preload only when
every affected hostname is permanently HTTPS-ready.

## Pre-deployment gates

Use an isolated PostgreSQL database for the test suite. From the exact source
revision that will be deployed, run:

```powershell
python -m pip install -r requirements.txt
python -m pip check
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --file schema.yml
python -m pytest
python manage.py check --deploy --settings=config.production_settings
```

The final command requires real-shaped production configuration, but it must be
pointed at a non-production database during validation. Every error must be fixed.
If the only warnings are HSTS subdomain/preload warnings, retain them until the
domain owner confirms that every affected hostname is permanently HTTPS-only;
record that decision with the release. Keep all command output with the release record.

Before changing production data, take and verify a restorable PostgreSQL backup.
Review every new migration for table locks, long backfills, irreversible operations,
and compatibility with both the previous and new application versions. Then apply:

```powershell
python manage.py migrate --plan --settings=config.production_settings
python manage.py migrate --noinput --settings=config.production_settings
```

Do not run migration validation casually against production. Only the authorized
release operator should execute the second command against the named target.

## Deployment and health

Build one immutable artifact from the tested revision and record its source commit
and digest. Promote that same artifact; do not rebuild independently per environment.
Prevent two deployments from targeting the same environment concurrently.

- `GET /health/live/` checks only process and routing health. Use it for liveness.
- `GET /health/ready/` runs a minimal database query. Use it to admit traffic.

Both endpoints return a small response without configuration, credentials, exception
messages, or tenant data. Readiness returns HTTP 503 when PostgreSQL is unavailable.

## Router and WireGuard preparation

Provisioning uses the operating system OpenSSH client with strict host-key checking.
Before enabling it, install the VPS host key in the service account's dedicated
`WG_SSH_KNOWN_HOSTS` file, restrict the SSH private key permissions, and grant the
remote account only the `wg` and `wg-quick save` privileges required for the named
`WG_INTERFACE`. Limit `ROUTER_PROVISIONING_AGENT_ALLOWED_NETWORKS` to the actual
agent addresses; the endpoint deliberately ignores forwarded client-IP headers.

Generate `FERNET_KEY` exactly once, store it in the deployment secret manager, back
it up through the organization's secret recovery process, and keep it stable across
all instances and restarts. After applying router migrations, inspect and encrypt
legacy plaintext credentials:

```powershell
python manage.py encrypt_router_secrets --settings=config.production_settings
python manage.py encrypt_router_secrets --apply --settings=config.production_settings
```

The first command is a dry run. Take a database backup and verify the reported scope
before running `--apply`. Losing or rotating the Fernet key without a planned
decrypt-and-reencrypt procedure makes stored router credentials unusable.

## RADIUS accounting and disconnects

Django treats `radacct` as an externally managed FreeRADIUS table. The live-user
API scopes sessions through both router management and WireGuard addresses. A
disconnect request is considered delivered only after an authenticated
Disconnect-ACK; the row remains active until FreeRADIUS receives and persists the
corresponding Accounting-Stop packet.

The inspected local `radacct` table has only its primary-key constraint and does
not contain a standard unique accounting identifier, calling-station ID, or framed
client IP. Before production, install or review the FreeRADIUS PostgreSQL accounting
schema and SQL queries so duplicate Start and Interim packets are idempotent,
Interim-Update is enabled, and session identity is unique across routers. Re-audit
the deployed table and run Start, Interim-Update, Stop, Disconnect-ACK,
Disconnect-NAK, timeout, and duplicate-packet staging tests. Django must not own or
silently migrate that external schema.

After deployment, repeat both health checks and smoke-test login, tenant isolation,
one safe voucher journey, and webhook signature rejection. Use isolated test data;
never trigger a real charge or uncontrolled customer message.

## Observation and recovery

Before rollout, identify the previous known-good artifact and define who can stop or
roll back the release. Observe request error rate and latency, process restarts,
database errors/locks/connections, failed payment callbacks, and voucher fulfillment
through a defined window. A release is not proven healthy merely because no alert fired.

Prefer rolling back application code only while the migrated schema remains compatible.
Do not automatically reverse an irreversible migration. If external effects already
occurred, use idempotent replay/reconciliation or a controlled forward repair.

## Known release blockers

These items remain NOT VERIFIED or incomplete and block an unconditional
production-ready declaration:

- WireGuard provisioning has a strict SSH implementation, but VPS host-key setup,
  privilege policy, persistence, and router connectivity have no live staging proof.
- The RADIUS authentication probe is implemented, but needs a live FreeRADIUS
  Access-Accept/Access-Reject staging test using an isolated probe credential.
- The local FreeRADIUS accounting schema lacks verified duplicate-packet protection;
  Accounting-Start/Interim/Stop and live disconnect behavior remain staging checks.
- Password reset requires a configured SMTP provider and a real inbox delivery test.
- Subscription checkout/renewal is implemented, but production expiry scheduling
  and a live Paystack subscription payment have not been verified in staging.
- Live Paystack and WhatsApp provider journeys have not been exercised in staging.
- No repository CI workflow, immutable artifact definition, security scan, metrics,
  alert thresholds, deployment lock, or tested rollback automation is present.
- PostgreSQL backup restoration and a production-like migration rehearsal are unverified.

Assign an owner and due date to every blocker before release approval.
