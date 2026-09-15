from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from apps.subscriptions.test_support import grant_test_subscription
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher, Radcheck
from apps.vouchers.radius_test_support import RadiusTablesMixin
from apps.vouchers.terms import snapshot_plan
from .recovery import fulfill_verified_voucher


@override_settings(MULTI_DEVICE_VOUCHERS_ENABLED=True)
class DevicePricingTests(RadiusTablesMixin, APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Devices', slug='device-pricing')
        self.sub = grant_test_subscription(self.tenant)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=50000, duration_hours=24)

    def checkout(self, count=3, key=None):
        with patch('apps.payments.views.get_paystack_service') as service:
            service.return_value.initialize_transaction.return_value = {'data':{'authorization_url':'https://checkout.example.test'}}
            kwargs = {'HTTP_IDEMPOTENCY_KEY':key} if key else {}
            result = self.client.post('/api/v1/buy/', {'plan_id':self.plan.pk, 'email':'buyer@example.test',
                'device_limit':count, 'amount':1}, format='json', **kwargs)
        return result, service

    def verified(self, payment):
        return {'status':'success', 'reference':payment.reference, 'amount':payment.amount, 'currency':'NGN'}

    def test_total_is_server_calculated_and_sent_to_provider(self):
        response, service = self.checkout()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['amount'], 150000)
        self.assertEqual(response.data['base_amount'], 50000)
        self.assertEqual(response.data['device_limit'], 3)
        self.assertEqual(service.return_value.initialize_transaction.call_args.kwargs['amount'], 150000)
        payment = PaymentTransaction.objects.get(reference=response.data['reference'])
        self.assertEqual(payment.purchased_terms['version'], 3)
        self.assertEqual(payment.purchased_terms['base_price'], 50000)
        self.assertEqual(payment.purchased_terms['total_price'], payment.amount)
        public = self.client.get('/api/v1/public/tenants/device-pricing/plans/')
        self.assertEqual(public.data['results'][0]['max_devices'], 10)

    def test_replay_does_not_create_second_order_and_changed_count_conflicts(self):
        response, _ = self.checkout(key='device-checkout-12345')
        replay, service = self.checkout(key='device-checkout-12345')
        self.assertEqual(replay.data, response.data)
        service.assert_not_called()
        changed, service = self.checkout(2, key='device-checkout-12345')
        self.assertEqual(changed.status_code, 409)
        service.assert_not_called()
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_paid_capacity_survives_plan_and_feature_changes_and_operator_expiry(self):
        response, _ = self.checkout()
        payment = PaymentTransaction.objects.get(reference=response.data['reference'])
        self.plan.price = 99999
        self.plan.duration_hours = 72
        self.plan.save()
        self.sub.expires_at = timezone.now()-timedelta(seconds=1)
        self.sub.save()
        with override_settings(MULTI_DEVICE_VOUCHERS_ENABLED=False):
            fulfilled = fulfill_verified_voucher(payment, self.verified(payment))
            repeated = fulfill_verified_voucher(payment, self.verified(payment))
        self.assertEqual(fulfilled.voucher_id, repeated.voucher_id)
        self.assertEqual(Voucher.objects.count(), 1)
        voucher = fulfilled.voucher
        self.assertEqual(voucher.device_limit, 3)
        self.assertEqual(voucher.service_terms['duration_seconds'], 86400)
        self.assertEqual(voucher.service_terms['price'], 150000)
        self.assertEqual(Radcheck.objects.get(username=voucher.username, attribute='Simultaneous-Use').value, '3')

    def test_invalid_counts_and_disabled_policy_create_no_order(self):
        for count in (0, 11, -1, 1.5, True, 'abc'):
            result, service = self.checkout(count)
            self.assertEqual(result.status_code, 400, result.data)
            service.assert_not_called()
        with override_settings(MULTI_DEVICE_VOUCHERS_ENABLED=False):
            result, service = self.checkout(2)
            self.assertEqual(result.status_code, 400)
            service.assert_not_called()
            public = self.client.get('/api/v1/public/tenants/device-pricing/plans/')
            self.assertEqual(public.data['results'][0]['max_devices'], 1)
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_overflow_is_rejected_before_order_or_provider(self):
        self.plan.price = 1000000000
        self.plan.save()
        result, service = self.checkout(3)
        self.assertEqual(result.status_code, 400)
        service.assert_not_called()
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_inconsistent_snapshot_or_verified_amount_never_issues(self):
        response, _ = self.checkout()
        payment = PaymentTransaction.objects.get(reference=response.data['reference'])
        wrong = self.verified(payment)
        wrong['amount'] = 50000
        with self.assertRaises(ValueError):
            fulfill_verified_voucher(payment, wrong)
        payment.purchased_terms['device_limit'] = 2
        payment.save()
        with self.assertRaises(ValueError):
            fulfill_verified_voucher(payment, self.verified(payment))
        self.assertFalse(Voucher.objects.exists())

    def test_old_version_two_paid_amount_is_not_recalculated(self):
        terms = snapshot_plan(self.plan, 3)
        terms.update(version=2, price=50000)
        for key in ('base_price','total_price','currency'):
            terms.pop(key)
        payment = PaymentTransaction.objects.create(tenant=self.tenant, plan=self.plan, reference='legacy-device-order',
            amount=50000, purchased_terms=terms)
        result = fulfill_verified_voucher(payment, self.verified(payment))
        self.assertEqual(result.voucher.device_limit, 3)
        self.assertEqual(result.voucher.service_terms['price'], 50000)

    def test_batch_capacity_is_separate_from_quantity(self):
        owner = get_user_model().objects.create_user(username='device-owner', email='owner@example.test')
        TenantMembership.objects.create(user=owner, tenant=self.tenant, role='owner')
        self.client.force_authenticate(owner)
        result = self.client.post('/api/v1/vouchers/generate/', {'plan_id':self.plan.pk,'quantity':2,'device_limit':3}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(list(Voucher.objects.values_list('device_limit', flat=True)), [3,3])
        self.assertTrue(all(v.service_terms['price'] == 150000 for v in Voucher.objects.all()))
        with override_settings(MULTI_DEVICE_VOUCHERS_ENABLED=False):
            rejected = self.client.post('/api/v1/vouchers/generate/', {'plan_id':self.plan.pk,'quantity':2,'device_limit':3}, format='json')
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(Voucher.objects.count(), 2)
