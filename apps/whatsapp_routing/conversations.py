"""Deterministic conversation transitions. No provider calls inside these transactions."""
import json
import secrets
from decimal import Decimal
from apps.customers.purchases import create_purchase_payment
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.payments.services import get_paystack_service
from apps.routers.secret_store import secret_store
from apps.vouchers.models import InternetPlan, PaymentTransaction
from apps.vouchers.terms import snapshot_plan
from .models import (SharedWhatsAppEndpoint, WhatsAppInboundEvent, WhatsAppProcessedEvent,
    WhatsAppConversation, WhatsAppOrder, WhatsAppOutbound, WhatsAppRoutedSender)
from .shared_routing import resolve_sender, reserve_purchase


def queue_message(*, endpoint, tenant_id, sender, customer_hash, text, dedup_key,
                  binding_version=None, event=None, order=None, kind='reply', template=None):
    payload = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': sender,
        'type': 'text', 'text': {'body': text[:4096], 'preview_url': False}}
    if template:
        payload.pop('text')
        payload.update(type='template', template=template)
    row, _ = WhatsAppOutbound.objects.get_or_create(dedup_key=dedup_key, defaults={
        'endpoint': endpoint, 'endpoint_version': order.endpoint_version if order else endpoint.version,
        'phone_number_id': order.phone_number_id if order else endpoint.phone_number_id,
        'tenant_id': tenant_id, 'customer_hash': customer_hash, 'binding_version': binding_version,
        'source_event': event, 'order': order, 'kind': kind,
        'payload_encrypted': secret_store.encrypt(json.dumps(payload))})
    return row


def eligible_plans(tenant_id):
    return InternetPlan.objects.filter(tenant_id=tenant_id, is_active=True, is_public=True,
        archived_at__isnull=True, plan_type='voucher').order_by('price', 'pk')


def menu(conversation, *, advance=False):
    offset = conversation.menu_offset + 10 if advance else 0
    plans = list(eligible_plans(conversation.tenant_id)[offset:offset+11])
    if not plans and offset:
        offset = 0
        plans = list(eligible_plans(conversation.tenant_id)[:11])
    conversation.menu_offset = offset
    conversation.menu = [snapshot_plan(plan) for plan in plans[:10]]
    conversation.selected_terms = None
    conversation.state = 'menu'
    lines = [f'{conversation.tenant.name} internet plans (one device):']
    lines += [f"{i+1}. {p['name'][:100]} - NGN {Decimal(p['price'])/100:.2f}" for i, p in enumerate(conversation.menu)]
    lines.append('Reply with a plan number.' if plans else 'No plans are available. Contact support.')
    if len(plans) > 10:
        lines.append('Reply MORE for more plans.')
    lines.append('STATUS | MY VOUCHER | SUPPORT | REMINDERS ON/OFF')
    return '\n'.join(lines)


def _text(item):
    def field(value, key):
        result = value.get(key, '') if isinstance(value, dict) else ''
        return result.strip() if isinstance(result, str) else ''
    if item.get('type') == 'text':
        return field(item.get('text'), 'body')
    if item.get('type') == 'button':
        return field(item.get('button'), 'payload')
    interactive = item.get('interactive') or {}
    if not isinstance(interactive, dict):
        return ''
    value = interactive.get('button_reply') or interactive.get('list_reply') or {}
    return field(value, 'id')


def credential_text(order):
    payment = order.payment
    voucher = payment.voucher
    if (payment.status != 'success' or not payment.verified_at or not voucher
        or voucher.tenant_id != order.tenant_id or voucher.plan_id != payment.plan_id):
        raise ValueError('Voucher is not verified and fulfilled.')
    return (f'{order.tenant.name} Wi-Fi voucher\nUsername: {voucher.username}\nPassword: {voucher.password}\n'
        f"Plan: {payment.purchased_terms['name']}\nJoin the business Wi-Fi and use these login details.")


