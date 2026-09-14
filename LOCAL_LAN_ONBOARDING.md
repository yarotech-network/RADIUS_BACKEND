# Local LAN laboratory onboarding

This mode discovers an explicitly approved physical router over HTTPS and exports
the existing staged Hotspot lab package using its LAN source address. It does not
create a WireGuard peer, change deployment status, send configuration commands to
the router, or claim successful RADIUS authentication.

## Register and approve the target

1. Register the router in the tenant dashboard with its actual management IP,
   model, RouterOS version, RADIUS secret and RouterOS credentials. WireGuard
   fields may be empty. Select **Continue to Hotspot configuration review**.
2. Obtain the router UUID from its dashboard URL. The backend operator sets this
   environment value, substituting that UUID (not the tenant ID):

   ```dotenv
   ROUTER_LOCAL_LAN_TARGETS={"ROUTER_UUID":{"address":"192.168.88.1","management_interface":"ether2","wan_interface":"ether1","preparation_interfaces":["ether3"]}}
   ```

   Approval is disabled by default. The exact registered IP must match, must be
   RFC1918 IPv4, and management, WAN and preparation port names must differ.
   A tenant cannot grant approval by submitting an address or URL to discovery.
   Restart the backend after changing environment configuration.
3. Configure RouterOS HTTPS REST access with a certificate trusted by the backend,
   valid for the management IP. Use `ROUTER_DISCOVERY_CA_BUNDLE` for a private CA
   if needed. Restrict router HTTPS access to the management computer. WinBox
   connectivity alone does not establish HTTPS access. Discovery does not enable
   services or install certificates and never disables TLS verification.
4. Choose **Local LAN laboratory** under **Discovery connection**. Discovery uses
   the saved router credentials, fixed HTTPS port, no redirects or environment
   proxies, and bounded read-only property requests. No HTTP fallback is offered.

## Review port preparation

For the reported lab topology, ether1, ether2 and ether3 initially share
`bridgeLocal`. The management address is on that bridge. Discovery conservatively
protects the entire connected bridge/VLAN/bond topology, including ether3.

The dashboard displays a non-executable preparation checklist and the observed
bridge membership of the operator-designated candidate ports. This is an operator
review step, not an automatic migration script. Download the encrypted router
backup and configuration export, keep the computer on ether2, and independently
review existing services and VLANs before manually changing bridge membership.
Keep ether1 disconnected from the internet while firewall policy is absent.

The desired preparation leaves ether2 and its management address reachable,
separates ether1 from the management bridge, places ether1 in the WAN interface
list, and leaves ether3 unbridged and free of conflicting services. Rediscover
after preparation. A fresh-install review cannot select a protected or bridged
client port. Do not mark a VPN deployed to bypass these checks.

## Review and export

Adopt the current inventory explicitly, save the exact discovered model/version
on the router record if necessary, and rediscover after that edit. Select the
customer interface and a separate customer subnet. Save a fresh-install review,
then acknowledge the lab limitation and export the package.

`stage.rsc` creates disabled services; `activate.rsc` enables them separately;
`cleanup.rsc` removes owned package resources. Local packages additionally check
the approved management port, IP binding, bridge membership and WAN separation
at execution time. Existing RADIUS entry/secret/source IP, reachable DNS, Hotspot
device permission, WAN list and firewall review remain prerequisites. No complete
firewall, credential bootstrap or captive-portal assets are installed by this
change. FreeRADIUS is still required for system voucher authentication.

Never import a script until its target and port selections have been reviewed.
No RouterOS parser or physical-hardware acceptance is implied by local unit tests.

## API compatibility and rollback

`POST /routers/{id}/hotspot-setup/discover/` accepts optional `connection_mode`:
`wireguard` (the backwards-compatible default) or `local_lan`. Setup responses
include `local_lan_available`. Inventory stores the selected mode, management IP,
approved port policy and preparation review in the existing audit snapshot. No
database migration is required. Changing the router record invalidates discovery;
revoking/changing approval blocks local export until a new valid discovery.

Removing the approval disables future discovery/export. Already downloaded
scripts cannot be revoked: discard them after configuration or approval changes.
Preparation changes are outside package cleanup; use the saved router backups and
reviewed manual rollback for those changes. This release never applies them.


## Local-user lab mode without FreeRADIUS

After current approved LAN discovery, choose **Authentication mode > Local user ?
lab test without FreeRADIUS** in the Hotspot setup form. Use fresh setup on unused
client interfaces. RADIUS address is omitted in this mode; no placeholder server
or fake RADIUS success is needed. Use a separate customer subnet, for example
`10.40.0.1/24` after confirming it does not overlap your environment.

The package creates a dedicated Hotspot user profile and a disabled local test
user, restricted to the package's Hotspot server. It initializes the password
randomly on the router; no password is in the package or sent to the application.
After staging, open the named user under WinBox **IP > Hotspot > Users** and set
its password privately (at least eight characters). Activation checks password
length without printing it. This account is not a RouterOS administrator.

