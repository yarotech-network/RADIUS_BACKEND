"""Explicit paid access for unrelated API regression fixtures."""
from datetime import timedelta
from django.utils import timezone
from .models import SubscriptionPlan, TenantSubscription, SubscriptionPeriod
from .entitlements import snapshot_plan


def grant_test_subscription(tenant):
    plan = SubscriptionPlan.objects.create(name='Test unlimited', price=100, duration_days=30,
        max_routers=None, daily_voucher_print_limit=None, whatsapp_enabled=True)
    now = timezone.now()
    subscription = TenantSubscription.objects.create(tenant=tenant, plan=plan, status='active',
        is_trial=False, started_at=now, expires_at=now+timedelta(days=30))
    SubscriptionPeriod.objects.create(tenant=tenant, plan=plan, starts_at=now,
        ends_at=subscription.expires_at, terms=snapshot_plan(plan))
    return subscription
