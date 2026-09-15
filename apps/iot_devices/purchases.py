"""Public device purchases: reserved terms, proof of renewal ownership, no voucher issuance."""
import secrets
from datetime import timedelta
from django.conf import settings
from django.core import signing
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError as ModelValidationError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.customers.purchases import create_purchase_payment
from apps.payments.services import get_paystack_service
from apps.routers.secret_store import secret_store
from apps.subscriptions.access import require_tenant_access
from apps.vouchers.models import InternetPlan, PaymentTransaction
from .models import MacDevice, PublicIoTPurchase, DeviceRenewal
from .lifecycle import plan_terms


def renewal_token(device):
    return signing.dumps({'device': device.pk, 'tenant': device.tenant_id,
                          'mac': device.mac_address_compact}, salt='iot-renewal-v1')


def resolve_renewal(token, tenant, mac):
    try:
        payload = signing.loads(token, salt='iot-renewal-v1')
        device = MacDevice.objects.select_for_update().get(pk=payload['device'], tenant=tenant)
        if payload['tenant'] != tenant.pk or payload['mac'] != device.mac_address_compact or device.mac_address != mac:
            raise ValueError()
        if device.configured_status in ('revoked', 'deleted') or device.access_type != 'timed':
            raise ValueError()
        return device
    except (signing.BadSignature, KeyError, ValueError, TypeError, MacDevice.DoesNotExist):
        raise ValidationError({'renewal_token': 'This renewal link is not valid for the selected device.'})


@transaction.atomic
def reserve_purchase(data):
    if not getattr(settings, 'IOT_PUBLIC_PURCHASE_ENABLED', False) or not getattr(settings, 'RADIUS_REST_ENABLED', False):
        raise ValidationError('Device purchases are not enabled.')
    # Device -> plan -> router matches the operator-renewal lock order.
    initial = InternetPlan.objects.select_related('tenant').get(pk=data['plan'].pk)
    try:
        mac = MacDevice.normalize_mac(data['mac_address'])
    except ModelValidationError:
        raise ValidationError({'mac_address': 'Enter a valid MAC address.'})
    device = resolve_renewal(data['renewal_token'], initial.tenant, mac) if data.get('renewal_token') else None
    plan = InternetPlan.objects.select_for_update().select_related('tenant').get(pk=initial.pk)
    require_tenant_access(plan.tenant)
    if not plan.tenant.is_active or not plan.is_active or not plan.is_public or plan.archived_at or plan.plan_type != 'iot_mac':
        raise ValidationError({'plan_id': 'This device plan is unavailable.'})
    from apps.routers.models import NASDevice
    router = NASDevice.objects.select_for_update().filter(pk=plan.public_router_id, tenant=plan.tenant,
        is_active=True, onboarding_state='active').first()
    if router is None or (device and device.router_id != router.pk):
        raise ValidationError({'plan_id': 'This plan has no eligible router for this device.'})
    if not device and MacDevice.objects.filter(mac_address_compact=mac.replace(':', '')).exists():
        raise ValidationError({'mac_address': 'An existing registration requires its renewal link or operator assistance.'})
    terms = plan_terms(plan)
    terms.update(source='paid_purchase', price=plan.price, router_id=str(router.pk))
    if terms['price'] <= 0:
        raise ValidationError({'plan_id': 'A paid device plan must have a positive price.'})
    service = get_paystack_service(plan.tenant)
    if not service.secret_key:
        raise ValidationError('Payment configuration is unavailable.')
    payment = create_purchase_payment(tenant=plan.tenant, plan=plan, amount=terms['price'],
        reference='iot-'+secrets.token_hex(24), purchased_terms=terms,
        customer_email=data['email'], customer_name=data.get('name', ''), customer_phone=data.get('phone', ''))
    try:
        with transaction.atomic():
            PublicIoTPurchase.objects.create(payment=payment, tenant=plan.tenant, router=router, device=device,
                expected_version=device.version if device else None, device_name=data['device_name'], mac_address=mac,
                payment_secret_encrypted=secret_store.encrypt(service.secret_key))
    except IntegrityError:
        raise ValidationError('An existing purchase for this device needs checking. Use its payment reference or contact the operator.')
    return payment


