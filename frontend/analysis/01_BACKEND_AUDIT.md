# 01 — Backend Audit (source of truth)

Audit of `yarotech-network/RADIUS_BACKEND` @ `b88c2d4` ("final api testing"), Django 5.2 / DRF 3.15 / SimpleJWT / drf-spectacular.
Everything in the frontend plan is derived from this audit. Where the backend is silent, the frontend stays silent (see `05_API_GAPS.md`).

---

## 1. What the system is

A **multi-tenant hotspot / ISP voucher platform** built on FreeRADIUS:

- A **platform** (Yarotech) hosts many **tenants** (ISPs / hotspot operators).
- A tenant defines **internet plans** (price in kobo, duration in hours, rate limit, data cap).
- A tenant issues **vouchers** (username/password pairs) for those plans. Voucher credentials are written to the FreeRADIUS `radcheck` table so routers can authenticate customers.
- **Routers (NAS devices)** are onboarded through a **state machine** (pending → reviewed → approved → waiting_for_vpn → testing_radius → active …), optionally provisioned as **WireGuard peers** by a background worker, and tested against FreeRADIUS.
- **Agents** (resellers / shops) have a **wallet** funded through **Paystack**; they buy vouchers from their wallet.
- **Customers** can buy a voucher publicly (Paystack checkout); a signed webhook fulfils the payment.
- Tenants pay the platform through **subscriptions** (Paystack, platform account).
- **Live RADIUS sessions** (`radacct`) can be listed per tenant and disconnected (RADIUS Disconnect-Request).
- Tenants can register **MAC/IoT devices**, and configure a **WhatsApp route** (credentials only — no messaging features are exposed).
- Cross-cutting: **audit events**, **idempotent commands**, **payment recovery/delivery**, **platform staff** with per-tenant service grants.

Base URL: `/api/v1/`. Swagger at `/api/docs/`, schema at `/api/schema/`, health at `/health/live/`, `/health/ready/`.

---

## 2. Django project map

| App | Models | API surface |
|---|---|---|
| `accounts` | `User` (custom; `email` unique CI, `phone`, `is_platform_admin`, computed `role`), `StaffAssignment`, `StaffInvitation` | `auth/*`, `platform/staff-*`, `staff/assignments/`, `staff-invitations/accept/` |
| `tenants` | `Tenant`, `TenantMembership` (OneToOne user→tenant, role owner/manager/staff), `TenantSetting` | `tenants/`, `tenants/profile/`, `tenants/settings/`, `tenant-memberships/`, `public/tenants/{slug}/…` |
| `vouchers` | `InternetPlan`, `Voucher`, `PaymentTransaction`, unmanaged FreeRADIUS tables `Radcheck`, `Radreply`, `Radacct`, `Radpostauth` | `plans/`, `vouchers/`, `payments/transactions/` |
| `routers` | `NASDevice` (UUID pk), `RouterAuditEvent`, `RouterOnboardingCheck`, `RouterOperation`, `ProvisioningAgentRequest` | `routers/` (+ actions), `router-operations/`, `internal/router-provisioning/` (machine-only) |
| `agents` | `AgentProfile`, `AgentWallet`, `AgentWalletFundingPayment`, `AgentVoucherAllocation`, `AgentCreditAccount`, `AgentCreditLedger` (credit models have **no API**) | `tenant/agents/` (management), `agents/`, `agent/*` (self-service) |
| `payments` | `PaystackWebhookEvent`, `PaymentDelivery` | `buy/`, `payments/callback/`, `payments/paystack/webhook/{token}/` (machine), `payment-recovery/`, `payment-deliveries/` |
| `subscriptions` | `SubscriptionPlan`, `TenantSubscription`, `SubscriptionPayment` | `pricing/`, `subscriptions/`, `subscriptions/checkout/`, `subscriptions/payments/{reference}/` |
| `whatsapp_routing` | `TenantWhatsAppRoute` (OneToOne per tenant), `WhatsAppSenderBinding` (no API) | `whatsapp/routes/` |
| `iot_devices` | `MacDevice` | `iot-devices/` |
| `dashboard` | — | `dashboard/stats/`, `dashboard/live-users/`, `dashboard/live-users/{id}/disconnect/` |
| `core` | `ApiCommand` (idempotency), `AuditEvent` | `audit-events/`, `platform/*` read models, `platform/dashboard/` |

