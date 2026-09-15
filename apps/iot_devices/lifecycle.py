from datetime import timedelta
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from apps.vouchers.terms import duration_seconds


class StaleDevice(APIException):
    status_code = 409
    default_detail = 'Device changed. Reload and review before trying again.'


def check_version(device, version):
    if version != device.version:
        raise StaleDevice()


def validate_grant(device, *, require_plan=False):
    # Callers hold an atomic transaction. Re-read mutable grant definitions under locks.
    if device.plan_id:
        from apps.vouchers.models import InternetPlan
        plan = InternetPlan.objects.select_for_update().filter(pk=device.plan_id, tenant_id=device.tenant_id).first()
        if plan is None:
            raise ValidationError({'plan': 'Choose a plan belonging to this tenant.'})
        device.plan = plan
    if device.router_id:
        from apps.routers.models import NASDevice
        router = NASDevice.objects.select_for_update().filter(pk=device.router_id, tenant_id=device.tenant_id).first()
        if router is None:
            raise ValidationError({'router': 'Choose a router belonging to this tenant.'})
        device.router = router
    if not device.router_id or device.router.tenant_id != device.tenant_id or not device.router.is_active:
        raise ValidationError({'router':'Choose an active router belonging to this tenant.'})
    plan = device.plan
    if require_plan and not plan:
        raise ValidationError({'plan':'Choose an IoT plan for renewal.'})
    if plan and (plan.tenant_id != device.tenant_id or not plan.is_active or plan.archived_at or plan.plan_type != 'iot_mac'):
        raise ValidationError({'plan':'Choose an active, unarchived IoT / MAC plan.'})
    if plan and plan.public_router_id and plan.public_router_id != device.router_id:
        raise ValidationError({'router':'This plan is restricted to another router.'})
    if device.access_type == 'timed' and (not device.expires_at or device.expires_at <= timezone.now()):
        raise ValidationError({'expires_at':'Set a future expiry or renew the device first.'})


def plan_terms(plan):
    return {'plan_id':plan.pk, 'tenant_id':plan.tenant_id, 'name':plan.name,
        'duration_seconds':duration_seconds(plan.duration_hours), 'rate_limit':plan.rate_limit or '',
        'data_limit_bytes':plan.data_limit * 1024 * 1024 if plan.data_limit else None,
        'price_kobo':plan.price, 'currency':'NGN', 'source':'operator_grant'}


def apply_plan_snapshot(device):
    if device.plan:
        device.issued_terms = plan_terms(device.plan)
        device.speed_limit = device.issued_terms['rate_limit']
        device.data_limit_bytes = device.issued_terms['data_limit_bytes']
    else:
        device.issued_terms = None
        device.speed_limit = ''
        device.data_limit_bytes = None


def transition(device, action):
    if device.configured_status == 'deleted':
        raise ValidationError('Deleted registrations are retained for history and cannot be changed.')
    if device.configured_status == 'revoked' and action == 'suspend':
        raise ValidationError('A revoked registration must be explicitly reactivated.')
    state = {'suspend':'suspended', 'reactivate':'active', 'revoke':'revoked', 'delete':'deleted'}[action]
    if state == 'active':
        validate_grant(device)
    device.status, device.is_active = state, state == 'active'
    if state == 'deleted':
        device.deleted_at = timezone.now()
    device.version += 1
    device.save()


def renew(device, plan, actor):
    from .models import DeviceRenewal
    if device.configured_status in ('deleted', 'revoked') or device.access_type != 'timed':
        raise ValidationError('Only timed, non-revoked registrations can be renewed.')
    previous = device.expires_at
    device.plan = plan
    terms = plan_terms(plan)
    now = timezone.now()
    try:
        device.expires_at = max(now, previous or now) + timedelta(seconds=terms['duration_seconds'])
    except OverflowError:
        raise ValidationError({'plan': 'The renewal exceeds the supported expiry date.'})
    validate_grant(device, require_plan=True)
    state = 'suspended' if device.configured_status == 'suspended' else 'active'
    device.status, device.is_active = state, state == 'active'
    apply_plan_snapshot(device)
    device.version += 1
    device.save()
    DeviceRenewal.objects.create(device=device, tenant_id=device.tenant_id, actor=actor,
        previous_expiry=previous, expires_at=device.expires_at, terms=terms)
