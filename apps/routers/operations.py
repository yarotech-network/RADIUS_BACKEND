from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import NASDevice, RouterOperation, RouterAuditEvent, RouterOnboardingCheck
from .provisioners import WireGuardManager


def run_one_router_operation():
    now = timezone.now()
    with transaction.atomic():
        operation = RouterOperation.objects.select_for_update(skip_locked=True).filter(
            Q(status="pending") | Q(status="running", lease_until__lt=now)
        ).order_by("created_at", "id").first()
        if operation is None:
            return False
        operation.status = "running"
        operation.attempts += 1
        operation.lease_until = now + timedelta(minutes=5)
        operation.save(update_fields=["status", "attempts", "lease_until"])
    # No transaction or row lock is held while SSH is executing. wg set/remove
    # converge on the stored desired state after a worker crash and retry.
    try:
        manager = WireGuardManager(
            settings.WG_VPS_HOST, settings.WG_VPS_SSH_KEY,
            known_hosts=settings.WG_SSH_KNOWN_HOSTS, interface=settings.WG_INTERFACE,
            managed_subnet=settings.WG_MANAGED_SUBNET,
            use_sudo=settings.WG_SSH_USE_SUDO, save_config=settings.WG_SAVE_CONFIG,
        )
        if operation.action == "provision":
            manager.create_peer(operation.payload["public_key"], operation.payload["wireguard_ip"])
        else:
            manager.remove_peer(operation.payload["public_key"])
        error = ""
    except Exception:
        error = "provisioning_failed"
    with transaction.atomic():
        current = RouterOperation.objects.select_for_update().get(pk=operation.pk)
        if current.attempts != operation.attempts or current.status != "running":
            return True
        current.status = "failed" if error else "succeeded"
        current.error_code = error
        current.completed_at = timezone.now()
        current.save(update_fields=["status", "error_code", "completed_at"])
        router = NASDevice.objects.select_for_update().get(pk=operation.router_id)
        router.deployment_status = "failed" if error else ("deployed" if operation.action == "provision" else "not_deployed")
        router.save(update_fields=["deployment_status", "updated_at"])
        RouterOnboardingCheck.objects.update_or_create(router=router, check_type="wireguard_peer", defaults={"passed": not error and operation.action == "provision", "checked_at": timezone.now(), "details": {"operation_id": str(operation.pk), "outcome": current.status}})
        RouterAuditEvent.objects.create(router=router, action=f"provisioning_{current.status}", details={"operation_id": str(operation.pk)})
    return True
