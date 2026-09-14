import time
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections
from apps.customers.device_access_sync import sync_device_access


class Command(BaseCommand):
    help = "Import tenant-scoped device MAC / voucher accounting history without counting reconnects as new codes."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, **options):
        if options["interval"] < 10:
            raise CommandError("Interval must be at least 10 seconds.")
        while True:
            try:
                close_old_connections()
                count, missing = sync_device_access()
                self.stdout.write(f"Device history synced: {count} accounting rows; {missing} rows without a valid MAC.")
            except (DatabaseError, ValueError):
                if not options["watch"]:
                    raise CommandError("Device history sync failed. Check the database and callingstationid accounting column.") from None
                self.stderr.write("Device history sync failed; retrying on the next interval.")
            if not options["watch"]:
                return
            time.sleep(options["interval"])
