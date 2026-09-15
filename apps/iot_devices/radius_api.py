"""Private FreeRADIUS boundary. NAS packet source is supplied only by a trusted server."""
import hmac
import math
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone
from rest_framework import serializers
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.routers.selectors import tenant_radius_addresses
from apps.vouchers.models import Voucher, Radacct
from apps.vouchers.lifecycle import finalize_authenticated_voucher
from .models import MacDevice


def attributes(values):
    return {name: {'value': [value], 'op': ':=', 'do_xlat': False} for name, value in values.items()}


def bandwidth_remaining(username, addresses, cap, *, compact=False, since=None):
    if not cap:
        return None
    rows = Radacct.objects.filter(nasipaddress__in=addresses)
    if since:
        rows = rows.filter(acctstarttime__gte=since)
    if compact:
        key = Upper(Replace(Replace(Replace('username', Value(':'), Value('')), Value('-'), Value('')), Value('.'), Value('')))
        rows = rows.annotate(mac_key=key).filter(mac_key=username)
    else:
        rows = rows.filter(username=username)
    totals = rows.aggregate(incoming=Sum('acctinputoctets'), outgoing=Sum('acctoutputoctets'))
    return cap - (totals['incoming'] or 0) - (totals['outgoing'] or 0)


class RadiusInput(serializers.Serializer):
    username = serializers.CharField(max_length=64, trim_whitespace=False)
    packet_src_ip = serializers.IPAddressField()
    calling_station_id = serializers.CharField(max_length=32)
    # Only provided from reply attributes in the trusted server's post-auth section.
    session_timeout = serializers.IntegerField(min_value=1, required=False)


class HotspotRadiusBoundary(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = []
    parser_classes = [FormParser, JSONParser]
    phase = 'authorize'

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response

    @transaction.atomic
    def post(self, request):
        token = getattr(settings, 'RADIUS_REST_TOKEN', '')
        if not getattr(settings, 'RADIUS_REST_ENABLED', False) or len(token) < 32:
            return Response(status=503)
        supplied = request.headers.get('X-Radius-Token', '')
        if len(supplied) > 512 or not hmac.compare_digest(supplied.encode(), token.encode()):
            return Response(status=403)
        payload = RadiusInput(data=request.data)
        if not payload.is_valid():
            return Response(status=403)
        data = payload.validated_data
        username, source = data['username'], data['packet_src_ip']
        voucher = Voucher.objects.select_for_update(of=('self',)).select_related('tenant').filter(username=username).first()
        compact = ''
        try:
            compact = MacDevice.normalize_mac(username).replace(':', '')
        except Exception:
            pass
        devices = MacDevice.objects.select_for_update(of=('self',)).select_related('router', 'tenant').filter(
            mac_address_compact=compact, is_active=True) if compact else MacDevice.objects.none()
        device = devices.first()
        if voucher and compact and MacDevice.objects.filter(mac_address_compact=compact).exists():
            return Response(status=403)  # No identity-owner guessing across services.
        if device:
            return self.device_response(device, data)
        if not voucher or voucher.deleted_at or voucher.status not in ('unused', 'sold', 'used', 'active') or not voucher.tenant.is_active:
            return Response(status=403)
        if source not in tenant_radius_addresses(voucher.tenant):
            return Response(status=403)
        if voucher.expires_at and voucher.expires_at <= timezone.now():
            return Response(status=403)
        terms = voucher.service_terms
        remaining = bandwidth_remaining(username, tenant_radius_addresses(voucher.tenant), terms.get('data_limit', 0) * 1024 * 1024)
        if remaining is not None and remaining <= 0:
            return Response(status=403)
        if self.phase == 'post-auth':
            decision = finalize_authenticated_voucher(voucher.pk, credential_verified=True,
                nas_ip_address=source, mac_address=data['calling_station_id'])
            if not decision['allowed']:
                return Response(status=403)
            timeout = min(300, decision['timeout'], data.get('session_timeout', 300))
            values = {'reply:Session-Timeout': timeout, 'reply:Acct-Interim-Interval': 60}
        else:
            values = {'control:Cleartext-Password': voucher.password,
                      'control:Simultaneous-Use': terms.get('device_limit', voucher.device_limit)}
        if terms.get('radius_rate_limit'):
            values['reply:Mikrotik-Rate-Limit'] = terms['radius_rate_limit']
        self.add_cap(values, remaining)
        return Response(attributes(values))

    @staticmethod
    def add_cap(values, remaining):
        if remaining is not None:
            values['reply:Mikrotik-Total-Limit'] = remaining % (2 ** 32)
            values['reply:Mikrotik-Total-Limit-Gigawords'] = remaining // (2 ** 32)

    def device_response(self, device, data):
        try:
            calling = MacDevice.normalize_mac(data['calling_station_id'])
        except Exception:
            return Response(status=403)
        router = device.router
        if (device.effective_status != 'active' or calling != device.mac_address or not device.tenant.is_active
            or not router or router.tenant_id != device.tenant_id or not router.is_active or router.onboarding_state != 'active'
            or data['packet_src_ip'] != str(router.radius_ip) or data['packet_src_ip'] not in tenant_radius_addresses(device.tenant)):
            return Response(status=403)
        # Reused MAC histories cannot be apportioned safely; reject capped ambiguous grants.
        if device.data_limit_bytes and MacDevice.objects.filter(tenant_id=device.tenant_id, router_id=device.router_id,
                mac_address_compact=device.mac_address_compact).exclude(pk=device.pk).exists():
            return Response(status=403)
        grant = device.renewals.first()
        remaining = bandwidth_remaining(device.mac_address_compact, [data['packet_src_ip']], device.data_limit_bytes,
            compact=True, since=grant.created_at if grant else device.created_at)
        if remaining is not None and remaining <= 0:
            return Response(status=403)
        timeout = min(300, math.floor((device.expires_at - timezone.now()).total_seconds())) if device.access_type == 'timed' else 300
        if timeout < 1:
            return Response(status=403)
        values = {'reply:Session-Timeout': min(timeout, data.get('session_timeout', timeout)), 'reply:Acct-Interim-Interval': 60}
        if self.phase == 'authorize':
            values['control:Cleartext-Password'] = data['username']
            values['control:Simultaneous-Use'] = 1
        if device.speed_limit:
            values['reply:Mikrotik-Rate-Limit'] = device.speed_limit
        if device.vlan_id:
            values.update({'reply:Tunnel-Type': 'VLAN', 'reply:Tunnel-Medium-Type': 'IEEE-802', 'reply:Tunnel-Private-Group-Id': str(device.vlan_id)})
        self.add_cap(values, remaining)
        return Response(attributes(values))


class HotspotPostAuth(HotspotRadiusBoundary):
    phase = 'post-auth'
