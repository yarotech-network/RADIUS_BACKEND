"""Offline validation and conservative RouterOS 7.17+ HotSpot provisioning.

No router API calls are made here. Existing objects are compared, not adopted
by comment or overwritten. RouterOS imports are not transactions.
"""
import ipaddress
import re
import uuid
from django.conf import settings

from django.core.exceptions import ValidationError


FIELDS = (
    'network_mode', 'gateway_cidr', 'dhcp_range', 'dns_servers',
    'hotspot_dns_name', 'reuse_pool', 'reuse_dhcp', 'reuse_hotspot', 'nat_mode', 'wan_interface', 'dhcp_range_mode',
)


def lan_gateway(value):
    """Validate an explicit RFC1918 LAN and preserve the VPN exclusion."""
    value = str(value or '').strip()
    try:
        if not re.fullmatch(r'[0-9.]+/[0-9]{1,2}', value):
            raise ValueError()
        gateway = ipaddress.IPv4Interface(value)
    except ValueError as exc:
        raise ValidationError('Enter a valid IPv4 gateway and subnet prefix (for example, /24).') from exc
    network = gateway.network
    if network.prefixlen >= 31:
        raise ValidationError('/31 and /32 networks have no usable DHCP range after excluding the gateway.')
    if gateway.ip in (network.network_address, network.broadcast_address):
        raise ValidationError('The gateway cannot be the network or broadcast address.')
    if not any(network.subnet_of(ipaddress.IPv4Network(block)) for block in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValidationError('Use a private LAN subnet, not a public, loopback or reserved network.')
    if network.overlaps(ipaddress.IPv4Network(settings.WG_MANAGED_SUBNET)):
        raise ValidationError('The LAN subnet must not overlap the WireGuard VPN subnet.')
    return gateway


def automatic_dhcp_range(value):
    """O(1) IPv4 arithmetic; choose the lower interval on equal lengths."""
    gateway = lan_gateway(value)
    first, last, excluded = int(gateway.network.network_address)+1, int(gateway.network.broadcast_address)-1, int(gateway.ip)
    intervals = [(first, excluded-1), (excluded+1, last)]
    start, end = max((pair for pair in intervals if pair[0] <= pair[1]), key=lambda pair: (pair[1]-pair[0]+1, -pair[0]))
    return f'{ipaddress.IPv4Address(start)}-{ipaddress.IPv4Address(end)}'


def name(value, label):
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', value or ''):
        raise ValidationError(f'{label}: use an exact interface/object name containing letters, digits, dot, dash or underscore.')
    return value


def validate_setup(data):
    result = {key: str(data.get(key) or '').strip() for key in FIELDS}
    # Older saved scripts specified their range explicitly; never enlarge them.
    result['dhcp_range_mode'] = result['dhcp_range_mode'] or 'custom'
    if result['dhcp_range_mode'] not in ('automatic', 'custom'):
        raise ValidationError('Select automatic DHCP or a custom DHCP range.')
    if result['network_mode'] not in {'create', 'reuse'}:
        raise ValidationError('Select create or reuse for the LAN/DHCP network.')
    gateway = lan_gateway(result['gateway_cidr'])
    network = gateway.network
    if result['dhcp_range_mode'] == 'automatic':
        result['dhcp_range'] = automatic_dhcp_range(result['gateway_cidr'])
    try:
        start, end = [ipaddress.IPv4Address(v.strip()) for v in result['dhcp_range'].split('-')]
        if not (network.network_address < start <= end < network.broadcast_address):
            raise ValueError()
        if start <= gateway.ip <= end:
            raise ValueError()
        dns = [ipaddress.IPv4Address(v.strip()) for v in result['dns_servers'].split(',')]
        if not 1 <= len(dns) <= 3 or any(v.is_unspecified or v.is_multicast or v.is_loopback or v == gateway.ip for v in dns):
            raise ValueError()
    except ValueError as exc:
        raise ValidationError('Enter a DHCP range inside the LAN subnet excluding network, broadcast and gateway addresses, and 1–3 upstream DNS IPv4 addresses.') from exc
    domain = result['hotspot_dns_name'].lower()
    if len(domain) > 253 or '.' not in domain or not all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
        for label in domain.split('.')
    ):
        raise ValidationError('Enter a valid local HotSpot DNS name, for example login.example.lan.')
    if result['network_mode'] == 'reuse':
        name(result['reuse_pool'], 'Existing pool')
        name(result['reuse_dhcp'], 'Existing DHCP server')
    if result['reuse_hotspot']:
        name(result['reuse_hotspot'], 'Existing HotSpot server')
    if result['nat_mode'] not in {'existing', 'interface', 'interface-list'}:
        raise ValidationError('Select existing NAT/routed upstream, or an explicit WAN interface/interface-list.')
    if result['nat_mode'] != 'existing':
        name(result['wan_interface'], 'WAN')
    result.update(gateway_cidr=str(gateway), dhcp_range=f'{start}-{end}',
                  dns_servers=','.join(map(str, dns)), hotspot_dns_name=domain)
    return result


