from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.tenants.models import Tenant
from .models import TenantSubscription, SubscriptionPeriod, VoucherPrintAuthorization


def snapshot_plan(plan):
    return {field: getattr(plan, field) for field in (
        "name", "price", "duration_days", "max_routers", "daily_voucher_print_limit", "whatsapp_enabled", "version"
    )}


def print_day():
    return timezone.localtime(timezone.now(), ZoneInfo("Africa/Lagos")).date()


def current_period(tenant):
    now = timezone.now()
    return SubscriptionPeriod.objects.filter(tenant=tenant, superseded=False, starts_at__lte=now, ends_at__gt=now).order_by("-starts_at", "-pk").first()


def entitlement_terms(tenant):
    subscription = TenantSubscription.objects.select_related("plan").filter(tenant=tenant).first()
    if subscription is None:
        return {"max_routers": None, "daily_voucher_print_limit": None, "whatsapp_enabled": True}
    if not subscription.is_active:
        raise PermissionDenied("Your subscription has expired. Renew it to use this feature.")
    period = current_period(tenant)
    if period:
        return period.terms
    # Legacy/manual subscriptions that have not passed through checkout.
    return snapshot_plan(subscription.plan)


def require_router_slot(tenant):
    from apps.routers.models import NASDevice
    terms = entitlement_terms(tenant)
    limit = terms.get("max_routers")
    if limit is not None and NASDevice.objects.filter(tenant=tenant).count() >= limit:
        raise PermissionDenied("Your plan's router limit has been reached. Upgrade your subscription or remove a router.")


def whatsapp_allowed(tenant):
    try:
        return bool(entitlement_terms(tenant).get("whatsapp_enabled", False))
    except PermissionDenied:
        return False


def require_whatsapp(tenant):
    if not whatsapp_allowed(tenant):
        raise PermissionDenied("WhatsApp is not enabled on your current subscription.")


@transaction.atomic
def authorize_print(tenant, voucher_ids):
    from apps.vouchers.models import Voucher
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    ids = set(voucher_ids)
    if set(Voucher.objects.filter(tenant=tenant, pk__in=ids).values_list("pk", flat=True)) != ids:
        raise ValidationError({"voucher_ids": "One or more vouchers are unavailable in this workspace."})
    terms = entitlement_terms(tenant)
    day = print_day()
    records = VoucherPrintAuthorization.objects.filter(tenant=tenant, day=day)
    existing = set(records.filter(voucher_id__in=ids).values_list("voucher_id", flat=True))
    new_ids = ids - existing
    used = records.count()
    limit = terms.get("daily_voucher_print_limit")
    if new_ids and limit is not None and used + len(new_ids) > limit:
        raise PermissionDenied(f"Daily voucher printing limit reached: {used} of {limit} used. Reduce the batch or wait until tomorrow (Africa/Lagos).")
    VoucherPrintAuthorization.objects.bulk_create([
        VoucherPrintAuthorization(tenant=tenant, day=day, voucher_id=pk) for pk in new_ids
    ])
    return {"used": used + len(new_ids), "limit": limit, "day": str(day), "timezone": "Africa/Lagos"}


def require_print_authorization(voucher):
    terms = entitlement_terms(voucher.tenant)
    if terms.get("daily_voucher_print_limit") is not None and not VoucherPrintAuthorization.objects.filter(
        tenant=voucher.tenant, day=print_day(), voucher_id=voucher.pk
    ).exists():
        raise PermissionDenied("Authorize this voucher for printing before requesting its print or PDF document.")
