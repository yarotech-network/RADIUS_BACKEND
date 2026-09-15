import uuid
from datetime import timedelta
from urllib.parse import urlsplit
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.payments.callbacks import payment_callback_url
from apps.payments.services import get_payment_paystack_service
from apps.payments.recovery import fulfill_verified_voucher
from apps.routers.secret_store import secret_store
from apps.subscriptions.entitlements import whatsapp_allowed
from apps.vouchers.models import PaymentTransaction
from .models import SharedWhatsAppEndpoint, WhatsAppOrder
from .conversations import queue_message, credential_text
from .shared_routing import release_purchase, _valid_binding, hash_key_fingerprint


def checkout_url(result, reference):
    if not isinstance(result, dict) or result.get('status') is not True:
        raise ValueError('Payment initialization rejected.')
    data = result.get('data') or {}
    url = data.get('authorization_url', '')
    parts = urlsplit(url)
    if (data.get('reference') != reference or parts.scheme != 'https' or parts.hostname != 'checkout.paystack.com'
        or parts.username or parts.password or parts.port not in (None, 443) or '\\' in url):
        raise ValueError('Unexpected checkout response.')
    return url


def _claim_order(order_id):
    with transaction.atomic():
        hint = WhatsAppOrder.objects.get(pk=order_id)
        endpoint = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=hint.endpoint_id)
        order = WhatsAppOrder.objects.select_for_update().select_related('payment', 'tenant').get(pk=order_id)
        now = timezone.now()
        if order.state in ('fulfilled', 'failed', 'recovery') or order.next_check_at > now:
            return None
        if order.claim and order.started_at > now-timedelta(minutes=5):
            return None
        if order.claim and order.state == 'initializing':
            order.state = 'unknown'
        if order.attempts >= 20:
            order.state, order.error_code = 'recovery', 'reconciliation_exhausted'
            order.claim = None
            order.save()
            return None
        initialize = order.state == 'new'
        binding = order.hold.binding
        if initialize and (endpoint.version != order.endpoint_version or not endpoint.verified_at
            or not endpoint.is_active or not whatsapp_allowed(order.tenant)
            or endpoint.hash_key_fingerprint != hash_key_fingerprint()
            or not _valid_binding(binding, endpoint, order.hold.binding_version)
            or binding.route.tenant_id != order.tenant_id):
            order.state, order.error_code = 'recovery', 'new_payment_not_allowed'
            order.save()
            return None
        order.claim, order.started_at = uuid.uuid4(), now
        order.attempts += 1
        if initialize:
            order.state = 'initializing'
        order.save()
        return order, initialize


def process_order(order_id):
    if not settings.WHATSAPP_CONSUMER_ENABLED:
        return False
    claimed = _claim_order(order_id)
    if not claimed:
        return False
    order, initialize = claimed
    payment = order.payment
    error, url = '', None
    terminal_failed = False
    try:
        service = get_payment_paystack_service(payment)
        if initialize:
            result = service.initialize_transaction(email=payment.customer_email, amount=payment.amount,
                reference=payment.reference, callback_url=payment_callback_url('voucher'),
                metadata={'source': 'whatsapp', 'transaction_id': payment.pk, 'plan_id': payment.plan_id, 'device_limit': 1})
            url = checkout_url(result, payment.reference)
        elif payment.status != 'success' or not payment.voucher_id:
            result = service.verify_transaction(payment.reference)
            data = result.get('data') if isinstance(result, dict) and result.get('status') is True else None
            if (not isinstance(data, dict) or data.get('reference') != payment.reference
                or type(data.get('amount')) is not int or data['amount'] != payment.amount or data.get('currency') != 'NGN'):
                raise ValueError('Verification mismatch.')
            if data.get('status') == 'success':
                payment = fulfill_verified_voucher(payment, data)
            elif data.get('status') == 'failed':
                with transaction.atomic():
                    locked = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
                    if not locked.voucher_id and locked.status != 'success' and not locked.verified_at:
                        locked.status, locked.verified_at = 'failed', timezone.now()
                        locked.save(update_fields=['status', 'verified_at'])
                        terminal_failed = True
    except Exception:
        error = 'initialization_outcome_unknown' if initialize else 'verification_or_fulfilment_pending'
    with transaction.atomic():
        endpoint = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=order.endpoint_id)
        locked = WhatsAppOrder.objects.select_for_update().select_related('payment__voucher', 'tenant').get(pk=order.pk)
        if locked.claim != order.claim:
            return True
        locked.claim = None
        locked.error_code = error
        locked.next_check_at = timezone.now()+timedelta(seconds=min(3600, 30*2**min(locked.attempts-1, 7)))
        sender = secret_store.decrypt(locked.recipient_encrypted)
        if locked.payment.status == 'success' and locked.payment.voucher_id and locked.payment.verified_at:
            release_purchase(locked.payment.reference)
            queue_message(endpoint=endpoint, tenant_id=locked.tenant_id, sender=sender,
                customer_hash=locked.customer_hash, text=credential_text(locked),
                dedup_key=f'voucher:{locked.pk}', order=locked, kind='credentials')
            locked.state, locked.error_code = 'fulfilled', ''
        elif terminal_failed or locked.payment.status == 'failed' and locked.payment.verified_at:
            release_purchase(locked.payment.reference)
            locked.state = 'failed'
        elif url:
            locked.checkout_encrypted = secret_store.encrypt(url)
            locked.state = 'pending'
            queue_message(endpoint=endpoint, tenant_id=locked.tenant_id, sender=sender,
                customer_hash=locked.customer_hash, text='Pay securely: '+url+'\nReply PAID after payment.',
                dedup_key=f'checkout:{locked.pk}', order=locked, kind='checkout',
                binding_version=locked.hold.binding_version)
        elif initialize:
            locked.state = 'unknown'
        locked.save()
    return True
