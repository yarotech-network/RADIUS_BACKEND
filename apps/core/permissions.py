from rest_framework.permissions import BasePermission


from .api import active_membership, platform_context, tenant_for
from rest_framework.exceptions import PermissionDenied


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return platform_context(request)


class IsTenantOwner(BasePermission):
    def has_permission(self, request, view):
        try:
            membership = active_membership(request.user)
            return bool(membership and membership.role == "owner" and tenant_for(request))
        except PermissionDenied:
            return False


class IsTenantManager(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_active:
            return False
        try:
            membership = active_membership(request.user)
            if membership:
                return membership.role in ("owner", "manager") and bool(tenant_for(request))
            if hasattr(request.user, "membership"):
                return False
            from .api import assigned_tenant
            assigned_tenant(request, view)
            return not request.user.is_platform_admin
        except PermissionDenied:
            return False


class IsAgent(BasePermission):
    def has_permission(self, request, view):
        try:
            active_membership(request.user)
            if hasattr(request.user, "membership") or getattr(request.user, "is_platform_admin", False):
                tenant_for(request)
        except PermissionDenied:
            return False
        return (
            request.user.is_authenticated
            and request.user.is_active
            and hasattr(request.user, "agent_profile")
            and request.user.agent_profile.status == "active"
            and request.user.agent_profile.tenant.is_active
        )