Test limits: one simultaneous device, 2 Mbps each direction, 15-minute sessions,
five-minute idle timeout, one hour of total connected time, and 100 MiB total
transfer. The limits are usage-based, not a calendar expiration; remove the lab
package when finished. MAC-cookie login is disabled for this profile.

Use the package's normal stage/activate/cleanup flow. Customer ports are enabled
last during activation. Cleanup checks ownership before removing the test account,
its active sessions and its profile. Do not rename/edit owned resources other than
the test-user password; altered ownership or configuration blocks automatic cleanup.

Without internet, visit the customer gateway's `/login` page by IP from a device
on the client port, such as `http://10.40.0.1/login`. Inspect the router's default
Hotspot HTML files before activating; this generator does not install portal files.
The package still asks for a DNS server, but reachability is not implied. DNS,
WAN browsing and internet speed tests require their corresponding connectivity.
It does not configure an uplink or full firewall: retain isolated lab usage until
firewall/IPv6 and client-to-management isolation have been reviewed.

This mode does not issue system vouchers, charge a customer, populate RADIUS
accounting, or mark the router ready. The existing RADIUS checks stay unverified.
Before switching to RADIUS, clean up the local lab package and create a new review
from fresh discovery so the test user cannot bypass the RADIUS service.

API: review payloads accept `authentication_mode` (`radius` by default, or
`local_user`). `radius_server` is mandatory for RADIUS and empty/omitted for local
users. Local users require current, approved local-LAN discovery and fresh mode.
Unknown modes and local-user migration requests are rejected. Existing audit JSON
stores the choice, so there is no database migration. Generator version is v2;
revoke and recreate an already-exported review rather than mixing package versions.

References: [HotSpot user limits](https://manual.mikrotik.com/docs/authentication-authorization-accounting/hotspot-captive-portal/),
[RouterOS random strings](https://manual.mikrotik.com/docs/developer-guides/scripting/).

## Read-only local lab verification

After activation, open Hotspot setup > Verification > Verify local lab. The
backend checks its approved HTTPS destination using verified TLS and saved
credentials. Keep the management path reachable and the generated local user
logged in from a customer port. With one cable, restore ether2 / 192.168.88.2
before checking; the customer session can expire after disconnecting.

`POST /api/v1/routers/{id}/hotspot-setup/verify-local-lab/` accepts only
`{"intent_id":"<exported review UUID>"}`. Tenant managers only. It reads model/OS,
bridge membership, gateway, Hotspot, DHCP, a bound lease and the generated user's
active session. It never imports scripts or reads passwords, MACs or client IPs.
The setup response includes `local_lab`: eligibility, status, checked_at, fixed
check results and a fixed failure code. Successful evidence expires in 10 minutes;
a failed connection replaces the current result instead of retaining a green badge.

Expired download access is allowed for an already exported package, but revocation,
a replacement intent, changed router record or changed operator approval prevents
verification. Concurrent changes discard the observation. Audit JSON stores only
bounded check results; no migration is needed.

“Local lab verified” means these observations passed. It does not prove firewall
isolation, internet service, speed or quota enforcement, vouchers, payments or
RADIUS accounting. `ready`, deployment status and onboarding checks are unchanged.
No new scripts or router reset are required for this feature. Physical-router
verification of this new endpoint remains a separate acceptance step.

The `local_lab.progress` response also separates `configuration` (all seven
non-login checks) from `customer_login`. Each includes `passed`, `checked_at` and
`fresh`. It uses the latest completed observation for the current approved package,
so existing saved checks appear automatically. A connection failure or ten-minute
expiry preserves that dated observation but sets freshness false. A later completed
check supersedes it, including a configuration failure. Revoked/replaced packages,
changed router records and withdrawn/changed approval cannot reuse the progress.
This is a saved test observation, not a permanent certificate or a manual login
confirmation. No database migration or router configuration change is required.

## Reviewed Wi-Fi addition to an installed local lab

Wired and wireless customer interfaces share the `client` role. Interface kind
`wireless` distinguishes a Wi-Fi radio; there is no separate Wi-Fi role.
An operator can approve up to two already configured wireless additions using
`ROUTER_LOCAL_LAN_WIFI_EXTENSIONS={"ROUTER_UUID":{"intent_id":"PACKAGE_UUID","interfaces":["wlan1"]}}`.
Approval applies only to that router and exported package. The original management,
WAN and package interfaces cannot be selected as additions. Keep the existing
`ROUTER_LOCAL_LAN_TARGETS` unchanged; restart the backend after editing settings.

Verification checks the exact expanded bridge membership, enabled wireless type,
and bridge-port comment `Yarotech WiFi lab extension`. Other additions still fail.
The setup response lists `local_lab.client_interfaces`, including each interface's
kind, role, bridge and source. Approval alone does not prove physical configuration.
Audit observations include the approved Wi-Fi names, preventing previous evidence
for ether3 alone from confirming the expanded configuration. Concurrent approval
changes discard a running verification result.

This does not rewrite the original intent or generate new installation commands.
Old offline cleanup/activation scripts retain their original membership guards:
review and separately detach/disable the manual Wi-Fi addition before using them.
Wi-Fi passwords, country/power settings and full firewall isolation are not certified
by the client-binding observation.
