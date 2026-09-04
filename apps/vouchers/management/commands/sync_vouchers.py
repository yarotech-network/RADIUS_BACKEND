from django.core.management.base import BaseCommand
from apps.vouchers.models import Voucher, Radcheck


class Command(BaseCommand):
    help = "Synchronize voucher state with RADIUS tables"

    def handle(self, *args, **options):
        # Ensure active vouchers have radcheck rows
        active = Voucher.objects.filter(status="active")
        created = 0
        for voucher in active:
            if not Radcheck.objects.filter(username=voucher.username).exists():
                Radcheck.objects.create(
                    username=voucher.username,
                    attribute="Cleartext-Password",
                    op=":=",
                    value=voucher.password,
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Synced {created} missing radcheck rows."))
