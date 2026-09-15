from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.exceptions import PermissionDenied
from apps.tenants.models import Tenant, TenantMembership
from apps.routers.models import NASDevice
from .models import SubscriptionPlan, SubscriptionPayment, TenantSubscription, SubscriptionPeriod
from .services import SubscriptionService
from .entitlements import snapshot_plan, entitlement_terms, router_usage
from .trials import assign_new_tenant_trial, TRIAL_CODE


class OperatorCompatibilityTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Operator', slug='operator')
        self.owner = get_user_model().objects.create_user('operator-owner')
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role='owner')
        self.client.force_authenticate(self.owner)
        self.now = timezone.now()
        self.plan = SubscriptionPlan.objects.create(name='Starter', price=10000, duration_days=30,
            max_routers=1, daily_voucher_print_limit=50, whatsapp_enabled=False)

    def subscribe(self):
        self.sub = TenantSubscription.objects.create(tenant=self.tenant, plan=self.plan,
            status='active', is_trial=False, started_at=self.now-timedelta(days=20), expires_at=self.now+timedelta(days=10))
        self.original = SubscriptionPeriod.objects.create(tenant=self.tenant, plan=self.plan,
            starts_at=self.sub.started_at, ends_at=self.sub.expires_at, terms=snapshot_plan(self.plan))
        return self.sub

    def buy(self, plan, reference='purchase'):
        payment = SubscriptionPayment.objects.create(tenant=self.tenant, plan=plan, amount=plan.price,
            reference=reference, plan_terms=snapshot_plan(plan))
        with patch('django.utils.timezone.now', return_value=self.now):
            SubscriptionService.complete_payment(payment)
        return payment

    def upgrade_plan(self, **changes):
        return SubscriptionPlan.objects.create(**{'name':'Upgrade','price':20000,'duration_days':30,
            'max_routers':3,'daily_voucher_print_limit':100,'whatsapp_enabled':True, **changes})

    def test_new_trial_is_thirty_days_and_existing_trial_deadline_is_preserved(self):
        trial = assign_new_tenant_trial(self.tenant)
        self.assertEqual(trial.expires_at-trial.started_at, timedelta(days=30))
        self.assertEqual(trial.plan.internal_code, TRIAL_CODE)
        old_end = trial.started_at+timedelta(days=15)
        trial.expires_at = old_end
        trial.save()
        self.assertEqual(assign_new_tenant_trial(self.tenant).expires_at, old_end)
        self.assertEqual(self.tenant.subscription_periods.count(), 1)

    def test_upgrade_is_immediate_preserves_paid_time_and_is_idempotent(self):
        self.subscribe()
        payment = self.buy(self.upgrade_plan())
        self.sub.refresh_from_db()
        self.original.refresh_from_db()
        self.assertEqual(entitlement_terms(self.tenant)['max_routers'], 3)
        self.assertEqual(self.sub.expires_at, self.now+timedelta(days=40))
        self.assertEqual(payment.period.starts_at, self.now)
        self.assertTrue(self.original.superseded)
        self.assertEqual(self.original.ends_at, self.now+timedelta(days=10))
        self.assertFalse(SubscriptionService.complete_payment(payment))
        self.assertEqual(SubscriptionPeriod.objects.filter(payment=payment).count(), 1)

    def test_same_plan_renewal_waits_and_does_not_remove_time(self):
        self.subscribe()
        self.plan.max_routers = 4
        self.plan.save()
        payment = self.buy(self.plan)
        self.assertEqual(payment.period.starts_at, self.now+timedelta(days=10))
        self.assertEqual(entitlement_terms(self.tenant)['max_routers'], 1)
        with patch('django.utils.timezone.now', return_value=self.now+timedelta(days=10)):
            self.assertEqual(entitlement_terms(self.tenant)['max_routers'], 4)

    def test_allowance_reduction_is_queued_even_when_price_increases(self):
        self.subscribe()
        payment = self.buy(self.upgrade_plan(daily_voucher_print_limit=10))
        self.assertEqual(payment.period.starts_at, self.now+timedelta(days=10))
        self.assertEqual(entitlement_terms(self.tenant)['daily_voucher_print_limit'], 50)

    def test_queued_paid_rights_are_not_discarded_by_later_change(self):
        self.subscribe()
        self.buy(self.upgrade_plan(max_routers=10), 'future-upgrade')
        payment = self.buy(self.upgrade_plan(max_routers=5), 'lower-cap')
        self.assertEqual(payment.period.starts_at, self.now+timedelta(days=40))
        self.assertEqual(entitlement_terms(self.tenant)['max_routers'], 10)

    def test_unlimited_cannot_be_replaced_immediately_by_finite_allowance(self):
        self.subscribe()
        self.original.terms = {**self.original.terms, 'max_routers':None}
        self.original.save()
        payment = self.buy(self.upgrade_plan())
        self.assertEqual(payment.period.starts_at, self.now+timedelta(days=10))
        self.assertIsNone(entitlement_terms(self.tenant)['max_routers'])

    def test_trial_payment_starts_paid_features_immediately(self):
        assign_new_tenant_trial(self.tenant)
        payment = self.buy(self.upgrade_plan())
        self.assertEqual(payment.period.starts_at, self.now)
        self.assertEqual(payment.period.ends_at, self.now+timedelta(days=30))
        self.assertTrue(entitlement_terms(self.tenant)['whatsapp_enabled'])

    def test_router_activation_checks_capacity_and_deactivation_releases_it(self):
        self.subscribe()
        active = NASDevice.objects.create(tenant=self.tenant, name='Active', ip_address='192.0.2.1')
        inactive = NASDevice.objects.create(tenant=self.tenant, name='Inactive', ip_address='192.0.2.2', is_active=False)
        self.assertEqual(router_usage(self.tenant), 1)
        url = f'/api/v1/routers/{inactive.pk}/'
        self.assertEqual(self.client.patch(url, {'is_active':True}).status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/routers/{active.pk}/', {'is_active':False}).status_code, 200)
        self.assertEqual(self.client.patch(url, {'is_active':True}).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/subscriptions/').data['entitlements']['routers_used'], 1)

    def test_missing_subscription_denies_features_without_creating_a_trial(self):
        with self.assertRaises(PermissionDenied):
            entitlement_terms(self.tenant)
        self.assertEqual(self.client.post('/api/v1/routers/', {'name':'Blocked','ip_address':'192.0.2.5','nas_secret':'test-only'}).status_code, 403)
        self.assertFalse(TenantSubscription.objects.filter(tenant=self.tenant).exists())
        self.assertEqual(self.client.get('/api/v1/subscriptions/').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/pricing/').status_code, 200)

    def test_expired_subscription_allows_read_and_disable_but_not_reactivation(self):
        self.subscribe()
        router = NASDevice.objects.create(tenant=self.tenant, name='Existing', ip_address='192.0.2.1')
        self.sub.expires_at = self.now-timedelta(seconds=1)
        self.sub.save()
        url = f'/api/v1/routers/{router.pk}/'
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.patch(url, {'is_active':False}).status_code, 200)
        self.assertEqual(self.client.patch(url, {'is_active':True}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/subscriptions/').status_code, 200)

    def test_platform_exemption_is_explicit_and_does_not_ignore_suspension(self):
        self.tenant.is_platform_admin = True
        self.tenant.save()
        self.assertIsNone(entitlement_terms(self.tenant)['max_routers'])
        self.tenant.is_active = False
        self.tenant.save()
        with self.assertRaises(PermissionDenied):
            entitlement_terms(self.tenant)

    def test_upgrade_does_not_replace_a_stronger_prepaid_future_period(self):
        self.subscribe()
        self.plan.max_routers = 10
        self.plan.save()
        self.buy(self.plan, 'renewal')
        payment = self.buy(self.upgrade_plan(max_routers=5), 'change')
        self.assertEqual(payment.period.starts_at, self.now+timedelta(days=40))
        self.assertEqual(entitlement_terms(self.tenant)['max_routers'], 1)
        with patch('django.utils.timezone.now', return_value=self.now+timedelta(days=11)):
            self.assertEqual(entitlement_terms(self.tenant)['max_routers'], 10)
