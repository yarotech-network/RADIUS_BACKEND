from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Tenant
from .models import SubscriptionPayment, TenantSubscription


class SubscriptionService:
    @staticmethod
    @transaction.atomic
    def complete_payment(payment):
        """Activate or extend a subscription exactly once."""
        locked_payment = SubscriptionPayment.objects.select_for_update().select_related(
            "plan", "tenant"
        ).get(pk=payment.pk)
        if locked_payment.status == "success":
            return False

        # Lock the parent even when no subscription row exists, preventing two
        # first-payment deliveries from racing to create the one-to-one row.
        tenant = Tenant.objects.select_for_update().get(pk=locked_payment.tenant_id)
        now = timezone.now()
        subscription = TenantSubscription.objects.select_for_update().filter(
            tenant=tenant
        ).first()

        if subscription is None:
            subscription = TenantSubscription(
                tenant=tenant,
                plan=locked_payment.plan,
                started_at=now,
                expires_at=now,
            )

        if subscription.is_active:
            extension_base = subscription.expires_at
        else:
            extension_base = now
            subscription.started_at = now

        subscription.plan = locked_payment.plan
        subscription.status = "active"
        subscription.is_trial = False
        subscription.expires_at = extension_base + timedelta(
            days=locked_payment.plan.duration_days
        )
        subscription.save()

        locked_payment.subscription = subscription
        locked_payment.status = "success"
        locked_payment.completed_at = now
        locked_payment.save(
            update_fields=["subscription", "status", "completed_at"]
        )
        return True

    @staticmethod
    @transaction.atomic
    def expire_due_subscriptions():
        return TenantSubscription.objects.filter(
            status__in=("trial", "active"),
            expires_at__lte=timezone.now(),
        ).update(status="expired")
