from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Tenant
from .models import SubscriptionPayment, TenantSubscription, SubscriptionPeriod
from .entitlements import snapshot_plan


class SubscriptionService:
    @staticmethod
    @transaction.atomic
    def complete_payment(payment):
        """Activate or extend a subscription exactly once."""
        locked_payment = SubscriptionPayment.objects.select_for_update(of=("self",)).select_related(
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
            if not SubscriptionPeriod.objects.filter(tenant=tenant).exists():
                SubscriptionPeriod.objects.create(tenant=tenant, plan=subscription.plan, starts_at=subscription.started_at, ends_at=subscription.expires_at, terms=snapshot_plan(subscription.plan))
            extension_base = subscription.expires_at
        else:
            SubscriptionPeriod.objects.filter(tenant=tenant, ends_at__gt=now).update(superseded=True)
            extension_base = now
            subscription.started_at = now

        terms = locked_payment.plan_terms or snapshot_plan(locked_payment.plan)
        if locked_payment.plan_terms is None:
            locked_payment.plan_terms = {**terms, "price": locked_payment.amount}
            locked_payment.save(update_fields=["plan_terms"])
        subscription.plan = locked_payment.plan
        subscription.status = "active"
        subscription.is_trial = False
        subscription.expires_at = extension_base + timedelta(
            days=terms["duration_days"]
        )
        subscription.save()
        SubscriptionPeriod.objects.create(tenant=tenant, plan=locked_payment.plan, payment=locked_payment, starts_at=extension_base, ends_at=subscription.expires_at, terms=terms)

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


class SubscriptionVerificationUnavailable(Exception):
    pass


class SubscriptionVerificationMismatch(Exception):
    pass


def verify_subscription_payment(payment):
    """Recover a missing webhook using the platform provider, without network I/O under locks."""
    from apps.payments.services import get_paystack_service

    payment.refresh_from_db()
    if payment.status == "success":
        return payment
    try:
        result = get_paystack_service().verify_transaction(payment.reference)
    except Exception as exc:
        raise SubscriptionVerificationUnavailable() from exc
    if not isinstance(result, dict) or result.get("status") is not True:
        raise SubscriptionVerificationUnavailable()
    data = result.get("data")
    if not isinstance(data, dict):
        raise SubscriptionVerificationUnavailable()
    if (data.get("reference") != payment.reference
            or type(data.get("amount")) is not int
            or data["amount"] != payment.amount
            or data.get("currency") != "NGN"):
        raise SubscriptionVerificationMismatch()
    if data.get("status") == "success":
        SubscriptionService.complete_payment(payment)
    # A pending/abandoned/failed provider attempt is not proof that settlement
    # cannot follow. Only verified success changes the local payment here.
    payment.refresh_from_db()
    return payment
