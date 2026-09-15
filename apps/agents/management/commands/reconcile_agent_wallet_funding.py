from django.core.management.base import BaseCommand, CommandError
from apps.agents.models import AgentWalletFundingPayment
from apps.agents.funding import verify_wallet_funding, FundingVerificationMismatch, FundingVerificationUnavailable


class Command(BaseCommand):
    help = 'Inspect or reconcile up to 20 explicitly selected wallet funding payments.'

    def add_arguments(self, parser):
        parser.add_argument('--payment-id', action='append', type=int, required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        ids = set(options['payment_id'])
        if not 1 <= len(ids) <= 20 or any(pk <= 0 for pk in ids):
            raise CommandError('Select between 1 and 20 positive payment IDs.')
        rows = list(AgentWalletFundingPayment.objects.filter(pk__in=ids).order_by('pk'))
        if len(rows) != len(ids):
            raise CommandError('One or more selected payments do not exist.')
        self.stdout.write('Mode: APPLY' if options['apply'] else 'Mode: READ-ONLY (no provider calls or credits)')
        errors = 0
        for payment in rows:
            if options['apply']:
                try:
                    payment = verify_wallet_funding(payment)
                except (FundingVerificationMismatch, FundingVerificationUnavailable):
                    errors += 1
                    self.stdout.write(f'Payment {payment.pk}: unresolved; no recovery success claimed')
                    continue
            self.stdout.write(f'Payment {payment.pk}: {payment.status}; wallet credit {payment.amount} kobo')
        if errors:
            raise CommandError(f'{errors} payment(s) remain unresolved. Review before attempting a new payment.')
