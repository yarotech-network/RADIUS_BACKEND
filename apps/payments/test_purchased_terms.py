import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership, TenantSetting
from apps.vouchers.models import BandwidthProfile, InternetPlan, PaymentTransaction, Radcheck, Radreply, Voucher
from apps.vouchers.serializers import VoucherSerializer
from .delivery import build_credential_email
from .recovery import fulfill_verified_voucher


class PurchasedTermsTests(TransactionTestCase):
    def setUp(self):
        self.created_tables = []
        for model in (Radcheck, Radreply):
            if model._meta.db_table not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)
                self.created_tables.append(model)
        self.tenant = Tenant.objects.create(name='Shop', slug='shop')
        TenantSetting.objects.create(tenant=self.tenant, paystack_secret_key='test-signing-key')
        self.owner = get_user_model().objects.create_user(username='owner')
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role='owner')
        profile = BandwidthProfile.objects.create(tenant=self.tenant, name='Basic', upload_kbps=1000, download_kbps=2000)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Original', price=50000,
            duration_hours=24, data_limit=1024, rate_limit=profile.rate_limit, bandwidth_profile=profile)
        self.client = APIClient()

    def tearDown(self):
        for model in reversed(self.created_tables):
            with connection.schema_editor() as editor:
                editor.delete_model(model)

    def checkout(self):
        with patch('apps.payments.views.get_paystack_service') as provider:
            provider.return_value.initialize_transaction.return_value = {'data': {'authorization_url': 'https://checkout.example/test'}}
            response = self.client.post('/api/v1/buy/', {'plan_id': self.plan.pk, 'email': 'buyer@example.com',
                'purchased_terms': {'price': 1, 'duration_hours': 999}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        payment = PaymentTransaction.objects.get(reference=response.data['reference'])
        self.assertEqual(payment.purchased_terms['price'], 50000)
        self.assertEqual(payment.purchased_terms['duration_hours'], 24)
        return payment

    def deactivate(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(f'/api/v1/plans/{self.plan.pk}/', {
            'name': 'Changed', 'price': 90000, 'duration_hours': 1, 'data_limit': 0,
            'rate_limit': '9M/9M', 'bandwidth_profile': None, 'is_active': False,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(None)

    def verified(self, payment):
        return {'status': 'success', 'reference': payment.reference, 'amount': payment.amount, 'currency': 'NGN'}

    def assert_original_voucher(self, payment):
        payment.refresh_from_db()
        voucher = payment.voucher
        self.assertEqual(voucher.purchased_terms, payment.purchased_terms)
        self.assertEqual(Voucher.objects.count(), 1)
        self.assertEqual(payment.deliveries.count(), 1)
        attrs = dict(Radcheck.objects.filter(username=voucher.username).values_list('attribute', 'value'))
        self.assertEqual(attrs['Max-Days'], str(24*3600))
        self.assertEqual(attrs['Max-Total-Octets'], str(1024*1024*1024))
        self.assertEqual(Radreply.objects.get(username=voucher.username).value, '1000k/2000k')
        detail = VoucherSerializer(voucher).data
        self.assertEqual(detail['plan_name'], 'Original')
        self.assertEqual(detail['plan_duration'], '24')
        _, text, html = build_credential_email(payment)
        for body in (text, html):
            self.assertIn('Original', body)
            self.assertNotIn('Changed', body)
            self.assertIn('500', body)
        response = self.client.get('/api/v1/payments/callback/', {'reference': payment.reference})
        self.assertEqual(response.data['plan'], {'name': 'Original', 'duration_hours': 24, 'data_limit': 1024})
        self.client.force_authenticate(self.owner)
        response = self.client.get(f'/api/v1/vouchers/{voucher.pk}/print/')
        self.assertContains(response, 'Original')
        self.assertContains(response, '24 hours')
        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now):
            voucher.activate()
        self.assertEqual(voucher.expires_at, now + timedelta(hours=24))

    def test_verification_honors_original_terms_after_edit_and_deactivation(self):
        payment = self.checkout()
        self.deactivate()
        with patch('apps.payments.services.get_paystack_service') as provider:
            provider.return_value.verify_transaction.return_value = {'status': True, 'data': self.verified(payment)}
            for _ in range(2):
                response = self.client.post('/api/v1/payments/verify/', {'reference': payment.reference})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertTrue(response.data['fulfilled'])
        self.assert_original_voucher(payment)
        self.assertEqual(self.client.post('/api/v1/buy/', {'plan_id': self.plan.pk, 'email': 'new@example.com'}).status_code, 400)

    def test_webhook_and_recovery_share_original_terms_and_do_not_duplicate(self):
        payment = self.checkout()
        self.deactivate()
        payload = json.dumps({'event': 'charge.success', 'data': {'id': 771, 'reference': payment.reference}})
        signature = hmac.new(b'test-signing-key', payload.encode(), hashlib.sha512).hexdigest()
        with patch('apps.payments.webhooks.get_paystack_service') as provider:
            provider.return_value.verify_transaction.return_value = {'data': self.verified(payment)}
            for _ in range(2):
                response = self.client.post('/api/v1/payments/paystack/webhook/test/', payload,
                    content_type='application/json', HTTP_X_PAYSTACK_SIGNATURE=signature)
                self.assertEqual(response.status_code, 200, response.content)
        fulfill_verified_voucher(payment, self.verified(payment))
        self.assert_original_voucher(payment)

    def test_order_prevents_plan_deletion(self):
        self.checkout()
        self.client.force_authenticate(self.owner)
        response = self.client.delete(f'/api/v1/plans/{self.plan.pk}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(InternetPlan.objects.filter(pk=self.plan.pk).exists())

    def test_radius_failure_remains_recoverable_without_partial_issuance(self):
        payment = self.checkout()
        self.deactivate()
        with patch.object(Radreply.objects, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                fulfill_verified_voucher(payment, self.verified(payment))
        payment.refresh_from_db()
        self.assertIsNotNone(payment.verified_at)
        self.assertIsNone(payment.voucher_id)
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(Radcheck.objects.exists())
        fulfill_verified_voucher(payment, self.verified(payment))
        self.assert_original_voucher(payment)

    def test_amount_mismatch_never_issues_a_voucher(self):
        payment = self.checkout()
        self.deactivate()
        with self.assertRaises(ValueError):
            fulfill_verified_voucher(payment, {**self.verified(payment), 'amount': 1})
        self.assertFalse(Voucher.objects.exists())
        payment.refresh_from_db()
        self.assertIsNone(payment.verified_at)
