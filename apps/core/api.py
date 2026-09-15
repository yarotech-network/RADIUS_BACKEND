from rest_framework.exceptions import PermissionDenied
from .models import AuditEvent


def assigned_tenant(request, view=None):
    from apps.accounts.staff_models import StaffAssignment
    view = view or request.parser_context.get("view")
    name = type(view).__name__
    action = getattr(view, "action", request.method.lower())
    services = {
        "NASDeviceViewSet": {"list": "routers.view", "retrieve": "routers.view", "audit": "routers.view", "checks": "routers.view", "health": "routers.view", "test": "routers.test"},
        "VoucherViewSet": {"list": "vouchers.print", "retrieve": "vouchers.print", "print": "vouchers.print", "pdf": "vouchers.print", "authorize_print": "vouchers.print", "generate": "vouchers.generate"},
        "InternetPlanViewSet": {"list": "vouchers.generate", "retrieve": "vouchers.generate"},
        "PaymentTransactionViewSet": {"list": "payments.view", "retrieve": "payments.view"},
        "LiveUsersView": {"get": "live_sessions.view"},
        "DisconnectSessionView": {"post": "live_sessions.disconnect"},
        "PaymentRecoveryViewSet": {"list": "payments.view", "retrieve": "payments.view", "retry": "payments.support", "deliver": "payments.support"},
        "PaymentDeliveryViewSet": {"list": "payments.view", "retrieve": "payments.view"},
    }.get(name, {}).get(action)
    tenant_id = request.headers.get("X-Tenant-ID", "")
    if not services or not tenant_id.isdecimal() or len(tenant_id) > 19 or int(tenant_id) > 9223372036854775807:
        raise PermissionDenied("An explicit tenant assignment and service grant are required.")
    assignment = StaffAssignment.objects.select_related("tenant").filter(user=request.user, tenant_id=tenant_id, is_active=True, tenant__is_active=True).first()
    if not assignment or services not in assignment.services:
        raise PermissionDenied("This service is not assigned for the selected tenant.")
    return assignment.tenant


def platform_context(request):
    return bool(request.user.is_authenticated and request.user.is_active
                and request.user.is_platform_admin
                and request.headers.get("X-Access-Context", "platform") == "platform")


def active_membership(user):
    if not user.is_authenticated or not user.is_active:
        return None
    membership = getattr(user, "membership", None)
    agent = getattr(user, "agent_profile", None)
    if membership and agent and membership.tenant_id != agent.tenant_id:
        raise PermissionDenied("Conflicting tenant identities require administrator review.")
    if membership and membership.is_active and membership.tenant.is_active:
        return membership
    return None


def tenant_for(request):
    if request.headers.get("X-Access-Context", "platform") not in ("platform", "workspace"):
        raise PermissionDenied("Unknown access context.")
    if request.user.is_platform_admin and request.headers.get("X-Access-Context") != "workspace":
        raise PermissionDenied("Switch to My workspace to use tenant services.")
    membership = active_membership(request.user)
    if membership is not None:
        return membership.tenant
    # An inactive membership must not fall through to delegated staff grants.
    if hasattr(request.user, "membership") or request.user.is_platform_admin:
        raise PermissionDenied("An active tenant membership is required.")
    return assigned_tenant(request)


def audit(request, action, obj, details=None):
    return AuditEvent.objects.create(
        actor=request.user, tenant_id=(obj.pk if obj._meta.label_lower == "tenants.tenant" else getattr(obj, "tenant_id", None)),
        action=action, resource=f"{obj._meta.label_lower}:{obj.pk}", details=details or {},
    )
