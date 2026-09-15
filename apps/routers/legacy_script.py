"""Deterministic legacy RouterOS renderer; no database, SSH or router calls.
Ported from yarotech-radius-system-current/routers/services.py.
Deployment-specific constants are explicit per-render configuration.
"""
import ipaddress
import re
from django.conf import settings
from .secret_store import secret_store
ROUTER_NAME_PATTERN = re.compile(r'^[A-Za-z0-9._:-]{1,64}$')
reveal = secret_store.decrypt

def get_clean_ip(value):
    return str(ipaddress.ip_address(str(value).split('/')[0]))

def _wireguard_service_networks(config):
    """Router-side peer Allowed Address list for tightly scoped YAROTECH services."""
    networks = [f'{config.RADIUS_SERVER_IP}/32']
    extra = getattr(settings, 'ROUTER_WIREGUARD_SERVICE_CIDRS', '') or ''
    for item in str(extra).split(','):
        value = item.strip()
        if not value:
            continue
        try:
            network = ipaddress.ip_network(value, strict=True)
        except ValueError as exc:
            raise ValueError('ROUTER_WIREGUARD_SERVICE_CIDRS must contain IPv4 /32 CIDRs only.') from exc
        if network.version != 4 or network.prefixlen != 32:
            raise ValueError('ROUTER_WIREGUARD_SERVICE_CIDRS must contain IPv4 /32 CIDRs only.')
        if not network.subnet_of(ipaddress.ip_network(config.WG_SUBNET_CIDR)):
            raise ValueError('ROUTER_WIREGUARD_SERVICE_CIDRS must stay inside the YAROTECH WireGuard subnet.')
        networks.append(str(network))
    return list(dict.fromkeys(networks))


def _validate_routeros_name(value, field_name):
    text = (value or '').strip()
    if not text:
        raise ValueError(f'{field_name} is required.')
    if not ROUTER_NAME_PATTERN.match(text):
        raise ValueError(f'{field_name} has unsupported characters. Use letters, numbers, dot, underscore, dash, or colon only.')
    return text


def _ros_escape(value):
    text = '' if value is None else str(value)
    text = text.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('\r', '').replace('\n', ' ')
    return text