@transaction.atomic
def process_event(event_id):
    if not settings.WHATSAPP_CONSUMER_ENABLED:
        return False
    hint = WhatsAppInboundEvent.objects.get(pk=event_id)
    endpoint = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=hint.endpoint_id)
    event = WhatsAppInboundEvent.objects.select_for_update().get(pk=event_id)
    if hasattr(event, 'processing'):
        return False
    if event.state != 'ready':
        return False
    data = json.loads(secret_store.decrypt(event.payload_encrypted))
    sender = data['item']['from'].lstrip('+')
    try:
        binding = resolve_sender(endpoint_id=endpoint.pk, endpoint_version=event.endpoint_version,
            sender=sender, expected_version=event.binding_version)
    except ValidationError:
        binding = None
    if not binding or binding.route.tenant_id != event.tenant_id or binding.pk != event.binding_id:
        WhatsAppProcessedEvent.objects.create(event=event, outcome='stale_selection')
        return True
    conversation, _ = WhatsAppConversation.objects.get_or_create(binding=binding, defaults={
        'binding_version': binding.version, 'tenant_id': event.tenant_id})
    if conversation.binding_version != binding.version or conversation.tenant_id != event.tenant_id:
        conversation.binding_version = binding.version
        conversation.tenant_id = event.tenant_id
        conversation.menu, conversation.selected_terms = [], None
        conversation.state, conversation.reminders_opt_in = 'menu', False
    if event.provider_timestamp <= conversation.last_event_timestamp:
        WhatsAppProcessedEvent.objects.create(event=event, outcome='out_of_order')
        return True
    conversation.last_event_timestamp = event.provider_timestamp
    text = _text(data['item'])
    lowered = text.lower()
    latest = WhatsAppOrder.objects.filter(tenant_id=event.tenant_id, customer_hash=event.customer_hash,
        endpoint=endpoint).select_related('payment__voucher', 'tenant').order_by('-pk').first()
    reply = ''
    response_kind = 'reply'
    response_order = None
    if lowered in ('reminders on', 'reminders off'):
        conversation.reminders_opt_in = lowered.endswith(' on')
        WhatsAppOrder.objects.filter(tenant_id=event.tenant_id, customer_hash=event.customer_hash,
            endpoint=endpoint).update(reminders_opt_in=conversation.reminders_opt_in)
        reply = 'Voucher reminders enabled when available.' if conversation.reminders_opt_in else 'Voucher reminders turned off.'
    elif lowered in ('status', 'paid', 'i paid', 'pay'):
        if latest:
            WhatsAppOrder.objects.filter(pk=latest.pk).update(next_check_at=timezone.now())
            if latest.payment.status == 'success' and latest.payment.voucher_id:
                reply = 'Payment confirmed. Your voucher is ready. Reply MY VOUCHER to receive it.'
            elif latest.checkout_encrypted and latest.state == 'pending':
                reply = 'Pay securely: '+secret_store.decrypt(latest.checkout_encrypted)+'\nA voucher is issued only after payment verification.'
                response_kind, response_order = 'checkout', latest
            else:
                reply = 'Your existing payment is being checked. No new payment will be created. Contact support if this persists.'
        else:
            reply = 'No order found. Reply MENU to start.'
    elif lowered == 'my voucher':
        if latest and latest.payment.status == 'success' and latest.payment.voucher_id:
            reply, response_kind, response_order = credential_text(latest), 'credentials', latest
        else:
            reply = 'No verified paid voucher found. Reply STATUS to check your order.'
    elif lowered in ('help', 'support'):
        tenant = conversation.tenant
        reply = f'Contact {tenant.name}: {tenant.phone or tenant.email or "your business operator"}.'
    elif text.startswith('START ') or lowered in ('menu', 'start', 'hi', 'hello', 'more') or not conversation.menu:
        reply = menu(conversation, advance=lowered == 'more')
    elif conversation.state == 'menu' and text.isdigit() and len(text) <= 3:
        index = int(text)-1
        if not 0 <= index < len(conversation.menu):
            reply = 'Please select one of the displayed plan numbers.'
        else:
            conversation.selected_terms = conversation.menu[index]
            conversation.state = 'email'
            reply = 'Please reply with your email address for the payment receipt.'
    elif conversation.state == 'email':
        try:
            if len(text) > 254:
                raise DjangoValidationError('Email too long')
            validate_email(text)
        except DjangoValidationError:
            reply = 'Please enter a valid email address.'
        else:
            if binding.purchase_holds.filter(released_at__isnull=True).exists():
                reply = 'Finish your existing purchase first. Reply STATUS.'
            else:
                plan = eligible_plans(event.tenant_id).select_for_update().filter(pk=conversation.selected_terms['plan_id']).first()
                if not plan or snapshot_plan(plan) != conversation.selected_terms:
                    reply = 'That plan changed. Please choose again.\n'+menu(conversation)
                else:
                    key = get_paystack_service(conversation.tenant).secret_key
                    if not key:
                        reply = 'Payments are unavailable. Please contact support.'
                    else:
                        reference = 'wa-'+secrets.token_hex(16)
                        hold = reserve_purchase(endpoint_id=endpoint.pk, endpoint_version=endpoint.version,
                            sender=sender, binding_version=binding.version, reference=reference)
                        payment = create_purchase_payment(tenant_id=event.tenant_id, plan=plan,
                            reference=reference, amount=conversation.selected_terms['price'], customer_email=text.lower(),
                            customer_phone=sender, purchased_terms=conversation.selected_terms)
                        WhatsAppOrder.objects.create(source_event=event, conversation=conversation, tenant_id=event.tenant_id,
                            endpoint=endpoint, endpoint_version=endpoint.version, phone_number_id=endpoint.phone_number_id,
                            customer_hash=event.customer_hash, recipient_encrypted=secret_store.encrypt(sender),
                            payment=payment, payment_secret_encrypted=secret_store.encrypt(key), hold=hold,
                            reminders_opt_in=conversation.reminders_opt_in)
                        conversation.state = 'payment'
                        reply = 'Your payment link is being prepared. Reply STATUS to check progress.'
    else:
        reply = 'Reply MENU, STATUS, MY VOUCHER or SUPPORT.'
    conversation.save()
    if reply:
        queue_message(endpoint=endpoint, tenant_id=event.tenant_id, sender=sender, customer_hash=event.customer_hash,
            text=reply, dedup_key=f'event:{event.pk}', binding_version=binding.version, event=event,
            kind=response_kind, order=response_order)
    WhatsAppProcessedEvent.objects.create(event=event, outcome='processed')
    return True
