from django.core.management.base import BaseCommand

from apps.subscriptions.services import SubscriptionService


class Command(BaseCommand):
    help = "Mark active or trial subscriptions as expired after their end time."

    def handle(self, *args, **options):
        count = SubscriptionService.expire_due_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} subscription(s)."))
