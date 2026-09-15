from datetime import timedelta
from unittest.mock import patch, Mock
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantSetting
from apps.routers.models import NASDevice
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher
from apps.subscriptions.test_support import grant_test_subscription
from apps.payments.recovery import fulfill_verified_voucher
from .models import MacDevice, DeviceRenewal
from .purchases import reserve_purchase, renewal_token


@override_settings(IOT_PUBLIC_PURCHASE_ENABLED=True, RADIUS_REST_ENABLED=True)
class PublicIoTTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='IoT', slug='iot-sales')
        self.subscription = grant_test_subscription(self.tenant)
        TenantSetting.objects.create(tenant=self.tenant, paystack_secret_key='test-provider-secret')
        self.router = NASDevice.objects.create(tenant=self.tenant, name='NAS', ip_address='192.0.2.40', onboarding_state='active')
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Device day', price=50000, duration_hours=24,
            plan_type='iot_mac', public_router=self.router, rate_limit='1M/1M')
        self.data = dict(plan=self.plan, email='test@example.test', device_name='Camera', mac_address='AA:BB:CC:DD:EE:FF')

    def verified(self, payment):
        return dict(reference=payment.reference, amount=payment.amount, status='success', currency='NGN')

    def test_paid_device_uses_reserved_terms_and_never_generates_voucher(self):
        payment = reserve_purchase(self.data)
        self.plan.price = 90000
        self.plan.duration_hours = 48
        self.plan.save()
        payment = fulfill_verified_voucher(payment, self.verified(payment))
        order = payment.iot_purchase
        self.assertEqual(payment.status, 'success')
        self.assertEqual(order.expires_at - order.fulfilled_at, timedelta(hours=24))
        self.assertEqual(order.device.speed_limit, '1M/1M')
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(payment.deliveries.exists())
        fulfill_verified_voucher(payment, self.verified(payment))
        self.assertEqual(MacDevice.objects.count(), 1)
        self.assertEqual(DeviceRenewal.objects.count(), 1)
        response = self.client.get(reverse('payment-callback'), {'reference': payment.reference})
        self.assertTrue(response.data['fulfilled'])
        self.assertEqual(response.data['kind'], 'iot')
        self.assertIsNone(response.data['access_code'])
        self.assertTrue(response.data['renewal_token'])
        self.assertNotIn('mac_address', response.data)

    def test_renewal_requires_capability_and_keeps_unused_time_and_suspension(self):
        payment = reserve_purchase(self.data)
        payment = fulfill_verified_voucher(payment, self.verified(payment))
        device = payment.iot_purchase.device
        device.status, device.is_active = 'suspended', False
        device.save()
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            reserve_purchase(self.data)
        with self.assertRaises(ValidationError):
            reserve_purchase({**self.data, 'renewal_token': 'invalid'})
        renewal = reserve_purchase({**self.data, 'renewal_token': renewal_token(device)})
        previous = device.expires_at
        fulfill_verified_voucher(renewal, self.verified(renewal))
        device.refresh_from_db()
        self.assertEqual(device.expires_at, previous + timedelta(hours=24))
        self.assertEqual(device.status, 'suspended')
        self.assertEqual(DeviceRenewal.objects.count(), 2)

    def test_stale_device_retains_paid_unfulfilled_evidence_without_overriding_operator(self):
        first = reserve_purchase(self.data)
        first = fulfill_verified_voucher(first, self.verified(first))
        device = first.iot_purchase.device
        payment = reserve_purchase({**self.data, 'renewal_token': renewal_token(device)})
        device.version += 1
        device.status, device.is_active = 'revoked', False
        device.save()
        with self.assertRaises(ValueError):
            fulfill_verified_voucher(payment, self.verified(payment))
        payment.refresh_from_db()
        self.assertIsNotNone(payment.verified_at)
        self.assertIsNone(payment.iot_purchase.fulfilled_at)
        self.assertEqual(DeviceRenewal.objects.count(), 1)

    def test_expired_tenant_cannot_buy_but_prepaid_order_is_fulfilled(self):
        payment = reserve_purchase(self.data)
        self.subscription.expires_at = timezone.now() - timedelta(days=1)
        self.subscription.save()
        from apps.subscriptions.access import SubscriptionRequired
        with self.assertRaises(SubscriptionRequired):
            reserve_purchase({**self.data, 'mac_address': 'AA:BB:CC:DD:EE:02'})
        self.assertEqual(fulfill_verified_voucher(payment, self.verified(payment)).status, 'success')

    def test_initialize_replay_and_provider_failure_do_not_create_another_charge(self):
        payload = {k:v for k,v in self.data.items() if k != 'plan'}
        payload['plan_id'] = self.plan.pk
        with patch('apps.payments.services.PaystackService.initialize_transaction', side_effect=TimeoutError()) as provider:
            first = self.client.post(reverse('buy-iot'), payload, format='json', HTTP_IDEMPOTENCY_KEY='iot-checkout-attempt-001')
            second = self.client.post(reverse('buy-iot'), payload, format='json', HTTP_IDEMPOTENCY_KEY='iot-checkout-attempt-001')
        self.assertEqual(first.status_code, 503, first.data)
        self.assertEqual(second.status_code, 503)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(first.data['reference'], second.data['reference'])

    def test_checkout_accepts_only_matching_provider_reference(self):
        payload = {k:v for k,v in self.data.items() if k != 'plan'}
        payload['plan_id'] = self.plan.pk
        def provider(**kwargs):
            return {'status': True, 'data': {'reference': kwargs['reference'], 'authorization_url':'https://checkout.paystack.com/test-checkout'}}
        with patch('apps.payments.services.PaystackService.initialize_transaction', side_effect=provider):
            response = self.client.post(reverse('buy-iot'), payload, format='json', HTTP_IDEMPOTENCY_KEY='iot-valid-provider-001')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['reference'], PaymentTransaction.objects.get().reference)
        self.assertFalse(MacDevice.objects.exists())
        payload['mac_address'] = 'AA:BB:CC:DD:EE:02'
        with patch('apps.payments.services.PaystackService.initialize_transaction', return_value={
            'status':True, 'data':{'reference':'wrong-payment','authorization_url':'https://checkout.paystack.com/test-checkout'}}):
            response = self.client.post(reverse('buy-iot'), payload, format='json', HTTP_IDEMPOTENCY_KEY='iot-wrong-provider-001')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('authorization_url', response.data)
        self.assertFalse(MacDevice.objects.exists())

    def test_invalid_mac_is_validation_error_without_reservation(self):
        payload = {k:v for k,v in self.data.items() if k != 'plan'}
        payload.update(plan_id=self.plan.pk, mac_address='invalid')
        response = self.client.post(reverse('buy-iot'), payload, format='json', HTTP_IDEMPOTENCY_KEY='iot-invalid-mac-001')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_amount_mismatch_has_no_grant(self):
        payment = reserve_purchase(self.data)
        with self.assertRaises(ValueError):
            fulfill_verified_voucher(payment, {**self.verified(payment), 'amount': 1})
        self.assertFalse(MacDevice.objects.exists())
        self.assertFalse(DeviceRenewal.objects.exists())

    def test_public_catalogue_hides_iot_without_activation_gate(self):
        url = reverse('public-plans', kwargs={'slug': self.tenant.slug})
        self.assertEqual(self.client.get(url).data['count'], 1)
        with override_settings(IOT_PUBLIC_PURCHASE_ENABLED=False):
            self.assertEqual(self.client.get(url).data['count'], 0)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, connections, close_old_connections