def fulfill_purchase(payment, verified):
    if (not isinstance(verified, dict) or verified.get('status') != 'success' or verified.get('reference') != payment.reference
            or type(verified.get('amount')) is not int or verified['amount'] != payment.amount or verified.get('currency') != 'NGN'):
        raise ValueError('Payment verification mismatch.')
    PaymentTransaction.objects.filter(pk=payment.pk).update(verified_at=timezone.now())
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
        order = PublicIoTPurchase.objects.select_for_update().get(payment=payment)
        if order.fulfilled_at:
            return payment
        terms = payment.purchased_terms
        if (not terms or terms.get('source') != 'paid_purchase' or terms.get('price') != payment.amount
            or terms.get('tenant_id') != payment.tenant_id or terms.get('plan_id') != payment.plan_id
            or terms.get('router_id') != str(order.router_id) or payment.voucher_id
            or order.tenant_id != payment.tenant_id or payment.customer.tenant_id != payment.tenant_id):
            raise ValueError('Reserved device purchase requires reconciliation.')
        device = MacDevice.objects.select_for_update().filter(pk=order.device_id).first() if order.device_id else None
        if order.device_id and device is None:
            raise ValueError('Reserved device is missing; operator review required.')
        if device and (device.version != order.expected_version or device.configured_status in ('deleted', 'revoked')
            or device.tenant_id != order.tenant_id or device.router_id != order.router_id or device.mac_address != order.mac_address
            or device.access_type != 'timed'):
            raise ValueError('Device changed after payment reservation; operator review required.')
        # Paid rights use reserved terms, even if the plan or operator subscription expired meanwhile.
        previous = device.expires_at if device else None
        now = timezone.now()
        expires = max(now, previous or now) + timedelta(seconds=terms['duration_seconds'])
        if device is None:
            device = MacDevice(tenant_id=order.tenant_id, router_id=order.router_id, plan_id=payment.plan_id,
                device_name=order.device_name, mac_address=order.mac_address, access_type='timed', status='active')
        else:
            device.version += 1
            device.status = 'suspended' if device.configured_status == 'suspended' else 'active'
            device.is_active = device.status == 'active'
            device.plan_id = payment.plan_id
        device.expires_at = expires
        device.issued_terms = terms
        device.speed_limit = terms['rate_limit']
        device.data_limit_bytes = terms['data_limit_bytes']
        device.save()
        DeviceRenewal.objects.create(payment=payment, device=device, tenant_id=order.tenant_id, actor=None,
            previous_expiry=previous, expires_at=expires, terms=terms)
        order.device, order.fulfilled_at, order.expires_at = device, now, expires
        order.save(update_fields=['device', 'fulfilled_at', 'expires_at'])
        payment.status, payment.paid_at = 'success', payment.paid_at or now
        payment.save(update_fields=['status', 'paid_at'])
        return payment


def purchase_response(payment):
    order = payment.iot_purchase
    fulfilled = payment.status == 'success' and order.fulfilled_at is not None
    return {'kind': 'iot', 'status': payment.status, 'payment_verified': payment.verified_at is not None,
        'reference': payment.reference, 'fulfilled': fulfilled, 'voucher': None, 'access_code': None,
        'code_revealed': False, 'tenant_name': payment.tenant.name,
        'device_status': order.device.effective_status if fulfilled else None,
        'expires_at': order.expires_at, 'renewal_token': renewal_token(order.device) if fulfilled else None,
        'network_enforcement': 'rest_configured' if getattr(settings, 'RADIUS_REST_ENABLED', False) else 'not_connected'}
