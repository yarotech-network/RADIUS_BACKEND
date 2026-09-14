"""Read-only local lab evidence. Never changes deployment or RADIUS state."""
import time
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone
from django.db.models import Q

from .discovery import DiscoveryError, destination, read_table
from .local_lan import approved_target
from .secret_store import secret_store

TABLES = {
    'resource': ('system/resource', 'board-name,version'),
    'bridges': ('interface/bridge', 'name,disabled,comment'),
    'ports': ('interface/bridge/port', 'interface,bridge,disabled,comment'),
    'addresses': ('ip/address', 'address,interface,disabled,comment'),
    'hotspots': ('ip/hotspot', 'name,interface,profile,disabled,invalid'),
    'profiles': ('ip/hotspot/profile', 'name,use-radius'),
    'dhcp': ('ip/dhcp-server', 'name,interface,address-pool,disabled,invalid,comment'),
    'leases': ('ip/dhcp-server/lease', 'server,status'),
    'users': ('ip/hotspot/user', 'name,server,profile,disabled,comment'),
    'active': ('ip/hotspot/active', 'user,server'),
}
CONFIGURATION_CHECKS = frozenset({
    'management_separation', 'device', 'client_binding', 'gateway',
    'hotspot', 'dhcp', 'client_lease',
})


def approved_wifi(router, context):
    """Operator-only additions, scoped to one package; never grants management access."""
    if not context:
        return []
    event, target = context
    config = getattr(settings, 'ROUTER_LOCAL_LAN_WIFI_EXTENSIONS', {})
    entry = config.get(str(router.pk), {}) if isinstance(config, dict) else {}
    if not isinstance(entry, dict) or entry.get('intent_id') != str(event.pk):
        return []
    names = entry.get('interfaces')
    reserved = {p['name'] for p in event.details['intent']['interfaces']}
    reserved.update([target['management_interface'], target['wan_interface'], event.details['intent']['bridge']])
    if (not isinstance(names, list) or not 1 <= len(names) <= 2
            or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,62}', n) for n in names)
            or len(set(names)) != len(names) or reserved.intersection(names)):
        return []
    return sorted(names)


def observation_scope(names):
    # Existing observations predate this field and describe no Wi-Fi extension.
    return Q(details__wifi_interfaces=names) if names else (Q(details__wifi_interfaces=[]) | Q(details__wifi_interfaces__isnull=True))


def saved_progress(router, context, latest):
    """Keep completed observations across expiry/connection failures, never as live proof."""
    empty = {'configuration': {'passed': False, 'checked_at': None, 'fresh': False},
             'customer_login': {'passed': False, 'checked_at': None, 'fresh': False}}
    if not context:
        return empty
    event, target = context
    observation = router.audit_events.filter(observation_scope(approved_wifi(router, context))).filter(
        action='hotspot.lab_verified', details__intent_id=str(event.pk),
        details__router_version=router.updated_at.isoformat(), details__target=target,
        details__status__in=['verified', 'incomplete'], created_at__lte=timezone.now(),
    ).first()
    if not observation:
        return empty
    checks = observation.details.get('checks', [])
    by_name = {check.get('check_type'): check.get('passed') is True for check in checks}
    fresh = bool(latest and latest.pk == observation.pk
                 and observation.created_at >= timezone.now() - timedelta(minutes=10))
    metadata = {'checked_at': observation.created_at, 'fresh': fresh}
    return {
        'configuration': {**metadata, 'passed': all(by_name.get(name, False) for name in CONFIGURATION_CHECKS)},
        'customer_login': {**metadata, 'passed': by_name.get('local_login', False)},
    }


def package_context(router):
    """Expired download access does not prevent observing an already exported package."""
    event = router.audit_events.filter(action='hotspot.intent_created').first()
    target = approved_target(router)
    if not event or not target or event.details.get('router_version') != router.updated_at.isoformat():
        return None
    intent = event.details.get('intent', {})
    inventory = router.audit_events.filter(pk=intent.get('inventory_id'), action='hotspot.inventory_discovered').first()
    if (intent.get('authentication_mode') != 'local_user' or intent.get('mode') != 'fresh'
            or not inventory or inventory.details.get('inventory', {}).get('local_target') != target
            or router.audit_events.filter(action='hotspot.intent_revoked', details__intent_id=str(event.pk)).exists()
            or not router.audit_events.filter(action='hotspot.lab_package_exported', details__intent_id=str(event.pk)).exists()):
        return None
    return event, target


