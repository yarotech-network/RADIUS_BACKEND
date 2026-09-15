import hashlib
from datetime import timedelta
from django.db import DatabaseError, transaction
from django.utils import timezone
from apps.routers.secret_store import secret_store
from apps.subscriptions.entitlements import whatsapp_allowed
from apps.vouchers.models import Radacct, Radpostauth
from .models import TenantWhatsAppEntryRoute, SharedWhatsAppEndpoint, WhatsAppOrder
from .conversations import queue_message

DEFAULTS = {'enabled': False, 'unused_enabled': False, 'expiry_enabled': False,
    'unused_hours': 24, 'short_lead_hours': 2, 'medium_lead_hours': 24, 'long_lead_hours': 72,
    'unused_template': '', 'expiry_template': '', 'language': 'en'}


def preferences(tenant_id):
    route = TenantWhatsAppEntryRoute.objects.filter(tenant_id=tenant_id).first()
    return {**DEFAULTS, **(route.reminder_preferences if route else {})}


def reminder_eligible(order, kind, expected_expiry=None):
    payment = order.payment
    voucher = payment.voucher
    config = preferences(order.tenant_id)
    if (not config['enabled'] or not order.reminders_opt_in or not whatsapp_allowed(order.tenant)
        or not voucher or voucher.tenant_id != order.tenant_id or payment.tenant_id != order.tenant_id
        or not payment.verified_at or payment.status != 'success' or not payment.paid_at
        or voucher.status in ('disabled', 'expired') or voucher.deleted_at):
        return False
    now = timezone.now()
    if kind == 'unused_reminder':
        if (not config['unused_enabled'] or payment.paid_at > now-timedelta(hours=config['unused_hours'])
            or voucher.status != 'unused' or voucher.is_used or voucher.activated_at or voucher.first_used_at
            or voucher.last_used_at or voucher.used_at):
            return False
        try:
            # Suppress unused reminders after any recorded authentication attempt. The
        # existing unmanaged model does not expose a portable reply-status column.
        # Failure to obtain accounting evidence is not evidence of non-use.
            with transaction.atomic():
                return not Radacct.objects.filter(username=voucher.username).exists() and not Radpostauth.objects.filter(
                    username=voucher.username).exists()
        except DatabaseError:
            return False
    if not config['expiry_enabled'] or not voucher.expires_at or not (voucher.activated_at or voucher.first_used_at):
        return False
    if expected_expiry and voucher.expires_at.isoformat() != expected_expiry:
        return False
    hours = payment.purchased_terms['duration_seconds']/3600
    lead = config['short_lead_hours'] if hours <= 24 else config['medium_lead_hours'] if hours < 720 else config['long_lead_hours']
    return now < voucher.expires_at <= now+timedelta(hours=lead)


@transaction.atomic
def schedule_order_reminders(order_id):
    hint = WhatsAppOrder.objects.get(pk=order_id)
    endpoint = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=hint.endpoint_id)
    order = WhatsAppOrder.objects.select_related('payment__voucher', 'tenant').get(pk=order_id)
    WhatsAppOrder.objects.filter(pk=order.pk).update(next_reminder_check_at=timezone.now()+timedelta(minutes=15))
    if not endpoint.verified_at or not endpoint.is_active or endpoint.version != order.endpoint_version:
        return 0
    config = preferences(order.tenant_id)
    made = 0
    for kind, name in [('unused_reminder', config['unused_template']), ('expiry_reminder', config['expiry_template'])]:
        if not name or not reminder_eligible(order, kind):
            continue
        voucher = order.payment.voucher
        expiry = voucher.expires_at.isoformat() if kind == 'expiry_reminder' else ''
        key = hashlib.sha256(f'{order.pk}:{kind}:{expiry}'.encode()).hexdigest()
        if order.outbound.filter(dedup_key='reminder:'+key).exists():
            continue
        values = [order.tenant.name, order.payment.purchased_terms['name']]
        if expiry:
            values.append(expiry)
        template = {'name': name, 'language': {'code': config['language']}, 'components': [
            {'type': 'body', 'parameters': [{'type': 'text', 'text': str(value)} for value in values]}]}
        row = queue_message(endpoint=endpoint, tenant_id=order.tenant_id,
            sender=secret_store.decrypt(order.recipient_encrypted), customer_hash=order.customer_hash,
            text='', dedup_key='reminder:'+key, order=order, kind=kind, template=template)
        row.context = {'expiry': expiry, 'voucher_id': voucher.pk}
        row.save(update_fields=['context'])
        made += 1
    return made