Background workers (not API, but they change state the UI shows): `expire_vouchers`, `expire_subscriptions`, `refresh_router_statuses`, `process_router_operations`, `process_payment_deliveries`, `sync_vouchers`.

---

## 3. Entity relationships (what the UI must respect)

```
Tenant 1──* TenantMembership *──1 User        (a user has at most ONE membership)
Tenant 1──1 TenantSetting
Tenant 1──* InternetPlan 1──* Voucher
Tenant 1──* Voucher *──0..1 AgentProfile      (voucher.agent set when agent-generated)
Voucher 1──0..1 PaymentTransaction            (customer purchase)
Voucher 1──0..1 AgentVoucherAllocation        (agent purchase)
Tenant 1──* AgentProfile 1──1 AgentWallet 1──* AgentWalletFundingPayment
Tenant 1──* NASDevice 1──* RouterAuditEvent / RouterOnboardingCheck / RouterOperation
Tenant 1──0..1 TenantSubscription *──1 SubscriptionPlan ; Tenant 1──* SubscriptionPayment
Tenant 1──0..1 TenantWhatsAppRoute
Tenant 1──* MacDevice *──1 InternetPlan
User  1──* StaffAssignment *──1 Tenant         (platform staff, per-tenant service grants)
Radacct.nasipaddress ⇔ NASDevice.ip_address | wireguard_ip  (live sessions are attributed by NAS IP;
                                                             ambiguous addresses shared across tenants are excluded)
```

Voucher lifecycle: `unused → active (first RADIUS auth) → expired (worker)`; `disabled` at any point via `disable`. Only `unused` vouchers **without** a payment/agent allocation can be edited or deleted.

Router onboarding transitions (enforced by `RouterStateMachine.VALID_TRANSITIONS`):

```
pending → reviewed
reviewed → approved | pending
approved → waiting_for_vpn
waiting_for_vpn → vpn_failed | testing_radius
vpn_failed → waiting_for_vpn | suspended
testing_radius → radius_failed | accounting_failed | active
radius_failed → testing_radius | suspended
accounting_failed → testing_radius | suspended
active → suspended
suspended → active | pending
```
`deployment_status` (`not_deployed | deploying | deployed | failed`) is separate and driven by provisioning operations.

---

## 4. Authentication (as implemented)

| Aspect | Backend behaviour |
|---|---|
| Scheme | JWT bearer (`Authorization: Bearer <access>`). |
| Login | `POST auth/login/` `{username, password}` → `{access, refresh, user}`; `401 {error:"Invalid credentials"}`; throttled **10/min** (429 + `Retry-After`). |
| Agent login | `POST agent/login/` → `{access, refresh, agent:{id, username, shop_name}}`; `403 {error}` if not an agent / not active. Same JWT; either login works for either role — the agent endpoint just adds agent-specific checks & messages. |
| Register | `POST auth/register/` `{username, email, password, password_confirm, tenant_name, phone}` → **creates a new tenant + owner membership**, returns tokens + user. |
| Lifetimes | access **60 min**, refresh **7 days**, **rotation + blacklist** on refresh (`POST auth/token/refresh/` returns a NEW refresh; the old one is dead). |
| Logout | `POST auth/logout/` `{refresh}` → 204 (blacklists refresh). |
| Revocation | Password change / reset revokes previously issued tokens (`CHECK_REVOKE_TOKEN`). |
| Current user | `GET/PATCH auth/user/` → `{id, username, email, first_name, last_name, phone, role, tenant_name, tenant_id}`. |
| Password | `POST auth/change-password/` `{old_password,new_password}`; reset `POST auth/password-reset/` `{email}` (5/hour) → email with `PASSWORD_RESET_FRONTEND_URL` = `…/reset-password?uid={uid}&token={token}`; `POST auth/password-reset/confirm/` `{uid, token, password, password_confirm}`. |
| CORS | Allows `Idempotency-Key`, `X-Tenant-ID`; exposes `Idempotency-Replayed`, `Retry-After`. Default dev origin `http://localhost:5173`. |

