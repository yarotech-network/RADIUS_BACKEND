# 02 — API → Frontend Feature Map

Format per row: **Backend capability → endpoint(s) → frontend feature → screen → user actions**.
`*` = command supports `Idempotency-Key` (client sends one, generated per logical action, reused on retry).
"Workspace" = the tenant application (owner/manager/staff + platform staff with `X-Tenant-ID`). "Console" = platform admin. "Agent" = agent portal. "Public" = unauthenticated.

Every one of the 93 schema paths is accounted for below (except the two machine-only endpoints, listed at the end).

---

## A. Authentication & account (all apps)

| Capability | Endpoint | Frontend feature | Screen | Actions |
|---|---|---|---|---|
| Tenant/user login | `POST auth/login/` | Sign in | `/login` | Sign in; 401 message; 429 countdown |
| Agent login | `POST agent/login/` | Agent sign in | `/agent/login` | Sign in; 403 "not an agent / not active" messaging |
| Register tenant | `POST auth/register/` | Create workspace | `/register` | Register (creates tenant + owner) → straight into workspace |
| Refresh | `POST auth/token/refresh/` | Silent session renewal | — (HTTP client) | Single-flight refresh, store rotated refresh, logout on failure |
| Logout | `POST auth/logout/` | Sign out | Header user menu | Blacklist refresh, clear state |
| Current user | `GET/PATCH auth/user/` | Session bootstrap + Profile | `/settings/profile`, `/agent/profile` | Edit name/phone/email/username |
| Change password | `POST auth/change-password/` | Security | `/settings/security` | Change password (then re-login: tokens revoked) |
| Reset request | `POST auth/password-reset/` | Forgot password | `/forgot-password` | Request email (neutral confirmation) |
| Reset confirm | `POST auth/password-reset/confirm/` | Reset password | `/reset-password?uid=&token=` | Set new password |
| My staff grants | `GET staff/assignments/` | Tenant picker for platform staff | `/select-tenant` + header switcher | Choose tenant → sets `X-Tenant-ID` |
| Accept staff invite | `POST staff-invitations/accept/` | Invitation acceptance | `/accept-invitation?token=` | Accept as new account (username+password) or signed-in account |

## B. Workspace — Dashboard & monitoring

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| Tenant KPIs | `GET dashboard/stats/` | Overview metrics + "needs attention" | `/dashboard` | View; deep-links (pending payments → Payments filtered; paid-unfulfilled → Recovery; routers not active → Routers) |
| Recent activity | `GET audit-events/?page_size=8` | Activity feed | `/dashboard` | View; link to full log |
| Live sessions | `GET dashboard/live-users/?username&router&page&page_size` | Live sessions | `/sessions` | Search username (debounced), filter by router, paginate, refresh/auto-refresh toggle, view bytes/duration |
| Disconnect session | `POST dashboard/live-users/{id}/disconnect/*` | Disconnect | `/sessions` row action | Confirm → result (`acknowledged` true/false, 503 retry hint) |

## C. Workspace — Plans

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| List/search/filter | `GET plans/?search&is_active&duration_hours&ordering&page` | Plan catalogue | `/plans` | Search, active filter, sort by price/duration |
| Create | `POST plans/*` | New plan | `/plans` → drawer | Name, price (₦ input → kobo), duration, rate limit (`up/down` helper), data cap (0 = unlimited), prefix, active |
| Detail/edit | `GET/PATCH plans/{id}/` | Edit plan | drawer | Edit fields; toggle active |
| Delete | `DELETE plans/{id}/` | Delete | drawer | Confirm; 409 "referenced by vouchers" → suggest deactivate |

