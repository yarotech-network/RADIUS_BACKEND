"""Trusted first-authentication boundary, independent of operator subscription expiry.

credential_verified is a server assertion, never a public request parameter.
The RADIUS adapter must validate credentials before calling this service.
"""
import math
import re
from datetime import datetime, timezone as datetime_timezone
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.routers.models import NASDevice
from apps.routers.selectors import tenant_radius_addresses
from .models import Voucher, Radcheck


def _expiration(value):
    if value.isdigit():
        return datetime.fromtimestamp(int(value), datetime_timezone.utc)
    # Retain the recovered portal's historical RADIUS date interpretation.
    naive = datetime.strptime(value, '%d %b %Y %H:%M:%S')
    zone = ZoneInfo('Europe/Berlin')
    first, second = (naive.replace(tzinfo=zone, fold=fold) for fold in (0, 1))
    if first.utcoffset() != second.utcoffset():
        raise ValueError('Ambiguous historical deadline')
    return first


def _mac(value):
    compact = re.sub('[:-]', '', value).upper()
    if not re.fullmatch('[0-9A-F]{12}', compact):
        return None
    return ':'.join(compact[i:i+2] for i in range(0, 12, 2))


@transaction.atomic
def finalize_authenticated_voucher(voucher_id, *, credential_verified=False, nas_ip_address='', mac_address=''):
    denied = {'allowed': False, 'activated': False, 'timeout': None}
    if credential_verified is not True or not nas_ip_address:
        return denied
    voucher = Voucher.objects.select_for_update(of=("self",)).select_related('tenant').filter(pk=voucher_id).first()
    if not voucher or not voucher.tenant.is_active or voucher.deleted_at or voucher.status not in ('unused', 'sold', 'active', 'used'):
        return denied
    router = NASDevice.objects.filter(tenant_id=voucher.tenant_id, is_active=True,
        onboarding_state='active').filter(Q(ip_address=nas_ip_address) | Q(wireguard_ip=nas_ip_address)).first()
    if not router or nas_ip_address not in tenant_radius_addresses(voucher.tenant):
        return denied
    if voucher.legacy_provenance and (not isinstance(voucher.legacy_provenance, dict) or voucher.legacy_provenance.get('requires_review')):
        return denied
    consumed = bool(voucher.is_used or voucher.activated_at or voucher.first_used_at or
        voucher.used_at or voucher.last_used_at or voucher.status in ('active', 'used'))
    if consumed and voucher.expires_at is None:
        return denied
    now = timezone.now()
    deadline = voucher.expires_at
    try:
        for value in Radcheck.objects.filter(username=voucher.username, attribute='Expiration').values_list('value', flat=True):
            expiration = _expiration(value)
            deadline = min(deadline, expiration) if deadline else expiration
    except (ValueError, OverflowError, OSError):
        return denied
    if deadline and deadline <= now:
        return denied
    mac = _mac(mac_address)
    if voucher.bound_device_mac and (not voucher.device_lock_enabled or not voucher.device_bound_at or not voucher.device_bound_nas_id):
        return denied
    if not voucher.bound_device_mac and (voucher.device_bound_at or voucher.device_bound_nas_id):
        return denied
    if voucher.device_lock_enabled:
        if not mac or (voucher.bound_device_mac and _mac(voucher.bound_device_mac) != mac):
            return denied
    activating = not consumed
    if activating:
        try:
            seconds = voucher.service_terms['duration_seconds']
        except (ValidationError, ValueError, KeyError, TypeError):
            return denied
        if type(seconds) is not int or seconds < 1:
            return denied
        proposed = now + timezone.timedelta(seconds=seconds)
        deadline = min(deadline, proposed) if deadline else proposed
    remaining = math.floor((deadline-now).total_seconds())
    if remaining < 1:
        return denied
    fields = []
    if activating:
        voucher.status = 'active'
        voucher.activated_at = now
        voucher.first_used_at = now
        fields += ['status', 'activated_at', 'first_used_at']
    if voucher.expires_at != deadline:
        voucher.expires_at = deadline
        fields.append('expires_at')
    if voucher.device_lock_enabled and not voucher.bound_device_mac:
        voucher.bound_device_mac = mac
        voucher.device_bound_at = now
        voucher.device_bound_nas = router
        fields += ['bound_device_mac', 'device_bound_at', 'device_bound_nas']
    if fields:
        voucher.save(update_fields=fields)
    return {'allowed': True, 'activated': activating, 'timeout': remaining}
