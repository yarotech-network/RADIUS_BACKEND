# Yarotech RADIUS Backend

Production-oriented, multi-tenant hotspot and ISP management API built with Django REST Framework. The backend manages tenants, users, internet plans, vouchers, router onboarding, RADIUS sessions, agents, Paystack payments, subscriptions, WhatsApp routing, and registered client devices.

The API is designed for a separate web or mobile frontend and exposes versioned endpoints under `/api/v1/`.

## Contents

- [Core capabilities](#core-capabilities)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Requirements](#requirements)
- [Local development on Windows](#local-development-on-windows)
- [Environment configuration](#environment-configuration)
- [Running the application](#running-the-application)
- [Authentication and authorization](#authentication-and-authorization)
- [API overview](#api-overview)
- [External integrations](#external-integrations)
- [Background maintenance](#background-maintenance)
- [Testing and validation](#testing-and-validation)
- [Ubuntu VPS deployment](#ubuntu-vps-deployment)
- [Security guidance](#security-guidance)
- [Health checks and operations](#health-checks-and-operations)
- [Known verification boundaries](#known-verification-boundaries)
- [Project structure](#project-structure)

## Core capabilities

- JWT authentication, registration, password changes, and one-time password-reset tokens.
- Tenant isolation with platform administrator, tenant owner, tenant manager, staff, and agent responsibilities.
- Internet-plan and voucher lifecycle management.
- Bulk voucher generation, disabling, HTML printing, and PDF generation.
- FreeRADIUS-compatible authentication and accounting models.
- Live-session visibility and RADIUS Disconnect-Request support.
- Router onboarding state, audit history, health checks, encrypted credentials, and WireGuard provisioning support.
- Agent wallets, funding, voucher allocation, statistics, and transaction-safe balance updates.
- Public Paystack voucher checkout and tenant subscription checkout.
- Signed, idempotent Paystack webhook processing.
- Subscription plans, renewals, payment status, and expiration processing.
- Tenant-specific WhatsApp routing.
- Tenant-scoped IoT/MAC-device registration.
- OpenAPI schema, Swagger UI, ReDoc, liveness, and dependency-readiness endpoints.

## Architecture

The application is a modular Django monolith. Each domain is implemented as an app under `apps/`, while shared configuration is kept under `config/`.

| Module | Responsibility |
| --- | --- |
| `accounts` | Custom users, JWT login, registration, user profile, passwords, and password reset |
| `tenants` | Tenant records, memberships, roles, settings, and request tenant context |
| `vouchers` | Internet plans, voucher generation/lifecycle, RADIUS records, and purchase transactions |
| `routers` | NAS/router inventory, onboarding state, encrypted secrets, WireGuard provisioning, audit events, and RADIUS probes |
| `agents` | Agent profiles, wallets, funding records, credit ledgers, and voucher allocations |
| `payments` | Paystack initialization, callbacks, webhook authentication, verification, and fulfillment |
| `subscriptions` | Subscription catalogue, tenant subscriptions, checkout, renewal, and expiry |
| `whatsapp_routing` | Tenant WhatsApp routes and sender bindings |
| `iot_devices` | Tenant-owned MAC/client device records |
| `dashboard` | Tenant statistics, live RADIUS sessions, and session disconnection |
| `core` | Shared permissions, pagination, errors, utility functions, and health checks |

Business-critical workflows are implemented in service modules rather than duplicated in API views. Database transactions, row locks, uniqueness constraints, and idempotency records protect payment, wallet, voucher, subscription, and provisioning workflows.

## Technology stack

- Python 3.13 recommended
- Django 5.2 LTS
- Django REST Framework
- Simple JWT
- PostgreSQL
- Redis in production
- Gunicorn and Nginx on Ubuntu
- FreeRADIUS and WireGuard for network integration
- Paystack for payments
- `drf-spectacular` for OpenAPI documentation
- `pytest` and `pytest-django` for automated tests

See [`requirements.txt`](requirements.txt) and [`requirements-production.txt`](requirements-production.txt) for pinned Python packages.

## Requirements

For local development:

- Python 3.13
- PostgreSQL with an application database and user
- Git
- A Python virtual environment

For the complete production integration:

- Ubuntu VPS
- PostgreSQL
- Redis
- Nginx
- Gunicorn
- FreeRADIUS
- WireGuard tools
- SMTP credentials
- Paystack credentials

External services are optional for basic API development, but their workflows cannot be declared production-ready until tested against isolated live infrastructure.

## Local development on Windows

### 1. Clone the repository

```powershell
git clone https://github.com/yarotech-network/RADIUS_BACKEND.git
Set-Location RADIUS_BACKEND
```

### 2. Create and activate the virtual environment

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, either adjust the execution policy for the current process or call the virtual-environment interpreter directly:

```powershell
.\venv\Scripts\python.exe manage.py check
```

### 3. Create the PostgreSQL database

Create a PostgreSQL database and role matching the values you will place in `.env`. Example names are:

```text
Database: yarotech_radius
User:     yarotech_radius
Host:     localhost
Port:     5432
```

Use a strong local password and do not commit it.

### 4. Create the environment file

```powershell
Copy-Item .env.example .env
```

For development, change `DJANGO_SETTINGS_MODULE` in `.env` to:

```env
DJANGO_SETTINGS_MODULE=config.settings
```

Set the local PostgreSQL credentials and development origins. Production-only integrations may remain empty until their features are exercised.

Generate a Fernet key for encrypted router credentials:

```powershell
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the result only in `.env` or a deployment secret manager. Never commit it or paste a production key into logs, issues, or chat.

### 5. Initialize Django

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createsuperuser
```

If router credentials existed before encryption was enabled, preview and then apply the conversion:

```powershell
.\venv\Scripts\python.exe manage.py encrypt_router_secrets
.\venv\Scripts\python.exe manage.py encrypt_router_secrets --apply
```

Back up the database before applying encryption to an existing environment.

## Environment configuration

`.env.example` contains the supported production variables. Important groups are summarized below.

### Django and browser security

| Variable | Purpose |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | Use `config.settings` locally and `config.production_settings` in production |
| `SECRET_KEY` | Unique Django signing key; production requires at least 50 characters |
| `DEBUG` | Must be `False` in production |
| `ALLOWED_HOSTS` | Comma-separated API hostnames |
| `CORS_ALLOWED_ORIGINS` | Explicit frontend origins |
| `CSRF_TRUSTED_ORIGINS` | Trusted HTTPS origins for CSRF validation |
| `TRUST_X_FORWARDED_PROTO` | Enable only behind a trusted proxy that overwrites the forwarded scheme |

### Data services

| Variable | Purpose |
| --- | --- |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL database credentials |
| `DB_HOST`, `DB_PORT` | PostgreSQL location |
| `DB_CONN_MAX_AGE` | Production persistent-connection lifetime |
| `DB_TEST_NAME`, `DB_TEST_HOST`, `DB_TEST_PORT` | PostgreSQL test-database configuration |
| `REDIS_URL` | Production cache and replay-state storage |

### Integrations and secrets

| Variable | Purpose |
| --- | --- |
| `FERNET_KEY` | Stable key used to encrypt router and integration secrets |
| `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY` | Paystack API credentials |
| `WG_VPS_HOST`, `WG_VPS_SSH_KEY`, `WG_SSH_KNOWN_HOSTS` | WireGuard host and SSH trust configuration |
| `WG_INTERFACE`, `WG_MANAGED_SUBNET` | Managed WireGuard interface and address range |
| `ROUTER_PROVISIONING_AGENT_KEYS` | Comma-separated provisioning-agent keys |
| `ROUTER_PROVISIONING_AGENT_ALLOWED_NETWORKS` | Networks permitted to call the internal provisioning endpoint |
| `RADIUS_AUTH_HOST`, `RADIUS_AUTH_PORT` | FreeRADIUS authentication endpoint |
| `RADIUS_COA_PORT` | RADIUS Change-of-Authorization/disconnect port |
| `WHATSAPP_APP_SECRET` | WhatsApp integration secret |
| `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` | Password-reset email delivery; fallback transport for access-code emails |
| `RESEND_API_KEY` | Resend API key for voucher access-code emails (`DEFAULT_FROM_EMAIL` domain must be verified in Resend). Empty = use `EMAIL_BACKEND` |
| `PASSWORD_RESET_FRONTEND_URL` | HTTPS reset URL containing `{uid}` and `{token}` placeholders |

Production startup deliberately fails when critical security values are missing or unsafe.

## Running the application

Start the local development server:

```powershell
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Useful local addresses:

- API root: `http://127.0.0.1:8000/api/v1/`
- Django admin: `http://127.0.0.1:8000/admin/`
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- ReDoc: `http://127.0.0.1:8000/api/redoc/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`
- Liveness: `http://127.0.0.1:8000/health/live/`
- Readiness: `http://127.0.0.1:8000/health/ready/`

## Authentication and authorization

Most endpoints require a JWT access token:

```http
Authorization: Bearer <access-token>
```

The access token lasts 60 minutes and the refresh token lasts seven days. Refresh tokens rotate when refreshed. Password changes and completed password resets revoke older JWTs through the configured user-token state.

The authorization model includes:

- **Platform administrator:** platform-wide tenant administration.
- **Tenant owner:** controls the tenant, membership changes, and subscription checkout.
- **Tenant manager:** manages tenant plans, vouchers, routers, settings, devices, and operational actions.
- **Authenticated tenant member:** receives tenant-scoped read access where permitted.
- **Agent:** accesses only the assigned agent profile, wallet, allocation history, and agent workflows.

Tenant-owned querysets are filtered from the authenticated membership. Clients must never use a submitted tenant identifier as proof of authorization.

## API overview

This is a route summary. Request and response schemas are available from Swagger/ReDoc and the generated OpenAPI document.

### Authentication

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register/` | Register a user and tenant context (returns no tokens — an emailed OTP must be confirmed first) |
| `POST` | `/api/v1/auth/verify-email/` | Confirm the 6-digit OTP and activate the account (returns tokens) |
| `POST` | `/api/v1/auth/resend-verification/` | Email a fresh OTP to an unverified account (max 1/minute) |
| `POST` | `/api/v1/auth/login/` | Obtain access and refresh tokens (403 `email_not_verified` until the OTP is confirmed) |
| `POST` | `/api/v1/auth/token/refresh/` | Refresh an access token |
| `GET/PATCH` | `/api/v1/auth/user/` | Read or update the current user |
| `POST` | `/api/v1/auth/change-password/` | Change the authenticated user's password |
| `POST` | `/api/v1/auth/password-reset/` | Request a reset email |
| `POST` | `/api/v1/auth/password-reset/confirm/` | Consume a one-time reset token |

### Tenants

| Endpoint family | Purpose |
| --- | --- |
| `/api/v1/tenants/` | Tenant list/detail and platform-admin mutations |
| `/api/v1/tenant-memberships/` | Tenant membership and role management |
| `/api/v1/tenants/settings/` | Current tenant settings |

### Plans and vouchers

| Endpoint | Purpose |
| --- | --- |
| `/api/v1/plans/` | CRUD for tenant internet plans |
| `/api/v1/vouchers/` | Tenant voucher list/detail and CRUD |
| `POST /api/v1/vouchers/generate/` | Generate a voucher batch |
| `POST /api/v1/vouchers/{id}/disable/` | Disable a voucher |
| `GET /api/v1/vouchers/{id}/print/` | Render printable voucher HTML |
| `GET /api/v1/vouchers/{id}/pdf/` | Download a voucher PDF |
| `/api/v1/payments/transactions/` | Read-only tenant payment history |

Voucher lists support filtering, search, ordering, and standard pagination.

### Public voucher purchases and Paystack

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/buy/` | Initialize public voucher checkout |
| `GET` | `/api/v1/payments/callback/?reference=...` | Read checkout result after provider redirect; carries the voucher `access_code` only while the voucher is still unused |
| `POST` | `/api/v1/payments/paystack/webhook/{token}/` | Receive authenticated Paystack events |

The callback only reads local payment state. Final fulfillment is driven by authenticated provider verification/webhook processing.

### Routers and RADIUS

| Endpoint | Purpose |
| --- | --- |
| `/api/v1/routers/` | Tenant router/NAS management |
| `POST /api/v1/routers/{id}/transition/` | Apply an allowed onboarding-state transition |
| `GET /api/v1/routers/{id}/audit/` | Read router audit events |
| `GET /api/v1/routers/{id}/checks/` | Read onboarding checks |
| `POST /api/v1/routers/{id}/test/` | Test an isolated voucher against FreeRADIUS |
| `POST /api/v1/internal/router-provisioning/` | Restricted provisioning-agent callback/poll endpoint |

Router mutations require tenant-manager access. The internal provisioning endpoint additionally uses agent keys and source-network restrictions.

### Agent operations

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/agent/login/` | Agent authentication |
| `GET /api/v1/agent/dashboard/` | Agent dashboard |
| `GET /api/v1/agents/me/` | Current agent profile |
| `GET /api/v1/agent/wallet/balance/` | Current wallet balance |
| `POST /api/v1/agent/wallet/fund/` | Initialize wallet funding |
| `POST /api/v1/agent/vouchers/generate/` | Buy/generate vouchers from wallet balance |
| `GET /api/v1/agent/vouchers/history/` | Voucher-allocation history |
| `GET /api/v1/agent/vouchers/stats/` | Agent statistics |

### Subscriptions

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/pricing/` | Public active subscription plans |
| `GET` | `/api/v1/subscriptions/` | Current tenant subscription |
| `POST` | `/api/v1/subscriptions/checkout/` | Owner-only subscription checkout |
| `GET` | `/api/v1/subscriptions/payments/{reference}/` | Owner-only payment status |

### Tenant operations

| Endpoint family | Purpose |
| --- | --- |
| `/api/v1/whatsapp/routes/` | Tenant WhatsApp route management |
| `/api/v1/iot-devices/` | Tenant device/MAC-address management |
| `/api/v1/dashboard/stats/` | Tenant dashboard totals |
| `/api/v1/dashboard/live-users/` | Active RADIUS accounting sessions |
| `POST /api/v1/dashboard/live-users/{session_id}/disconnect/` | Send a RADIUS Disconnect-Request |

Standard DRF routers provide list, create, retrieve, update, partial-update, and delete methods according to each viewset's permissions.

## External integrations

### PostgreSQL and FreeRADIUS

Django uses PostgreSQL as its primary datastore. The voucher app includes FreeRADIUS-compatible check, reply, authentication-history, and accounting models. A production FreeRADIUS deployment must use the expected PostgreSQL schema and share the intended database records with this application.

RADIUS authentication probes use UDP authentication requests. Live-session disconnection uses RADIUS Disconnect-Request/CoA behavior and requires correct NAS addressing, shared secrets, firewall rules, and router support.

### Paystack

Paystack supports:

- Public voucher checkout.
- Agent-wallet funding.
- Tenant-subscription checkout.
- Server-side transaction verification.
- Signed webhook processing.
- Persisted replay/idempotency protection.

Never treat the browser callback as proof of payment. Configure the webhook URL and secrets in the Paystack dashboard and verify a real sandbox transaction before launch.

### WireGuard and router provisioning

Router onboarding can manage WireGuard peers through a restricted SSH connection to the VPN host. Production requires:

- A dedicated SSH key with minimal privileges.
- A pinned `known_hosts` file.
- A narrowly scoped managed subnet.
- Restricted provisioning-agent keys and source networks.
- Firewall rules that expose RADIUS/CoA only to the VPN or approved router networks.

### Email

Password reset requires a working SMTP backend in production. The reset frontend URL must use HTTPS and preserve the `{uid}` and `{token}` placeholders.

## Background maintenance

Run these commands periodically:

```powershell
.\venv\Scripts\python.exe manage.py expire_vouchers
.\venv\Scripts\python.exe manage.py expire_subscriptions
.\venv\Scripts\python.exe manage.py refresh_router_statuses
```

The supplied Ubuntu systemd timer runs voucher and subscription expiry every five minutes. Router-status refresh should be scheduled separately if it is required by the deployment's operating model.

Voucher reconciliation/synchronization is available through:

```powershell
.\venv\Scripts\python.exe manage.py sync_vouchers
```

Review command help and take an appropriate backup before running maintenance against production data.

## Testing and validation

The automated test suite uses `config.test_settings` and a PostgreSQL test database.

```powershell
.\venv\Scripts\python.exe -m pytest
```

Run framework and migration checks:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py migrate --plan
.\venv\Scripts\python.exe -m pip check
```

Generate and validate the OpenAPI schema:

```powershell
.\venv\Scripts\python.exe manage.py spectacular --file schema.yml --validate
```

Before production deployment, load production-shaped environment values and run:

```powershell
$env:DJANGO_SETTINGS_MODULE='config.production_settings'
.\venv\Scripts\python.exe manage.py check --deploy
```

Do not run this production-settings check with real secrets printed into terminal history or logs.

## Ubuntu VPS deployment

Production dependencies are installed with:

```bash
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements-production.txt
```

Deployment templates are provided under `deploy/ubuntu/`:

- Hardened Gunicorn systemd service.
- Maintenance systemd service and timer.
- HTTP bootstrap Nginx configuration.
- HTTPS Nginx configuration.
- Step-by-step Ubuntu installation and release procedure.

Read `deploy/ubuntu/README.md` before deployment. The intended paths are:

```text
/opt/yarotech-radius/backend
/etc/yarotech-radius/backend.env
```

The high-level release sequence is:

1. Provision DNS, Ubuntu, firewalling, PostgreSQL, and Redis.
2. Install an exact reviewed Git revision.
3. Create the production environment file with new secrets.
4. Back up PostgreSQL.
5. Run `check --deploy` and review `migrate --plan`.
6. Apply migrations and collect static assets.
7. start Gunicorn through systemd.
8. Validate local liveness/readiness.
9. Configure Nginx and issue a TLS certificate.
10. Execute authenticated API, payment, FreeRADIUS, WireGuard, and rollback smoke tests.

## Security guidance

- Never commit `.env`, database passwords, API secrets, SSH private keys, router credentials, or Fernet keys.
- Generate a new `SECRET_KEY` and `FERNET_KEY` for production.
- Retain the Fernet key securely: losing it makes encrypted router credentials unrecoverable.
- Rotate any key that has been exposed in a terminal recording, message, issue, or source-control history.
- Keep `DEBUG=False` and use explicit production hosts and HTTPS origins.
- Bind PostgreSQL and Redis to loopback unless access is explicitly required and firewalled.
- Never expose RADIUS authentication or CoA ports broadly to the internet.
- Restrict SSH and provisioning agents to least privilege.
- Use database backups and tested restore procedures before migrations or key rotation.
- Scrub credentials and provider payloads from application logs.
- Keep tenant scope derived from authenticated membership, not client input.

## Health checks and operations

`GET /health/live/` verifies that the Django process and routing respond.

`GET /health/ready/` verifies both:

- A database query can complete.
- Redis/cache can write, read, and delete a short-lived readiness value.

The readiness endpoint returns HTTP `503` when an essential dependency is unavailable.

Recommended production monitoring includes:

- HTTP availability, latency, and 5xx rate.
- Gunicorn restarts and worker timeouts.
- PostgreSQL capacity, connections, locks, and backup success.
- Redis availability.
- Disk, memory, CPU, and certificate expiry.
- Payment verification/webhook failures.
- Voucher fulfillment failures.
- Router provisioning failures.
- RADIUS reject/unavailable rates and disconnect failures.

## Known verification boundaries

Automated tests and Django checks validate application behavior, but they do not replace live infrastructure tests. Before calling the complete system production-ready, verify:

- A real isolated FreeRADIUS authentication flow.
- Accounting records generated by a router or controlled RADIUS client.
- RADIUS Disconnect-Request against a supported test router/session.
- WireGuard peer provisioning on the target Ubuntu VPS.
- Router reachability through the VPN.
- Paystack sandbox checkout, signed webhook delivery, replay handling, and fulfillment.
- SMTP password-reset delivery and one-time token use.
- Nginx TLS behavior and forwarded-protocol configuration.
- PostgreSQL backup restoration and application rollback.
- Production Fernet-key storage and a documented rotation/recovery procedure.

Passing simulated or mocked integration tests must not be described as proof that these external systems work in production.

## Project structure

```text
yarotech-radius-backend/
|-- apps/
|   |-- accounts/
|   |-- agents/
|   |-- core/
|   |-- dashboard/
|   |-- iot_devices/
|   |-- payments/
|   |-- routers/
|   |-- subscriptions/
|   |-- tenants/
|   |-- vouchers/
|   `-- whatsapp_routing/
|-- config/
|   |-- settings.py
|   |-- production_settings.py
|   |-- test_settings.py
|   |-- urls.py
|   |-- asgi.py
|   `-- wsgi.py
|-- deploy/ubuntu/
|-- .env.example
|-- manage.py
|-- pytest.ini
|-- requirements.txt
`-- requirements-production.txt
```

## Contribution workflow

Before pushing a change:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe -m pip check
```

Keep migrations, tests, API schema changes, configuration examples, and deployment implications in the same review as the behavior they introduce.


### Paystack browser return URLs

Set `PAYSTACK_CALLBACK_ORIGIN` to the frontend origin, for example `https://app.example.com`. Production requires an explicit HTTPS origin. Local development defaults to `http://localhost:5173`; override it when using a different port or host. Do not include a path, query, fragment or credentials. Restart the API after changing this setting.

Every new checkout sends its own `callback_url`: voucher purchases return to `/pay/result`, tenant business subscriptions to `/settings/subscription`, and agent funding to `/agent/wallet/return`. Paystack appends the transaction reference. These routes are on the frontend, not `/api/v1/payments/callback/` (the JSON status endpoint). Previously initialized checkouts retain their original provider settings.

Keep the existing Paystack webhook configured: browser return URLs do not settle payments or replace verified webhook handling. Confirm frontend SPA fallback serves these paths and authenticated users can return to their workspace.


## Public payment result credential redaction

The public callback and verification endpoints now return `fulfilled` independently
of credential disclosure. Both `voucher` and `access_code` are null unless the
payment succeeded and its voucher is unused and uses a single access code.
`code_revealed` describes that same disclosure decision. Legacy separate-password
vouchers also return no username. Authenticated voucher management is unchanged.

Consumers must use `fulfilled` to decide whether issuance is complete; a null
`voucher` no longer means fulfillment is pending. The top-level frontend supports
older servers for fulfillment detection but never displays their legacy `voucher`
value. It displays `access_code` only when `code_revealed` is explicitly true.

Deploy the updated frontend before or alongside the backend to avoid old clients
mistaking redacted completed purchases for pending issuance. Backend protection is
required to close the API disclosure. No migration or router change is needed.
Do not restore credential disclosure on rollback; retain the backend redaction and
forward-fix client compatibility. The nested backend/frontend copy is not updated.

This change does not add purchase ownership verification. Unused single-code
vouchers remain retrievable by payment reference under the existing policy.
First-login status still depends on the existing RADIUS activation integration.
Previously viewed or copied credentials cannot be recalled by response redaction.


## New tenant trial

New workspaces created through email-first registration, legacy registration,
platform tenant creation, or Django admin receive a 15-day trial starting at
creation: 1 registered router, 50 distinct voucher print authorizations per
Africa/Lagos calendar day, and no WhatsApp eligibility. Same-day reprints do not
consume another allowance. This is a printing allowance, not an issuance quota.
Platform administration workspaces are excluded.

Assignment and creation commit together. The trial period snapshots its terms;
repeated assignment cannot extend an existing subscription. Existing tenant
subscriptions and legacy no-subscription access are not backfilled or changed.
Trial expiry uses the existing entitlement checks; it does not disconnect customer
sessions or delete purchased vouchers. Existing subscription purchase scheduling
is unchanged: an early purchase begins after the current active period.

Deployment: apply subscriptions.0006_subscriptionplan_internal_code before the
new backend code. This adds a nullable unique catalogue identifier; it performs no
tenant backfill. Review catalogue size and lock acquisition before production DDL.
The hidden trial plan is created once on first signup, is not purchasable, and is
excluded from platform catalogue CRUD. Roll out all tenant-creation writers before
reopening signup; old writers still omit trial assignment. On code rollback retain
the additive column and recorded trial periods, and pause new registration until
trial assignment is restored. Do not reverse the schema while new code is running.

Validation uses isolated local PostgreSQL test databases and mocked frontend APIs.
Production migration, provider calls, and live router enforcement are separate
operational checks; this change does not apply production configuration.


## Purchased internet-plan terms

New customer checkout orders snapshot the server-owned plan name, price, duration,
data allowance, advertised speed, and existing RADIUS speed-reply mode. Checkout
locks the plan while capturing the order and rechecks availability; provider I/O
runs after commit. The snapshot is not a writable API field.

Verified fulfillment copies these terms to the voucher and allows that original
plan to be inactive. Result pages, voucher details, print/PDF, email, activation
expiry, and RADIUS writes use the saved terms. Payment matching, tenant checks,
transaction locks, paid-unfulfilled recovery, and duplicate suppression remain.
New purchases and ordinary generation still require an active plan. Plans with
payment history cannot be deleted through the ORM/API; deactivate them instead.
Tenant inactivity is still enforced; this is not an override of tenant suspension.

Legacy orders and vouchers retain null snapshots and their existing behavior;
original historical terms cannot be reconstructed safely from the current plan.
Deactivated legacy orders may still require operator investigation. Payment-account
rotation and physical RADIUS enforcement are separate concerns. Custom-rate plans
retain their prior enforcement mode; this change does not retrofit speed replies.

Deploy vouchers.0004_paymenttransaction_purchased_terms_and_more before the new
backend and workers. Its SQL adds two nullable JSONB columns without a data backfill;
the deletion-policy change is enforced by Django. Review lock acquisition and use
a short lock timeout on busy production tables. Upgrade checkout and fulfillment
writers together; old code does not honor snapshots. Retain the additive columns
and saved terms on rollback, and pause new checkout/fulfillment if reverting to an
older writer until snapshot-aware code is restored. No frontend contract change is
required: existing displayed plan fields now contain the purchased values.
