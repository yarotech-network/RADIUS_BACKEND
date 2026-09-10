from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant, TenantMembership
from apps.vouchers.models import InternetPlan, Voucher
from .entitlements import entitlement_terms
from .models import SubscriptionPlan, TenantSubscription
from .trials import assign_new_tenant_trial, TRIAL_TERMS


class SignupTrialTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='New tenant', slug='new-tenant')
        self.owner = get_user_model().objects.create_user(username='trialowner')
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role='owner')
        self.client.force_authenticate(self.owner)
        self.subscription = assign_new_tenant_trial(self.tenant)

    def test_limits_are_enforced_and_returned_by_subscription_api(self):
        body = self.client.get('/api/v1/subscriptions/').json()
        self.assertEqual(body['status'], 'trial')
        self.assertEqual(body['entitlements']['terms'], TRIAL_TERMS)
        for number, expected in [(1, 201), (2, 403)]:
            response = self.client.post('/api/v1/routers/', {
                'name': f'Router {number}', 'ip_address': f'10.0.0.{number}', 'nas_secret': 'test-only',
            })
            self.assertEqual(response.status_code, expected, response.data)
        plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=100, duration_hours=24, rate_limit='1M/1M')
        vouchers = Voucher.objects.bulk_create([
            Voucher(tenant=self.tenant, plan=plan, username=f'test-{i}', password='test-only') for i in range(51)
        ])
        ids = [v.pk for v in vouchers[:50]]
        self.assertEqual(self.client.post('/api/v1/vouchers/authorize-print/', {'voucher_ids': ids}, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/vouchers/authorize-print/', {'voucher_ids': ids}, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/vouchers/authorize-print/', {'voucher_ids': [vouchers[-1].pk]}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/v1/whatsapp/routes/', {
            'phone_number_id': 'test', 'access_token_encrypted': 'test-only',
        }).status_code, 403)
        with patch('apps.subscriptions.entitlements.timezone.now', return_value=timezone.now()+timedelta(days=1)):
            self.assertEqual(self.client.post('/api/v1/vouchers/authorize-print/', {'voucher_ids': [vouchers[-1].pk]}, format='json').status_code, 200)
        with patch('django.utils.timezone.now', return_value=self.subscription.expires_at):
            self.assertEqual(self.client.post('/api/v1/vouchers/authorize-print/', {'voucher_ids': ids}, format='json').status_code, 403)
            self.assertEqual(self.client.get('/api/v1/subscriptions/').status_code, 200)
        self.assertEqual(Voucher.objects.filter(tenant=self.tenant, status='unused').count(), 51)

    def test_legacy_tenants_are_unchanged_and_trial_cannot_be_reset(self):
        legacy = Tenant.objects.create(name='Legacy', slug='legacy')
        self.assertIsNone(entitlement_terms(legacy)['max_routers'])
        self.assertFalse(TenantSubscription.objects.filter(tenant=legacy).exists())
        again = assign_new_tenant_trial(self.tenant)
        self.assertEqual(again.pk, self.subscription.pk)
        self.assertEqual(again.expires_at, self.subscription.expires_at)
        self.assertEqual(self.tenant.subscription_periods.count(), 1)
        SubscriptionPlan.objects.filter(pk=again.plan_id).update(max_routers=99)
        self.assertEqual(entitlement_terms(self.tenant)['max_routers'], 1)

    def test_trial_is_not_a_purchasable_or_editable_catalogue_plan(self):
        # Even an accidental admin activation cannot publish this internal plan.
        SubscriptionPlan.objects.filter(pk=self.subscription.plan_id).update(is_active=True)
        self.assertEqual(self.client.get('/api/v1/pricing/').json()['count'], 0)
        self.assertEqual(self.client.post('/api/v1/subscriptions/checkout/', {'plan_id': self.subscription.plan_id}).status_code, 400)
        self.owner.is_platform_admin = True
        self.owner.save()
        self.assertEqual(self.client.get('/api/v1/platform/business-plans/').json()['count'], 0)

    def test_platform_created_tenant_receives_trial(self):
        self.owner.is_platform_admin = True
        self.owner.save()
        response = self.client.post('/api/v1/tenants/', {'name': 'Admin created', 'slug': 'admin-created'})
        self.assertEqual(response.status_code, 201, response.data)
        created = Tenant.objects.get(pk=response.data['id'])
        self.assertEqual(entitlement_terms(created), TRIAL_TERMS)
        self.assertEqual(SubscriptionPlan.objects.filter(internal_code='signup-trial-v1').count(), 1)


class ConcurrentTrialTests(TransactionTestCase):
    def test_simultaneous_new_tenants_share_one_internal_plan(self):
        tenants = [Tenant.objects.create(name=f'Tenant {i}', slug=f'tenant-{i}') for i in range(2)]
        barrier = Barrier(2)
        def assign(tenant):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return assign_new_tenant_trial(tenant).pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(assign, tenants))
        self.assertEqual(len(set(results)), 2)
        self.assertEqual(SubscriptionPlan.objects.filter(internal_code='signup-trial-v1').count(), 1)
        for tenant in tenants:
            self.assertEqual(entitlement_terms(tenant), TRIAL_TERMS)
