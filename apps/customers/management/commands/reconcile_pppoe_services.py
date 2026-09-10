from collections import Counter
from django.core.management.base import BaseCommand, CommandError
from apps.customers.reconciliation import claim_services, reconcile_service, record_failure


class Command(BaseCommand):
    help = "Reconcile a bounded batch of PPPoE accounting sessions; safe to rerun."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 100:
            raise CommandError("Use a limit between 1 and 100.")
        results = Counter()
        visited = []
        for _ in range(limit):
            claimed = claim_services(1, visited)
            if not claimed:
                break
            pk, token = claimed[0]
            visited.append(pk)
            try:
                results[reconcile_service(pk, token)] += 1
            except Exception:
                record_failure(pk, token)
                results["failed"] += 1
        self.stdout.write(str(dict(results)))
        if results["failed"]:
            raise CommandError("PPPoE reconciliation has failed items; inspect service states and integration health.")
