from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import RegistrationEmailChallenge

class Command(BaseCommand):
    help = 'Delete registration challenges expired more than one day ago. Schedule daily.'
    def handle(self, *args, **options):
        count, _ = RegistrationEmailChallenge.objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
        self.stdout.write(f'Removed {count} expired registration challenges.')
