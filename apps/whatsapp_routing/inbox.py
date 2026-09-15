"""Authenticated ingress only. No outbound or financial effects are performed here."""
import hashlib
import hmac
import json
import re

from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError
from apps.routers.secret_store import secret_store
from .models import SharedWhatsAppEndpoint, WhatsAppInboundEvent, WhatsAppRoutedSender, WhatsAppSenderWatermark
from .shared_routing import bind_sender, configured_key, customer_hash, hash_key_fingerprint, resolve_sender

MAX_BODY = 256 * 1024
MAX_EVENTS = 100
MAX_AGE_SECONDS = 7 * 24 * 3600
FUTURE_SKEW_SECONDS = 300


class InvalidEnvelope(ValueError):
    pass


def _dict(value):
    if not isinstance(value, dict):
        raise InvalidEnvelope()
    return value


def _list(value):
    if not isinstance(value, list) or len(value) > MAX_EVENTS:
        raise InvalidEnvelope()
    return value


def _string(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise InvalidEnvelope()
    return value


@sensitive_variables()
def parse_events(raw):
    """Validate the whole bounded envelope before any transaction or routing mutation."""
    try:
        payload = _dict(json.loads(raw))
        if payload.get('object') != 'whatsapp_business_account':
            raise InvalidEnvelope()
        events = []
        changes_seen = 0
        for entry in _list(payload.get('entry')):
            for change in _list(_dict(entry).get('changes')):
                changes_seen += 1
                if changes_seen > MAX_EVENTS:
                    raise InvalidEnvelope()
                change = _dict(change)
                if change.get('field') != 'messages':
                    continue
                value = _dict(change.get('value'))
                if value.get('messaging_product') != 'whatsapp':
                    raise InvalidEnvelope()
                phone = _string(_dict(value.get('metadata')).get('phone_number_id'), r'[0-9]{1,100}')
                for kind, collection in [('message', 'messages'), ('status', 'statuses')]:
                    for item in _list(value.get(collection, [])):
                        item = _dict(item)
                        message_id = _string(item.get('id'), r'[\x21-\x7e]{1,512}')
                        timestamp = int(_string(item.get('timestamp'), r'[0-9]{1,12}'))
                        sender = _string(item.get('from') if kind == 'message' else item.get('recipient_id'), r'\+?[1-9][0-9]{6,14}')
                        if kind == 'message':
                            message_type = _string(item.get('type'), r'[a-z_]{1,40}')
                            if message_type == 'text':
                                body = _dict(item.get('text')).get('body')
                                if not isinstance(body, str) or len(body) > 4096:
                                    raise InvalidEnvelope()
                        else:
                            _string(item.get('status'), r'[a-z_]{1,40}')
                        events.append({'phone': phone, 'kind': kind, 'id': message_id,
                            'timestamp': timestamp, 'sender': sender, 'item': item})
                        if len(events) > MAX_EVENTS:
                            raise InvalidEnvelope()
        return sorted(events, key=lambda event: event['timestamp'])
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise InvalidEnvelope('Invalid WhatsApp envelope.') from exc


def _identity(event):
    identity = [event['phone'], event['kind'], event['id']]
    if event['kind'] == 'status':
        identity += [event['item']['status'], event['timestamp']]
    return hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()


@sensitive_variables()
def _route(event, receipt, endpoint):
    now = int(timezone.now().timestamp())
    if not now - MAX_AGE_SECONDS <= event['timestamp'] <= now + FUTURE_SKEW_SECONDS:
        receipt.state, receipt.reason = 'stale', 'timestamp_outside_window'
        return
    watermark, _ = WhatsAppSenderWatermark.objects.get_or_create(endpoint=endpoint,
        phone_number_id=event['phone'], customer_hash=receipt.customer_hash)
    if event['timestamp'] <= watermark.provider_timestamp:
        receipt.state, receipt.reason = 'stale', 'timestamp_out_of_order_or_ambiguous'
        return
    watermark.provider_timestamp = event['timestamp']
    watermark.save(update_fields=['provider_timestamp'])
    # A signed, fresh opt-out must work even after the business selection expires.
    # It only removes consent; it cannot authorize a purchase or send a message.
    text = event['item'].get('text', {}).get('body', '').strip() if event['item']['type'] == 'text' else ''
    if text.lower() in ('stop', 'reminders off'):
        from .models import WhatsAppOrder, WhatsAppConversation, WhatsAppProcessedEvent
        WhatsAppOrder.objects.filter(endpoint=endpoint, phone_number_id=event['phone'],
            customer_hash=receipt.customer_hash).update(reminders_opt_in=False)
        conversations = WhatsAppConversation.objects.filter(binding__endpoint=endpoint,
            binding__customer_hash=receipt.customer_hash)
        conversations.update(reminders_opt_in=False)
        conversations.filter(last_event_timestamp__lt=event['timestamp']).update(last_event_timestamp=event['timestamp'])
        WhatsAppProcessedEvent.objects.create(event=receipt, outcome='reminders_opted_out')
        receipt.state, receipt.reason = 'blocked', 'reminders_opted_out'
        return
    if not endpoint.is_active or not endpoint.verified_at:
        receipt.state, receipt.reason = 'blocked', 'endpoint_unavailable'
        return
    if event['item']['type'] not in ('text', 'interactive', 'button'):
        receipt.state, receipt.reason = 'unsupported', 'message_type_unsupported'
        return
    args = {'endpoint_id': endpoint.pk, 'endpoint_version': endpoint.version, 'sender': event['sender']}
    text = event['item'].get('text', {}).get('body', '').strip() if event['item']['type'] == 'text' else ''
    try:
        if text.startswith('START '):
            binding = bind_sender(**args, token=text[6:])
        else:
            selected = WhatsAppRoutedSender.objects.filter(endpoint=endpoint, customer_hash=receipt.customer_hash).first()
            binding = resolve_sender(**args, expected_version=selected.version if selected else None)
        if binding is None:
            receipt.state, receipt.reason = 'blocked', 'business_selection_required'
            return
    except ValidationError:
        receipt.state, receipt.reason = 'blocked', 'routing_policy_rejected'
        return
    receipt.binding = binding
    receipt.binding_version = binding.version
    receipt.tenant_id = binding.route.tenant_id
    receipt.state = 'ready'


@transaction.atomic
@sensitive_variables()
def accept_events(events):
    """Commit receipts, deduplication and routing together; callers ack only after return."""
    summary = {'received': 0, 'duplicates': 0, 'conflicts': 0, 'ignored': 0}
    endpoint = SharedWhatsAppEndpoint.objects.select_for_update().filter(pk=1).first()
    relevant = [event for event in events if endpoint and event['phone'] == endpoint.phone_number_id]
    summary['ignored'] = len(events) - len(relevant)
    if not relevant:
        return summary
    if endpoint.hash_key_fingerprint != hash_key_fingerprint():
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured('WhatsApp sender hashing requires reconciliation.')
    configured_key('WHATSAPP_TENANT_ROUTING_SIGNING_KEY')
    for event in relevant:
        key = _identity(event)
        canonical = json.dumps({'phone': event['phone'], 'kind': event['kind'], 'item': event['item']}, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        fingerprint = hmac.new(configured_key('WHATSAPP_SENDER_HASH_KEY'), canonical.encode(), hashlib.sha256).hexdigest()
        previous = WhatsAppInboundEvent.objects.select_for_update().filter(event_key=key).first()
        if previous:
            if not hmac.compare_digest(previous.payload_fingerprint, fingerprint):
                previous.state, previous.reason = 'conflict', 'provider_identity_content_changed'
                summary['conflicts'] += 1
            else:
                summary['duplicates'] += 1
            previous.duplicate_count += 1
            previous.save(update_fields=['state', 'reason', 'duplicate_count'])
            continue
        receipt = WhatsAppInboundEvent.objects.create(endpoint=endpoint, phone_number_id=event['phone'],
            event_key=key, message_id=event['id'], kind=event['kind'], provider_timestamp=event['timestamp'],
            customer_hash=customer_hash(event['sender']), payload_fingerprint=fingerprint,
            payload_encrypted=secret_store.encrypt(canonical), endpoint_version=endpoint.version,
            state='status' if event['kind'] == 'status' else 'blocked')
        if event['kind'] == 'message':
            _route(event, receipt, endpoint)
            receipt.save(update_fields=['state', 'reason', 'binding', 'binding_version', 'tenant'])
        summary['received'] += 1
    return summary
