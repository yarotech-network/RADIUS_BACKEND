"""Explicit trial assignment for newly created tenant workspaces only."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Tenant
from .models import SubscriptionPlan, SubscriptionPeriod, TenantSubscription

TRIAL_CODE = 'signup-trial-v1'
TRIAL_TERMS = {
    'name': '15-day trial', 'price': 0, 'duration_days': 15,
    'max_routers': 1, 'daily_voucher_print_limit': 50,
    'whatsapp_enabled': False, 'version': 1,
}


@transaction.atomic
def assign_new_tenant_trial(tenant):
    """Call inside tenant creation's transaction; never backfill existing tenants."""
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    existing = TenantSubscription.objects.filter(tenant=tenant).first()
    if existing or tenant.is_platform_admin:
        return existing
    plan, _ = SubscriptionPlan.objects.get_or_create(
        internal_code=TRIAL_CODE, defaults={**TRIAL_TERMS, 'is_active': False},
    )
    started_at = timezone.now()
    expires_at = started_at + timedelta(days=TRIAL_TERMS['duration_days'])
    subscription = TenantSubscription.objects.create(
        tenant=tenant, plan=plan, status='trial', is_trial=True,
        started_at=started_at, expires_at=expires_at,
    )
    SubscriptionPeriod.objects.create(
        tenant=tenant, plan=plan, starts_at=started_at, ends_at=expires_at,
        terms=dict(TRIAL_TERMS),
    )
    return subscription
