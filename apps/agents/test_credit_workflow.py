import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from apps.subscriptions.test_support import grant_test_subscription
from apps.vouchers.models import InternetPlan, Voucher, Radacct, Radpostauth, Radcheck
from .tests import AgentFixtureMixin
from .models import AgentCreditAccount, AgentCreditBatch, AgentCreditLedger, AgentCreditMovement


class CreditWorkflowTests(AgentFixtureMixin, APITestCase):
    @classmethod
    def setUpClass(cls):
        cls.extra_tables = []
        for model in (Radacct, Radpostauth):
            if model._meta.db_table not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)
                cls.extra_tables.append(model)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        for model in reversed(cls.extra_tables):
            with connection.schema_editor() as editor:
                editor.delete_model(model)

    def setUp(self):
        self.tenant = Tenant.objects.create(name='Credit', slug='credit-test')
        grant_test_subscription(self.tenant)
        self.user, self.agent, self.wallet = self.create_agent()
        self.owner = get_user_model().objects.create_user(username='owner', email='owner@credit.test')
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role='owner')
        self.client.force_authenticate(self.owner)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=10000, duration_hours=24, agent_enabled=True)
        self.account = AgentCreditAccount.objects.create(agent=self.agent, credit_limit=100000)
        self.url = f'/api/v1/tenant/agents/{self.agent.pk}/'

    def command(self, kind, **payload):
        payload.setdefault('request_key', str(uuid.uuid4()))
        if kind == 'reverse':
            batch = AgentCreditBatch.objects.get(pk=payload['batch_id'])
            payload.setdefault('expected_outstanding', batch.outstanding)
            payload.setdefault('expected_repaid', batch.repaid)
        return self.client.post(self.url + f'credit-{kind}/', payload, format='json')

    def issue(self, **extra):
        payload = dict(plan_id=self.plan.pk, quantity=2, expected_total=18000)
        payload.update(extra)
        result = self.command('issue', **payload)
        self.assertEqual(result.status_code, 200, result.data)
        return result.data

    def repay(self, batch, amount=4000, **extra):
        payload = dict(batch_id=batch['id'], amount=amount, method='cash', received_on='2026-09-15', external_reference='RECEIPT-1')
        payload.update(extra)
        return self.command('repay', **payload)

    def test_partial_repayment_then_reversal_retains_repayment_and_wallet(self):
        batch = self.issue()
        self.assertEqual(self.repay(batch).status_code, 200)
        result = self.command('reverse', batch_id=batch['id'], reason='Returned unused vouchers')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual((result.data['repaid'], result.data['cancelled_debt'], result.data['outstanding']), (4000, 14000, 0))
        self.account.refresh_from_db()
        self.wallet.refresh_from_db()
        self.assertEqual(self.account.current_balance, 0)
        self.assertEqual(self.wallet.balance, 100000)
        self.assertEqual(list(AgentCreditLedger.objects.order_by('pk').values_list('amount', flat=True)), [18000, -4000, -14000])
        self.assertEqual(Voucher.objects.filter(status='disabled').count(), 2)
        self.assertFalse(Radcheck.objects.exists())
        self.assertEqual(self.command('reverse', batch_id=batch['id'], reason='Retry').status_code, 200)
        self.assertEqual(AgentCreditMovement.objects.count(), 3)

    def test_request_replay_and_payload_conflict(self):
        key = str(uuid.uuid4())
        batch = self.issue(request_key=key)
        self.assertEqual(self.issue(request_key=key)['id'], batch['id'])
        self.assertEqual(AgentCreditBatch.objects.count(), 1)
        result = self.command('issue', request_key=key, plan_id=self.plan.pk, quantity=1, expected_total=9000)
        self.assertEqual(result.status_code, 400)

    def test_receipt_duplicate_overpayment_and_replay(self):
        batch = self.issue()
        key = str(uuid.uuid4())
        self.assertEqual(self.repay(batch, request_key=key).status_code, 200)
        self.assertEqual(self.repay(batch, request_key=key).status_code, 200)
        self.assertEqual(self.repay(batch).status_code, 400)
        self.assertEqual(self.repay(batch, amount=14001, external_reference='SECOND').status_code, 400)
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 14000)

    def test_limit_required_and_negative_history_preserved(self):
        for balance, limit in [(0, 0), (0, 17000), (-500, 100000)]:
            self.account.current_balance, self.account.credit_limit = balance, limit
            self.account.save()
            result = self.command('issue', plan_id=self.plan.pk, quantity=2, expected_total=18000)
            self.assertEqual(result.status_code, 400)
            self.account.refresh_from_db()
            self.assertEqual(self.account.current_balance, balance)
        self.assertFalse(Voucher.objects.exists())

    def test_price_snapshot_and_changed_quote(self):
        self.plan.price = 101
        self.plan.save()
        self.assertEqual(self.command('issue', plan_id=self.plan.pk, quantity=2, expected_total=18000).status_code, 400)
        batch = self.issue(expected_total=182)
        self.assertEqual(batch['unit_price'], 91)
        self.agent.commission_rate = 50
        self.agent.save()
        self.assertEqual(AgentCreditBatch.objects.get(pk=batch['id']).total, 182)

    def test_rollback_includes_vouchers_radius_and_balance(self):
        with patch('apps.agents.credit._movement', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.issue()
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 0)
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(Radcheck.objects.exists())
        self.assertFalse(AgentCreditBatch.objects.exists())

    def test_used_bound_expired_or_uncertain_vouchers_block_reversal(self):
        batch = self.issue()
        voucher = Voucher.objects.first()
        for changes in [dict(is_used=True), dict(bound_device_mac='AA:BB:CC:DD:EE:FF'),
                        dict(expires_at=timezone.now()), dict(legacy_provenance={'source': 'legacy'})]:
            Voucher.objects.filter(pk=voucher.pk).update(**changes)
            self.assertEqual(self.command('reverse', batch_id=batch['id'], reason='Return').status_code, 400)
            Voucher.objects.filter(pk=voucher.pk).update(is_used=False, bound_device_mac='', expires_at=None, legacy_provenance=None)
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 18000)

    def test_accounting_history_blocks_reversal(self):
        batch = self.issue()
        Radacct.objects.create(username=Voucher.objects.first().username, sessionid='old', nasipaddress='127.0.0.1')
        self.assertEqual(self.command('reverse', batch_id=batch['id'], reason='Return').status_code, 400)

    def test_owner_only_and_cross_tenant_denial(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.url+'credit/').status_code, 403)
        membership = self.owner.membership
        membership.role = 'manager'
        membership.save()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.owner.pk))
        self.assertEqual(self.client.get(self.url+'credit/').status_code, 403)
        membership.role = 'owner'
        membership.tenant = Tenant.objects.create(name='Other', slug='other-credit')
        membership.save()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.owner.pk))
        self.assertEqual(self.client.get(self.url+'credit/').status_code, 404)

    def test_settings_preserve_balance_detect_stale_update_and_get_does_not_create(self):
        self.issue()
        before = self.client.get(self.url+'credit/').data
        payload = dict(credit_limit=1000, is_active=False, expected=before, note='Pause further credit')
        response = self.client.patch(self.url+'credit/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['current_balance'], 18000)
        self.assertEqual(self.client.patch(self.url+'credit/', payload, format='json').status_code, 400)
        _, agent, _ = self.create_agent(username='unconfigured')
        response = self.client.get(f'/api/v1/tenant/agents/{agent.pk}/credit/')
        self.assertFalse(response.data['exists'])
        self.assertFalse(AgentCreditAccount.objects.filter(agent=agent).exists())

    def test_history_is_paginated_and_contains_receipt_evidence(self):
        batch = self.issue()
        self.repay(batch)
        result = self.client.get(self.url+'credit-history/', {'page_size': 1})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['count'], 2)
        self.assertEqual(result.data['results'][0]['evidence']['external_reference'], 'RECEIPT-1')
        self.assertNotIn('request_payload', result.data['results'][0]['evidence'])

    def test_agent_reads_only_own_credit_and_cannot_record_payments(self):
        self.issue()
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/v1/agent/credit/batches/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(self.client.post('/api/v1/agent/credit/', {'amount': 10}).status_code, 405)
        other_user, _, _ = self.create_agent(username='other-agent')
        self.client.force_authenticate(other_user)
        self.assertEqual(self.client.get('/api/v1/agent/credit/batches/').data['count'], 0)

    def test_disabled_account_can_accept_repayment_but_not_new_credit(self):
        batch = self.issue(due_date='2026-10-15')
        self.assertEqual(batch['due_date'], '2026-10-15')
        self.account.is_active = False
        self.account.save(update_fields=['is_active'])
        self.assertEqual(self.repay(batch).status_code, 200)
        self.assertEqual(self.command('issue', plan_id=self.plan.pk, quantity=1, expected_total=9000).status_code, 400)

    def test_full_repayment_reversal_records_zero_debt_cancellation_without_refund(self):
        batch = self.issue()
        self.assertEqual(self.repay(batch, amount=18000).status_code, 200)
        result = self.command('reverse', batch_id=batch['id'], reason='Return unused')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['repaid'], 18000)
        self.assertEqual(result.data['cancelled_debt'], 0)
        from .services import AgentService
        self.assertEqual(AgentService.get_agent_stats(self.agent)['commission_this_month'], 0)

    def test_reversal_failure_restores_radius_and_debt(self):
        batch = self.issue()
        before = Radcheck.objects.count()
        with patch('apps.agents.credit._movement', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.command('reverse', batch_id=batch['id'], reason='Return')
        self.assertEqual(Radcheck.objects.count(), before)
        self.assertFalse(Voucher.objects.filter(status='disabled').exists())
        self.assertIsNone(AgentCreditBatch.objects.get(pk=batch['id']).reversed_at)

    def test_expired_operator_cannot_issue_credit(self):
        from apps.subscriptions.models import TenantSubscription
        TenantSubscription.objects.filter(tenant=self.tenant).update(expires_at=timezone.now())
        result = self.command('issue', plan_id=self.plan.pk, quantity=1, expected_total=9000)
        self.assertNotEqual(result.status_code, 200)
        self.assertFalse(AgentCreditBatch.objects.exists())

    def test_reversal_requires_review_when_repayment_changed(self):
        batch = self.issue()
        self.repay(batch)
        result = self.command('reverse', batch_id=batch['id'], reason='Return', expected_outstanding=18000, expected_repaid=0)
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Voucher.objects.filter(status='disabled').exists())