## D. Workspace — Vouchers

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| List | `GET vouchers/?status&plan&search&created_after&created_before&ordering&page&page_size` | Voucher inventory | `/vouchers` | Status tabs, plan filter, date range, search (username/agent), sort, paginate |
| Generate batch | `POST vouchers/generate/*` `{plan_id, quantity≤100, prefix?}` | Generate vouchers | `/vouchers/generate` (dialog on desktop, page on mobile) | Choose plan, quantity, prefix → result sheet with batch list → open print for each / bulk print (sequential fetch of `print/` HTML) |
| Detail | `GET vouchers/{id}/` | Voucher detail | `/vouchers/:id` drawer | View plan, status timeline (created/activated/expires), source, agent, linked payment |
| Print | `GET vouchers/{id}/print/` (HTML, auth) | Print voucher | detail action | Fetch blob → print-friendly window / iframe |
| PDF | `GET vouchers/{id}/pdf/` (auth; 503 possible) | Download PDF | detail action | Download; on 503 show "PDF unavailable on server — use Print" |
| Disable | `POST vouchers/{id}/disable/*` | Disable | detail action | Confirm (irreversible) |
| Manual create | `POST vouchers/*` `{username,password,plan,device_limit?}` | Add custom voucher | `/vouchers` → "Add custom voucher" (secondary) | Create with chosen credentials |
| Edit | `PATCH vouchers/{id}/` | Edit unused custom voucher | detail (only when `status=unused` and no payment/agent) | Change username/password/plan |
| Delete | `DELETE vouchers/{id}/` | Delete unused voucher | detail (same guard) | Confirm; 400 explains "issued vouchers cannot be deleted; disable instead" |

## E. Workspace — Payments (customer purchases)

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| Transactions | `GET payments/transactions/?status&search&ordering&page` | Payment history | `/payments` | Status filter, search (reference/email/name), paginate |
| Transaction detail | `GET payments/transactions/{id}/` | Detail | `/payments/:id` drawer | View customer, amount, voucher link, timestamps |
| Recovery board | `GET payment-recovery/?status&plan&search&page` | Recovery & delivery | `/payments/recovery` | Filter by fulfillment/delivery status (client-side on returned page + server `status`), search |
| Recovery detail | `GET payment-recovery/{id}/` | Detail | drawer | View fulfillment/delivery status |
| Retry fulfillment | `POST payment-recovery/{id}/retry/*` | Re-verify & fulfil | drawer action (`payments.support`) | Confirm → result (409 mismatch / 503 unavailable messaging) |
| Deliver credentials | `POST payment-recovery/{id}/deliver/*` `{acknowledge_duplicate_risk}` | Email voucher | drawer action | Confirm; if 409 duplicate-risk → second confirm with checkbox |
| Delivery history | `GET payment-deliveries/?payment&status`, `GET payment-deliveries/{id}/` | Delivery timeline | drawer tab | View statuses (`pending/sending/accepted/failed/unknown`), poll while live |

## F. Workspace — Routers (NAS)

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| List | `GET routers/?search&is_active&onboarding_state&deployment_status&ordering&page` | Router inventory | `/routers` | Search name/IP/location, state filters, paginate |
| Register | `POST routers/*` | Add router | `/routers/new` (stepped form) | Basics → RADIUS secret → optional WireGuard → optional RouterOS creds |
| Detail | `GET routers/{id}/` | Router page | `/routers/:id` | Header: state + deployment badges, last seen |
| Edit | `PATCH routers/{id}/` | Edit config (non-secret) | detail → Edit | Name, IP, location, WireGuard fields, RouterOS user, active; 409 busy handling |
| Delete | `DELETE routers/{id}/` | Remove router | detail action | Confirm; 409 when deployed/deploying |
| Onboarding transitions | `POST routers/{id}/transition/*` `{to_state}` | Onboarding stepper | detail → "Onboarding" tab | Buttons limited to valid next states from the state machine; 400 error shown |
| Provision / suspend peer | `POST routers/{id}/provisioning/*` `{action}` | WireGuard provisioning | detail → "VPN" tab | Provision / Suspend; precondition hints (key, IP, active); poll operation |
| Operation status | `GET router-operations/{id}/`, `GET router-operations/?router&status&action` | Operation tracker | detail → VPN tab + `/routers/operations` | Poll live op; history list |
| Replace secrets | `POST routers/{id}/replace-secrets/*` `{current_password, nas_secret?, routeros_password_encrypted?, expected_updated_at}` | Rotate secrets | detail → "Secrets" | Enter own password + new secret(s); 409 stale → reload prompt |
| RADIUS test | `POST routers/{id}/test/` `{username,password}` (10/min) | Test authentication | detail → "Tests" tab | Run test → passed/rejected/503; 429 countdown |
| Checks | `GET routers/{id}/checks/` | Onboarding checklist | detail → Onboarding tab | View 6 check types (ping, routeros_api, wireguard_peer, radius_auth, radius_acct, firewall) with pass/fail/never-run |
| Health | `GET routers/{id}/health/` | Health summary | detail header | Show stored state; explicitly "Telemetry not available" |
| Router audit | `GET routers/{id}/audit/?page` | Router history | detail → "History" tab | Paginated timeline |

