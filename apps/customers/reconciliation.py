import uuid
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from apps.routers.selectors import tenant_radius_addresses
from apps.routers.secret_store import secret_store
from apps.vouchers.models import Radacct
from apps.vouchers.services import RadiusService
from .models import PPPoEService


def claim_services(limit, exclude_ids=()):
    now = timezone.now()
    with transaction.atomic():
        rows = list(PPPoEService.objects.select_for_update(skip_locked=True).exclude(pk__in=exclude_ids).filter(
            Q(lease_until__isnull=True)|Q(lease_until__lte=now)
        ).order_by(F("last_reconciled_at").asc(nulls_first=True), "id")[:limit])
        result = []
        for service in rows:
            service.lease_token = uuid.uuid4()
            service.lease_until = now+timezone.timedelta(minutes=5)
            service.save(update_fields=["lease_token", "lease_until"])
            result.append((service.pk, service.lease_token))
        return result


def reconcile_service(pk, token):
    service = PPPoEService.objects.select_related("tenant", "customer", "router").get(pk=pk)
    if service.lease_token != token:
        return "superseded"
    now = timezone.now()
    cutoff = service.disconnect_before
    if service.expires_at <= now:
        cutoff = max(cutoff or service.expires_at, service.expires_at)
    if service.suspended or service.customer.archived_at or not service.tenant.is_active or not service.router.is_active or service.router.onboarding_state != "active":
        cutoff = now
    state = "clear"
    if cutoff:
        source = str(service.router.radius_ip)
        if service.router.tenant_id != service.tenant_id or source not in tenant_radius_addresses(service.tenant):
            state = "failed"
        else:
            sessions = list(Radacct.objects.filter(username=service.username, nasipaddress=source,
                acctstoptime__isnull=True).filter(Q(acctstarttime__lte=cutoff)|Q(acctstarttime__isnull=True)).order_by("radacctid")[:10])
            if sessions:
                state = "acknowledged"
                for session in sessions:
                    acknowledged = RadiusService.disconnect_session(session_id=session.sessionid, nas_ip=source,
                        nas_port=session.nasportid, callingsession_id="", shared_secret=secret_store.decrypt(service.router.nas_secret))
                    if not acknowledged:
                        state = "failed"
    with transaction.atomic():
        current = PPPoEService.objects.select_for_update().get(pk=pk)
        if current.lease_token != token:
            return "superseded"
        if current.version != service.version:
            state = "pending"
        current.disconnect_state = state
        current.last_reconciled_at = timezone.now()
        current.lease_token = None
        current.lease_until = None
        current.save(update_fields=["disconnect_state", "last_reconciled_at", "lease_token", "lease_until"])
    return state


def record_failure(pk, token):
    PPPoEService.objects.filter(pk=pk, lease_token=token).update(disconnect_state="failed",
        last_reconciled_at=timezone.now(), lease_token=None, lease_until=None)
