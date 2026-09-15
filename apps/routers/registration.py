"""Self-service router registration; credentials never enter public CRUD payloads."""
import base64
import hashlib
import ipaddress
import secrets
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction
from django.utils.text import slugify
from rest_framework import serializers

from .legacy_hotspot_setup import validate_setup, name as validate_name
from .legacy_script import build_mikrotik_deployment_script
from .models import NASDevice, RouterRegistration, RouterOperation, RouterAuditEvent
from .provisioners import validate_wireguard_public_key
from .secret_store import secret_store


class RegistrationSerializer(serializers.Serializer):
    name = serializers.RegexField(r'^[A-Za-z0-9 ._:-]{1,64}$')
    nas_identifier = serializers.RegexField(r'^[A-Za-z0-9._:-]{1,120}$', required=False, allow_blank=True, default='')
    hotspot_interface = serializers.CharField(max_length=64)
    hotspot_profile = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    location = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    model = serializers.RegexField(r'^[A-Za-z0-9][A-Za-z0-9 +_.-]{0,79}$', required=False, allow_blank=True, default='')
    routeros_version = serializers.RegexField(r'^[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[a-zA-Z0-9.-]*)?$', required=False, allow_blank=True, default='')
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')
    complete_hotspot_setup = serializers.BooleanField(default=True)
    network_reviewed = serializers.BooleanField()
    network_mode = serializers.ChoiceField(choices=['create', 'reuse'], default='create')
    gateway_cidr = serializers.CharField(required=False, allow_blank=True, default='')
    dhcp_range_mode = serializers.ChoiceField(choices=['automatic', 'custom'], default='automatic')
    dhcp_range = serializers.CharField(required=False, allow_blank=True, default='')
    dns_servers = serializers.CharField(default='1.1.1.1,8.8.8.8')
    hotspot_dns_name = serializers.CharField(default='login.hotspot.lan')
    reuse_pool = serializers.CharField(required=False, allow_blank=True, default='')
    reuse_dhcp = serializers.CharField(required=False, allow_blank=True, default='')
    reuse_hotspot = serializers.CharField(required=False, allow_blank=True, default='')
    nat_mode = serializers.ChoiceField(choices=['existing', 'interface', 'interface-list'], default='existing')
    wan_interface = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, values):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: 'Unknown registration field.' for key in sorted(unknown)})
        if not values['network_reviewed']:
            raise serializers.ValidationError({'network_reviewed': 'Confirm the router network settings.'})
        try:
            validate_name(values['hotspot_interface'], 'HotSpot LAN interface')
            if values['hotspot_profile']:
                validate_name(values['hotspot_profile'], 'HotSpot profile')
            if values['complete_hotspot_setup']:
                values['setup'] = validate_setup(values)
                if values['wan_interface'] == values['hotspot_interface']:
                    raise DjangoValidationError('WAN and HotSpot LAN interfaces must differ.')
            elif not values['hotspot_profile']:
                raise serializers.ValidationError({'hotspot_profile': 'Enter the existing HotSpot profile.'})
            else:
                values['setup'] = {}
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'network': exc.messages}) from exc
        return values


def allocate_address():
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [0x5941524F])
    pool = ipaddress.IPv4Network(settings.WG_MANAGED_SUBNET)
    if pool.prefixlen < 16:
        raise serializers.ValidationError('The router address pool must be /16 or smaller.')
    used = set(NASDevice.objects.values_list('wireguard_ip', flat=True))
    used.update(NASDevice.objects.values_list('ip_address', flat=True))
    with connection.cursor() as cursor:
        if 'nas' not in connection.introspection.table_names(cursor):
            raise serializers.ValidationError('Install the staging RADIUS SQL schema before adding routers.')
        cursor.execute('SELECT nasname FROM nas')
        used.update(str(row[0]).split('/')[0] for row in cursor.fetchall())
    reserved = {str(pool.network_address + offset) for offset in (1, 2, 10)}
    reserved.add(getattr(settings, 'RADIUS_SERVER_WG_IP', ''))
    for address in pool.hosts():
        if str(address) not in used | reserved:
            return str(address)
    raise serializers.ValidationError('No unused WireGuard addresses remain.')