Frontend consequence: single-flight refresh, always persist the **new** refresh token, hard logout on refresh failure, honour `Retry-After` on 429.

---

## 5. Roles (discovered, not invented)

`User.role` is computed server-side and returned by login / `auth/user/`:

| `role` | Source | Tenant scope resolution |
|---|---|---|
| `platform_admin` | `is_platform_admin=True` | none by default (platform console); tenant-scoped endpoints 403 unless they also hold a membership |
| `owner` | `TenantMembership.role="owner"` | membership tenant |
| `manager` | `TenantMembership.role="manager"` | membership tenant |
| `staff` | `TenantMembership.role="staff"` | membership tenant (read-mostly) |
| `agent` | `AgentProfile` exists (must be `status=active` to pass `IsAgent`) | agent's tenant (self-service endpoints only) |
| `platform_staff` | active `StaffAssignment`(s) | **must send `X-Tenant-ID`** and hold the matching service grant |
| `user` | none of the above | nothing useful |

Platform-staff service grants: `routers.view`, `routers.test`, `live_sessions.view`, `live_sessions.disconnect`, `payments.view`, `payments.support`, `vouchers.generate`, `vouchers.print`. Grants map to specific viewset actions only (`apps/core/api.py::assigned_tenant`).

### Permission matrix (derived from `get_permissions` + `tenant_for`)

Legend: **A** platform admin · **O** owner · **M** manager · **S** tenant staff member · **G** agent · **P** platform staff (with grant)

| Capability | A | O | M | S | G | P (grant) |
|---|---|---|---|---|---|---|
| Tenants list/detail | all | own | own | own | – | – |
| Tenant create/update/delete/activate | ✔ | – | – | – | – | – |
| Tenant profile (name/contact) read/edit | – | ✔ | ✔ | – | – | – |
| Tenant settings (Paystack keys, prefix, funding cap, commission %) | – | ✔ | ✔ | – | – | – |
| Memberships list | all | own tenant | own tenant | own tenant | – | – |
| Memberships create / change role / remove | ✔ | ✔ (last-owner guard) | – | – | – | – |
| Plans list/detail | – | ✔ | ✔ | ✔ | – | `vouchers.generate` |
| Plans create/edit/delete | – | ✔ | ✔ | – | – | – |
| Vouchers list/detail/print/pdf | – | ✔ | ✔ | ✔ | – | `vouchers.print` |
| Vouchers generate batch | – | ✔ | ✔ | – | – | `vouchers.generate` |
| Voucher manual create / edit / delete / disable | – | ✔ | ✔ | – | – | – |
| Payment transactions (read) | – | ✔ | ✔ | ✔ | – | `payments.view` |
| Payment recovery list/detail; deliveries | – | ✔ | ✔ | – | – | `payments.view` |
| Payment recovery `retry` / `deliver` | – | ✔ | ✔ | – | – | `payments.support` |
| Routers list/detail | – | ✔ | ✔ | ✔ | – | `routers.view` |
| Router audit / checks / health | – | ✔ | ✔ | – | – | `routers.view` |
| Router create/edit/delete/transition/provisioning/replace-secrets | – | ✔ | ✔ | – | – | – |
| Router RADIUS test | – | ✔ | ✔ | – | – | `routers.test` |
| Router operations (queue) list | – | ✔ | ✔ | – | – | – |
| Agents management (list/create/edit/approve/suspend) | – | ✔ | ✔ | – | – | – |
| Agent self-service (me, wallet, fund, generate, history, stats) | – | – | – | – | ✔ | – |
| Dashboard stats | – | ✔ | ✔ | ✔ | – | – |
| Live sessions list | – | ✔ | ✔ | ✔ | – | `live_sessions.view` |
| Live session disconnect | – | ✔ | ✔ | – | – | `live_sessions.disconnect` |
| Subscription (current) read | – | ✔ | ✔ | ✔ | – | – |
| Subscription checkout / payment status | – | ✔ | – | – | – | – |
| WhatsApp route read | – | ✔ | ✔ | ✔ | – | – |
| WhatsApp route create/edit/delete | – | ✔ | ✔ | – | – | – |
| MAC devices read | – | ✔ | ✔ | ✔ | – | – |
| MAC devices create/edit/delete | – | ✔ | ✔ | – | – | – |
| Tenant audit events | – | ✔ | ✔ | – | – | – |
| Platform dashboard / routers / payments / audit | ✔ | – | – | – | – | – |
| Staff invitations & assignments (manage) | ✔ | – | – | – | – | – |
| My staff assignments (`staff/assignments/`, returns own) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Public: pricing, storefront, plans, buy, callback, accept invitation, register, reset | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ (and anonymous) |

