from django.core.management.base import BaseCommand
from apps.routers.operations import run_one_router_operation


class Command(BaseCommand):
    help = "Process a bounded batch of durable router operations."
    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        count = 0
        for _ in range(max(0, min(options["limit"], 100))):
            if not run_one_router_operation():
                break
            count += 1
        self.stdout.write(f"Processed {count} router operations.")
