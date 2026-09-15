from django.conf import settings
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from apps.whatsapp_routing.models import WhatsAppInboundEvent, WhatsAppOrder, WhatsAppOutbound
from apps.whatsapp_routing.conversations import process_event
from apps.whatsapp_routing.orders import process_order
from apps.whatsapp_routing.outbound import send_one, process_delivery_status
from apps.whatsapp_routing.reminders import schedule_order_reminders


class Command(BaseCommand):
    help = 'Process a bounded WhatsApp batch. Sending and consumers require separate server flags.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=25)

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 100:
            raise CommandError('Limit must be between 1 and 100.')
        if not settings.WHATSAPP_CONSUMER_ENABLED:
            self.stdout.write('WhatsApp consumer is disabled.')
            return
        failures = 0
        batches = [
            (process_event, WhatsAppInboundEvent.objects.filter(state='ready', processing__isnull=True).order_by('provider_timestamp', 'pk')),
            (process_order, WhatsAppOrder.objects.filter(state__in=['new', 'initializing', 'pending', 'unknown'], next_check_at__lte=timezone.now()).order_by('next_check_at', 'pk')),
            (schedule_order_reminders, WhatsAppOrder.objects.filter(state='fulfilled', reminders_opt_in=True, next_reminder_check_at__lte=timezone.now()).order_by('next_reminder_check_at', 'pk')),
            (send_one, WhatsAppOutbound.objects.filter(
                Q(state='pending', next_attempt_at__lte=timezone.now()) |
                Q(state='sending', started_at__lte=timezone.now()-timedelta(minutes=5))).order_by('created_at')),
            (process_delivery_status, WhatsAppInboundEvent.objects.filter(state='status', processing__isnull=True).order_by('provider_timestamp', 'pk')),
        ]
        for action, query in batches:
            for pk in list(query.values_list('pk', flat=True)[:limit]):
                try:
                    action(pk)
                except Exception:
                    failures += 1
                    self.stderr.write(f'{action.__name__} failed for record {pk}; state retained for recovery.')
        if failures:
            raise CommandError(f'{failures} WhatsApp operations require retry or review.')
        self.stdout.write('WhatsApp batch completed. Provider acceptance does not prove delivery.')