> Frontend permission checks are UX only. Every mutation above is enforced server-side; the UI will still handle 403 gracefully.

---

## 6. Cross-cutting API contracts

| Contract | Detail |
|---|---|
| **Pagination** | `{count, total_pages, current_page, results}`; `?page=&page_size=` (default 20, **max 100**). Exceptions: `dashboard/live-users/` → `{users, count, current_page, total_pages, observed_at, source}`; `routers/{id}/checks/` → plain array; `routers/{id}/health/`, stats endpoints → single objects. |
| **Filtering** | django-filter fields per view (see `02_API_FEATURE_MAP.md`); `?search=` (DRF SearchFilter); `?ordering=field|-field` (all readable serializer fields unless `ordering_fields` restricts: vouchers → `created_at,status,expires_at`; tenant agents → `created_at,id`; public plans → `price,duration_hours`). |
| **Errors** | Any `/api/` response ≥400 carries `problem: {code:"http_<status>", message, fields:{field:[…]}}` **in addition to** legacy fields (`detail`, `error`, `<field>: [...]`, `non_field_errors`). Client normalises on `problem`. |
| **Idempotency** | Optional `Idempotency-Key` header (`[A-Za-z0-9_.:-]{16,128}`) on marked commands. Replay → same body + `Idempotency-Replayed: true`; different payload → 409; in-flight → 409 + `Retry-After`. **Never mint a new key after a timeout.** Marked commands: `vouchers/generate`, `vouchers/{id}/disable`, POST `vouchers/`, POST `plans/`, POST `routers/`, `routers/{id}/transition|provisioning|replace-secrets`, POST `iot-devices/`, POST `whatsapp/routes/`, `tenant/agents/` create/approve/suspend, `agent/wallet/fund`, `agent/vouchers/generate`, `buy/`, `subscriptions/checkout`, `payment-recovery/{id}/retry|deliver`, `live-users/{id}/disconnect`. |
| **Tenant context** | Members: implicit from membership. Platform staff: `X-Tenant-ID: <tenant id>` on every tenant-scoped call. |
| **Money** | All amounts are **integers in kobo (NGN)**; `price_display` strings are pre-formatted (`₦1,000`). UI formats kobo → `₦` with `Intl.NumberFormat`. |
| **Time** | ISO-8601 with offset (server TZ Africa/Lagos, `USE_TZ=True`). UI renders in the viewer's locale/timezone. |
| **Secrets** | `nas_secret`, `routeros_password_encrypted`, `paystack_*_key`, WhatsApp `access_token_encrypted`, voucher `password` are **write-only** — never returned. Router secrets change only via `replace-secrets` (needs `current_password` + `expected_updated_at`; 409 on stale/busy). |
| **Throttles** | login 10/min, password reset 5/h, router RADIUS test 10/min → 429 + `Retry-After`. |
| **Binary endpoints** | `vouchers/{id}/print/` → `text/html`; `vouchers/{id}/pdf/` → `application/pdf` or **503** when WeasyPrint is unavailable. Both require the bearer token → fetch as blob, not `<a href>`. |

---

## 7. Key workflows traced end-to-end

### 7.1 Tenant onboarding
`POST auth/register/` → `RegisterSerializer.create` (atomic): `User` + `Tenant(slug=slugify(tenant_name))` + `TenantMembership(role=owner)` → tokens. No subscription/trial row is created (`GET subscriptions/` → 404 until first paid checkout).

### 7.2 Voucher issuance (manager)
`POST vouchers/generate/ {plan_id, quantity ≤100, prefix?}` (idempotent, atomic) → `VoucherService.generate_vouchers` creates N vouchers + `radcheck` rows (`Cleartext-Password`, `Max-Days`, optional `Max-Total-Octets`) → audit `vouchers.generated` → **201 array of `VoucherSerializer` (password omitted)**. Credentials are only readable via `GET vouchers/{id}/print/` or `/pdf/`.

