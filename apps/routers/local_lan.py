"""Operator-approved LAN endpoints; tenant input never grants network access."""
import ipaddress
import re

from django.conf import settings


def approved_target(router):
    targets = getattr(settings, 'ROUTER_LOCAL_LAN_TARGETS', {})
    target = targets.get(str(router.pk)) if isinstance(targets, dict) else None
    if not isinstance(target, dict) or not router.is_active:
        return None
    try:
        address = ipaddress.IPv4Address(target['address'])
        if str(address) != str(router.ip_address) or not any(
            address in ipaddress.IPv4Network(cidr)
            for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
        ):
            return None
        names = [target['management_interface'], target['wan_interface']]
        clients = target.get('preparation_interfaces', [])
        if not isinstance(clients, list) or len(clients) > 8:
            return None
        names += clients
        if len(names) != len(set(names)) or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,62}', n) for n in names):
            return None
        return {key: target[key] for key in ('address', 'management_interface', 'wan_interface')} | {'preparation_interfaces': clients}
    except (KeyError, ValueError, TypeError):
        return None


def preparation_review(target, inventory):
    """Deliberately non-executable: bridge changes need an independent operator review."""
    ports = {p['name']: p for p in inventory['interfaces']}
    return {
        'management_interface': target['management_interface'],
        'wan_interface': target['wan_interface'],
        'steps': [
            'Download an encrypted router backup and configuration export before preparing ports.',
            f"Keep the computer on {target['management_interface']} and verify IP management access.",
            f"Keep the internet uplink disconnected from {target['wan_interface']} until WAN and management are separated and firewall policy is reviewed.",
            'Review bridge membership, VLANs and services before manually detaching a customer port. This review does not authorize moving protected management or WAN ports.',
            'After preparation, discover again. Fresh setup remains blocked for bridged or protected client interfaces.',
        ],
        'ports': [
            {'name': name, 'bridge': ports[name]['bridge'], 'protected_reasons': ports[name]['protected_reasons'],
             'state': 'review_required' if ports[name]['bridge'] or ports[name]['protected_reasons'] else 'unbridged'}
            for name in target['preparation_interfaces'] if name in ports
        ],
    }
