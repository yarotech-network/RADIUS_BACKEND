"""Secret-free, explicitly lab-only RouterOS fresh-Hotspot artifacts.

No router IO occurs here. RADIUS-mode scripts require an existing RADIUS entry;
credential bootstrap and migration of existing configurations are separate work.
"""
import hashlib
import ipaddress
import re
from uuid import UUID

from rest_framework.exceptions import ValidationError

from .discovery import compatibility
from .hotspot_setup import HotspotIntentSerializer

VERSION = 'hotspot-lab-fresh-v8'


def quote(value):
    # RouterOS strings interpolate $, even inside double quotes.
    text = str(value)
    if any(ord(c) < 32 or ord(c) > 126 for c in text):
        raise ValidationError({'detail': 'The lab generator requires printable ASCII identifiers.'})
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'


def guard(condition, message):
    return f':if ({condition}) do={{ :error {quote(message)} }}'


def generate(router, result, dns_server):
    intent, observed = result.get('intent'), result.get('discovery')
    if not intent or intent['state'] != 'review' or not observed or observed['state'] != 'current':
        raise ValidationError({'detail': 'Save a review based on a current discovery before exporting.'})
    data = intent['configuration']
    local_user = data.get('authentication_mode', 'radius') == 'local_user'
    if data.get('inventory_id') != observed['id']:
        raise ValidationError({'detail': 'The review must use the latest discovered interfaces.'})
    local = observed.get('connection_mode') == 'local_lan'
    if not local and (router.deployment_status != 'deployed' or not router.is_active or not router.wireguard_ip):
        raise ValidationError({'detail': 'The router must have an active deployed management VPN.'})
    if compatibility(router, observed)['status'] != 'unverified':
        raise ValidationError({'detail': 'Resolve discovery compatibility blockers before exporting.'})
    if not router.model or not router.routeros_version or router.model != observed['model'] or router.routeros_version != observed['routeros_version']:
        raise ValidationError({'detail': 'Save the exact discovered model and OS in Edit router, then rediscover.'})
    if not re.fullmatch(r'7\.(?:1[6-9]|[2-9][0-9]|[1-9][0-9]{2,})(?:\.[0-9]+)?', observed['routeros_version']):
        raise ValidationError({'detail': 'This laboratory generator targets stable RouterOS 7.16 or newer in the 7.x series.'})
    if data['mode'] != 'fresh' or observed['hotspots']:
        raise ValidationError({'detail': 'Existing Hotspot migration is review-only. Lab export requires a fresh target.'})
    serializer = HotspotIntentSerializer(data={**data, 'expected_updated_at': router.updated_at}, context={'router': router})
    serializer.is_valid(raise_exception=True)
    clients = [p for p in data['interfaces'] if p['role'] == 'client']
    if any(p['kind'] not in ('ethernet', 'wireless') for p in clients):
        raise ValidationError({'detail': 'The first lab generator supports unused Ethernet and wireless client interfaces only.'})
    addresses = observed.get('addresses')
    if addresses is None:
        raise ValidationError({'detail': 'Discover again to collect the addressing baseline required by this generator.'})
    gateway = ipaddress.IPv4Interface(data['gateway'])
    radius = None if local_user else ipaddress.IPv4Address(data['radius_server'])
    peer = ipaddress.IPv4Address(observed['management_ip'] if local else router.wireguard_ip)
    dns = ipaddress.IPv4Address(dns_server)
    if dns in gateway.network or dns.is_loopback or dns.is_multicast or dns.is_unspecified:
        raise ValidationError({'dns_server': 'Use a reachable unicast DNS server outside the client subnet.'})
    if peer in gateway.network or (radius is not None and (radius in gateway.network or radius.is_loopback or radius.is_multicast or radius.is_unspecified)):
        raise ValidationError({'detail': 'Client addressing must be separate from RADIUS and the management VPN.'})
    if any(row.get('interface') in {p['name'] for p in clients} for row in addresses):
        raise ValidationError({'detail': 'Client interfaces already have IP addresses; this is not a fresh target.'})
    for row in addresses:
        try:
            network = ipaddress.IPv4Interface(row['address']).network
        except (ValueError, KeyError):
            raise ValidationError({'detail': 'Discovery contains an unsupported address. Review the addressing baseline.'})
        if gateway.network.overlaps(network):
            raise ValidationError({'detail': 'The client subnet overlaps an existing router address.'})
    package_id = str(UUID(intent['id']))
    owner = 'yarotech-lab:' + package_id
    auxiliary = 'yr-' + UUID(package_id).hex[:16]
    network = str(gateway.network)
    hosts = [str(gateway.network.network_address + 1), str(gateway.network.broadcast_address - 1)]
    # Split DHCP ranges around the router gateway; /16 maximum keeps this bounded.
    ranges = []
    if gateway.ip > gateway.network.network_address + 1:
        ranges.append(f'{hosts[0]}-{gateway.ip - 1}')
    if gateway.ip < gateway.network.broadcast_address - 1:
        ranges.append(f'{gateway.ip + 1}-{hosts[1]}')
    q = quote
    def find(path, selector):
        return f'[{path} find where {selector}]'
    resources = []
    def add(path, selector, properties, switch=False):
        resources.append({'path':path, 'selector':selector, 'properties':properties, 'switch':switch})
    add('/interface bridge', f'name={q(data["bridge"])}', f'name={q(data["bridge"])} protocol-mode=rstp vlan-filtering=no')
    add('/ip pool', f'name={q(auxiliary)}', f'name={q(auxiliary)} ranges={q(",".join(ranges))}')
    add('/ip address', f'address={q(data["gateway"])}', f'address={q(data["gateway"])} interface={q(data["bridge"])} disabled=yes', True)
    add('/ip dhcp-server network', f'address={q(network)}', f'address={q(network)} gateway={gateway.ip} dns-server={dns}')
    add('/ip dhcp-server', f'name={q(auxiliary)}', f'name={q(auxiliary)} interface={q(data["bridge"])} address-pool={q(auxiliary)} lease-time=1h disabled=yes', True)
    # RouterOS 7.24.2 returns empty values for the accounting fields when
    # use-radius=no. Do not use inactive fields as ownership predicates.
    radius_properties = 'use-radius=no' if local_user else 'use-radius=yes radius-accounting=yes radius-interim-update=5m'
    add('/ip hotspot profile', f'name={q(data["profile_name"])}', f'name={q(data["profile_name"])} hotspot-address={gateway.ip} {radius_properties} login-by=http-chap')
    add('/ip hotspot', f'name={q(data["hotspot_name"])}', f'name={q(data["hotspot_name"])} interface={q(data["bridge"])} profile={q(data["profile_name"])} address-pool=none disabled=yes', True)
    if local_user:
        # This menu exposes idle-timeout as a string (unlike session-timeout).
        # Quote it in both creation and ownership filters to preserve its type.
        add('/ip hotspot user profile', f'name={q(auxiliary)}', f'name={q(auxiliary)} shared-users=1 session-timeout=15m idle-timeout="5m" rate-limit="2M/2M" add-mac-cookie=no')
        add('/ip hotspot user', f'name={q(auxiliary)}', f'name={q(auxiliary)} server={q(data["hotspot_name"])} profile={q(auxiliary)} limit-uptime=1h limit-bytes-total=104857600 disabled=yes', True)
    # Firewall prefixes are reported as strings; quote them in ownership filters.
    add('/ip firewall nat', f'comment={q(owner)}', f'chain=srcnat src-address={q(network)} out-interface-list=WAN action=masquerade disabled=yes', True)
    for p in clients:
        add('/interface bridge port', f'interface={q(p["name"])}', f'interface={q(p["name"])} bridge={q(data["bridge"])} disabled=yes', True)
    # Do not assume all RouterOS menus support comments: /ip hotspot rejects
    # them on the physical 7.24.2 lab router. For uncommented resources, require
    # the package bridge marker and exact expected properties before mutation.
    uncommented = ('/ip pool', '/ip hotspot', '/ip hotspot profile', '/ip hotspot user profile')
    def owned(r):
        # Match all stable properties, not just a name. Operator edits require
        # manual inspection rather than activation or deletion of changed data.
        props = r['properties'].replace(' disabled=yes', '')
        if r['path'] == '/ip hotspot':
            # `get address-pool` reports an unset pool as empty on RouterOS
            # 7.24.2. Check its value separately instead of matching `none`.
            props = props.replace(' address-pool=none', '')
        if r['path'] == '/ip firewall nat':
            # RouterOS list references do not reliably match their displayed
            # names in find filters. Validate the resolved name via get below.
            props = props.replace(' out-interface-list=WAN', '')
        return props + ('' if r['path'] in uncommented else f' comment={q(owner)}')
    server_selector = find('/ip hotspot', f'name={q(data["hotspot_name"])}')
    pool_checks = [
        guard(f'[:len {server_selector}] > 1', 'Duplicate Hotspot server; inspect before continuing'),
        f':if ([:len {server_selector}] = 1) do={{ :local hotspotPool [:tostr [/ip hotspot get {server_selector} address-pool]]; '
        ':if (($hotspotPool != "") && ($hotspotPool != "none")) do={ :error "Hotspot address pool changed; inspect before continuing" } }',
    ]
    nat_selector = find('/ip firewall nat', f'comment={q(owner)}')
    nat_checks = [
        guard(f'[:len {nat_selector}] > 1', 'Duplicate package NAT rules; inspect before continuing'),
        f':if ([:len {nat_selector}] = 1) do={{ '
        + guard(f'[:tostr [/ip firewall nat get {nat_selector} out-interface-list]] != "WAN"', 'Package NAT WAN list changed; inspect before continuing') + ' }',
    ]
    identity = [
        guard(f'[/system resource get board-name] != {q(observed["model"])}', 'Wrong router model'),
        guard(f'[/system resource get version] != {q(observed["reported_version"])}', 'RouterOS changed; regenerate the package'),
        guard(f'[:len [/ip address find where address~{q("^"+str(peer).replace(".", "\\.")+"/")}]] != 1', 'Management address does not match this package'),
    ]
    if local:
        target = observed['local_target']
        management = next(p for p in observed['interfaces'] if p['name'] == target['management_interface'])
        identity += [
            guard(f'[:len [/interface bridge port find where interface={q(target["wan_interface"])}]] != 0', 'WAN port must remain separate from management'),
            guard(f'[:len [/interface list member find where list="WAN" interface={q(target["wan_interface"])}]] != 1', 'Approved WAN interface must belong to the WAN list'),
            guard(f'[:len [/interface find where name={q(management["name"])} type="ether" disabled=no]] != 1', 'Management Ethernet port changed'),
            guard(f'[:len [/ip address find where address~{q("^"+str(peer).replace(".", "\\.")+"/")} interface={q(management["bridge"] or management["name"])} disabled=no]] != 1', 'Management address binding changed'),
        ]
        if management['bridge']:
            identity.append(guard(f'[:len [/interface bridge port find where interface={q(management["name"])} bridge={q(management["bridge"])} disabled=no]] != 1', 'Management bridge membership changed'))
        else:
            identity.append(guard(f'[:len [/interface bridge port find where interface={q(management["name"])}]] != 0', 'Management port was bridged after discovery'))
    # Infrastructure secrets are never read, transmitted or logged.
    radius_selector = f'address={q(data.get("radius_server", ""))} disabled=no service~"hotspot"'
    service_checks = [
        guard('[:len [/ip firewall filter find where action=fasttrack-connection disabled=no]] != 0', 'Active FastTrack needs manual Hotspot policy review before using this lab package'),
        guard('[:len [/interface list find where name="WAN"]] != 1', 'A WAN interface list is required for scoped NAT'),
        guard('[/system device-mode get hotspot] != true', 'Hotspot device-mode is not enabled'),
    ]
    if not local_user:
        service_checks += [
            guard(f'[:len [/radius find where {radius_selector}]] != 1', 'Configure one existing enabled Hotspot RADIUS entry for this server first'),
            guard(f'[/radius get [/radius find where {radius_selector}] src-address] != {q(str(peer))}', 'RADIUS must use the registered management source address'),
        ]
    for p in clients:
        pname = q(p['name'])
        reported = next(row for row in observed['interfaces'] if row['name'] == p['name'])
        service_checks += [
            guard(f'[/interface get [/interface find where name={pname}] type] != {q(reported["type"])}', 'Client interface type changed'),
            guard(f'[:len [/ipv6 address find where interface={pname}]] != 0', 'Client interface has IPv6 addressing; inspect it manually'),
            guard(f'[:len [/interface find where name={pname} disabled=no]] != 1', 'A selected client interface is missing or disabled'),
            guard(f'[:len [/ip dhcp-client find where interface={pname}]] != 0', 'Client interface has a DHCP client'),
            guard(f'[:len [/interface list member find where interface={pname}]] != 0', 'Client interface belongs to an interface list; inspect it manually'),
            guard(f'[:len [/interface vlan find where interface={pname}]] != 0', 'Client interface has VLAN children'),
            guard(f'[:len [/interface pppoe-client find where interface={pname}]] != 0', 'Client interface has a PPPoE uplink'),
        ]
    # Reject bonds outright in this initial lab template; avoid indirectly moving slaves.
    service_checks.append(guard('[:len [/interface bonding find]] != 0', 'Bonded topologies require a later generator'))
    stage = identity + service_checks
    stage += [guard(f'[:len [/ip address find]] != {len(addresses)}', 'Addressing changed; rediscover')]
    for row in addresses:
        stage.append(guard(f'[:len [/ip address find where address={q(row["address"])} interface={q(row["interface"])}]] != 1', 'Addressing changed; rediscover'))
    stage.append(guard('[:len [/ip hotspot find]] != 0', 'Existing Hotspot detected; migration is not supported by this package'))
    for r in resources:
        stage.append(guard(f'[:len {find(r["path"], r["selector"])}] != 0', 'A target resource already exists. Inspect it or clean up this package before retrying'))
    # Do not automatically clean up an interrupted stage: preserve the evidence and
    # require the explicit, ownership-checked cleanup artifact.
    stage.append(':local stagingResource ""')
    stage.append(':do {')
    for r in resources:
        comment = '' if r['path'] in uncommented else f' comment={q(owner)}'
        initial_password = ' password=[:rndstr length=24]' if r['path'] == '/ip hotspot user' else ''
        stage.append(f'  :set stagingResource {q(r["path"])}')
        stage.append(f'  {r["path"]} add {r["properties"]}{comment}{initial_password}')
    stage += ['} on-error={ :error ("Staging stopped while creating " . $stagingResource . ". Services remain disabled. Inspect and run this package cleanup before retrying.") }', ':put "STAGED ONLY: services and bridge ports are disabled. Inspect, then use activate.rsc in the lab."']
    validate_owned = []
    for r in resources:
        validate_owned.append(guard(f'[:len {find(r["path"], owned(r))}] != 1', 'Package resources are missing or ownership changed; inspect before continuing'))
    activate = identity + service_checks + validate_owned + pool_checks + nat_checks
    if local_user:
        activate.append(guard(f'[:len [/ip hotspot user get [find where name={q(auxiliary)}] password]] < 8', 'Set a private test-user password of at least eight characters in WinBox before activation'))
    activate += [guard(f'[:len [/interface bridge port find where bridge={q(data["bridge"])}]] != {len(clients)}', 'Unexpected bridge members; activation refused'),
                 guard(f'[:len [/ip address find]] != {len(addresses)+1}', 'Addressing changed since staging')]
    for row in addresses:
        activate.append(guard(f'[:len [/ip address find where address={q(row["address"])} interface={q(row["interface"])}]] != 1', 'Addressing changed since staging'))
    # Binding checks catch edits to the highest impact owned objects.
    for r in resources:
        if r['path'] in ('/ip address', '/ip dhcp-server', '/ip hotspot', '/interface bridge port'):
            prop = 'bridge' if r['path']=='/interface bridge port' else 'interface'
            activate.append(guard(f'[{r["path"]} get {find(r["path"], owned(r))} {prop}] != {q(data["bridge"])}', 'Package interface binding changed'))
    switched = [r for r in resources if r['switch']]
    disable = [f'{r["path"]} set {find(r["path"], owned(r))} disabled=yes' for r in reversed(switched)]
    activate.append(':do {')
    # Enable client ports last, after Hotspot and DHCP, to avoid an access window.
    ordered = sorted(switched, key=lambda r: 3 if r['path']=='/interface bridge port' else 2 if r['path']=='/ip dhcp-server' else 1 if r['path']=='/ip hotspot' else 0)
    activate += [f'  {r["path"]} set {find(r["path"], owned(r))} disabled=no' for r in ordered]
    activate += ['} on-error={'] + [f'  :do {{ {line} }} on-error={{ :put "Disable failed; inspect package resources manually" }}' for line in disable] + ['  :error "Activation failed. Package disable attempted; inspect before retrying."', '}', ':put "ACTIVATED IN LAB: verify client login, isolation, DNS, RADIUS authentication and accounting. Dashboard readiness is unchanged."']
    cleanup = list(identity)
    cleanup.append(guard(f'[:len [/interface bridge find where name={q(data["bridge"])} comment={q(owner)}]] != 1', 'The package bridge ownership marker is missing. Inspect remaining resources manually'))
    # Check every ownership collision before ANY removal. Missing resources are OK
    # after partial staging/cleanup. Never remove an unowned name collision.
    for r in resources:
        cleanup.append(guard(f'[:len {find(r["path"], r["selector"])}] != [:len {find(r["path"], owned(r))}]', 'Ownership conflict; cleanup refused'))
    cleanup += pool_checks + nat_checks
    cleanup += [f':do {{ {line} }} on-error={{ :put "Disable failed; inspect before removal" }}' for line in disable]
    if local_user:
        cleanup.append(f'/ip hotspot active remove [find where user={q(auxiliary)} server={q(data["hotspot_name"])}]')
    cleanup += [f'{r["path"]} remove {find(r["path"], owned(r))}' for r in reversed(resources)]
    cleanup.append(':put "Package resources removed. Existing RADIUS credentials and network configuration were not changed."')
    if local_user:
        activate[-1] = ':put "LOCAL USER LAB ACTIVE: test DHCP and local login. System vouchers and RADIUS accounting are NOT verified."'
    def script(lines):
        return '\n'.join([f'# {VERSION} / {package_id}', '# LAB ONLY. Read README before importing. No hardware validation has been performed.', '{', *['  '+line for line in lines], '}', ''])
    readme = '\n'.join([
        f'Yarotech lab package {package_id} ({VERSION})',
        'This is executable, unvalidated lab software. It is not a production deployment certificate.',
        f'Target: {observed["model"]}, exact OS {observed["reported_version"]}, management {peer}.',
        'Use local/serial or independent management access and take a router backup before testing.',
        'Use RouterOS /import file-name=stage.rsc verbose=yes dry-run first (RouterOS 7.16+).',
        f'Connection mode: {"local LAN" if local else "WireGuard"}. Export does not change deployment status.',
        (f'1. LOCAL USER LAB. After staging, open WinBox > IP > Hotspot > Users > {auxiliary} and set a private test password before activation. Do not change its name, server, profile or limits.' if local_user else '1. Existing RADIUS Hotspot entry must already hold the correct shared secret and use the registered management source IP.'),
        '2. Import stage.rsc. Inspect disabled resources. Existing Hotspot installations are rejected.',
        f'3. Confirm the selected DNS resolver {dns} is reachable from clients before activation.',
        '4. Inspect firewall/IPv6/FastTrack policy and captive portal files. This template does not rewrite global firewall/DNS or install portal assets.',
        ('5. Import activate.rsc only in the lab. Test local-user login, rejection, logout, one-device limit, 2 Mbps speed, 15-minute sessions, one-hour total uptime and 100 MiB total quota. This does not validate system vouchers or RADIUS.' if local_user else '5. Import activate.rsc only in the lab. Check DHCP, DNS, client isolation, login, RADIUS auth/accounting and logout.'),
        '6. Import cleanup.rsc to remove this package, including after interrupted staging. It cannot restore later operator edits.',
        'Retry staging only after cleanup. Repeated activation sets the same owned resources enabled; it creates no duplicates.',
        'Import one script at a time. Concurrent manual router changes are outside the offline package transaction boundary.',
        'Offline files cannot be expired or revoked by the server after download. Delete obsolete copies; rediscover after network changes.',
        'No secrets, tokens or callback URLs are included. No successful import updates dashboard readiness.',
        'Secure credential bootstrap, existing-network migration and hardware acceptance remain separate Phase 4 work.',
    ])
    if local_user:
        readme += '\nLocal user password is initialized randomly on the router and is never sent to the backend. It is not an admin account. Cleanup removes this test user, profile and its active sessions. Limits are usage-based, not calendar expiry: clean up after testing.\nWithout internet, open http://' + str(gateway.ip) + '/login directly from a customer device. Default Hotspot login assets must exist on the router; inspect Files before activation. No internet/DNS availability is implied.\nTo switch to RADIUS later, clean up this lab package and create a new discovered RADIUS review; do not merely enable RADIUS while a local test account remains.\n'
    files = {'stage.rsc':script(stage), 'activate.rsc':script(activate), 'cleanup.rsc':script(cleanup), 'README.txt':readme}
    return {'id':package_id, 'generator':VERSION, 'lab_only':True, 'hardware_validated':False,
            'files':files, 'sha256':{name:hashlib.sha256(body.encode()).hexdigest() for name,body in files.items()}}
