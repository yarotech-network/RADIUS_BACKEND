"""Secret-free, explicitly lab-only RouterOS fresh-Hotspot artifacts.

No router IO occurs here. Generated scripts require an existing RADIUS entry;
credential bootstrap and migration of existing configurations are separate work.
"""
import hashlib
import ipaddress
import re
from uuid import UUID

from rest_framework.exceptions import ValidationError

from .discovery import compatibility
from .hotspot_setup import HotspotIntentSerializer

VERSION = 'hotspot-lab-fresh-v1'


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
    if data.get('inventory_id') != observed['id']:
        raise ValidationError({'detail': 'The review must use the latest discovered interfaces.'})
    if router.deployment_status != 'deployed' or not router.is_active or not router.wireguard_ip:
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
    radius = ipaddress.IPv4Address(data['radius_server'])
    peer = ipaddress.IPv4Address(router.wireguard_ip)
    dns = ipaddress.IPv4Address(dns_server)
    if dns in gateway.network or dns.is_loopback or dns.is_multicast or dns.is_unspecified:
        raise ValidationError({'dns_server': 'Use a reachable unicast DNS server outside the client subnet.'})
    if radius in gateway.network or peer in gateway.network or radius.is_loopback or radius.is_multicast or radius.is_unspecified:
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
    add('/ip hotspot profile', f'name={q(data["profile_name"])}', f'name={q(data["profile_name"])} hotspot-address={gateway.ip} use-radius=yes radius-accounting=yes radius-interim-update=5m login-by=http-chap')
    add('/ip hotspot', f'name={q(data["hotspot_name"])}', f'name={q(data["hotspot_name"])} interface={q(data["bridge"])} profile={q(data["profile_name"])} address-pool=none disabled=yes', True)
    add('/ip firewall nat', f'comment={q(owner)}', f'chain=srcnat src-address={network} out-interface-list=WAN action=masquerade disabled=yes', True)
    for p in clients:
        add('/interface bridge port', f'interface={q(p["name"])}', f'interface={q(p["name"])} bridge={q(data["bridge"])} disabled=yes', True)
    # Pools and Hotspot profiles do not offer a comment property in RouterOS; ownership is proven by a
    # dedicated named bridge marker plus the exact expected pool range.
    uncommented = ('/ip pool', '/ip hotspot profile')
    def owned(r):
        # Match all stable properties, not just a name. Operator edits require
        # manual inspection rather than activation or deletion of changed data.
        props = r['properties'].replace(' disabled=yes', '')
        return props + ('' if r['path'] in uncommented else f' comment={q(owner)}')
    identity = [
        guard(f'[/system resource get board-name] != {q(observed["model"])}', 'Wrong router model'),
        guard(f'[/system resource get version] != {q(observed["reported_version"])}', 'RouterOS changed; regenerate the package'),
        guard(f'[:len [/ip address find where address~{q("^"+str(peer).replace(".", "\\.")+"/")}]] != 1', 'Management address does not match this package'),
    ]
    # No secrets are read, transmitted or logged by any generated script.
    radius_selector = f'address={q(data["radius_server"])} disabled=no service~"hotspot"'
    service_checks = [
        guard('[:len [/ip firewall filter find where action=fasttrack-connection disabled=no]] != 0', 'Active FastTrack needs manual Hotspot policy review before using this lab package'),
        guard('[:len [/interface list find where name="WAN"]] != 1', 'A WAN interface list is required for scoped NAT'),
        guard('[/system device-mode get hotspot] != true', 'Hotspot device-mode is not enabled'),
        guard(f'[:len [/radius find where {radius_selector}]] != 1', 'Configure one existing enabled Hotspot RADIUS entry for this server first'),
        guard(f'[/radius get [/radius find where {radius_selector}] src-address] != {q(str(peer))}', 'RADIUS must use the registered management VPN source address'),
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
    stage.append(':do {')
    for r in resources:
        comment = '' if r['path'] in uncommented else f' comment={q(owner)}'
        stage.append(f'  {r["path"]} add {r["properties"]}{comment}')
    stage += ['} on-error={ :error "Staging stopped. Services remain disabled. Inspect and run this package cleanup before retrying." }', ':put "STAGED ONLY: services and bridge ports are disabled. Inspect, then use activate.rsc in the lab."']
    validate_owned = []
    for r in resources:
        validate_owned.append(guard(f'[:len {find(r["path"], owned(r))}] != 1', 'Package resources are missing or ownership changed; inspect before continuing'))
    activate = identity + service_checks + validate_owned
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
    cleanup += [f':do {{ {line} }} on-error={{ :put "Disable failed; inspect before removal" }}' for line in disable]
    cleanup += [f'{r["path"]} remove {find(r["path"], owned(r))}' for r in reversed(resources)]
    cleanup.append(':put "Package resources removed. Existing RADIUS credentials and network configuration were not changed."')
    def script(lines):
        return '\n'.join([f'# {VERSION} / {package_id}', '# LAB ONLY. Read README before importing. No hardware validation has been performed.', '{', *['  '+line for line in lines], '}', ''])
    readme = '\n'.join([
        f'Yarotech lab package {package_id} ({VERSION})',
        'This is executable, unvalidated lab software. It is not a production deployment certificate.',
        f'Target: {observed["model"]}, exact OS {observed["reported_version"]}, management {peer}.',
        'Use local/serial or independent management access and take a router backup before testing.',
        'Use RouterOS import verbose=yes dry-run=yes file-name=stage.rsc first (RouterOS 7.16+).',
        '1. Existing RADIUS Hotspot entry must already hold the correct shared secret and use the VPN source IP.',
        '2. Import stage.rsc. Inspect disabled resources. Existing Hotspot installations are rejected.',
        f'3. Confirm the selected DNS resolver {dns} is reachable from clients before activation.',
        '4. Inspect firewall/IPv6/FastTrack policy and captive portal files. This template does not rewrite global firewall/DNS or install portal assets.',
        '5. Import activate.rsc only in the lab. Check DHCP, DNS, client isolation, login, RADIUS auth/accounting and logout.',
        '6. Import cleanup.rsc to remove this package, including after interrupted staging. It cannot restore later operator edits.',
        'Retry staging only after cleanup. Repeated activation sets the same owned resources enabled; it creates no duplicates.',
        'Import one script at a time. Concurrent manual router changes are outside the offline package transaction boundary.',
        'Offline files cannot be expired or revoked by the server after download. Delete obsolete copies; rediscover after network changes.',
        'No secrets, tokens or callback URLs are included. No successful import updates dashboard readiness.',
        'Secure credential bootstrap, existing-network migration and hardware acceptance remain separate Phase 4 work.',
    ])
    files = {'stage.rsc':script(stage), 'activate.rsc':script(activate), 'cleanup.rsc':script(cleanup), 'README.txt':readme}
    return {'id':package_id, 'generator':VERSION, 'lab_only':True, 'hardware_validated':False,
            'files':files, 'sha256':{name:hashlib.sha256(body.encode()).hexdigest() for name,body in files.items()}}
