"""Internal routing for a future verified/deduplicated WhatsApp inbox; no sending.

All mutations lock endpoint first. Customer identifiers never leave this module in plaintext.
"""
import base64
import hashlib
import hmac
import re
import uuid
from datetime import timedelta
from urllib.parse import quote
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.subscriptions.entitlements import whatsapp_allowed
from .models import SharedWhatsAppEndpoint, TenantWhatsAppEntryRoute, WhatsAppRoutedSender, WhatsAppRoutingHold

TOKEN_RE = re.compile(r'^(?P<selector>[A-Za-z0-9_-]{40,64})\.(?P<signature>[A-Za-z0-9_-]{43})$')


def configured_key(name):
    value = str(getattr(settings, name, '') or '').encode('utf-8')
    if len(value) < 32:
        raise ImproperlyConfigured('WhatsApp routing keys are not configured.')
    return value


def hash_key_fingerprint():
    return hmac.new(configured_key('WHATSAPP_SENDER_HASH_KEY'), b'whatsapp-hash-key-check-v1', hashlib.sha256).hexdigest()


def customer_hash(sender):
    if not isinstance(sender, str) or not re.fullmatch(r'\+?[1-9][0-9]{6,14}', sender):
        raise ValidationError('Invalid WhatsApp sender identity.')
    return hmac.new(configured_key('WHATSAPP_SENDER_HASH_KEY'), sender.lstrip('+').encode('ascii'), hashlib.sha256).hexdigest()