## G. Workspace — Agents (resellers)

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| List | `GET tenant/agents/?status&search&ordering&page` | Agent directory | `/agents` | Status tabs, search (username/shop/phone), paginate |
| Create | `POST tenant/agents/*` | Onboard agent | `/agents` → drawer | Username, email, password, phone, shop, commission → created as `pending` |
| Detail | `GET tenant/agents/{id}/` | Agent detail | `/agents/:id` | Profile, wallet balance, status |
| Edit | `PATCH tenant/agents/{id}/` `{phone, shop_name, commission_rate}` | Edit | drawer | Edit editable fields |
| Approve | `POST tenant/agents/{id}/approve/*` | Activate | detail action | Confirm |
| Suspend | `POST tenant/agents/{id}/suspend/*` | Suspend | detail action | Confirm |
| Agent's vouchers | `GET vouchers/?search=<agent username>` | Agent sales | detail tab | Reuse voucher list filtered by agent username |

## H. Workspace — Devices & integrations

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| MAC devices list | `GET iot-devices/?search&is_active&plan&page` | Registered devices | `/devices` | Search name/MAC, filters |
| Create/edit/delete | `POST iot-devices/*`, `GET/PATCH/DELETE iot-devices/{id}/` | Manage device | drawer | MAC (auto-normalised), name, plan, expiry, active |
| WhatsApp route | `GET/POST whatsapp/routes/`, `GET/PATCH/DELETE whatsapp/routes/{id}/` | WhatsApp integration | `/settings/integrations` | Configure phone number id + access token (write-only), enable/disable, remove (one route per tenant) |

## I. Workspace — Settings & team

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| Tenant profile | `GET/PATCH tenants/profile/` | Business profile | `/settings/general` | Name, phone, email, address (slug read-only, storefront link shown) |
| Tenant settings | `GET/PATCH tenants/settings/` | Billing & voucher settings | `/settings/billing` | Paystack keys (write-only, "set/replace"), voucher prefix, max agent funding, commission % |
| Memberships | `GET tenant-memberships/?role&page`, `POST`, `PATCH {role}`, `DELETE` | Team | `/settings/team` | List members; owner: add by **existing user id**, change role, remove (last owner guard messaging) |
| Subscription | `GET subscriptions/` (404 → "no subscription yet"), `GET pricing/` | Subscription | `/settings/subscription` | View status/expiry; owner: choose plan → checkout |
| Checkout | `POST subscriptions/checkout/*` `{plan_id}` | Pay | same | Redirect to Paystack |
| Payment status | `GET subscriptions/payments/{reference}/` | Return handling | `/settings/subscription?reference=` | Poll status after return |
| Audit log | `GET audit-events/?action&actor&search&page`, `GET audit-events/{id}/` | Audit log | `/audit` | Filter by action, search resource, view details JSON |
| My tenant record | `GET tenants/`, `GET tenants/{id}/` | (used for header tenant info / member & voucher counts) | header | — |

