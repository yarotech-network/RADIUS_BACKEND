import json
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.routers.secret_store import secret_store
from apps.subscriptions.entitlements import whatsapp_allowed
from .models import SharedWhatsAppEndpoint, WhatsAppOutbound, WhatsAppSenderWatermark, WhatsAppInboundEvent, WhatsAppProcessedEvent
from .provider import send_payload, ProviderFailure
from .shared_routing import resolve_sender, customer_hash


def _claim(outbound_id):
    with transaction.atomic():
        hint = WhatsAppOutbound.objects.get(pk=outbound_id)
        endpoint = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=hint.endpoint_id)
        row = WhatsAppOutbound.objects.select_for_update().select_related('order__payment__voucher', 'tenant', 'source_event').get(pk=outbound_id)
        now = timezone.now()
        if row.state == 'sending' and row.started_at < now-timedelta(minutes=5):
            row.state, row.error_code = 'unknown', 'delivery_outcome_unknown'
            row.claim = None
            row.save()
            return None
        if row.state != 'pending' or row.next_attempt_at > now:
            return None
        if WhatsAppOutbound.objects.filter(endpoint=endpoint, customer_hash=row.customer_hash,
            state='sending').exists():
            return None
        if WhatsAppOutbound.objects.filter(endpoint=endpoint, customer_hash=row.customer_hash,
            state='pending', created_at__lt=row.created_at).exists():
            return None
        payload = json.loads(secret_store.decrypt(row.payload_encrypted))
        error = ''
        if not endpoint.is_active or not endpoint.verified_at or endpoint.version != row.endpoint_version or endpoint.phone_number_id != row.phone_number_id:
            error = 'endpoint_changed_or_unverified'
        elif row.source_event_id and row.source_event.state != 'ready':
            error = 'source_event_no_longer_valid'
        elif row.customer_hash != customer_hash(payload['to']):
            error = 'recipient_mismatch'
        elif row.kind in ('credentials', 'unused_reminder', 'expiry_reminder'):
            payment = row.order.payment if row.order else None
            if (not payment or payment.status != 'success' or not payment.verified_at or not payment.voucher_id
                or payment.tenant_id != row.tenant_id or payment.voucher.tenant_id != row.tenant_id
                or row.order.customer_hash != row.customer_hash):
                error = 'paid_voucher_mapping_invalid'
            elif row.kind.endswith('_reminder'):
                from .reminders import reminder_eligible, preferences
                config = preferences(row.tenant_id)
                template = payload.get('template', {})
                if (not reminder_eligible(row.order, row.kind, row.context.get('expiry'))
                    or row.context.get('voucher_id') != payment.voucher_id
                    or template.get('name') != config['unused_template' if row.kind == 'unused_reminder' else 'expiry_template']
                    or template.get('language', {}).get('code') != config['language']):
                    error = 'reminder_no_longer_eligible'
        else:
            try:
                binding = resolve_sender(endpoint_id=endpoint.pk, endpoint_version=row.endpoint_version,
                    sender=payload['to'], expected_version=row.binding_version)
            except ValidationError:
                binding = None
            if not binding or binding.route.tenant_id != row.tenant_id or not whatsapp_allowed(row.tenant):
                error = 'business_selection_expired'
            elif row.kind == 'checkout' and (not row.order or row.order.payment.status != 'pending'):
                error = 'checkout_no_longer_pending'
        watermark = WhatsAppSenderWatermark.objects.filter(endpoint=endpoint, phone_number_id=row.phone_number_id,
            customer_hash=row.customer_hash).first()
        if not error and payload.get('type') != 'template' and (not watermark or watermark.provider_timestamp <= now.timestamp()-24*3600):
            error = 'customer_reply_window_closed'
        if error:
            row.state, row.error_code = 'blocked', error
            row.save(update_fields=['state', 'error_code'])
            return None
        row.state, row.claim, row.started_at = 'sending', uuid.uuid4(), now
        row.attempts += 1
        row.save()
        return row, endpoint, payload


def send_one(outbound_id):
    if not settings.WHATSAPP_SEND_ENABLED:
        return False
    claimed = _claim(outbound_id)
    if not claimed:
        return False
    row, endpoint, payload = claimed
    state, error, message_id = 'unknown', 'delivery_outcome_unknown', ''
    try:
        message_id = send_payload(endpoint, payload)
        state, error = 'accepted', ''
    except ProviderFailure as exc:
        error = exc.code
        state = 'pending' if exc.retryable and row.attempts < 5 else 'unknown' if exc.ambiguous else 'failed'
    except Exception:
        pass  # An unexpected exception after claiming may follow an accepted POST. Never blindly resend.
    WhatsAppOutbound.objects.filter(pk=row.pk, claim=row.claim, state='sending').update(state=state,
        error_code=error, provider_message_id=message_id, claim=None,
        next_attempt_at=timezone.now()+timedelta(seconds=60*2**min(row.attempts-1, 4)))
    return True


@transaction.atomic
def process_delivery_status(event_id):
    hint = WhatsAppInboundEvent.objects.get(pk=event_id)
    SharedWhatsAppEndpoint.objects.select_for_update().get(pk=hint.endpoint_id)
    event = WhatsAppInboundEvent.objects.select_for_update().get(pk=event_id)
    if event.state != 'status' or hasattr(event, 'processing'):
        return False
    item = json.loads(secret_store.decrypt(event.payload_encrypted))['item']
    row = WhatsAppOutbound.objects.select_for_update().filter(endpoint_id=event.endpoint_id,
        phone_number_id=event.phone_number_id, provider_message_id=event.message_id,
        customer_hash=event.customer_hash).first()
    if row is None:
        # The POST response may still be in flight. Leave this durable receipt available for retry.
        if event.received_at < timezone.now()-timedelta(minutes=5):
            WhatsAppProcessedEvent.objects.create(event=event, outcome='unmatched_delivery_status')
            return True
        return False
    incoming = item.get('status')
    rank = {'accepted': 0, 'sent': 1, 'delivered': 2, 'read': 3}
    if incoming in rank and rank[incoming] > rank.get(row.state, -1):
        row.state, row.error_code = incoming, ''
        row.save(update_fields=['state', 'error_code'])
    elif incoming == 'failed' and row.state not in ('delivered', 'read'):
        row.state, row.error_code = 'failed', 'meta_delivery_failed'
        row.save(update_fields=['state', 'error_code'])
    WhatsAppProcessedEvent.objects.create(event=event, outcome='delivery_status_recorded')
    return True