### 7.3 Agent voucher sale
`POST agent/vouchers/generate/ {plan_id, quantity}` → locks agent + wallet → `wallet.debit(price×qty)` → generate vouchers (`source=agent`, prefix = tenant setting) → `AgentVoucherAllocation` rows (`commission_earned` is **never computed**; stays 0) → **201 `{vouchers:[allocation…]}` (username only)**. 400 `{error:"Insufficient wallet balance"}` etc.

### 7.4 Agent wallet funding
`POST agent/wallet/fund/ {amount ≥ 50 000 kobo, ≤ tenant.max_funding_amount}` → pending `AgentWalletFundingPayment` → Paystack initialise → `{authorization_url, reference}` (503 `{error, reference}` if provider down; reference retained). Browser goes to Paystack; on return, poll `GET agent/wallet/payments/?reference=`. Webhook (`charge.success`, signature + server-side verify of amount/currency) credits the wallet once.

### 7.5 Public voucher purchase
`GET public/tenants/{slug}/` + `GET public/tenants/{slug}/plans/` → `POST buy/ {plan_id, email, name?, phone?}` (idempotent) → pending `PaymentTransaction` → `{authorization_url, reference}` → Paystack → return to the URL **configured in the Paystack dashboard** (backend passes no `callback_url`) → `GET payments/callback/?reference=` → `{status, reference, voucher: <username|null>}`. Fulfilment happens in the webhook (`fulfill_verified_voucher`: sets `verified_at`, issues one voucher, `status=success`). Credential **delivery** (email) is a separate, manager-triggered `payment-recovery/{id}/deliver/`.

### 7.6 Payment recovery & delivery (manager)
`GET payment-recovery/` annotates each transaction with `fulfillment_status ∈ {fulfilled, paid_unfulfilled, unverified}` and `delivery_status ∈ {not_requested, pending, sending, accepted, failed, unknown}`. `retry/` re-verifies with Paystack (never re-charges) and fulfils; `deliver/` enqueues an email (`acknowledge_duplicate_risk:true` required when a previous delivery was `accepted|unknown`); `GET payment-deliveries/?payment=` for history.

### 7.7 Router onboarding
`POST routers/` (name, ip_address, nas_secret, optional WireGuard fields validated against `WG_MANAGED_SUBNET` + 32-byte base64 key, RouterOS creds, location, is_active) → state `pending`. Manager drives `POST routers/{id}/transition/ {to_state}` through the state machine (400 `{error}` on invalid). `POST routers/{id}/provisioning/ {action: provision|suspend}` → 202 `RouterOperation` (requires `wireguard_public_key`, and for provision `is_active` + `wireguard_ip`; 409 if an operation is live) → worker executes SSH → operation `succeeded|failed`, router `deployment_status` updated, `wireguard_peer` check recorded, router audit event. UI polls `GET router-operations/{id}/`. `POST routers/{id}/test/ {username,password}` → `{passed}` (records `radius_auth` check) or 503. `GET routers/{id}/health/` returns stored state only (`online:null`, `telemetry_available:false`). Edits/deletes are blocked (409) while an operation is pending or the router is deploying/deployed (delete).

### 7.8 Live sessions
`GET dashboard/live-users/?username=&router=&page=&page_size=` → open `radacct` rows for the tenant's unambiguous NAS addresses, enriched with `router_id/router_name`. `POST dashboard/live-users/{session_id}/disconnect/` → RADIUS Disconnect-Request via NAS secret → `{acknowledged}`; 404 if the session/router isn't the tenant's; 503 if RADIUS unreachable.

### 7.9 Team & staff
Owner: `POST tenant-memberships/ {user:<existing user id>, role}` (tenant forced), `PATCH {role}`, `DELETE` — last owner protected. Platform admin: `POST platform/staff-invitations/ {email, tenant, services[]}` → **token returned once**; recipient `POST staff-invitations/accept/ {token, username?, password?}` (new account) or while signed in as the invited email; assignments then manageable via `platform/staff-assignments/`.

