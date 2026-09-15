from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.subscriptions.test_support import grant_test_subscription
from apps.tenants.models import Tenant
from apps.vouchers.models import InternetPlan, Voucher, Radcheck
from .models import AgentProfile, AgentWalletFundingPayment, AgentWalletTransaction, AgentVoucherAllocation
from .pricing import agent_price
from .services import AgentService
from .tests import AgentFixtureMixin


class AgentCommissionCompatibilityTests(AgentFixtureMixin, APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Commission', slug='commission')
        grant_test_subscription(self.tenant)
        self.user, self.agent, self.wallet = self.create_agent(balance=90_000)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=100_000, duration_hours=24)
        self.client.force_authenticate(self.user)

    def evidence(self, payment, **changes):
        return {'status': 'success', 'reference': payment.reference, 'amount': payment.amount, 'currency': 'NGN', **changes}

    def test_discounted_balance_is_sufficient_and_sale_is_snapshotted(self):
        vouchers, rows = AgentService.generate_voucher_from_wallet(self.agent, self.plan.pk)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)
        row = rows[0]
        self.assertEqual((row.amount_charged, row.commission_earned, row.retail_price), (90_000, 10_000, 100_000))
        self.assertEqual(row.commission_rate_snapshot, Decimal('10'))
        movement = row.wallet_transaction
        self.assertEqual((movement.previous_balance, movement.amount, movement.new_balance), (90_000, 90_000, 0))
        self.assertEqual(vouchers[0].purchased_terms['price'], 100_000)
        self.plan.price = 200_000
        self.plan.save()
        self.agent.commission_rate = Decimal('80')
        self.agent.save()
        row.refresh_from_db()
        self.assertEqual(row.amount_charged, 90_000)
        self.assertEqual(row.commission_rate_snapshot, Decimal('10'))
        self.assertEqual(AgentService.get_agent_stats(self.agent)['commission_this_month'], 10_000)

    def test_rounding_is_per_voucher_and_full_commission_does_not_credit_wallet(self):
        self.assertEqual(agent_price(101, '50')['agent_cost'], 51)
        self.assertEqual(agent_price(101, '50')['commission_amount'], 50)
        self.assertEqual(agent_price(101, '0')['agent_cost'], 101)
        self.agent.commission_rate = Decimal('100')
        self.agent.save()
        _, rows = AgentService.generate_voucher_from_wallet(self.agent, self.plan.pk, quantity=2)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 90_000)
        self.assertEqual(sum(row.amount_charged for row in rows), 0)
        self.assertEqual(sum(row.commission_earned for row in rows), 200_000)
        self.assertEqual(AgentWalletTransaction.objects.get().amount, 0)

    def test_invalid_rate_rejected_without_financial_writes(self):
        for rate in ['-1', '101', 'NaN', 'Infinity', 'invalid']:
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                agent_price(100, rate)
        AgentProfile.objects.filter(pk=self.agent.pk).update(commission_rate=101)
        with self.assertRaises(ValueError):
            AgentService.generate_voucher_from_wallet(self.agent, self.plan.pk)
        self.assertFalse(AgentWalletTransaction.objects.exists())

    def test_radius_failure_rolls_back_movement_and_debit(self):
        with patch('apps.vouchers.services.VoucherService.write_radius_credentials', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                AgentService.generate_voucher_from_wallet(self.agent, self.plan.pk)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 90_000)
        self.assertFalse(AgentWalletTransaction.objects.exists())
        self.assertFalse(AgentVoucherAllocation.objects.exists())
        self.assertFalse(Voucher.objects.exists())

    def test_api_replay_does_not_debit_twice_or_reprice_saved_result(self):
        url = reverse('agent-voucher-generate')
        headers = {'HTTP_IDEMPOTENCY_KEY': 'commission-sale-replay-1'}
        first = self.client.post(url, {'plan_id': self.plan.pk, 'quantity': 1}, format='json', **headers)
        self.assertEqual(first.status_code, 201, first.data)
        AgentProfile.objects.filter(pk=self.agent.pk).update(commission_rate=50)
        again = self.client.post(url, {'plan_id': self.plan.pk, 'quantity': 1}, format='json', **headers)
        self.assertEqual(again.data, first.data)
        conflict = self.client.post(url, {'plan_id': self.plan.pk, 'quantity': 2}, format='json', **headers)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(AgentWalletTransaction.objects.count(), 1)
        self.assertEqual(Voucher.objects.count(), 1)

    def test_catalogue_prices_are_agent_scoped_and_single_device(self):
        result = self.client.get('/api/v1/agent/plans/')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['results'][0]['agent_cost'], 90_000)
        self.assertEqual(result.data['results'][0]['commission_amount'], 10_000)
        self.assertEqual(result.data['results'][0]['max_devices'], 1)
        with self.settings(MULTI_DEVICE_VOUCHERS_ENABLED=True):
            rejected = self.client.post(reverse('agent-voucher-generate'), {'plan_id': self.plan.pk, 'quantity': 1, 'device_limit': 2})
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(Voucher.objects.exists())

    def test_cross_tenant_plan_is_denied_without_debit(self):
        other = Tenant.objects.create(name='Other', slug='other-commission')
        plan = InternetPlan.objects.create(tenant=other, name='Other', price=10, duration_hours=1)
        with self.assertRaises(ValueError):
            AgentService.generate_voucher_from_wallet(self.agent, plan.pk)
        self.assertFalse(AgentWalletTransaction.objects.exists())

    def test_funding_credits_once_with_linked_movement(self):
        payment = AgentWalletFundingPayment.objects.create(wallet=self.wallet, amount=10_000, reference='fund-compat')
        self.assertTrue(AgentService.complete_wallet_funding(payment, self.evidence(payment)))
        self.assertFalse(AgentService.complete_wallet_funding(payment, self.evidence(payment)))
        self.wallet.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100_000)
        self.assertEqual(payment.wallet_transaction.new_balance, 100_000)
        self.assertEqual(AgentWalletTransaction.objects.count(), 1)

    def test_bad_funding_evidence_and_overflow_do_not_credit(self):
        payment = AgentWalletFundingPayment.objects.create(wallet=self.wallet, amount=10_000, reference='fund-invalid')
        for changes in [{'amount': 10_000.0}, {'amount': 1}, {'reference': 'other'}, {'currency': 'USD'}, {'status': 'failed'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                AgentService.complete_wallet_funding(payment, self.evidence(payment, **changes))
        self.wallet.balance = 2147483647
        self.wallet.save()
        with self.assertRaises(ValueError):
            AgentService.complete_wallet_funding(payment, self.evidence(payment))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
        self.assertFalse(AgentWalletTransaction.objects.exists())

    def test_ledger_failure_rolls_back_funding_completion(self):
        payment = AgentWalletFundingPayment.objects.create(wallet=self.wallet, amount=10_000, reference='fund-ledger-fail')
        with patch('apps.agents.services.AgentWalletTransaction.objects.create', side_effect=RuntimeError('ledger failure')):
            with self.assertRaises(RuntimeError):
                AgentService.complete_wallet_funding(payment, self.evidence(payment))
        self.wallet.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.wallet.balance, 90_000)
        self.assertEqual(payment.status, 'pending')

    def test_movements_are_read_only_and_wallet_scoped(self):
        AgentService.generate_voucher_from_wallet(self.agent, self.plan.pk)
        _, _, other_wallet = self.create_agent(username='other-agent')
        AgentWalletTransaction.objects.create(wallet=other_wallet, category='funding', amount=5, previous_balance=0, new_balance=5)
        response = self.client.get('/api/v1/agent/wallet/transactions/?page_size=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['amount'], 90_000)
        self.assertNotIn('wallet', response.data['results'][0])
        denied = self.client.post('/api/v1/agent/wallet/transactions/', {'amount': 1})
        self.assertEqual(denied.status_code, 405)
        row = AgentWalletTransaction.objects.get(wallet=self.wallet)
        with self.assertRaises(ValueError):
            row.save()
        with self.assertRaises(ProtectedError):
            self.wallet.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AgentWalletTransaction.objects.create(wallet=self.wallet, category='voucher_sale', amount=1, previous_balance=0, new_balance=0)

    def test_existing_successful_funding_and_allocations_are_not_recalculated(self):
        payment = AgentWalletFundingPayment.objects.create(wallet=self.wallet, amount=10_000, reference='old-paid', status='success')
        self.assertFalse(AgentService.complete_wallet_funding(payment, self.evidence(payment)))
        voucher = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='LEGACY01', password='legacy')
        old = AgentVoucherAllocation.objects.create(agent=self.agent, voucher=voucher, amount_charged=100_000, commission_earned=0)
        self.assertIsNone(old.retail_price)
        self.assertIsNone(old.commission_rate_snapshot)
        self.assertIsNone(old.wallet_transaction)
        self.assertFalse(AgentWalletTransaction.objects.exists())
