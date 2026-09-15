# Router creation and setup script parity

Reference: `yarotech-radius-system-current/vouchers/forms.py` QuickRouterDeploymentForm,
`vouchers/views.py` router_create and _auto_generate_router_configuration,
`routers/onboarding.py`, `routers/manual_onboarding.py` and the complete HotSpot
generator in `routers/hotspot_setup.py` / `routers/services.py`.

Requested workflow: router name and optional NAS identifier; exact customer LAN
interface; optional hardware/location/notes; automatic HotSpot setup enabled by
default; gateway, automatic/custom DHCP range, explicit reuse and NAT options;
network confirmation; create -> automatic identity/address/secret preparation ->
script page with copy/download/import instructions. Infrastructure failure retains
the router and offers retry. Approval does not prove VPN, authentication or accounting.

Implementation boundaries:
- Dedicated self-service registration API keeps the existing manual CRUD contract
  compatible. Tenant selection uses the existing authorized workspace scope.
- Persist registration intent and encrypted private key/script separately from
  existing router fields. Prepare a migration, never apply to live/local user DBs.
- Port deterministic legacy script functions; remove hardcoded production network
  defaults. Match network validation/ownership checks and retain the existing lab UI.
- Serialize address allocation across tenants and enforce subscription capacity.
  Save SQL NAS identity transactionally in the same database; no live FreeRADIUS edits.
- Reuse durable provisioning operations for external SSH, with explicit enablement.
  Generated script release follows successful server preparation; retries retain
  identity, secrets and the original registration. No secrets in audit/idempotency data.
- Frontend replaces manual secret/VPN creation steps with the reference form and
  exposes setup status, retry, copy and download in router detail.
- Test validation, tenant isolation, capacity, repeat submission, allocation,
  secret exposure, generation and error recovery plus frontend form/actions.
- No VPS deployment, live migration or physical-router execution is part of local
  implementation. Test RouterOS syntax and packet behavior separately on the test router.

## Implemented API and application flow

POST `/api/v1/routers/register/` accepts the reference HotSpot form fields, generates
NAS identifier/profile names when blank, allocates an unused tunnel address and
creates encrypted RADIUS/WireGuard credentials. Requests support Idempotency-Key;
the ordinary response and its replay contain no secrets. Unsupported fields,
unreviewed networks, invalid LAN/DHCP choices and duplicate explicit NAS identifiers
are rejected before partial registration can commit.

The legacy HotSpot validation and RouterOS renderer are ported into
`legacy_hotspot_setup.py` and `legacy_script.py`. New adaptations are UUID object
names and environment-configured tunnel/RADIUS addresses and ports instead of the
legacy deployment's hardcoded infrastructure. Complete setup retains the legacy
RouterOS 7.17+ preflight and ownership checks. Existing-router/manual lab tools
remain available for records created through the prior API.

Infrastructure work uses the existing durable RouterOperation worker instead of
performing SSH within the create transaction. The UI polls preparation status.
POST `routers/{id}/setup-script/retry/` retries failed preparation with the same
identity. GET `routers/{id}/setup-script/` reveals the encrypted-at-rest script only
to an authorized tenant manager after successful preparation, with no-store headers.
The UI supports copy, .rsc download and the import command. The legacy public
single-use installer URL is not ported: download uses the authenticated API.
Server preparation does not mark VPN checks passed or the physical router deployed.

## Activation sequence (not executed)

1. Deploy backend changes and apply `routers.0006_routerregistration` only against
   the isolated test database, before exposing the new frontend/API.
2. Keep the current working Resend/Paystack environment and keys. Configure the
   dedicated staging WG_INTERFACE/WG_MANAGED_SUBNET, WG_VPS_HOST,
   WG_VPS_SSH_KEY/WG_SSH_KNOWN_HOSTS, WG_VPS_ENDPOINT (host only), WG_VPS_PUBLIC_KEY,
   WG_ENDPOINT_PORT, RADIUS_SERVER_WG_IP and router-facing RADIUS ports. Suggested
   isolated auth/accounting ports remain 18120/18130. Never reuse the legacy
   production tunnel interface by assumption.
3. Prepare the isolated FreeRADIUS SQL/REST runtime and its client discovery/loading
   policy; a nas table row alone does not prove that FreeRADIUS accepts that client.
   Open only the reviewed staging network paths. Retain the staging RADIUS HTTP
   block in public Nginx. RADIUS REST enablement still requires an explicit update
   to the provider-testing settings profile, separately from this form change.
4. Enable ROUTER_SELF_SERVICE_PROVISIONING_ENABLED only after the dedicated peer
   manager can reach that staging interface. Run the existing router-operation
   worker under the reviewed staging environment. The web request itself never
   performs SSH or executes anything on a physical router.
5. Build/deploy the React update, create a test router, review the script and back
   up the intended router before importing. Verify VPN/authentication/accounting
   separately. PPPoE/EAP parity is outside this HotSpot form and script flow.

The migration is additive. No existing router is assigned generated credentials or
converted to self-service automatically. New users must not use the manual identity
editor or secret rotation endpoint to desynchronize generated scripts and SQL NAS.

## Local validation

- All 90 backend router tests passed against an isolated PostgreSQL test database.
- All 52 frontend router tests passed with one test worker. An earlier concurrent
  run had two timeouts; neither recurred in the complete single-worker rerun.
- After the final generated-identity guards, all 12 registration tests and the
  router frontend ESLint check passed again.
- Migration consistency check reported no changes required.
- Final frontend production build passed, including TypeScript checks. Vite
  reported non-blocking dependency annotation and subscription chunk warnings.
- Physical router import, VPN handshake, live RADIUS authentication/accounting,
  and VPS activation remain unverified. No deployment or live migration was run.
