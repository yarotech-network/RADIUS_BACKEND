import json
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from apps.tenants.models import Tenant
from .models import AgentProfile, AgentCreditAccount, AgentCreditLedger


class AgentCreditAuditTests(TestCase):
    def test_reports_review_ids_without_rewriting_signed_balances_or_history(self):
        tenant = Tenant.objects.create(name='Credit audit', slug='credit-audit')
        accounts = []
        for index, balance in enumerate([1000, -500, 2000]):
            user = get_user_model().objects.create_user(username=f'credit-agent-{index}', email=f'credit-{index}@example.test')
            agent = AgentProfile.objects.create(tenant=tenant, user=user)
            accounts.append(AgentCreditAccount.objects.create(agent=agent, current_balance=balance, credit_limit=1500))
        AgentCreditLedger.objects.create(credit_account=accounts[0], amount=1500, description='Historical charge')
        AgentCreditLedger.objects.create(credit_account=accounts[0], amount=-500, description='Historical repayment')
        before = list(AgentCreditAccount.objects.order_by('pk').values_list('pk', 'current_balance', 'credit_limit'))
        out = StringIO()
        call_command('audit_agent_credit_compatibility', stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(report['negative_balance_account_ids'], [accounts[1].pk])
        self.assertEqual(report['balance_history_review_account_ids'], [accounts[1].pk, accounts[2].pk])
        self.assertEqual(report['above_recorded_limit_account_ids'], [accounts[2].pk])
        self.assertEqual(report['ledger_entries'], 2)
        self.assertEqual(before, list(AgentCreditAccount.objects.order_by('pk').values_list('pk', 'current_balance', 'credit_limit')))
        self.assertEqual(AgentCreditLedger.objects.count(), 2)