### 7.10 Subscription (tenant → platform)
`GET pricing/` (public) → owner `POST subscriptions/checkout/ {plan_id}` → `{authorization_url, reference}` → Paystack (platform keys) → `GET subscriptions/payments/{reference}/` for status; webhook activates/extends `TenantSubscription` exactly once. Subscription status is **not enforced** anywhere in the API (informational).

---

## 8. Observed data shapes (abridged; full detail in `openapi-v1.yaml`)

- `User`: `{id, username, email, first_name, last_name, phone, role, tenant_name, tenant_id}`
- `Tenant`: `{id, name, slug, phone, email, address, is_active, is_platform_admin, created_at, updated_at, member_count, voucher_count}`
- `TenantSetting`: `{id, tenant, agent_commission_percent, voucher_prefix, max_funding_amount, updated_at}` (+ write-only `paystack_secret_key`, `paystack_public_key`)
- `InternetPlan`: `{id, name, price, price_display, duration_hours, rate_limit, data_limit, voucher_prefix, is_active, created_at}`
- `Voucher`: `{id, username, plan, plan_name, plan_duration, price_display, tenant, tenant_name, agent, agent_name, status, generation_source, device_limit, expires_at, activated_at, created_at}`
- `PaymentTransaction`: `{id, reference, amount, status, customer_email, customer_name, customer_phone, voucher, voucher_username, tenant, plan, paystack_reference, created_at, paid_at}`
- `Recovery`: `{id, reference, amount, status, verified_at, voucher, fulfillment_status, delivery_status}`; `PaymentDelivery`: `{id, payment, status, error_code, created_at, started_at, completed_at}`
- `NASDevice`: `{id(uuid), name, ip_address, wireguard_ip, wireguard_public_key, wireguard_port, routeros_username, location, tenant, tenant_name, onboarding_state, deployment_status, is_active, last_seen_at, created_at, updated_at}`
- `RouterAuditEvent`: `{id, router, action, from_state, to_state, correlation_id, details, created_at}`; `RouterOnboardingCheck`: `{id, router, check_type, passed, details, checked_at}`; `RouterOperation`: `{id, router, action, status, attempts, error_code, created_at, completed_at}`; `RouterHealth`: `{router, is_active, onboarding_state, deployment_status, last_seen_at, observed_at, checks[], online:null, telemetry_available:false}`
- `AgentProfile`: `{id, user, username, tenant, phone, shop_name, status, commission_rate, wallet_balance, created_at}`; `AgentWallet`: `{id, agent, balance, updated_at}`; `FundingPayment`: `{id, reference, amount, status, created_at, completed_at}`; `Allocation`: `{id, agent, voucher, voucher_username, allocation_type, amount_charged, commission_earned, created_at}`; `AgentStats`: `{wallet_balance, vouchers_today, commission_this_month, total_vouchers}`
- `DashboardStats`: `{total_vouchers, active_vouchers, total_revenue, total_agents, total_routers, active_routers, currency, amount_unit, observed_at, pending_payments, paid_unfulfilled_payments}`
- `LiveUser`: `{session_id, username, ip_address, client_ip:null, session_time, bytes_in, bytes_out, connected_at, router_id, router_name}`
- `SubscriptionPlan`: `{id, name, price, price_display, duration_days, features[], is_active}`; `TenantSubscription`: `{id, tenant, plan, plan_name, status, started_at, expires_at, is_trial, is_expired}`; `SubscriptionPayment`: `{reference, amount, status, plan, subscription, created_at, completed_at}`
- `MacDevice`: `{id, mac_address, device_name, plan, plan_name, tenant, is_active, expires_at, created_at}`
- `WhatsAppRoute`: `{id, tenant, phone_number_id, is_active, created_at}` (+ write-only token)
- `AuditEvent`: `{id, tenant, actor(user id), action, resource("app.model:pk"), details, created_at}`
- `StaffAssignment`: `{id, user, tenant, services[], is_active, created_at}`; `StaffInvitation`: `{id, email, tenant, services[], expires_at, status, created_at}` (+ `token` on create only)
- `PlatformStats`: `{tenants, active_tenants, routers, onboarded_routers, agents, vouchers, successful_payment_amount, pending_payments, currency, amount_unit, successful_wallet_funding_amount, successful_subscription_amount}`
