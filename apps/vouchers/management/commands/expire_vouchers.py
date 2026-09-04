from django.core.management.base import BaseCommand
from apps.vouchers.services import VoucherService


class Command(BaseCommand):
    help = "Expire vouchers past their expiration time"

    def handle(self, *args, **options):
        count = VoucherService.expire_vouchers()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} vouchers."))
