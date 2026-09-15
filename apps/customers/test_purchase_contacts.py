from unittest.mock import patch
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant, TenantMembership
from apps.subscriptions.test_support import grant_test_subscription
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher, Radcheck
from apps.vouchers.radius_test_support import RadiusTablesMixin
from apps.vouchers.terms import snapshot_plan
from apps.payments.recovery import fulfill_verified_voucher
from .models import Customer, DeviceAccessSession
from .purchases import create_purchase_payment


class PurchaseContactTests(RadiusTablesMixin, APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Contacts', slug='purchase-contacts')
        self.other = Tenant.objects.create(name='Other', slug='other-contacts')
        grant_test_subscription(self.tenant)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Day', price=10000, duration_hours=24)
        self.user = get_user_model().objects.create_user(username='contacts-owner', email='contacts-owner@example.test')
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role='owner')

    def purchase(self, reference='test-contact'):
        return create_purchase_payment(tenant=self.tenant, plan=self.plan, reference=reference, amount=self.plan.price,
            customer_email='same@example.test', purchased_terms=snapshot_plan(self.plan))

    def proof(self, payment):
        return dict(status='success', reference=payment.reference, amount=payment.amount, currency='NGN')

    def test_new_purchases_do_not_merge_email_and_fulfillment_retains_customer(self):
        first, second = self.purchase('first'), self.purchase('second')
        self.assertNotEqual(first.customer_id, second.customer_id)
        self.assertEqual(first.customer.name, '')
        self.assertEqual(first.customer.email, second.customer.email)
        payment = fulfill_verified_voucher(first, self.proof(first))
        self.assertEqual(payment.voucher.customer_id, first.customer_id)
        again = fulfill_verified_voucher(payment, self.proof(payment))
        self.assertEqual(again.voucher_id, payment.voucher_id)
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(Voucher.objects.count(), 1)

    def test_failed_reservation_rolls_back_contact(self):
        self.purchase()
        with self.assertRaises(IntegrityError):
            self.purchase()
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_storefront_replay_reuses_contact_and_rejects_customer_assignment(self):
        data = {'plan_id':self.plan.pk, 'email':'same@example.test', 'device_limit':1}
        with patch('apps.payments.views.get_paystack_service') as service:
            service.return_value.initialize_transaction.return_value = {'data':{'authorization_url':'https://checkout.paystack.com/example'}}
            for _ in range(2):
                response = self.client.post('/api/v1/buy/', data, format='json', HTTP_IDEMPOTENCY_KEY='contact-purchase-replay')
                self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(service.return_value.initialize_transaction.call_count, 1)
            self.assertEqual(self.client.post('/api/v1/buy/', {**data, 'customer_id':1}, format='json').status_code, 400)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertIsNotNone(PaymentTransaction.objects.get().customer_id)

    def test_cross_tenant_contact_blocks_issuance_without_radius_rows(self):
        payment = self.purchase()
        alien = Customer.objects.create(tenant=self.other, reference='OTHER', name='Other')
        PaymentTransaction.objects.filter(pk=payment.pk).update(customer=alien)
        with self.assertRaises(ValueError):
            fulfill_verified_voucher(payment, self.proof(payment))
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(Radcheck.objects.exists())

    def test_old_unlinked_payment_stays_unlinked(self):
        payment = PaymentTransaction.objects.create(tenant=self.tenant, plan=self.plan, reference='old-unlinked',
            customer_email='same@example.test', amount=self.plan.price, purchased_terms=snapshot_plan(self.plan))
        fulfilled = fulfill_verified_voucher(payment, self.proof(payment))
        self.assertIsNone(fulfilled.customer_id)
        self.assertIsNone(fulfilled.voucher.customer_id)
        self.assertFalse(Customer.objects.exists())

    def test_history_is_paginated_scoped_manager_only_and_has_no_credentials(self):
        payment = self.purchase()
        payment = fulfill_verified_voucher(payment, self.proof(payment))
        self.client.force_authenticate(self.user)
        url = f'/api/v1/customers/{payment.customer_id}/purchases/'
        response = self.client.get(url, {'page_size':1})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(set(row), {'id','amount','status','created_at','paid_at','plan_name','fulfilled'})
        self.assertTrue(row['fulfilled'])
        self.assertEqual(row['plan_name'], 'Day')
        self.assertNotIn(payment.voucher.username, str(response.data))
        alien = Customer.objects.create(tenant=self.other, reference='OTHER', name='Other')
        self.assertEqual(self.client.get(f'/api/v1/customers/{alien.pk}/purchases/').status_code, 404)
        TenantMembership.objects.filter(user=self.user).update(role='staff')
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_contact_edit_and_archive_preserve_purchase_snapshot_and_access(self):
        payment = self.purchase()
        payment = fulfill_verified_voucher(payment, self.proof(payment))
        self.client.force_authenticate(self.user)
        url = f'/api/v1/customers/{payment.customer_id}/'
        self.assertEqual(self.client.patch(url, {'email':'changed@example.test'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(url+'archive/', {}, format='json').status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.customer_email, 'same@example.test')
        self.assertEqual(payment.customer.email, 'changed@example.test')
        self.assertEqual(payment.voucher.status, 'unused')
        self.assertTrue(Radcheck.objects.filter(username=payment.voucher.username).exists())

    def test_unnamed_contact_and_mac_only_csv_do_not_create_access(self):
        self.client.force_authenticate(self.user)
        response = self.client.post('/api/v1/customers/', {'reference':'ANON', 'name':'', 'mac_address':'legacy MAC text'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['display_name'], 'ANON')
        csv = 'reference,name,mac_address\nMAC-ONLY,,AA-BB-CC-DD-EE-FF'
        preview = self.client.post('/api/v1/customers/import-preview/', {'csv':csv}, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(self.client.post('/api/v1/customers/import-confirm/', {'csv':csv, 'preview_token':preview.data['preview_token']}, format='json').status_code, 201)
        self.assertEqual(Customer.objects.get(reference='MAC-ONLY').name, '')
        self.assertFalse(DeviceAccessSession.objects.exists())
        self.assertFalse(Radcheck.objects.exists())
        self.assertFalse(Voucher.objects.exists())

    def test_source_identity_is_protected_and_unique_within_source_tenant(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post('/api/v1/customers/', {'reference':'BAD', 'legacy_source':'snapshot', 'legacy_id':1}, format='json').status_code, 400)
        Customer.objects.create(tenant=self.tenant, reference='LEGACY-1', legacy_source='snapshot', legacy_id=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create(tenant=self.tenant, reference='LEGACY-2', legacy_source='snapshot', legacy_id=1)
        Customer.objects.create(tenant=self.other, reference='LEGACY-1', legacy_source='snapshot', legacy_id=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create(tenant=self.tenant, reference='INCOMPLETE', legacy_source='snapshot')

    def test_inconsistent_foreign_plan_link_does_not_disclose_its_name(self):
        payment = self.purchase()
        foreign_plan = InternetPlan.objects.create(tenant=self.other, name='Private foreign plan', price=20000, duration_hours=12)
        PaymentTransaction.objects.filter(pk=payment.pk).update(plan=foreign_plan, purchased_terms=None)
        self.client.force_authenticate(self.user)
        response = self.client.get(f'/api/v1/customers/{payment.customer_id}/purchases/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['plan_name'], '')
