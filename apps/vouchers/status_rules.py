"""Read-only voucher classification shared by lists and customer access."""
from django.db.models import Case, When, Value, F, CharField, Q, Exists, OuterRef
from django.utils import timezone
from apps.routers.selectors import tenant_radius_addresses
from .models import Radacct


def effective_status(voucher, now=None):
    now = now or timezone.now()
    if voucher.status == 'disabled':
        return 'disabled'
    if voucher.status == 'expired' or (voucher.expires_at and voucher.expires_at <= now):
        return 'expired'
    return voucher.status


def classify(query, tenant, now=None):
    now = now or timezone.now()
    from apps.customers.models import DeviceAccessSession
    observed = DeviceAccessSession.objects.filter(voucher_id=OuterRef('pk'), tenant=tenant)
    accounting = Radacct.objects.filter(username=OuterRef('username'),
        nasipaddress__in=tenant_radius_addresses(tenant), acctstarttime__isnull=False, acctstarttime__lte=now)
    return query.annotate(has_observed=Exists(observed), has_accounting=Exists(accounting), effective_status=Case(
        When(status='disabled', then=Value('disabled')),
        When(Q(status='expired') | Q(expires_at__lte=now), then=Value('expired')),
        default=F('status'), output_field=CharField()))


def filter_status(query, value):
    if value == 'used':
        return query.filter(Q(is_used=True) | Q(status__in=['active', 'used']) |
            Q(activated_at__isnull=False) | Q(first_used_at__isnull=False) |
            Q(used_at__isnull=False) | Q(last_used_at__isnull=False) | Q(has_accounting=True) | Q(has_observed=True))
    return query.filter(effective_status=value)