def render(registration):
    router = registration.router
    radius = str(ipaddress.IPv4Address(getattr(settings, 'RADIUS_SERVER_WG_IP', '')))
    if ipaddress.ip_address(radius) not in ipaddress.ip_network(settings.WG_MANAGED_SUBNET):
        raise ValueError('RADIUS hub must be in the managed WireGuard network.')
    public_key = validate_wireguard_public_key(getattr(settings, 'WG_VPS_PUBLIC_KEY', ''))
    endpoint = getattr(settings, 'WG_VPS_ENDPOINT', '')
    import re
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', endpoint):
        raise ValueError('Configure a WireGuard endpoint host without URL or port.')
    ports = [int(getattr(settings, key, default)) for key, default in (
        ('WG_ENDPOINT_PORT', 51820), ('ROUTER_RADIUS_AUTH_PORT', 1812), ('ROUTER_RADIUS_ACCT_PORT', 1813))]
    if any(not 1 <= port <= 65535 for port in ports):
        raise ValueError('Invalid infrastructure port.')
    config = SimpleNamespace(
        RADIUS_SERVER_IP=radius, WG_SUBNET_CIDR=settings.WG_MANAGED_SUBNET,
        DEFAULT_HOTSPOT_PROFILE=registration.hotspot_profile,
        DEFAULT_WG_INTERFACE='wg-yarotech', DEFAULT_WG_LISTEN_PORT=router.wireguard_port,
        DEFAULT_WG_VPS_PUBLIC_KEY=public_key, WG_HUB_IP=radius,
        WG_ENDPOINT_PORT=ports[0], RADIUS_AUTH_PORT=ports[1], RADIUS_ACCT_PORT=ports[2],
    )
    adapted = SimpleNamespace(
        pk=router.pk, name=router.name, tenant=SimpleNamespace(business_name=router.tenant.name),
        wireguard_ip=router.wireguard_ip, wireguard_public_key=router.wireguard_public_key,
        wireguard_private_key=registration.private_key_encrypted,
        secret=router.nas_secret, hotspot_profile=registration.hotspot_profile,
        hotspot_interface=registration.hotspot_interface,
    )
    return build_mikrotik_deployment_script(adapted, {
        'wireguard_endpoint': endpoint, 'vps_public_key': public_key,
        'hotspot_setup_v1': registration.setup,
    }, config)


def prepare(registration):
    """Caller holds the router lock; no remote action occurs in this transaction."""
    router = registration.router
    if router.operations.filter(status__in=['pending', 'running']).exists():
        return
    try:
        script = render(registration)
    except (ValueError, DjangoValidationError):
        registration.status, registration.error_code = 'needs_attention', 'server_configuration_required'
        registration.save(update_fields=['status', 'error_code', 'updated_at'])
        return
    registration.script_encrypted = secret_store.encrypt(script)
    registration.script_sha256 = hashlib.sha256(script.encode()).hexdigest()
    if not getattr(settings, 'ROUTER_SELF_SERVICE_PROVISIONING_ENABLED', False):
        registration.status, registration.error_code = 'needs_attention', 'server_provisioning_disabled'
    else:
        RouterOperation.objects.create(router=router, action='self_service_provision', payload={
            'public_key': router.wireguard_public_key, 'wireguard_ip': router.wireguard_ip,
            'interface': settings.WG_INTERFACE, 'subnet': settings.WG_MANAGED_SUBNET,
            'host': settings.WG_VPS_HOST,
        })
        router.deployment_status = 'deploying'
        router.save(update_fields=['deployment_status', 'updated_at'])
        registration.status, registration.error_code = 'preparing', ''
    registration.save()


@transaction.atomic
def register(tenant, actor, values):
    from apps.tenants.models import Tenant
    from apps.subscriptions.entitlements import require_router_slot
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    require_router_slot(tenant)
    address = allocate_address()
    identifier = values['nas_identifier'] or slugify(values['name'])[:90] or 'router'
    if not values['nas_identifier']:
        base, counter = identifier, 1
        while RouterRegistration.objects.filter(router__tenant=tenant, nas_identifier=identifier).exists():
            counter += 1
            identifier = f'{base}-{counter}'
    elif RouterRegistration.objects.filter(router__tenant=tenant, nas_identifier=identifier).exists():
        raise serializers.ValidationError({'nas_identifier': 'This NAS identifier is already in use.'})
    key = X25519PrivateKey.generate()
    private = base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    secret = secrets.token_urlsafe(36)
    router = NASDevice.objects.create(
        tenant=tenant, name=values['name'], model=values['model'], routeros_version=values['routeros_version'],
        location=values['location'], ip_address=address, wireguard_ip=address,
        nas_secret=secret_store.encrypt(secret), wireguard_public_key=public,
        onboarding_state='approved', is_active=True,
    )
    profile = values['hotspot_profile'] or 'yaro-' + hashlib.sha256(f'{tenant.pk}:{identifier}'.encode()).hexdigest()[:20] + '-profile'
    registration = RouterRegistration.objects.create(
        router=router, nas_identifier=identifier, hotspot_interface=values['hotspot_interface'],
        hotspot_profile=profile, notes=values['notes'], setup=values['setup'],
        private_key_encrypted=secret_store.encrypt(private),
    )
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO nas (nasname, shortname, type, secret, description) VALUES (%s,%s,%s,%s,%s)',
                       [address, f'yaro-{router.pk.hex[:20]}', 'mikrotik', secret, f'Yarotech router {router.pk}'])
    RouterAuditEvent.objects.create(router=router, action='self_service_registered', to_state='approved',
                                    details={'actor_id': actor.pk})
    prepare(registration)
    return router
