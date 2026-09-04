from django.core.management.base import BaseCommand
from apps.routers.services import RouterService


class Command(BaseCommand):
    help = "Refresh router online/offline status"

    def handle(self, *args, **options):
        results = RouterService.refresh_all_statuses()
        online = sum(1 for r in results if r["online"])
        self.stdout.write(
            self.style.SUCCESS(f"Checked {len(results)} routers. {online} online.")
        )
