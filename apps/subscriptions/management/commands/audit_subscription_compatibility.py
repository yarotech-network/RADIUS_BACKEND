"""Read-only structural audit; a clean report does not prove historical provenance."""
import json
from collections import Counter
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.subscriptions.models import TenantSubscription, SubscriptionPeriod, SubscriptionPayment


class Command(BaseCommand):
    help = 'Report subscription mapping blockers without writing data or calling providers.'

    def handle(self, *args, **options):
        counts, samples = Counter(), {}
        now = timezone.now()

        def report(code, pk):
            counts[code] += 1
            if len(samples.setdefault(code, [])) < 20:
                samples[code].append(pk)

        for tenant in Tenant.objects.filter(is_platform_admin=False, subscription__isnull=True).only('pk').iterator():
            report('missing_subscription_tenant', tenant.pk)
        for sub in TenantSubscription.objects.all().iterator(chunk_size=500):
            if sub.expires_at <= sub.started_at:
                report('invalid_subscription_window', sub.pk)
            periods = SubscriptionPeriod.objects.filter(tenant_id=sub.tenant_id, superseded=False).order_by('starts_at', 'pk')
            prior_end = None
            covered = False
            for period in periods.iterator(chunk_size=500):
                if prior_end is not None and period.starts_at < prior_end:
                    report('overlapping_period', period.pk)
                if prior_end is not None and prior_end < period.starts_at and period.starts_at > now and prior_end < sub.expires_at:
                    report('future_period_gap', period.pk)
                prior_end = max(prior_end, period.ends_at) if prior_end else period.ends_at
                covered = covered or period.starts_at <= now < period.ends_at
            if sub.is_active and not covered:
                report('active_subscription_without_current_snapshot', sub.pk)
            if sub.is_active and (prior_end is None or prior_end < sub.expires_at):
                report('subscription_end_not_covered', sub.pk)
        required = {'name', 'price', 'duration_days', 'max_routers', 'daily_voucher_print_limit', 'whatsapp_enabled'}
        for period in SubscriptionPeriod.objects.select_related('payment').iterator(chunk_size=500):
            if not isinstance(period.terms, dict) or not required.issubset(period.terms):
                report('incomplete_period_snapshot', period.pk)
            if period.payment_id and (period.payment.tenant_id != period.tenant_id or period.payment.plan_id != period.plan_id):
                report('period_payment_scope_mismatch', period.pk)
        for payment in SubscriptionPayment.objects.select_related('subscription').iterator(chunk_size=500):
            if payment.plan_terms is None:
                report('payment_without_snapshot', payment.pk)
            if payment.subscription_id and payment.subscription.tenant_id != payment.tenant_id:
                report('payment_subscription_scope_mismatch', payment.pk)
            if payment.status == 'success' and not SubscriptionPeriod.objects.filter(payment=payment).exists():
                report('successful_payment_without_period', payment.pk)
        self.stdout.write(json.dumps({'read_only':True, 'counts':dict(counts), 'sample_ids':samples}, sort_keys=True))
        if counts:
            raise CommandError('Subscription mapping exceptions require reconciliation; no records were changed.')
