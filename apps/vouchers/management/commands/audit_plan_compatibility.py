"""Read-only readiness checks; never print access codes or credentials."""
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from apps.vouchers.models import Voucher, PaymentTransaction
from apps.vouchers.terms import historical_terms


class Command(BaseCommand):
    help = 'Audit unsnapshotted voucher durations and unfulfilled order terms without changing data.'

    def handle(self, *args, **options):
        checked = blocked = 0
        for voucher in Voucher.objects.filter(purchased_terms__isnull=True).select_related('plan').iterator(chunk_size=500):
            checked += 1
            try:
                historical_terms(voucher)
            except ValidationError:
                blocked += 1
                if blocked <= 20:
                    self.stdout.write(f'Unresolved voucher id={voucher.pk}')
        orders = PaymentTransaction.objects.filter(purchased_terms__isnull=True, voucher__isnull=True)
        count = orders.count()
        for pk in orders.values_list('pk', flat=True)[:20]:
            self.stdout.write(f'Unresolved unfulfilled order id={pk}')
        self.stdout.write(f'Unsnapshotted vouchers checked: {checked}; unresolved: {blocked}; unresolved orders: {count}')
        self.stdout.write('Read-only audit. Available duration evidence does not prove original price or data cap when their records are missing.')
        if blocked or count:
            raise CommandError('Reconcile unresolved historical terms before enabling plan edits or archiving.')
