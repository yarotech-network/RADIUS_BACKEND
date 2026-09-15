from datetime import timedelta
import ipaddress
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
        if operation.action == 'self_service_provision':
            if not getattr(settings, 'ROUTER_SELF_SERVICE_PROVISIONING_ENABLED', False):
                raise ValueError('Self-service provisioning is disabled.')
            if not NASDevice.objects.filter(pk=operation.router_id, is_active=True).exists():
                raise ValueError('Router is inactive.')
            if (operation.payload.get('interface'), operation.payload.get('subnet'), operation.payload.get('host')) != (
                    settings.WG_INTERFACE, settings.WG_MANAGED_SUBNET, settings.WG_VPS_HOST):
                raise ValueError('Infrastructure changed since setup was prepared; review and retry.')
            for peer in manager.list_peers():
                address = operation.payload['wireguard_ip'] + '/32'
                overlaps = any(ipaddress.ip_address(operation.payload['wireguard_ip']) in ipaddress.ip_network(route)
                               for route in peer['allowed_ips'])
                if overlaps and peer['public_key'] != operation.payload['public_key']:
                    raise ValueError('WireGuard address is already owned by another peer.')
                if peer['public_key'] == operation.payload['public_key'] and peer['allowed_ips'] != [address]:
                    raise ValueError('Existing peer has different routes.')
        if operation.action in ("provision", 'self_service_provision'):
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
        router.deployment_status = "failed" if error else ("deployed" if operation.action in ("provision", 'self_service_provision') else "not_deployed")
        if operation.action == 'self_service_provision':
            from .models import RouterRegistration
            RouterRegistration.objects.filter(router=router).update(
                status='needs_attention' if error else 'ready',
                error_code=error, updated_at=timezone.now(),
            )
            router.onboarding_state = 'vpn_failed' if error else 'waiting_for_vpn'
            # A server peer is not proof that the physical router imported its script.
            router.deployment_status = 'failed' if error else 'not_deployed'
            router.save(update_fields=['onboarding_state'])
        router.save(update_fields=["deployment_status", "updated_at"])
        RouterOnboardingCheck.objects.update_or_create(router=router, check_type="wireguard_peer", defaults={"passed": not error and operation.action == "provision", "checked_at": timezone.now(), "details": {"operation_id": str(operation.pk), "outcome": current.status}})
        RouterAuditEvent.objects.create(router=router, action=f"provisioning_{current.status}", details={"operation_id": str(operation.pk)})
    return True