def _signature(selector):
    digest = hmac.new(configured_key('WHATSAPP_TENANT_ROUTING_SIGNING_KEY'), selector.encode('ascii'), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def token_for_entry(route):
    return f'{route.selector}.{_signature(route.selector)}'


def resolve_entry(token, *, lock=False):
    match = TOKEN_RE.fullmatch(token) if isinstance(token, str) else None
    if not match or not hmac.compare_digest(match['signature'], _signature(match['selector'])):
        return None
    query = TenantWhatsAppEntryRoute.objects.select_related('tenant')
    if lock:
        query = query.select_for_update(of=('self',))
    route = query.filter(selector=match['selector'], revoked_at__isnull=True, tenant__is_active=True).first()
    return route if route and whatsapp_allowed(route.tenant) else None


def entry_preview(route, endpoint):
    if not endpoint or not endpoint.is_active or not route or route.revoked_at or not whatsapp_allowed(route.tenant):
        return None
    if not re.fullmatch(r'\+?[1-9][0-9]{6,14}', endpoint.display_number):
        return None
    return f"https://wa.me/{endpoint.display_number.lstrip('+')}?text={quote('START ' + token_for_entry(route), safe='')}"


def _endpoint(endpoint_id, version):
    endpoint = SharedWhatsAppEndpoint.objects.select_for_update().filter(pk=endpoint_id).first()
    if (not endpoint or not endpoint.is_active or not endpoint.verified_at or str(endpoint.version) != str(version)
        or not endpoint.access_token_encrypted or endpoint.hash_key_fingerprint != hash_key_fingerprint()):
        raise ValidationError('WhatsApp endpoint is unverified, changed or unavailable.')
    return endpoint


def _valid_binding(binding, endpoint, expected_version=None):
    return bool(binding and binding.expires_at > timezone.now()
        and binding.endpoint_version == endpoint.version
        and (expected_version is None or str(binding.version) == str(expected_version))
        and binding.route_selector == binding.route.selector and not binding.route.revoked_at
        and binding.route.tenant.is_active and whatsapp_allowed(binding.route.tenant))


@transaction.atomic
def bind_sender(*, endpoint_id, endpoint_version, sender, token):
    endpoint = _endpoint(endpoint_id, endpoint_version)
    route = resolve_entry(token, lock=True)
    if not route:
        raise ValidationError('Business link is invalid or unavailable.')
    identity = customer_hash(sender)
    binding = WhatsAppRoutedSender.objects.select_for_update().filter(endpoint=endpoint, customer_hash=identity).first()
    if binding and binding.route_id != route.pk and binding.purchase_holds.filter(released_at__isnull=True).exists():
        raise ValidationError('Finish the current purchase before switching businesses.')
    now = timezone.now()
    if binding is None:
        return WhatsAppRoutedSender.objects.create(endpoint=endpoint, route=route, customer_hash=identity,
            endpoint_version=endpoint.version, route_selector=route.selector, expires_at=now+timedelta(minutes=30), last_activity_at=now)
    if (binding.route_id != route.pk or binding.endpoint_version != endpoint.version
        or binding.route_selector != route.selector or binding.expires_at <= now):
        binding.version = uuid.uuid4()
    binding.route = route
    binding.route_selector = route.selector
    binding.endpoint_version = endpoint.version
    binding.expires_at = now + timedelta(minutes=30)
    binding.last_activity_at = now
    binding.save()
    return binding


@transaction.atomic
def resolve_sender(*, endpoint_id, endpoint_version, sender, expected_version):
    endpoint = _endpoint(endpoint_id, endpoint_version)
    binding = WhatsAppRoutedSender.objects.select_for_update(of=('self',)).select_related('route__tenant').filter(
        endpoint=endpoint, customer_hash=customer_hash(sender)).first()
    # A queued event must bring its captured version, never opt into the current tenant.
    if expected_version is None or not _valid_binding(binding, endpoint, expected_version):
        return None
    return binding


@transaction.atomic
def reserve_purchase(*, endpoint_id, endpoint_version, sender, binding_version, reference):
    if not isinstance(reference, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', reference):
        raise ValidationError('Invalid purchase reference.')
    endpoint = _endpoint(endpoint_id, endpoint_version)
    binding = resolve_sender(endpoint_id=endpoint.pk, endpoint_version=endpoint.version,
        sender=sender, expected_version=binding_version)
    if not binding:
        raise ValidationError('The business selection expired or changed.')
    previous = WhatsAppRoutingHold.objects.filter(reference=reference).first()
    if previous:
        if previous.binding_id != binding.pk or previous.binding_version != binding.version:
            raise ValidationError('Purchase reference belongs to another routing selection.')
        return previous
    from apps.vouchers.models import PaymentTransaction
    if PaymentTransaction.objects.filter(reference=reference).exists():
        raise ValidationError('Reserve the routing reference before creating the payment.')
    if binding.purchase_holds.filter(released_at__isnull=True).exists():
        raise ValidationError('Finish the current purchase first.')
    return WhatsAppRoutingHold.objects.create(binding=binding, binding_version=binding.version,
        tenant=binding.route.tenant, reference=reference)


@transaction.atomic
def release_purchase(reference):
    """Call after payment commit. Expired subscriptions must not prevent reconciliation."""
    from apps.vouchers.models import PaymentTransaction
    hint = WhatsAppRoutingHold.objects.select_related('binding').get(reference=reference)
    SharedWhatsAppEndpoint.objects.select_for_update().get(pk=hint.binding.endpoint_id)
    WhatsAppRoutedSender.objects.select_for_update().get(pk=hint.binding_id)
    hold = WhatsAppRoutingHold.objects.select_for_update().get(pk=hint.pk)
    if hold.released_at:
        return hold
    payment = PaymentTransaction.objects.select_for_update().filter(reference=reference, tenant=hold.tenant).first()
    if not payment or not payment.verified_at:
        raise ValidationError('Verified payment outcome is required before releasing the business selection.')
    if payment.status != 'failed' and not (payment.status == 'success' and payment.voucher_id
        and payment.voucher.tenant_id == hold.tenant_id):
        raise ValidationError('Payment or voucher fulfilment is still pending.')
    hold.released_at = timezone.now()
    hold.save(update_fields=['released_at'])
    return hold
