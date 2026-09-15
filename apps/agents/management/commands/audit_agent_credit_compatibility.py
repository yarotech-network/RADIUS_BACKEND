"""Existing-column preflight; never reconstruct or mutate financial balances."""
import json
from django.core.management.base import BaseCommand
from django.db.models import Sum
from apps.agents.models import AgentCreditAccount, AgentCreditLedger, AgentVoucherAllocation


class Command(BaseCommand):
    help = 'Read-only agent credit compatibility report (counts and review IDs).'

    def handle(self, *args, **options):
        negative, differences, over_limit = [], [], []
        accounts = AgentCreditAccount.objects.annotate(ledger_total=Sum('ledger_entries__amount')).order_by('id')
        count = 0
        for account in accounts.iterator():
            count += 1
            if account.current_balance < 0:
                negative.append(account.pk)
            if account.current_balance != (account.ledger_total or 0):
                differences.append(account.pk)
            if account.current_balance > account.credit_limit:
                over_limit.append(account.pk)
        self.stdout.write(json.dumps({
            'mode': 'read_only',
            'accounts': count,
            'ledger_entries': AgentCreditLedger.objects.count(),
            'credit_voucher_allocations': AgentVoucherAllocation.objects.filter(allocation_type='credit').count(),
            'negative_balance_account_ids': negative,
            'balance_history_review_account_ids': differences,
            'above_recorded_limit_account_ids': over_limit,
            'note': 'Review flags are not proof of corruption. Opening balances and legacy repayment mappings must be reconciled; no balances were changed.',
        }, sort_keys=True))