## J. Agent portal (`/agent/*`)

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| Stats | `GET agent/dashboard/` (or `agent/vouchers/stats/`) | Agent home | `/agent` | Wallet balance, vouchers today, total, commission (shown only if >0 — see gaps) |
| Profile | `GET agents/me/`, `PATCH agents/{id}/` `{phone, shop_name}` | Profile | `/agent/profile` | Edit phone/shop |
| Wallet balance | `GET agent/wallet/balance/` | Wallet | `/agent/wallet` | View balance |
| Fund wallet | `POST agent/wallet/fund/*` `{amount}` | Top up | `/agent/wallet` → sheet | Amount (₦ → kobo; min ₦500; tenant max) → Paystack redirect |
| Funding history | `GET agent/wallet/payments/?status&reference&page` | History + return polling | `/agent/wallet`, `/agent/wallet/return?reference=` | List; poll by reference after Paystack |
| Buy vouchers | `POST agent/vouchers/generate/*` `{plan_id, quantity}` | Sell voucher | `/agent/sell` | Pick plan (see gap: plan catalogue via `public/tenants/{slug}/plans/` requires slug — see `05_API_GAPS.md`), qty, cost preview vs balance → result list of usernames |
| Sales history | `GET agent/vouchers/history/?status&page` | My vouchers | `/agent/vouchers` | Filter by voucher status, paginate |

## K. Platform console (`/platform/*`, platform admin)

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| Platform KPIs | `GET platform/dashboard/` | Overview | `/platform` | Tenants, routers onboarded, agents, vouchers, revenue split (voucher / wallet / subscription) |
| Tenants | `GET tenants/?search&is_active&is_platform_admin&page`, `POST tenants/`, `GET/PATCH/DELETE tenants/{id}/` | Tenant management | `/platform/tenants`, `/platform/tenants/:id` | Search, create, edit, activate/deactivate, delete |
| Tenant members | `GET tenant-memberships/?tenant=`, `POST/PATCH/DELETE` | Tenant team (admin view) | tenant detail tab | Manage memberships across tenants |
| All routers | `GET platform/routers/?tenant&is_active&onboarding_state&deployment_status&search`, `GET platform/routers/{id}/` | Router fleet | `/platform/routers` | Read-only fleet view with filters |
| Voucher payments | `GET platform/payments/?tenant&status&plan&search`, `/{id}/` | Payments | `/platform/payments` (tab) | Read-only |
| Wallet fundings | `GET platform/wallet-payments/?status&wallet__agent__tenant&wallet__agent&search`, `/{id}/` | Wallet fundings | `/platform/payments` (tab) | Read-only |
| Subscription payments | `GET platform/subscription-payments/?tenant&status&plan&search`, `/{id}/` | Subscription payments | `/platform/payments` (tab) | Read-only |
| Staff invitations | `GET platform/staff-invitations/?tenant&status`, `POST`, `GET /{id}/`, `POST /{id}/revoke/` | Invite staff | `/platform/staff` | Invite (email, tenant, grants) → show token **once** with copy; revoke |
| Staff assignments | `GET platform/staff-assignments/?user&tenant&is_active`, `POST`, `GET/PUT/PATCH/DELETE /{id}/` | Staff grants | `/platform/staff` | Edit grants/active, revoke; create by user id |
| Platform audit | `GET platform/audit-events/?tenant&action&actor&search`, `/{id}/` | Audit | `/platform/audit` | Filter/search |
| Pricing catalogue | `GET pricing/`, `GET pricing/{id}/` | (read-only reference; no write API) | `/platform` info card | View plans |

## L. Public

| Capability | Endpoint | Feature | Screen | Actions |
|---|---|---|---|---|
| Storefront | `GET public/tenants/{slug}/`, `GET public/tenants/{slug}/plans/?search&ordering&page` | Buy Wi-Fi | `/s/:slug` | Browse plans |
| Checkout | `POST buy/*` `{plan_id, email, name?, phone?}` | Purchase | `/s/:slug/checkout/:planId` | Enter details → Paystack |
| Result | `GET payments/callback/?reference=` | Payment result | `/pay/result?reference=` | Poll until `success`/`failed`; show voucher username; explain credentials arrive via operator delivery (see gaps) |
| Pricing | `GET pricing/` | Platform pricing | `/pricing` | View plans; CTA → register |

## M. Machine-only (not surfaced in UI, documented for completeness)

- `POST internal/router-provisioning/` — HMAC + network-restricted provisioning agent endpoint.
- `POST payments/paystack/webhook/{token}/` — Paystack signed webhook.
- `GET /health/live/`, `GET /health/ready/` — used by the UI only for a small "API status" indicator on the login page (optional).
