from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from apps.tenants.models import Tenant, TenantMembership
from apps.agents.models import AgentProfile
from apps.vouchers.models import InternetPlan, PaymentTransaction
from apps.vouchers.services import VoucherService
from apps.vouchers.terms import snapshot_plan
from apps.vouchers.radius_test_support import RadiusTablesMixin
from .test_support import grant_test_subscription
from .models import SubscriptionPayment
from .services import SubscriptionService


class SubscriptionAccessGateTests(RadiusTablesMixin, APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Gate', slug='gate')
        self.owner = get_user_model().objects.create_user(username='gate-owner', email='gate@example.test',
            password='Strong-password-724!')
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role='owner')
        self.sub = grant_test_subscription(self.tenant)
        self.sub.expires_at = timezone.now()-timedelta(seconds=1)
        self.sub.save()
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=1000, duration_hours=24)
        self.authenticate(self.owner)

    def authenticate(self, user):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+str(RefreshToken.for_user(user).access_token))

    def test_login_succeeds_but_dashboard_and_operational_apis_are_blocked(self):
        self.client.credentials()
        response = self.client.post('/api/v1/auth/login/', {'username':'gate-owner','password':'Strong-password-724!'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+response.data['access'])
        for url in ['/api/v1/plans/', '/api/v1/routers/', '/api/v1/vouchers/', '/api/v1/audit-events/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, response.data)
            self.assertEqual(response.data['code'], 'subscription_required')
        self.assertEqual(self.client.get('/api/v1/auth/user/').status_code, 200)
        access = self.client.get('/api/v1/subscriptions/access/')
        self.assertTrue(access.data['required'])
        self.assertTrue(access.data['can_renew'])

    def test_staff_and_agent_are_blocked_without_becoming_owners(self):
        for role in ['staff', 'agent']:
            user = get_user_model().objects.create_user(username='gate-'+role, email=role+'@example.test')
            if role == 'staff':
                TenantMembership.objects.create(user=user, tenant=self.tenant, role=role)
                url = '/api/v1/plans/'
            else:
                AgentProfile.objects.create(user=user, tenant=self.tenant, status='active')
                url = '/api/v1/agent/dashboard/'
            self.authenticate(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            access = self.client.get('/api/v1/subscriptions/access/').data
            self.assertTrue(access['required'])
            self.assertFalse(access['can_renew'])
            self.assertEqual(self.client.post('/api/v1/subscriptions/checkout/', {'plan_id':self.sub.plan_id}).status_code, 403)

    def test_public_checkout_and_catalogue_stop_without_provider_call_or_order(self):
        self.client.credentials()
        with patch('apps.payments.views.get_paystack_service') as provider:
            result = self.client.post('/api/v1/buy/', {'plan_id':self.plan.pk, 'email':'buyer@example.test'}, format='json')
        self.assertEqual(result.status_code, 403, result.data)
        provider.assert_not_called()
        self.assertFalse(PaymentTransaction.objects.exists())
        catalogue = self.client.get('/api/v1/public/tenants/gate/plans/')
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.data['results'], [])
        self.assertEqual(catalogue['Cache-Control'], 'no-store')
        self.sub.expires_at = timezone.now()+timedelta(days=30)
        self.sub.save()
        restored = self.client.get('/api/v1/public/tenants/gate/plans/')
        self.assertEqual([plan['id'] for plan in restored.data['results']], [self.plan.pk])

    def test_owner_can_pay_and_successful_completion_unlocks_existing_token(self):
        with patch('apps.subscriptions.views.get_paystack_service') as provider:
            provider.return_value.initialize_transaction.return_value={'data':{'authorization_url':'https://checkout.example.test/pay'}}
            result = self.client.post('/api/v1/subscriptions/checkout/', {'plan_id':self.sub.plan_id}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        payment = SubscriptionPayment.objects.get(reference=result.data['reference'])
        SubscriptionService.complete_payment(payment)
        self.assertFalse(self.client.get('/api/v1/subscriptions/access/').data['required'])
        self.assertEqual(self.client.get('/api/v1/plans/').status_code, 200)

    def test_missing_and_cancelled_subscriptions_cannot_bypass_gate(self):
        self.sub.status = 'cancelled'
        self.sub.expires_at = timezone.now()+timedelta(days=30)
        self.sub.save()
        self.assertEqual(self.client.get('/api/v1/plans/').status_code, 403)
        self.sub.delete()
        self.assertEqual(self.client.get('/api/v1/plans/').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/subscriptions/access/').data['status'], 'missing')

    def test_platform_access_is_separate_from_expired_workspace(self):
        self.owner.is_platform_admin = True
        self.owner.save()
        self.authenticate(self.owner)
        self.assertFalse(self.client.get('/api/v1/subscriptions/access/').data['required'])
        self.assertTrue(self.client.get('/api/v1/subscriptions/access/', HTTP_X_ACCESS_CONTEXT='workspace').data['required'])
        self.assertEqual(self.client.get('/api/v1/plans/', HTTP_X_ACCESS_CONTEXT='workspace').status_code, 403)

    def test_already_reserved_customer_order_can_be_fulfilled(self):
        terms = snapshot_plan(self.plan)
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1, source='customer', purchased_terms=terms)[0]
        self.assertEqual(voucher.service_terms['duration_seconds'], 86400)
        from .access import SubscriptionRequired
        with self.assertRaises(SubscriptionRequired):
            VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)

    def test_hiding_storefront_does_not_change_issued_voucher_credentials(self):
        from apps.vouchers.models import Voucher, Radcheck, Radreply
        self.sub.expires_at = timezone.now()+timedelta(days=30)
        self.sub.save()
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)[0]
        before_voucher = Voucher.objects.filter(pk=voucher.pk).values().get()
        before_checks = list(Radcheck.objects.filter(username=voucher.username).values())
        before_replies = list(Radreply.objects.filter(username=voucher.username).values())
        self.sub.expires_at = timezone.now()-timedelta(seconds=1)
        self.sub.save()
        self.client.credentials()
        self.assertEqual(self.client.get('/api/v1/public/tenants/gate/plans/').data['results'], [])
        self.assertEqual(Voucher.objects.filter(pk=voucher.pk).values().get(), before_voucher)
        self.assertEqual(list(Radcheck.objects.filter(username=voucher.username).values()), before_checks)
        self.assertEqual(list(Radreply.objects.filter(username=voucher.username).values()), before_replies)
