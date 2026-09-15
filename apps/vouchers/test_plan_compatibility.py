from apps.vouchers.test_support import authenticated_activation
from apps.subscriptions.test_support import grant_test_subscription
from apps.vouchers.radius_test_support import RadiusTablesMixin
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.agents.models import AgentProfile, AgentWallet
from apps.agents.services import AgentService
from apps.routers.models import NASDevice
from apps.tenants.models import Tenant, TenantMembership
from .models import InternetPlan, Voucher, Radcheck, Radreply, PaymentTransaction
from .services import VoucherService
from .terms import snapshot_plan


class PlanCompatibilityTests(RadiusTablesMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name='Home', slug='home')
        grant_test_subscription(self.tenant)
        self.other = Tenant.objects.create(name='Other', slug='other')
        grant_test_subscription(self.other)
        self.owner = get_user_model().objects.create_user('owner', 'owner@example.test')
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role='owner')
        self.client.force_authenticate(self.owner)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Half hour', price=12500,
            duration_hours=Decimal('0.5'), rate_limit='2M/5M', data_limit=100)

    def test_fractional_hours_round_to_issued_seconds_and_activate_unchanged(self):
        response = self.client.post('/api/v1/plans/', {'name': 'Short', 'price': 100,
            'duration_hours': '0.333333', 'rate_limit': '1M/2M'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['duration_seconds'], 1200)
        voucher = VoucherService.generate_vouchers(self.tenant, response.data['id'], 1)[0]
        self.assertEqual(Radcheck.objects.get(username=voucher.username, attribute='Max-Days').value, '1200')
        authenticated_activation(voucher)
        self.assertEqual((voucher.expires_at - voucher.activated_at).total_seconds(), 1200)

    def test_all_new_issuance_terms_survive_plan_edits(self):
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)[0]
        original = dict(voucher.service_terms)
        response = self.client.patch(f'/api/v1/plans/{self.plan.pk}/', {
            'name': 'Changed', 'duration_hours': 24, 'price': 20000,
            'data_limit': 500, 'rate_limit': '3M/8M'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        voucher.refresh_from_db()
        self.assertEqual(voucher.service_terms, original)
        self.assertEqual(Radreply.objects.get(username=voucher.username).value, '2M/5M')
        authenticated_activation(voucher)
        self.assertEqual((voucher.expires_at - voucher.activated_at).total_seconds(), 1800)

    def test_manual_api_creation_snapshots_and_cannot_change_issued_capacity(self):
        response = self.client.post('/api/v1/vouchers/', {'username': 'manual', 'password': 'test-pass',
            'plan': self.plan.pk, 'device_limit': 3}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        voucher = Voucher.objects.get(pk=response.data['id'])
        self.assertEqual(voucher.service_terms['device_limit'], 3)
        self.assertEqual(Radcheck.objects.get(username='manual', attribute='Simultaneous-Use').value, '3')
        self.assertEqual(self.client.patch(f'/api/v1/vouchers/{voucher.pk}/', {'device_limit': 4}).status_code, 400)

    def test_archive_keeps_history_and_blocks_reactivation(self):
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)[0]
        response = self.client.delete(f'/api/v1/plans/{self.plan.pk}/')
        self.assertEqual(response.status_code, 204, response.data)
        self.plan.refresh_from_db()
        self.assertIsNotNone(self.plan.archived_at)
        self.assertFalse(self.plan.is_active or self.plan.is_public or self.plan.agent_enabled)
        self.assertEqual(self.client.get('/api/v1/plans/').data['count'], 0)
        self.assertEqual(self.client.get('/api/v1/plans/?archived=true').data['count'], 1)
        self.assertEqual(self.client.patch(f'/api/v1/plans/{self.plan.pk}/', {'is_active': True}).status_code, 400)
        authenticated_activation(voucher)
        self.assertEqual((voucher.expires_at - voucher.activated_at).total_seconds(), 1800)
        with self.assertRaises(InternetPlan.DoesNotExist):
            VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)

    def test_queryset_delete_archives_and_model_cannot_reactivate(self):
        InternetPlan.objects.filter(pk=self.plan.pk).delete()
        self.plan.refresh_from_db()
        self.plan.archived_at = None
        self.plan.is_active = True
        with self.assertRaises(ValidationError):
            self.plan.save()

    def test_private_plan_is_not_publicly_listed_or_purchasable(self):
        self.plan.is_public = False
        self.plan.save()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/v1/public/tenants/home/plans/').data['count'], 0)
        with patch('apps.payments.views.get_paystack_service') as provider:
            response = self.client.post('/api/v1/buy/', {'plan_id': self.plan.pk, 'email': 'buyer@example.test'})
        self.assertEqual(response.status_code, 400, response.data)
        provider.assert_not_called()

    def make_agent(self):
        user = get_user_model().objects.create_user('agent', 'agent@example.test')
        agent = AgentProfile.objects.create(user=user, tenant=self.tenant, status='active')
        AgentWallet.objects.create(agent=agent, balance=100000)
        return agent

    def test_agent_catalogue_uses_own_private_enabled_plans_and_issuance_snapshots(self):
        agent = self.make_agent()
        self.plan.is_public = False
        self.plan.save()
        InternetPlan.objects.create(tenant=self.other, name='Other', price=1, duration_hours=1)
        self.client.force_authenticate(agent.user)
        data = self.client.get('/api/v1/agent/plans/').data
        self.assertEqual([p['id'] for p in data['results']], [self.plan.pk])
        vouchers, _ = AgentService.generate_voucher_from_wallet(agent, self.plan.pk)
        self.assertEqual(vouchers[0].service_terms['duration_seconds'], 1800)
        self.plan.agent_enabled = False
        self.plan.save()
        agent.wallet.refresh_from_db()
        balance = agent.wallet.balance
        with self.assertRaises(ValueError):
            AgentService.generate_voucher_from_wallet(agent, self.plan.pk)
        agent.wallet.refresh_from_db()
        self.assertEqual(agent.wallet.balance, balance)
        self.assertEqual(self.client.get('/api/v1/agent/plans/').data['count'], 0)

    def test_iot_scope_and_cross_tenant_router_validation(self):
        router = NASDevice.objects.create(tenant=self.other, name='Other', ip_address='192.0.2.11')
        response = self.client.patch(f'/api/v1/plans/{self.plan.pk}/', {
            'plan_type': 'iot_mac', 'public_router': str(router.pk)}, format='json')
        self.assertEqual(response.status_code, 400)
        self.plan.plan_type = 'iot_mac'
        self.plan.is_public = False
        self.plan.save()
        with self.assertRaises(InternetPlan.DoesNotExist):
            VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)

    def test_reserved_customer_terms_still_fulfill_after_archival(self):
        terms = snapshot_plan(self.plan)
        PaymentTransaction.objects.create(tenant=self.tenant, plan=self.plan, reference='reserved',
            amount=self.plan.price, customer_email='buyer@example.test', purchased_terms=terms)
        self.plan.delete()
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1,
            source='customer', purchased_terms=terms)[0]
        self.assertEqual(voucher.service_terms['duration_seconds'], 1800)

    def test_legacy_duration_and_empty_rate_enforcement_are_preserved(self):
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)[0]
        Voucher.objects.filter(pk=voucher.pk).update(purchased_terms=None, issued_duration_seconds=None, rate_limit_snapshot='')
        Radreply.objects.filter(username=voucher.username).delete()
        self.plan.duration_hours = 10
        self.plan.save()
        voucher.refresh_from_db()
        self.assertEqual(voucher.service_terms['duration_seconds'], 1800)
        self.assertEqual(voucher.service_terms['radius_rate_limit'], '')

    def test_unknown_historical_duration_blocks_plan_edit_without_partial_writes(self):
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)[0]
        Voucher.objects.filter(pk=voucher.pk).update(purchased_terms=None, issued_duration_seconds=None)
        Radcheck.objects.filter(username=voucher.username).delete()
        self.plan.duration_hours = 10
        with self.assertRaises(ValidationError):
            self.plan.save()
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.duration_hours, Decimal('0.5'))

    def test_bad_duration_and_tenant_access_fail(self):
        for duration in ('0', '0.000001', '-1', '1.0000001'):
            response = self.client.patch(f'/api/v1/plans/{self.plan.pk}/', {'duration_hours': duration}, format='json')
            self.assertEqual(response.status_code, 400)
        other = InternetPlan.objects.create(tenant=self.other, name='Other', price=1, duration_hours=1)
        self.assertEqual(self.client.delete(f'/api/v1/plans/{other.pk}/').status_code, 404)

    def test_unknown_order_terms_block_edit_and_archive(self):
        PaymentTransaction.objects.create(tenant=self.tenant, plan=self.plan, reference='unknown-order', amount=100)
        with self.assertRaises(ValidationError):
            self.plan.delete()
        self.plan.price = 200
        with self.assertRaises(ValidationError):
            self.plan.save()
        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.archived_at)
        self.assertEqual(self.plan.price, 12500)

    def test_legacy_voucher_rename_preserves_radius_duration(self):
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)[0]
        Voucher.objects.filter(pk=voucher.pk).update(purchased_terms=None, issued_duration_seconds=None)
        response = self.client.patch(f'/api/v1/vouchers/{voucher.pk}/', {'username': 'renamed-legacy'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        voucher.refresh_from_db()
        self.assertEqual(voucher.service_terms['duration_seconds'], 1800)
        self.assertEqual(Radcheck.objects.get(username=voucher.username, attribute='Max-Days').value, '1800')

    def test_audit_is_read_only_and_reports_unknown_ids_without_credentials(self):
        from io import StringIO
        from django.core.management import call_command, CommandError
        voucher = VoucherService.generate_vouchers(self.tenant, self.plan.pk, 1)[0]
        Voucher.objects.filter(pk=voucher.pk).update(purchased_terms=None, issued_duration_seconds=None)
        Radcheck.objects.filter(username=voucher.username).delete()
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command('audit_plan_compatibility', stdout=output)
        self.assertIn(f'Unresolved voucher id={voucher.pk}', output.getvalue())
        self.assertNotIn(voucher.username, output.getvalue())
        voucher.refresh_from_db()
        self.assertIsNone(voucher.purchased_terms)