def result(router):
    context = package_context(router)
    base = {'eligible': bool(context), 'status': 'not_verified', 'checked_at': None, 'checks': [], 'code': None,
            'progress': saved_progress(router, None, None), 'client_interfaces': []}
    if not context:
        return base
    event, target = context
    wifi = approved_wifi(router, context)
    base['client_interfaces'] = [
        {'name': p['name'], 'kind': p['kind'], 'role': 'client', 'bridge': event.details['intent']['bridge'], 'source': 'package'}
        for p in event.details['intent']['interfaces'] if p['role'] == 'client'
    ] + [{'name': name, 'kind': 'wireless', 'role': 'client', 'bridge': event.details['intent']['bridge'], 'source': 'reviewed_extension'} for name in wifi]
    latest = router.audit_events.filter(action='hotspot.lab_verified', details__intent_id=str(event.pk)).first()
    base['progress'] = saved_progress(router, context, latest)
    if not latest or latest.details.get('wifi_interfaces', []) != wifi:
        return base
    fresh = (timezone.now() - timedelta(minutes=10) <= latest.created_at <= timezone.now()
             and latest.details.get('target') == target
             and latest.details.get('router_version') == router.updated_at.isoformat())
    return {**base, 'status': latest.details['status'] if fresh else 'stale',
            'checked_at': latest.created_at, 'checks': latest.details.get('checks', []),
            'code': latest.details.get('code')}


def collect_lab(router, context):
    base = destination(router, 'local_lan')
    if not router.routeros_username or not router.routeros_password_encrypted:
        raise DiscoveryError('credentials_required')
    try:
        password = secret_store.decrypt(router.routeros_password_encrypted)
    except Exception:
        raise DiscoveryError('credentials_required') from None
    deadline = time.monotonic() + 20
    tables = {}
    wifi = approved_wifi(router, context)
    with requests.Session() as session:
        session.trust_env = False
        session.verify = getattr(settings, 'ROUTER_DISCOVERY_CA_BUNDLE', '') or True
        session.auth = (router.routeros_username, password)
        for key, (path, fields) in TABLES.items():
            tables[key] = read_table(session, f'{base}/{path}', fields, deadline)
        if wifi:
            tables['interfaces'] = read_table(session, f'{base}/interface', 'name,type,disabled', deadline)
    return evaluate(tables, context, wifi)


def evaluate(tables, context, wifi=None):
    event, target = context
    intent = event.details['intent']
    owner = 'yarotech-lab:' + str(event.pk)
    user = 'yr-' + event.pk.hex[:16]
    bridge, hotspot = intent['bridge'], intent['hotspot_name']
    def matches(table, **fields):
        return [r for r in tables[table] if all(r.get(k) == v for k, v in fields.items())]
    def enabled(table, **fields):
        rows = matches(table, **fields)
        return len(rows) == 1 and rows[0].get('disabled') == 'false' and rows[0].get('invalid', 'false') == 'false'
    clients = [p['name'] for p in intent['interfaces'] if p['role'] == 'client']
    wifi = wifi or []
    expected_clients = set(clients) | set(wifi)
    wireless_ok = all(len([r for r in tables.get('interfaces', []) if r.get('name') == name
                          and r.get('type') in ('wlan', 'wifi') and r.get('disabled') == 'false']) == 1 for name in wifi)
    bindings = matches('ports', bridge=bridge)
    management_bindings = matches('ports', interface=target['management_interface'])
    management_bridge = management_bindings[0].get('bridge') if len(management_bindings) == 1 else target['management_interface']
    checks = {
        'management_separation': management_bridge != bridge
                  and not any(r.get('interface') in (target['management_interface'], target['wan_interface']) for r in bindings)
                  and not matches('ports', interface=target['wan_interface'])
                  and any(r.get('address', '').split('/')[0] == target['address']
                          and r.get('interface') == management_bridge and r.get('disabled') == 'false' for r in tables['addresses']),
        'device': len(tables['resource']) == 1 and tables['resource'][0].get('board-name') == intent['model']
                  and tables['resource'][0].get('version', '').split(' ')[0] == intent['routeros_version'],
        'client_binding': bool(clients) and set(clients).issubset(target['preparation_interfaces'])
                  and wireless_ok and len(bindings) == len(expected_clients) and {r.get('interface') for r in bindings} == expected_clients
                  and all(r.get('disabled') == 'false' and r.get('comment') == ('Yarotech WiFi lab extension' if r.get('interface') in wifi else owner) for r in bindings)
                  and enabled('bridges', name=bridge, comment=owner),
        'gateway': enabled('addresses', address=intent['gateway'], interface=bridge, comment=owner),
        'hotspot': enabled('hotspots', name=hotspot, interface=bridge, profile=intent['profile_name'])
                  and len(matches('profiles', name=intent['profile_name'], **{'use-radius': 'false'})) == 1,
        'dhcp': enabled('dhcp', name=user, interface=bridge, comment=owner, **{'address-pool': user}),
        'client_lease': bool(matches('leases', server=user, status='bound')),
        'local_login': enabled('users', name=user, server=hotspot, profile=user, comment=owner)
                  and len(matches('active', user=user, server=hotspot)) == 1,
    }
    return [{'check_type': key, 'passed': bool(value)} for key, value in checks.items()]
