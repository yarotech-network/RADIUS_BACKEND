"""Pre-migration read-only duplicate check; no voucher secrets in output."""
import json
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import Lower
from apps.vouchers.models import Voucher


class Command(BaseCommand):
    help = 'Find case-insensitive voucher identity conflicts before applying code-format migrations.'

    def handle(self, *args, **options):
        groups = Voucher.objects.order_by().annotate(identity=Lower('username')).values('identity').annotate(total=Count('id')).filter(total__gt=1)
        count = groups.count()
        samples = []
        for group in groups.order_by('identity')[:100]:
            samples.append({'voucher_ids':list(Voucher.objects.filter(username__iexact=group['identity']).order_by('id').values_list('id', flat=True)[:100]), 'count':group['total']})
        self.stdout.write(json.dumps({'conflicting_groups':count, 'samples':samples, 'sample_limit':100}))
