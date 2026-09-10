import uuid
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from apps.tenants.models import Tenant
from apps.routers.models import NASDevice
from apps.vouchers.models import Voucher
from .models import Customer, PPPoEPlan, PPPoEService


class StaleService(APIException):
    status_code = 409
    default_detail = "Service changed. Refresh before trying again."


@transaction.atomic
def create_service(tenant, data):
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    try:
        customer = Customer.objects.get(pk=data["customer"], tenant=tenant, archived_at__isnull=True)
        plan = PPPoEPlan.objects.select_for_update().select_related("bandwidth_profile").get(pk=data["plan"], tenant=tenant, is_active=True)
        router = NASDevice.objects.get(pk=data["router"], tenant=tenant, is_active=True)
    except (Customer.DoesNotExist, PPPoEPlan.DoesNotExist, NASDevice.DoesNotExist):
        raise ValidationError("Choose a current customer, active plan and router in this workspace.")
    if plan.bandwidth_profile.tenant_id != tenant.pk or not plan.bandwidth_profile.is_active:
        raise ValidationError("Plan bandwidth profile is inactive or unavailable.")
    if PPPoEService.objects.filter(customer=customer).exists():
        raise ValidationError("This customer already has a retained PPPoE service.")
    username = "yrp-" + uuid.uuid4().hex
    if Voucher.objects.filter(username=username).exists():
        raise ValidationError("Username conflict. Retry with a new request.")
    return PPPoEService.objects.create(tenant=tenant, customer=customer, plan=plan, router=router,
        username=username, password_hash=make_password(data["password"]),
        rate_limit=plan.bandwidth_profile.rate_limit, period_hours=plan.duration_hours,
        expires_at=timezone.now()+timezone.timedelta(hours=plan.duration_hours))


@transaction.atomic
def change_service(tenant, pk, action, data):
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    service = PPPoEService.objects.select_for_update().select_related("customer", "plan", "router").get(pk=pk, tenant=tenant)
    if service.version != data["expected_version"]:
        raise StaleService()
    now = timezone.now()
    if action in ("renew", "resume") and service.customer.archived_at:
        raise ValidationError("Restore this customer before renewing or resuming service.")
    if action == "renew":
        service.expires_at = max(service.expires_at, now) + timezone.timedelta(hours=service.period_hours)
    elif action == "suspend":
        service.suspended = True
        service.disconnect_before = now
        service.disconnect_state = "pending"
    elif action == "resume":
        if service.expires_at <= now:
            raise ValidationError("Renew the expired service before resuming.")
        service.suspended = False
    elif action == "password":
        service.password_hash = make_password(data["password"])
        service.disconnect_before = now
        service.disconnect_state = "pending"
    else:
        raise ValidationError("Unsupported action.")
    service.version += 1
    service.save()
    return service