from rest_framework.test import APITransactionTestCase


@skipUnless(connection.vendor == 'postgresql', 'Requires real PostgreSQL row locks.')
@override_settings(IOT_PUBLIC_PURCHASE_ENABLED=True, RADIUS_REST_ENABLED=True)
class PublicIoTConcurrencyTests(APITransactionTestCase):
    def setUp(self):
        PublicIoTTests.setUp(self)

    def race(self, operation):
        barrier = Barrier(2)
        def run():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                barrier.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            return [future.result(timeout=25) for future in futures]

    def test_competing_initial_reservations_have_one_payment_and_contact(self):
        from rest_framework.exceptions import ValidationError
        def reserve():
            try:
                return reserve_purchase(self.data).pk
            except ValidationError:
                return None
        results = self.race(reserve)
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        from apps.customers.models import Customer
        self.assertEqual(Customer.objects.count(), 1)

    def test_duplicate_verification_creates_one_grant_and_one_deadline(self):
        payment = reserve_purchase(self.data)
        verified = PublicIoTTests.verified(self, payment)
        self.race(lambda: fulfill_verified_voucher(PaymentTransaction.objects.get(pk=payment.pk), verified).pk)
        self.assertEqual(DeviceRenewal.objects.count(), 1)
        self.assertEqual(MacDevice.objects.count(), 1)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'success')
        self.assertEqual(payment.iot_purchase.expires_at, MacDevice.objects.get().expires_at)
