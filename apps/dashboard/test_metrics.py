from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, DatabaseError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from apps.agents.models import (AgentProfile, AgentVoucherAllocation, AgentCreditAccount,
    AgentCreditBatch, AgentCreditLedger, AgentCreditMovement)
from apps.routers.models import NASDevice
from apps.tenants.models import Tenant, TenantMembership
from apps.vouchers.models import InternetPlan, Voucher, PaymentTransaction, Radacct
from .metrics import business_metrics
from .network import sample_rates


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class MetricsTests(APITransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.created = 'radacct' not in connection.introspection.table_names()
        if cls.created:
            with connection.schema_editor() as editor:
                editor.create_model(Radacct)

    @classmethod
    def tearDownClass(cls):
        if cls.created:
            with connection.schema_editor() as editor:
                editor.delete_model(Radacct)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        Radacct.objects.all().delete()
        self.tenant = Tenant.objects.create(name='One', slug='one')
        self.other = Tenant.objects.create(name='Two', slug='two')
        self.user = get_user_model().objects.create_user(username='owner')
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role='owner')
        self.client.force_authenticate(self.user)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Day', price=1000, duration_hours=24)
        self.voucher = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='own', password='secret')
        self.router = NASDevice.objects.create(tenant=self.tenant, name='Router', ip_address='192.0.2.1', onboarding_state='active')
        self.now = datetime(2026, 9, 15, 0, 30, tzinfo=dt_timezone.utc)

    def row(self, name='own', ip='192.0.2.1', **kwargs):
        data = dict(username=name, nasipaddress=ip, sessionid=str(Radacct.objects.count()),
                    acctstarttime=self.now-timedelta(hours=3), acctupdatetime=self.now,
                    acctinputoctets=100, acctoutputoctets=200)
        data.update(kwargs)
        return Radacct.objects.create(**data)

    def test_financial_sources_periods_and_no_print_or_topup_revenue(self):
        payment = PaymentTransaction.objects.create(tenant=self.tenant, reference='paid', amount=1000,
            status='success', customer_email='owner@example.com', voucher=self.voucher)
        # 23:30 UTC is already today's 00:30 in Lagos.
        PaymentTransaction.objects.filter(pk=payment.pk).update(created_at=self.now-timedelta(hours=1))
        PaymentTransaction.objects.create(tenant=self.other, reference='other', amount=99000, status='success')
        PaymentTransaction.objects.create(tenant=self.tenant, reference='failed', amount=99000, status='failed')
        agent_user = get_user_model().objects.create_user(username='agent', email='agent@example.com')
        agent = AgentProfile.objects.create(tenant=self.tenant, user=agent_user)
        AgentVoucherAllocation.objects.create(agent=agent, voucher=self.voucher, amount_charged=500)
        manual = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='manual', password='x')
        allocation = AgentVoucherAllocation.objects.create(agent=agent, voucher=manual, amount_charged=700)
        AgentVoucherAllocation.objects.filter(pk=allocation.pk).update(created_at=self.now-timedelta(minutes=20))
        account = AgentCreditAccount.objects.create(agent=agent)
        batch = AgentCreditBatch.objects.create(agent=agent, plan=self.plan, quantity=1,
            unit_price=1000, retail_price=1000, commission_rate=0, total=1000, repaid=200)
        ledger = AgentCreditLedger.objects.create(credit_account=account, amount=-200)
        import uuid
        movement = AgentCreditMovement.objects.create(tenant=self.tenant, batch=batch, ledger=ledger,
            actor=self.user, kind='repay', request_key=uuid.uuid4(), request_payload={},
            previous_balance=1000, new_balance=800)
        AgentCreditMovement.objects.filter(pk=movement.pk).update(created_at=self.now-timedelta(minutes=10))
        with patch('apps.dashboard.metrics.timezone.now', return_value=self.now):
            data = business_metrics(self.tenant)
        self.assertEqual(data['total_revenue'], 1000)
        self.assertEqual(data['collected_revenue'], {'total': 1900, 'today': 1900, 'month': 1900})
        self.assertEqual(data['failed_payments'], 1)
        self.assertEqual(data['successful_payments'], 1)
        self.assertEqual(data['revenue_sources']['agent_wallet'], 700)
        self.assertNotIn('secret', str(data))

    def test_voucher_expiry_is_read_only_and_deleted_records_excluded(self):
        self.voucher.status = 'active'
        self.voucher.expires_at = self.now - timedelta(minutes=1)
        self.voucher.save()
        Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='gone', password='x', deleted_at=self.now)
        with patch('apps.dashboard.metrics.timezone.now', return_value=self.now):
            data = business_metrics(self.tenant)
        self.assertEqual(data['total_vouchers'], 1)
        self.assertEqual(data['voucher_usage']['expired'], 1)
        self.assertEqual(data['active_vouchers'], 0)
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.status, 'active')

    def test_network_scope_freshness_and_cross_midnight_traffic(self):
        self.row()
        self.row(acctupdatetime=self.now-timedelta(minutes=6), acctinputoctets=300)
        self.row(name='foreign', acctinputoctets=99000)
        self.row(ip='192.0.2.99', acctinputoctets=99000)
        with patch('apps.dashboard.network.timezone.now', return_value=self.now):
            response = self.client.get('/api/v1/dashboard/network/')
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['online_users'], 1)
        self.assertEqual(data['stale_sessions'], 1)
        self.assertEqual(data['sessions_today'], 0)
        self.assertEqual(data['today_upload_bytes'], 400)
        self.assertEqual(data['live_upload_bytes'], 100)
        self.assertEqual(data['router_counts']['online'], 1)
        self.assertIsNone(data['download_bytes_per_second'])
        self.assertNotIn('username', str(data))

    def test_ambiguous_nas_excluded_and_active_config_is_not_online(self):
        NASDevice.objects.create(tenant=self.other, name='Duplicate', ip_address=self.router.ip_address)
        self.row()
        with patch('apps.dashboard.network.timezone.now', return_value=self.now):
            data = self.client.get('/api/v1/dashboard/network/').data
        self.assertEqual(data['online_users'], 0)
        self.assertEqual(data['router_counts']['unknown'], 1)
        self.assertEqual(data['router_counts']['offline'], 0)

    def test_network_failure_is_not_zero_and_anonymous_access_denied(self):
        with patch('apps.dashboard.network.network_metrics', side_effect=DatabaseError('private database details')):
            response = self.client.get('/api/v1/dashboard/network/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', str(response.data))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/v1/dashboard/network/').status_code, 401)

    def test_rate_samples_do_not_invent_speeds_on_reconnect_or_counter_reset(self):
        def row(upload, seconds=0, identity=1):
            return {'radacctid': identity, 'acctupdatetime': self.now+timedelta(seconds=seconds),
                    'acctinputoctets': upload, 'acctoutputoctets': upload*2}
        self.assertIsNone(sample_rates(1, [row(100)], self.now)['upload_bytes_per_second'])
        self.assertEqual(sample_rates(1, [row(700, 60)], self.now)['upload_bytes_per_second'], 10)
        self.assertIsNone(sample_rates(2, [row(700, 60)], self.now)['upload_bytes_per_second'])
        self.assertIsNone(sample_rates(1, [row(10, 120)], self.now)['upload_bytes_per_second'])
        self.assertIsNone(sample_rates(1, [row(1000, 180, 2)], self.now)['upload_bytes_per_second'])

    def test_live_list_also_excludes_stale_records(self):
        self.row(acctstarttime=timezone.now(), acctupdatetime=timezone.now())
        self.row(acctupdatetime=timezone.now()-timedelta(minutes=6))
        response = self.client.get('/api/v1/dashboard/live-users/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_delegated_staff_need_network_grant_for_explicit_tenant(self):
        from apps.accounts.staff_models import StaffAssignment
        staff = get_user_model().objects.create_user(username='support', email='support@example.com')
        assignment = StaffAssignment.objects.create(user=staff, tenant=self.tenant, services=['payments.view'])
        self.client.force_authenticate(staff)
        url = '/api/v1/dashboard/network/'
        self.assertEqual(self.client.get(url, HTTP_X_TENANT_ID=str(self.tenant.pk)).status_code, 403)
        assignment.services = ['live_sessions.view']
        assignment.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(url, HTTP_X_TENANT_ID=str(self.other.pk)).status_code, 403)
        self.assertEqual(self.client.get(url, HTTP_X_TENANT_ID=str(self.tenant.pk)).status_code, 200)

    def test_revenue_periods_exclude_previous_day_and_previous_month(self):
        for reference, when in [('yesterday', self.now-timedelta(days=1)), ('last-month', self.now-timedelta(days=31))]:
            payment = PaymentTransaction.objects.create(tenant=self.tenant, reference=reference, amount=1000, status='success')
            PaymentTransaction.objects.filter(pk=payment.pk).update(created_at=when)
        with patch('apps.dashboard.metrics.timezone.now', return_value=self.now):
            data = business_metrics(self.tenant)
        self.assertEqual(data['collected_revenue'], {'today': 0, 'month': 1000, 'total': 2000})
