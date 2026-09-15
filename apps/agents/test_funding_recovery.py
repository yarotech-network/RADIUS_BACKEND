from io import StringIO
from unittest.mock import patch
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantSetting
from apps.subscriptions.test_support import grant_test_subscription
from .tests import AgentFixtureMixin
from .models import AgentWalletFundingPayment, AgentWalletTransaction
from .services import AgentService
from .funding import verify_wallet_funding, FundingVerificationMismatch


class FundingRecoveryTests(AgentFixtureMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name='Funding', slug='funding-recovery')
        grant_test_subscription(self.tenant)
        self.setting = TenantSetting.objects.create(tenant=self.tenant, max_funding_amount=1000000,
            agent_funding_fee_percent='1.50', agent_funding_flat_fee=1000)
        self.user, self.agent, self.wallet = self.create_agent(balance=0)
        self.client.force_authenticate(self.user)

    def payment(self):
        return AgentService.fund_wallet(self.agent, 50000, 'recovery-funding', expected_total=51750)

    @patch('apps.payments.webhooks.get_paystack_secret', return_value='funding-test-secret')
    @patch('apps.payments.webhooks.get_paystack_service')
    def test_fee_inclusive_webhook_credits_only_wallet_amount(self, provider, secret):
        import hashlib
        import hmac
        import json
        from django.urls import reverse
        payment = self.payment()
        data = {**self.evidence(payment)['data'], 'id': 9876}
        provider.return_value.verify_transaction.return_value = {'status': True, 'data': data}
        raw = json.dumps({'event': 'charge.success', 'data': data}).encode()
        signature = hmac.new(b'funding-test-secret', raw, hashlib.sha512).hexdigest()
        for _ in range(2):
            response = self.client.post(reverse('paystack-webhook', args=['test-route']), data=raw,
                content_type='application/json', HTTP_X_PAYSTACK_SIGNATURE=signature)
            self.assertEqual(response.status_code, 200, response.content)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 50000)
        self.assertEqual(AgentWalletTransaction.objects.count(), 1)

    def test_fee_rounding_zero_defaults_and_overflow(self):
        from .funding_terms import reserve_funding_terms, funding_policy
        free = reserve_funding_terms(50000, funding_policy(None))
        self.assertEqual((free['fee'], free['total']), (0, 50000))
        rounded = reserve_funding_terms(50001, {'minimum': 1, 'maximum': 100000, 'fee_percent': '50', 'flat_fee': 0})
        self.assertEqual(rounded['fee'], 25001)
        with self.assertRaises(ValueError):
            reserve_funding_terms(2147483647, {'minimum': 1, 'maximum': 2147483647, 'fee_percent': '1', 'flat_fee': 0})

    def evidence(self, payment, status='success', **changes):
        return {'status': True, 'data': {'reference': payment.reference, 'amount': 51750,
            'currency': 'NGN', 'status': status, **changes}}

    @patch('apps.payments.services.get_paystack_service')
    def test_initialization_charges_saved_total_and_rejects_stale_quote(self, provider):
        provider.return_value.initialize_transaction.return_value = {'data': {'authorization_url': 'https://checkout.paystack.test/pay'}}
        missing = self.client.post('/api/v1/agent/wallet/fund/', {'amount': 50000})
        self.assertEqual(missing.status_code, 400)
        provider.return_value.initialize_transaction.assert_not_called()
        bad = self.client.post('/api/v1/agent/wallet/fund/', {'amount': 50000, 'expected_total': 50000})
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(AgentWalletFundingPayment.objects.exists())
        good = self.client.post('/api/v1/agent/wallet/fund/', {'amount': 50000, 'expected_total': 51750})
        self.assertEqual(good.status_code, 200, good.data)
        self.assertEqual(good.data['fee'], 1750)
        self.assertEqual(provider.return_value.initialize_transaction.call_args.kwargs['amount'], 51750)

    @patch('apps.agents.funding.get_paystack_service')
    def test_missing_webhook_recovery_credits_requested_amount_only_once(self, provider):
        payment = self.payment()
        provider.return_value.verify_transaction.return_value = self.evidence(payment)
        self.setting.agent_funding_flat_fee = 5000
        self.setting.save()
        for _ in range(2):
            result = self.client.post('/api/v1/agent/wallet/verify/', {'reference': payment.reference})
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(result.data['status'], 'success')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 50000)
        self.assertEqual(AgentWalletTransaction.objects.count(), 1)
        self.assertEqual(provider.return_value.verify_transaction.call_count, 1)

    @patch('apps.agents.funding.get_paystack_service')
    def test_wrong_agent_is_denied_before_provider_call(self, provider):
        payment = self.payment()
        other, _, _ = self.create_agent(username='other')
        self.client.force_authenticate(other)
        response = self.client.post('/api/v1/agent/wallet/verify/', {'reference': payment.reference})
        self.assertEqual(response.status_code, 404)
        provider.assert_not_called()

    @patch('apps.agents.funding.get_paystack_service')
    def test_unavailable_and_mismatched_evidence_preserve_pending_payment(self, provider):
        payment = self.payment()
        provider.return_value.verify_transaction.side_effect = TimeoutError()
        response = self.client.post('/api/v1/agent/wallet/verify/', {'reference': payment.reference})
        self.assertEqual(response.status_code, 503)
        provider.return_value.verify_transaction.side_effect = None
        for changes in [{'amount': 50000}, {'amount': 51750.0}, {'reference': 'wrong'}, {'currency': 'USD'}]:
            provider.return_value.verify_transaction.return_value = self.evidence(payment, **changes)
            with self.assertRaises(FundingVerificationMismatch):
                verify_wallet_funding(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
        self.assertFalse(AgentWalletTransaction.objects.exists())

    @patch('apps.agents.funding.get_paystack_service')
    def test_failure_does_not_overwrite_concurrent_success(self, provider):
        payment = self.payment()
        def during_verify(reference):
            AgentService.complete_wallet_funding(payment, self.evidence(payment)['data'])
            return self.evidence(payment, status='failed')
        provider.return_value.verify_transaction.side_effect = during_verify
        result = verify_wallet_funding(payment)
        self.assertEqual(result.status, 'success')
        self.assertEqual(AgentWalletTransaction.objects.count(), 1)

    @patch('apps.agents.funding.get_paystack_service')
    def test_legacy_payment_keeps_original_amount_and_can_recover_after_failure(self, provider):
        payment = AgentWalletFundingPayment.objects.create(wallet=self.wallet, amount=50000, reference='legacy-fee-free')
        provider.return_value.verify_transaction.return_value = self.evidence(payment, status='failed', amount=50000)
        self.assertEqual(verify_wallet_funding(payment).status, 'failed')
        provider.return_value.verify_transaction.return_value = self.evidence(payment, amount=50000)
        self.assertEqual(verify_wallet_funding(payment).status, 'success')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 50000)

    @patch('apps.agents.funding.get_paystack_service')
    def test_command_is_read_only_unless_apply_is_explicit(self, provider):
        payment = self.payment()
        output = StringIO()
        call_command('reconcile_agent_wallet_funding', payment_id=[payment.pk], stdout=output)
        provider.assert_not_called()
        self.assertIn('READ-ONLY', output.getvalue())
        provider.return_value.verify_transaction.return_value = self.evidence(payment)
        call_command('reconcile_agent_wallet_funding', payment_id=[payment.pk], apply=True, stdout=output)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 50000)