def build_mikrotik_deployment_script(router, setup, config):
    network_setup = setup.get('hotspot_setup_v1')
    if network_setup:
        from .legacy_hotspot_setup import build_hotspot_sections
        before, after = build_hotspot_sections(router, network_setup)
        integration = build_mikrotik_deployment_script(
            router, {key: value for key, value in setup.items() if key != 'hotspot_setup_v1'}, config,
        )
        # The complete path validates/reuses profiles without resetting existing
        # login methods or sessions. Retain the existing VPN/RADIUS section.
        integration = integration.split('# Configure only the exact administrator-reviewed Hotspot profile.')[0]
        guard = ['# Check existing integration ownership before adding LAN objects.']
        for menu, comment in (
            ('/interface wireguard', 'YAROTECH-WG-INTERFACE'),
            ('/ip address', 'YAROTECH-WG-ADDRESS'),
            ('/interface wireguard peers', 'YAROTECH-WG-PEER'),
            ('/ip route', 'YAROTECH-RADIUS-ROUTE'),
            ('/radius', 'YAROTECH-CENTRAL-RADIUS'),
        ):
            guard.append(f':if ([:len [{menu} find where comment="{comment}"]] > 1) do={{ :error "Ambiguous existing integration object: {comment}" }}')
        guard += [
            f':if ([:len [/interface wireguard find where name="{_ros_escape(config.DEFAULT_WG_INTERFACE)}" and comment!="YAROTECH-WG-INTERFACE"]] > 0) do={{ :error "Unmanaged WireGuard interface name conflict" }}',
            ':if ([:len [/queue type find where name="hotspot-default"]] != 1) do={ :error "Required HotSpot queue type missing" }',
        ]
        registered_key = str(getattr(router, 'wireguard_public_key', '') or '').strip()
        if not registered_key:
            raise ValueError('Registered WireGuard public key is required for complete setup.')
        guard += [
            ':local yExistingWg [/interface wireguard find where comment="YAROTECH-WG-INTERFACE"]',
            f':if ([:len $yExistingWg] = 1) do={{ :if ([/interface wireguard get $yExistingWg public-key] != "{_ros_escape(registered_key)}") do={{ :error "Existing WireGuard identity belongs to a different registration; nothing changed" }} }}',
            ':local yExistingRadius [/radius find where comment="YAROTECH-CENTRAL-RADIUS"]',
        ]
        for attribute, expected in (
            ('address', config.RADIUS_SERVER_IP),
            ('src-address', get_clean_ip(router.wireguard_ip)),
            ('secret', reveal(getattr(router, 'radius_secret', '') or router.secret)),
        ):
            guard.append(f':if ([:len $yExistingRadius] = 1) do={{ :if ([:tostr [/radius get $yExistingRadius {attribute}]] != "{_ros_escape(expected)}") do={{ :error "Existing managed RADIUS identity differs; separate review required" }} }}')
        mutation_marker = ':put "YAROTECH stage 2: creating only missing compatible LAN/HotSpot objects"'
        before = before.replace(mutation_marker, '\n'.join(guard) + '\n' + mutation_marker, 1)
        return '{\n' + before + integration + after + '}\n'
    wg_ip = get_clean_ip(getattr(router, 'wireguard_ip', '') or setup.get('wireguard_ip') or '')
    if not wg_ip:
        raise ValueError('Router WireGuard IP is required before script generation.')

    hotspot_profile = _validate_routeros_name(
        setup.get('hotspot_profile_name') or getattr(router, 'hotspot_profile', '') or config.DEFAULT_HOTSPOT_PROFILE,
        'Hotspot profile',
    )
    hotspot_interface = _validate_routeros_name(
        setup.get('hotspot_interface') or getattr(router, 'hotspot_interface', '') or 'bridge',
        'Hotspot interface',
    )

    radius_secret = _ros_escape(reveal(getattr(router, 'radius_secret', '') or router.secret))
    vps_public_key = _ros_escape(setup.get('vps_public_key') or getattr(settings, 'WG_VPS_PUBLIC_KEY', config.DEFAULT_WG_VPS_PUBLIC_KEY) or config.DEFAULT_WG_VPS_PUBLIC_KEY)
    if not vps_public_key:
        raise ValueError('WireGuard VPS public key is not configured.')
    vps_endpoint = _ros_escape(setup.get('wireguard_endpoint') or getattr(settings, 'WG_VPS_ENDPOINT', config.WG_HUB_IP))
    router_private_key = _ros_escape(reveal(getattr(router, 'wireguard_private_key', '') or setup.get('router_private_key') or ''))
    if not router_private_key:
        raise ValueError('Router private key is required before script generation.')
    listen_port = int(getattr(router, 'wireguard_listen_port', 0) or setup.get('router_listen_port') or config.DEFAULT_WG_LISTEN_PORT)

    router_name = _ros_escape(router.name)
    tenant_name = _ros_escape(router.tenant.business_name)
    wg_name = _ros_escape(config.DEFAULT_WG_INTERFACE)
    wg_address = _ros_escape(f'{wg_ip}/32')
    # A tenant router receives only the explicitly configured YAROTECH service
    # /32 routes. Advertising the whole WireGuard subnet would permit attempts
    # to reach other tenant peers.
    service_networks = _wireguard_service_networks(config)
    wg_network = _ros_escape(','.join(service_networks))
    primary_route = _ros_escape(f'{config.RADIUS_SERVER_IP}/32')
    extra_routes = ''.join(
        f'''
:local managedServiceRoute{index} [/ip route find where comment="YAROTECH-SERVICE-ROUTE-{_ros_escape(network.replace('/', '_'))}"]
:if ([:len $managedServiceRoute{index}] > 1) do={{ :error "Multiple managed service routes found for {network}" }}
:if ([:len $managedServiceRoute{index}] = 0) do={{
    /ip route add \
        dst-address="{_ros_escape(network)}" \
        gateway=$wgName \
        comment="YAROTECH-SERVICE-ROUTE-{_ros_escape(network.replace('/', '_'))}"
}} else={{
    /ip route set \
        $managedServiceRoute{index} \
        dst-address="{_ros_escape(network)}" \
        gateway=$wgName \
        disabled=no
}}
'''
        for index, network in enumerate(service_networks[1:], start=1)
    )
    radius_server = _ros_escape(config.RADIUS_SERVER_IP)
    hotspot_profile_escaped = _ros_escape(hotspot_profile)
    hotspot_interface_escaped = _ros_escape(hotspot_interface)
    require_message_auth = getattr(settings, 'ROUTEROS_REQUIRE_MESSAGE_AUTH', 'yes-for-request-resp')
    valid_message_auth_values = {'no', 'yes', 'yes-for-request-resp'}
    if require_message_auth not in valid_message_auth_values:
        raise ValueError(
            'ROUTEROS_REQUIRE_MESSAGE_AUTH must be no, yes, or yes-for-request-resp.'
        )

    return f'''# ============================================
# YAROTECH AUTOMATIC RADIUS DEPLOYMENT
# Router: {router_name}
# Tenant: {tenant_name}
# WireGuard IP: {wg_ip}
# ============================================

:local wgName "{wg_name}"
:local wgSource "{wg_ip}"
:local wgNetwork "{wg_network}"
:local radiusServer "{radius_server}"
:local radiusSecret "{radius_secret}"
:local hotspotProfile "{hotspot_profile_escaped}"
:local hotspotInterface "{hotspot_interface_escaped}"
:local vpsPublicKey "{vps_public_key}"
:local vpsEndpoint "{vps_endpoint}"
:local vpsPort {config.WG_ENDPOINT_PORT}

# Create WireGuard interface when missing. Refuse to adopt an unrelated object
# that happens to use the configured name.
:local managedWg [/interface wireguard find where comment="YAROTECH-WG-INTERFACE"]
:if ([:len $managedWg] > 1) do={{ :error "Multiple managed WireGuard interfaces found" }}
:if ([:len $managedWg] = 0) do={{
    :if ([:len [/interface wireguard find where name=$wgName]] > 0) do={{
        :error "WireGuard interface name is already used by an unmanaged object"
    }}
    /interface wireguard add \
        name=$wgName \
        private-key="{router_private_key}" \
        listen-port={listen_port} \
        mtu=1420 \
        comment="YAROTECH-WG-INTERFACE"
}} else={{
    /interface wireguard set \
        $managedWg \
        name=$wgName \
        private-key="{router_private_key}" \
        listen-port={listen_port} \
        mtu=1420 \
        disabled=no \
        comment="YAROTECH-WG-INTERFACE"
}}
:set managedWg [/interface wireguard find where comment="YAROTECH-WG-INTERFACE"]
:if ([:len $managedWg] != 1) do={{ :error "Managed WireGuard interface could not be resolved" }}

# Create or update WireGuard IP address
:local managedAddress [/ip address find where comment="YAROTECH-WG-ADDRESS"]
:if ([:len $managedAddress] > 1) do={{ :error "Multiple managed WireGuard addresses found" }}
:if ([:len $managedAddress] = 0) do={{
    /ip address add \
        address={wg_address} \
        network={wg_ip} \
        interface=$managedWg \
        comment="YAROTECH-WG-ADDRESS"
}} else={{
    /ip address set \
        $managedAddress \
        address={wg_address} \
        network={wg_ip} \
        disabled=no
}}

# Create or update hub peer
:local managedPeer [/interface wireguard peers find where comment="YAROTECH-WG-PEER"]
:if ([:len $managedPeer] > 1) do={{ :error "Multiple managed WireGuard peers found" }}
:if ([:len $managedPeer] = 0) do={{
    /interface wireguard peers add \
        interface=$wgName \
        public-key=$vpsPublicKey \
        endpoint-address=$vpsEndpoint \
        endpoint-port=$vpsPort \
        allowed-address=$wgNetwork \
        persistent-keepalive=25s \
        comment="YAROTECH-WG-PEER"
}} else={{
    /interface wireguard peers set \
        $managedPeer \
        interface=$wgName \
        public-key=$vpsPublicKey \
        endpoint-address=$vpsEndpoint \
        endpoint-port=$vpsPort \
        allowed-address=$wgNetwork \
        persistent-keepalive=25s \
        disabled=no
}}

# Create or update WireGuard route
:local managedRoute [/ip route find where comment="YAROTECH-RADIUS-ROUTE"]
:if ([:len $managedRoute] > 1) do={{ :error "Multiple managed RADIUS routes found" }}
:if ([:len $managedRoute] = 0) do={{
    /ip route add \
        dst-address="{primary_route}" \
        gateway=$wgName \
        comment="YAROTECH-RADIUS-ROUTE"
}} else={{
    /ip route set \
        $managedRoute \
        dst-address="{primary_route}" \
        gateway=$wgName \
        disabled=no
}}
{extra_routes}

# Create or update central RADIUS entry
:local managedRadius [/radius find where comment="YAROTECH-CENTRAL-RADIUS"]
:if ([:len $managedRadius] > 1) do={{ :error "Multiple managed RADIUS entries found" }}
:if ([:len $managedRadius] = 0) do={{
    /radius add \
        address=$radiusServer \
        src-address=$wgSource \
        service=hotspot \
        secret=$radiusSecret \
        authentication-port={config.RADIUS_AUTH_PORT} \
        accounting-port={config.RADIUS_ACCT_PORT} \
        protocol=udp \
        timeout=3s \
        require-message-auth={require_message_auth} \
        comment="YAROTECH-CENTRAL-RADIUS"
}} else={{
    /radius set \
        $managedRadius \
        address=$radiusServer \
        src-address=$wgSource \
        service=hotspot \
        secret=$radiusSecret \
        authentication-port={config.RADIUS_AUTH_PORT} \
        accounting-port={config.RADIUS_ACCT_PORT} \
        protocol=udp \
        timeout=3s \
        require-message-auth={require_message_auth} \
        disabled=no
}}

# Verify the built-in Hotspot queue type required by dynamic user queues
:if ([:len [/queue type find where name="hotspot-default"]] = 0) do={{
    :error "YAROTECH deployment stopped: required queue type hotspot-default is missing"
}}

# Configure only the exact administrator-reviewed Hotspot profile.
:local managedProfile [/ip hotspot profile find where name=$hotspotProfile]
:if ([:len $managedProfile] > 1) do={{ :error "Multiple managed Hotspot profiles found" }}
:if ([:len $managedProfile] > 0) do={{
    /ip hotspot profile set \
        $managedProfile \
        use-radius=yes \
        login-by=http-chap,http-pap \
        radius-accounting=yes \
        radius-interim-update=1m
}} else={{
    :error ("YAROTECH deployment stopped: selected Hotspot profile does not exist")
}}

# Verify the exact enabled Hotspot server interface/profile pair reviewed by the administrator.
:if ([:len [/ip hotspot find where interface=$hotspotInterface and profile=$hotspotProfile and disabled=no]] != 1) do={{
    :error ("YAROTECH deployment stopped: the reviewed Hotspot interface/profile pair is not uniquely active")
}}

:put "YAROTECH automatic deployment completed."
:put "WireGuard address configured."
:put ("RADIUS server: " . $radiusServer)
:put ("Hotspot profile: " . $hotspotProfile)
:put ("Hotspot interface: " . $hotspotInterface)
'''
