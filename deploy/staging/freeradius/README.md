# Isolated FreeRADIUS acceptance candidate

These templates have NOT been loaded by FreeRADIUS or tested on the physical router. Keep public IoT purchases disabled until the complete matrix passes. This is a PAP/CHAP HotSpot/MAC adapter, not an EAP or PPPoE replacement.

For the September VPS rehearsal, reserve UDP **18121/18131** on loopback and
**10.101.100.1** (wgstage); live FreeRADIUS already owns loopback 18120. The original
template port numbers below must be replaced for that host. The candidate
`STAGING_ROUTER_TESTING=True` profile now permits REST alongside provider testing
only with the exact isolated database, tunnel and ports. It also requires
`RADIUS_REST_ENABLED=True` and a private token of at least 32 characters, while
retaining the IoT purchase and WhatsApp gates. Deploy the reviewed settings change
before enabling the opt-in on an older release. Configuration validation, service
activation, client admission and physical packet tests remain separate steps.

Use a separate configuration root, PID/log directory and listeners (candidate loopback UDP 18120/18130). Do not copy these into `/etc/freeradius/3.0/sites-enabled`, restart the active service, enable its SQL module against the new database, or point a production router at this candidate.

In the isolated instance, enable the vendor `pap`, `chap`, `always` and `expr` modules, load the `acct_unique` policy from `policy.d/accounting`, and enable these REST and SQL instances. Set a unique process name/PID/log file in its radiusd.conf, and remove all other listeners from that isolated configuration. Use a new random client secret and a single explicitly listed test NAS, never `0.0.0.0/0`. For initial loopback tests, create an isolated test router record with radius source 127.0.0.1. A real router test requires its actual trusted tunnel/source address and restricted firewall access to the staging ports. Keep `require_message_authenticator` appropriate to the installed server/router security configuration; validate support rather than weakening the live policy.

Create `staging_sql` from the installed vendor SQL module: `sql staging_sql { ... }`, PostgreSQL driver, only `yarotech_radius_staging` database/user, and the installed PostgreSQL `queries.conf`. Retain its accounting/session queries and table settings. Use the installed PostgreSQL `schema.sql` to create the unmanaged RADIUS tables in the EMPTY staging database before creating vouchers. Inspect that script before running it; never run it against the legacy database. The expected physical columns are `radacct.acctsessionid` and `radpostauth.reply`. Django migration 0009 changes model state only; it does not rename an existing table column.

Protect all module/client files with root ownership and mode 0600. Replace both REST header placeholders with the new staging token. The API checks that token and actual packet source; authorization provides the cleartext credential only to the private trusted server. PAP/CHAP must validate it before post-auth calls the activation endpoint. The Nginx staging template blocks external HTTP access to these endpoints.

Validate the isolated root first (example path only):

```bash
freeradius -d /etc/freeradius-staging -XC
```

Do not start it until validation passes and its listeners, SQL destination, PID/log paths and client scope are reviewed. Debug output can contain voucher passwords and tokens; inspect privately and redact before sharing.

Required acceptance: correct/wrong password; unknown/foreign NAS; failed API/DB; unused voucher activation once; repeat login never extends expiry; legacy unknown-duration blocked for reconciliation; expired voucher rejected; existing valid voucher accepted after operator subscription expiry; simultaneous-device limit; accounting Start/Interim/Stop updates the same session; rate/data limits; IoT wrong MAC/router, expired/revoked/suspended; renewal retains unused time and suspension; real disconnect/re-auth. Session-Timeout is capped at 300 seconds, so status changes are enforced on the next authentication, not claimed as immediate CoA. Account for reporting lag in data-cap tests and concurrent sessions. A successful HTTP test alone is insufficient.

Protocol references: [official FreeRADIUS 3.2 REST module](https://raw.githubusercontent.com/FreeRADIUS/freeradius-server/v3.2.x/raddb/mods-available/rest), [SQL module](https://raw.githubusercontent.com/FreeRADIUS/freeradius-server/v3.2.x/raddb/mods-available/sql). Validate against the installed 3.2.5 configuration, because branch documentation may include later changes.