def build_hotspot_sections(router, data):
    """Return (preflight + create/reuse, finalize); never touch live sessions.

    RouterOS Reset HTML provisions its own CHAP/PAP assets, avoiding an
    unverified external portal dependency. Existing custom HTML is not reset.
    """
    data = validate_setup(data)
    lan = name(router.hotspot_interface, 'LAN interface')
    profile = name(router.hotspot_profile, 'HotSpot profile')
    try:
        identity = uuid.UUID(str(router.pk)).hex
    except (ValueError, AttributeError):
        raise ValidationError('A persisted router UUID is required.') from None
    stem = f'yaro-{identity}'
    gateway = ipaddress.IPv4Interface(data['gateway_cidr'])
    network = str(gateway.network)
    pool = data['reuse_pool'] if data['network_mode'] == 'reuse' else f'{stem}-pool'
    dhcp = data['reuse_dhcp'] if data['network_mode'] == 'reuse' else f'{stem}-dhcp'
    server = data['reuse_hotspot'] or f'{stem}-hotspot'
    # RADIUS uses the built-in default unless it returns Mikrotik-Group.
    # A newly created, unselected yaro-*-users profile would have no effect.
    # Values below are validated IPs, constrained names or DNS labels.
    pre = [
        '# Complete HotSpot setup: RouterOS 7.17+; no interactive setup or reboot.',
        '# IMPORT IS NOT ATOMIC. Stages are logged without credentials.',
        '# On failure: stop, retain the exact stage/error, fix that conflict, then reimport.',
        f'# Only objects named {stem}-* are created; do not bulk-remove other objects.',
        ':local yVersion [/system resource get version]',
        ':if ((($yVersion . " ") ~ "^7[.](1[7-9]|[2-9][0-9])[. ]") = false) do={ :error "RouterOS 7.17 or newer stable 7.x is required; no automatic upgrade" }',
        '# Convert only decimal octet strings to numbers; RouterOS :tonum does not accept ip values.',
        ':local yIpNumber do={',
        '  :if ([:typeof $1] != "ip") do={ :error "Expected IPv4 address; nothing changed" }',
        '  :local yText [:tostr $1]',
        '  :local yStart 0',
        '  :local yNumber 0',
        '  :for yOctet from=0 to=3 do={',
        '    :local yDot [:find $yText "." $yStart]',
        '    :if ([:typeof $yDot] = "nil") do={ :set yDot [:len $yText] }',
        '    :local yPart [:tonum [:pick $yText $yStart $yDot]]',
        '    :if ([:typeof $yPart] != "num") do={ :error "Invalid IPv4 octet; nothing changed" }',
        '    :if (($yPart < 0) || ($yPart > 255)) do={ :error "IPv4 octet out of range; nothing changed" }',
        '    :set yNumber (($yNumber * 256) + $yPart)',
        '    :set yStart ($yDot + 1)',
        '  }',
        '  :return $yNumber',
        '}',
        ':if ([/system device-mode get hotspot] != true) do={ :error "HotSpot blocked by device-mode: operator must enable HotSpot with physical confirmation separately" }',
        f':if ([:len [/interface find where name="{lan}" and disabled=no]] != 1) do={{ :error "LAN interface missing or disabled" }}',
        f':local yLanType [/interface get [find where name="{lan}"] type]',
        ':if (($yLanType != "bridge") && ($yLanType != "ether") && ($yLanType != "vlan")) do={ :error "LAN must be an existing bridge, Ethernet or VLAN interface" }',
        f':if ([:len [/interface bridge port find where interface="{lan}"]] != 0) do={{ :error "LAN is a bridge slave: select its bridge instead" }}',
        f':local yGateway {gateway.ip}',
        f':local yNetwork {network}',
        f':local yHtml "{stem}-portal"',
        ':if ([:len [/file find where name="flash"]] = 1) do={ :set yHtml ("flash/" . $yHtml) }',
        ':put "YAROTECH stage 1: checking LAN, DHCP, HotSpot and portal conflicts"',
    ]
    # Every conflicting object is rejected before any add/set command.
    pre += [
        ':foreach yId in=[/ip address find where disabled=no] do={',
        '  :local yAddress [:tostr [/ip address get $yId address]]',
        '  :local yIp [:toip [:pick $yAddress 0 [:find $yAddress "/"]]]',
        '  :local yPrefix [:tonum [:pick $yAddress ([:find $yAddress "/"] + 1) [:len $yAddress]]]',
        '  :if (([:typeof $yIp] != "ip") || ([:typeof $yPrefix] != "num")) do={ :error "Invalid existing IPv4 prefix; nothing changed" }',
        '  :if (($yPrefix < 0) || ($yPrefix > 32)) do={ :error "Existing IPv4 prefix out of range; nothing changed" }',
        '  :local yMask 0.0.0.0',
        '  :if ($yPrefix > 0) do={ :set yMask (255.255.255.255 << (32 - $yPrefix)) }',
        f'  :if (($yIp in $yNetwork) || (($yGateway & $yMask) = ($yIp & $yMask)) || ([/ip address get $yId interface] = "{lan}")) do={{',
        f'    :if (([:tostr $yAddress] != "{gateway}") || ([/ip address get $yId interface] != "{lan}")) do={{ :error "Overlapping or conflicting LAN address; resolve manually" }}',
        '  }',
        '}',
    ]
    objects = [
        ('/ip pool', f'name="{pool}"', {'ranges': data['dhcp_range'], 'next-pool': 'none'}, f'name="{pool}" ranges="{data["dhcp_range"]}"'),
        ('/ip dhcp-server network', f'address="{network}"', {'gateway': str(gateway.ip), 'dns-server': data['dns_servers']}, f'address={network} gateway={gateway.ip} dns-server="{data["dns_servers"]}"'),
        ('/ip dhcp-server', f'name="{dhcp}"', {'interface': lan, 'address-pool': pool, 'disabled': 'false'}, f'name="{dhcp}" interface="{lan}" address-pool="{pool}" lease-time=1h disabled=no'),
        ('/ip hotspot profile', f'name="{profile}"', {'hotspot-address': str(gateway.ip), 'dns-name': data['hotspot_dns_name'], 'use-radius': 'true', 'radius-accounting': 'true'}, f'name="{profile}" hotspot-address={gateway.ip} dns-name="{data["hotspot_dns_name"]}" html-directory=$yHtml use-radius=yes radius-accounting=yes radius-interim-update=1m login-by=mac,cookie,http-chap,http-pap,mac-cookie mac-auth-mode=mac-as-username-and-password'),
        ('/ip hotspot user profile', 'name="default"', {}, None),
        ('/ip hotspot', f'name="{server}"', {'interface': lan, 'profile': profile}, f'name="{server}" interface="{lan}" profile="{profile}" address-pool="{pool}" idle-timeout=1m disabled=yes'),
    ]
    for index, (menu, selector, properties, _) in enumerate(objects):
        pre.append(f':local yObj{index} [{menu} find where {selector}]')
        pre.append(f':if ([:len $yObj{index}] > 1) do={{ :error "Ambiguous {menu} object" }}')
        if data['network_mode'] == 'reuse' and index < 3:
            pre.append(f':if ([:len $yObj{index}] != 1) do={{ :error "Requested reusable LAN/DHCP object missing" }}')
        for key, value in properties.items():
            if index == 0 and key == 'ranges' and data['dhcp_range_mode'] == 'automatic':
                # Reuse the selected compatible pool exactly as it is; no pool set command.
                pre += [
                    ':if ([:len $yObj0] = 1) do={',
                    '  :local yRanges [:toarray [/ip pool get $yObj0 ranges]]',
                    '  :if ([:len $yRanges] = 0) do={ :error "Existing pool is empty; manual review required" }',
                    '  :foreach yRange in=$yRanges do={',
                    '    :local yDash [:find $yRange "-"]',
                    '    :local yFirst [:toip $yRange]',
                    '    :local yLast $yFirst',
                    '    :if ([:typeof $yDash] != "nil") do={ :set yFirst [:toip [:pick $yRange 0 $yDash]]; :set yLast [:toip [:pick $yRange ($yDash + 1) [:len $yRange]]] }',
                    '    :if (([:typeof $yFirst] != "ip") || ([:typeof $yLast] != "ip")) do={ :error "Existing pool range format requires manual review" }',
                    f'    :if (([$yIpNumber $yFirst] <= {int(gateway.network.network_address)}) || ([$yIpNumber $yLast] >= {int(gateway.network.broadcast_address)}) || ([$yIpNumber $yFirst] > [$yIpNumber $yLast]) || (([$yIpNumber $yFirst] <= [$yIpNumber $yGateway]) && ([$yIpNumber $yLast] >= [$yIpNumber $yGateway]))) do={{ :error "Existing pool conflicts with LAN subnet or gateway; nothing overwritten" }}',
                    '  }',
                    '  :put "Compatible existing DHCP pool retained without expansion"',
                    '}',
                ]
                continue
            actual = f'[:tostr [{menu} get $yObj{index} {key}]]'
            expected = f'"{value}"'
            if key == 'radius-interim-update':
                actual, expected = f'[{menu} get $yObj{index} {key}]', '1m'
            elif key in {'dns-server', 'ranges'}:
                actual = f'[:tostr [:toarray [{menu} get $yObj{index} {key}]]]'
                expected = f'[:tostr [:toarray "{value}"]]'
            pre.append(f':if ([:len $yObj{index}] = 1) do={{ :if ({actual} != {expected}) do={{ :error "Conflicting {menu} {key}; nothing overwritten" }} }}')
    pre += [
        ':foreach yId in=[/ip pool find] do={',
        f'  :if ([/ip pool get $yId name] != "{pool}") do={{',
        '    :foreach yRange in=[:toarray [/ip pool get $yId ranges]] do={',
        '      :local yDash [:find $yRange "-"]',
        '      :local yFirst [:toip $yRange]',
        '      :local yLast $yFirst',
        '      :if ([:typeof $yDash] != "nil") do={ :set yFirst [:toip [:pick $yRange 0 $yDash]]; :set yLast [:toip [:pick $yRange ($yDash + 1) [:len $yRange]]] }',
        '      :if (([:typeof $yFirst] != "ip") || ([:typeof $yLast] != "ip")) do={ :error "Pool range format requires manual review" }',
        f'      :if (([$yIpNumber $yFirst] <= {int(gateway.network.broadcast_address)}) && ([$yIpNumber $yLast] >= {int(gateway.network.network_address)})) do={{ :error "Another pool overlaps selected LAN" }}',
        '    }',
        '  }',
        '}',
        ':foreach yId in=[/ip dhcp-server network find] do={',
        '  :local yAddress [:tostr [/ip dhcp-server network get $yId address]]',
        f'  :if ($yAddress != "{network}") do={{',
        '    :local yIp [:toip [:pick $yAddress 0 [:find $yAddress "/"]]]',
        '    :local yPrefix [:tonum [:pick $yAddress ([:find $yAddress "/"] + 1) [:len $yAddress]]]',
        '    :if (([:typeof $yIp] != "ip") || ([:typeof $yPrefix] != "num")) do={ :error "Invalid existing DHCP prefix; nothing changed" }',
        '    :if (($yPrefix < 0) || ($yPrefix > 32)) do={ :error "Existing DHCP prefix out of range; nothing changed" }',
        '    :local yMask 0.0.0.0',
        '    :if ($yPrefix > 0) do={ :set yMask (255.255.255.255 << (32 - $yPrefix)) }',
        '    :if (($yIp in $yNetwork) || (($yGateway & $yMask) = ($yIp & $yMask))) do={ :error "Overlapping DHCP network requires manual review" }',
        '  }',
        '}',
        f':if ([:len [/ip dhcp-server find where interface="{lan}" and name!="{dhcp}"]] > 0) do={{ :error "Another DHCP server uses LAN" }}',
        f':if ([:len [/ip dhcp-server find where address-pool="{pool}" and name!="{dhcp}"]] > 0) do={{ :error "Selected pool is shared with another DHCP server" }}',
        f':if ([:len [/ip hotspot find where address-pool="{pool}" and name!="{server}"]] > 0) do={{ :error "Selected pool is shared with another HotSpot" }}',
        f':if ([:len [/ip hotspot user profile find where address-pool="{pool}"]] > 0) do={{ :error "Selected pool is shared with a user profile; review manually" }}',
        f':if ([:len [/ppp profile find where local-address="{pool}" or remote-address="{pool}"]] > 0) do={{ :error "Selected pool is shared with PPP; review manually" }}',
        f':if ([:len [/ip pool find where next-pool="{pool}"]] > 0) do={{ :error "Selected pool is chained from another pool" }}',
        f':if ([:len [/ip hotspot find where interface="{lan}" and name!="{server}"]] > 0) do={{ :error "Another HotSpot uses LAN; request reviewed reuse mapping" }}',
        f':if ([:len [/ip hotspot find where profile="{profile}" and name!="{server}"]] > 0) do={{ :error "HotSpot profile is shared with another server" }}',
        *([f':if ([:len $yObj5] != 1) do={{ :error "Requested existing HotSpot server missing" }}', f':if ([/ip hotspot get $yObj5 disabled] = true) do={{ :error "Existing HotSpot is disabled; activation needs separate review" }}'] if data['reuse_hotspot'] else []),
        ':if ([:len $yObj3] = 1) do={ :set yHtml [/ip hotspot profile get $yObj3 html-directory] }',
        ':if ([:len $yObj3] = 1) do={',
        f'  :if (($yHtml != "{stem}-portal") && ($yHtml != "flash/{stem}-portal")) do={{',
        '    :foreach yFile in={"login.html";"md5.js";"api.json"} do={',
        '      :if ([:len [/file find where name=($yHtml . "/" . $yFile)]] != 1) do={ :error "Existing custom portal incomplete; no automatic reset" }',
        '    }',
        '  }',
        '}',
        ':if ([:len $yObj5] = 1) do={',
        '  :if ([/ip hotspot get $yObj5 disabled] = false) do={',
        '    :foreach yFile in={"login.html";"md5.js";"api.json"} do={',
        '      :if ([:len [/file find where name=($yHtml . "/" . $yFile)]] != 1) do={ :error "Existing active HotSpot assets missing; no automatic reset" }',
        '    }',
        '  }',
        '}',
    ]
    # Ownership is not inferred from a name alone: require the complete saved
    # gateway/pool/DHCP/server/profile bundle, the per-router portal path, and
    # the integration ownership guards inserted by the shared outer renderer.
    # Explicit unrelated HotSpot reuse is read-only when already compatible.
    pre += [
        ':local yOwnedHotspot false',
        f':if (([:len $yObj0] = 1) && ([:len $yObj1] = 1) && ([:len $yObj2] = 1) && ([:len $yObj3] = 1) && ([:len $yObj5] = 1) && ([:len [/ip address find where address="{gateway}" and interface="{lan}" and disabled=no]] = 1) && ("{server}" = "{stem}-hotspot") && (($yHtml = "{stem}-portal") || ($yHtml = "flash/{stem}-portal"))) do={{ :set yOwnedHotspot true }}',
        ':local ySetServer false',
        ':if ([:len $yObj5] = 1) do={',
        '  :local yOldPool [/ip hotspot get $yObj5 address-pool]',
        f'  :if (($yOldPool != "{pool}") && ($yOldPool != "none")) do={{ :error "HotSpot pool differs from reviewed LAN pool; nothing overwritten" }}',
        f'  :if (($yOldPool != "{pool}") || ([/ip hotspot get $yObj5 idle-timeout] != 1m)) do={{',
        '    :if ($yOwnedHotspot = false) do={ :error "HotSpot settings differ on an unrelated or incomplete setup; review ownership" }',
        '    :set ySetServer true',
        '  }',
        '}',
        ':local yWantedLogin "mac,cookie,http-chap,http-pap,mac-cookie"',
        ':local ySetProfile false',
        ':if ([:len $yObj3] = 1) do={',
        '  :local yLoginBy [:toarray [/ip hotspot profile get $yObj3 login-by]]',
        '  :if ("https" in $yLoginBy) do={ :set yWantedLogin ($yWantedLogin . ",https") }',
        '  :foreach yMethod in=$yLoginBy do={',
        '    :if (!($yMethod in [:toarray $yWantedLogin])) do={ :error "Existing login method requires manual review; nothing overwritten" }',
        '  }',
        '  :foreach yMethod in=[:toarray $yWantedLogin] do={ :if (!($yMethod in $yLoginBy)) do={ :set ySetProfile true } }',
        '  :if ([/ip hotspot profile get $yObj3 mac-auth-mode] != "mac-as-username-and-password") do={ :set ySetProfile true }',
        '  :if ($ySetProfile && ($yOwnedHotspot = false)) do={ :error "Authentication settings differ on an unrelated or incomplete profile; review ownership" }',
        '}',
        '# Effective RADIUS user profile: default, unless Mikrotik-Group selects another existing profile.',
        ':if ([:len $yObj4] != 1) do={ :error "Effective default HotSpot user profile missing or ambiguous" }',
        ':local ySetCookie false',
        ':foreach yUserProfile in=[/ip hotspot user profile find] do={',
        '  :if ([/ip hotspot user profile get $yUserProfile add-mac-cookie] != true) do={',
        '    :if ([/ip hotspot user profile get $yUserProfile name] != "default") do={ :error "Possible RADIUS-selected user profile disables MAC cookies; manual profile review required" }',
        f'    :if ([:len [/ip hotspot find where name!="{server}"]] > 0) do={{ :error "Default user profile is shared with another HotSpot; nothing changed" }}',
        f'    :if ([:len [/ip hotspot user find where profile="default" and server!="{server}"]] > 0) do={{ :error "Default user profile has unrelated or all-server local users; nothing changed" }}',
        '    :if (([:len $yObj5] = 1) && ($yOwnedHotspot = false)) do={ :error "Default user profile ownership is not established" }',
        '    :set ySetCookie true',
        '  }',
        '}',
        ':if (($ySetServer || $ySetProfile || $ySetCookie) && ([:len $yObj5] = 1)) do={',
        '  :if (([:len [/interface wireguard find where comment="YAROTECH-WG-INTERFACE"]] != 1) || ([:len [/radius find where comment="YAROTECH-CENTRAL-RADIUS"]] != 1)) do={ :error "Existing setup lacks authoritative integration ownership; nothing changed" }',
        '}',
        '# User/shared/session timeouts and cookie lifetimes are deliberately not changed.',
    ]
    # A proposed range is not evidence that its addresses are free. Read leases
    # and static reservations before any mutation; never clear or rewrite them.
    pre += [
        f':local yEffectiveRanges [:toarray "{data["dhcp_range"]}"]',
        ':if ([:len $yObj0] = 1) do={ :set yEffectiveRanges [:toarray [/ip pool get $yObj0 ranges]] }',
        ':foreach yLease in=[/ip dhcp-server lease find] do={',
        '  :local yLeaseIp [:toip [/ip dhcp-server lease get $yLease address]]',
        '  :if ([:typeof $yLeaseIp] = "ip") do={',
        '    :if ($yLeaseIp = $yGateway) do={ :error "DHCP reservation or lease conflicts with gateway" }',
        '    :foreach yRange in=$yEffectiveRanges do={',
        '      :local yDash [:find $yRange "-"]',
        '      :local yFirst [:toip $yRange]',
        '      :local yLast $yFirst',
        '      :if ([:typeof $yDash] != "nil") do={ :set yFirst [:toip [:pick $yRange 0 $yDash]]; :set yLast [:toip [:pick $yRange ($yDash + 1) [:len $yRange]]] }',
        '      :if (([$yIpNumber $yLeaseIp] >= [$yIpNumber $yFirst]) && ([$yIpNumber $yLeaseIp] <= [$yIpNumber $yLast])) do={',
        f'        :if (([:len $yObj0] != 1) || ([:len $yObj2] != 1) || ([/ip dhcp-server lease get $yLease server] != "{dhcp}")) do={{ :error "Existing DHCP lease or reservation overlaps proposed pool; review custom range or explicit reuse" }}',
        '      }',
        '    }',
        '  } else={ :error "DHCP lease address requires manual review; nothing overwritten" }',
        '}',
    ]
    if data['network_mode'] == 'reuse':
        pre.append(f':if ([:len [/ip address find where interface="{lan}" and address="{gateway}" and disabled=no]] != 1) do={{ :error "Reusable gateway address missing" }}')
    if data['nat_mode'] != 'existing':
        wan = data['wan_interface']
        if wan == lan:
            raise ValidationError('WAN and LAN must be different.')
        menu = '/interface list' if data['nat_mode'] == 'interface-list' else '/interface'
        prop = 'out-interface-list' if data['nat_mode'] == 'interface-list' else 'out-interface'
        pre.append(f':if ([:len [{menu} find where name="{wan}"]] != 1) do={{ :error "Selected WAN missing" }}')
        if data['nat_mode'] == 'interface-list':
            pre.append(f':if ([:len [/interface list member find where list="{wan}" and interface="{lan}"]] != 0) do={{ :error "LAN belongs to selected WAN list; review NAT selection" }}')
        objects.append(('/ip firewall nat', f'comment="{stem}-nat"', {}, f'chain=srcnat action=masquerade src-address={network} {prop}="{wan}" comment="{stem}-nat"'))
        pre += [
            f':local yNat [/ip firewall nat find where comment="{stem}-nat"]',
            ':if ([:len $yNat] > 1) do={ :error "Ambiguous managed NAT rule" }',
        ]
        for key, value in {'chain': 'srcnat', 'action': 'masquerade', 'src-address': network, prop: wan, 'disabled': 'false'}.items():
            pre.append(f':if ([:len $yNat] = 1) do={{ :if ([:tostr [/ip firewall nat get $yNat {key}]] != "{value}") do={{ :error "Managed NAT conflict" }} }}')
    pre.append(':put "YAROTECH stage 2: creating only missing compatible LAN/HotSpot objects"')
    pre.append(f':if ([:len [/ip address find where interface="{lan}" and address="{gateway}"]] = 0) do={{ /ip address add address={gateway} interface="{lan}" comment="{stem}-gateway" }}')
    for menu, selector, _, arguments in objects:
        if arguments is None:
            continue  # Built-in effective default must exist; never create bypass users/profiles.
        pre.append(f':if ([:len [{menu} find where {selector}]] = 0) do={{ {menu} add {arguments} }}')
    pre += [
        f':if ($ySetServer) do={{ /ip hotspot set $yObj5 address-pool="{pool}" idle-timeout=1m }}',
        ':if ($ySetProfile) do={ /ip hotspot profile set $yObj3 login-by=$yWantedLogin mac-auth-mode=mac-as-username-and-password }',
        ':if ($ySetCookie) do={ /ip hotspot user profile set $yObj4 add-mac-cookie=yes }',
    ]
    pre += [
        ':put "YAROTECH stage 3: validating built-in captive portal files"',
        ':local yMissing false',
        ':foreach yFile in={"login.html";"md5.js";"api.json"} do={',
        '  :if ([:len [/file find where name=($yHtml . "/" . $yFile)]] = 0) do={ :set yMissing true }',
        '}',
        f':if ($yMissing) do={{ /ip hotspot reset-html [find where name="{server}" and disabled=yes] }}',
        ':foreach yFile in={"login.html";"md5.js";"api.json"} do={',
        '  :local yFileId [/file find where name=($yHtml . "/" . $yFile)]',
        '  :if ([:len $yFileId] != 1) do={ :error "Portal provisioning failed; HotSpot left disabled. Inspect storage and stage 3" }',
        '  :if ([/file get $yFileId size] = 0) do={ :error "Empty portal asset; stop and review storage" }',
        '}',
        '# DNS resolvers are advertised by DHCP only. Global allow-remote-requests is unchanged.',
        '# Existing management services, bridge ports, VLANs and firewall rules are not rewritten.',
    ]
    for host in ('radius.yarotech.com.ng', 'checkout.paystack.com', 'standard.paystack.co'):
        pre.append(f':if ([:len [/ip hotspot walled-garden find where server="{server}" and dst-host="{host}" and action=allow]] = 0) do={{ /ip hotspot walled-garden add server="{server}" dst-host="{host}" action=allow comment="{stem}-portal" }}')
    finish = f'\n:put "YAROTECH stage 5: integration complete; enabling the new HotSpot only"\n' + ('' if data['reuse_hotspot'] else f'/ip hotspot enable [find where name="{server}" and disabled=yes]\n') + ':put "YAROTECH HotSpot import complete; verify one controlled client before customer rollout"\n'
    return '\n'.join(pre) + '\n:put "YAROTECH stage 4: existing WireGuard/RADIUS integration"\n', finish
