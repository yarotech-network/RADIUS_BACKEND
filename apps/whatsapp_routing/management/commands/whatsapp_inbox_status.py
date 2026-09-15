import json
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Min, Max, Sum
from apps.whatsapp_routing.models import WhatsAppInboundEvent


class Command(BaseCommand):
    help = 'Read aggregate WhatsApp inbox health without customer content or message identifiers.'

    def handle(self, *args, **options):
        rows = WhatsAppInboundEvent.objects
        summary = rows.aggregate(received=Count('id'), duplicates=Sum('duplicate_count'), latest=Max('received_at'))
        summary['states'] = dict(rows.values('state').annotate(total=Count('id')).values_list('state', 'total'))
        summary['oldest_ready'] = rows.filter(state='ready', processing__isnull=True).aggregate(value=Min('received_at'))['value']
        summary['consumer_enabled'] = settings.WHATSAPP_CONSUMER_ENABLED
        summary['send_enabled'] = settings.WHATSAPP_SEND_ENABLED
        from apps.whatsapp_routing.models import WhatsAppOrder, WhatsAppOutbound
        summary['orders'] = dict(WhatsAppOrder.objects.values('state').annotate(total=Count('pk')).values_list('state', 'total'))
        summary['outbound'] = dict(WhatsAppOutbound.objects.values('state').annotate(total=Count('pk')).values_list('state', 'total'))
        self.stdout.write(json.dumps(summary, default=str, sort_keys=True))
